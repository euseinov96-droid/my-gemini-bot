import os
import urllib.parse
import datetime
import threading
from flask import Flask
import telebot
from google import genai
from google.genai import types

# 1. Веб-заглушка для удержания порта на Render
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Инициализация Telegram и Gemini
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

# Хранилище сессий чата для каждого пользователя
user_chats = {}

def get_system_instruction():
    now = datetime.datetime.now()
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    return (
        f"Системная инструкция: Сегодня {now.strftime('%d.%m.%Y')}, {weekdays[now.weekday()]}. "
        f"Текущий год строго 2026. "
        f"Используй Google Search для поиска актуальных фактов при необходимости. "
        f"Отвечай емко, точно и по существу."
    )

def get_or_create_chat(user_id):
    if user_id not in user_chats:
        user_chats[user_id] = client.chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=get_system_instruction(),
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
    return user_chats[user_id]

@bot.message_handler(commands=['start', 'reset'])
def send_welcome(message):
    user_chats[message.chat.id] = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=get_system_instruction(),
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )
    bot.reply_to(
        message,
        "Привет! Я онлайн и готов к работе.\n\n"
        "💬 **Вопрос:** просто напиши мне текст.\n"
        "🎨 **Картинка:** отправь `/draw описание`\n"
        "🔄 **Сброс памяти:** /reset"
    )

# 3. Генерация изображений
@bot.message_handler(commands=['draw', 'image'])
def generate_image(message):
    user_prompt = message.text.replace("/draw", "").replace("/image", "").strip()
    
    if not user_prompt:
        bot.reply_to(message, "Укажи описание картинки. Пример:\n`/draw футуристичный город в неоновых огнях`", parse_mode="Markdown")
        return
    
    bot.send_chat_action(message.chat.id, 'upload_photo')
    
    final_prompt = user_prompt
    try:
        enhance_task = (
            f"Translate to English and optimize as a photo generation prompt: '{user_prompt}'. "
            f"Output ONLY the optimized prompt text without explanations."
        )
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=enhance_task
        )
        if resp.text:
            final_prompt = resp.text.strip()
    except Exception:
        final_prompt = user_prompt

    try:
        encoded_prompt = urllib.parse.quote(final_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
        bot.send_photo(message.chat.id, image_url, caption=f"🎨 *Запрос:* {user_prompt}", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"Ошибка при отправке изображения: {e}")

# 4. Текстовые ответы через Chat API (корректная обработка AFC и Search)
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.chat.id
    bot.send_chat_action(user_id, 'typing')
    
    try:
        chat = get_or_create_chat(user_id)
        response = chat.send_message(message.text)
        
        reply_text = response.text if response.text else "Не удалось сформировать ответ."
        bot.reply_to(message, reply_text)
    except Exception as e:
        err = str(e)
        if "429" in err:
            bot.reply_to(message, "⚠️ Превышен лимит запросов к Google API. Подождите 1 минуту.")
        else:
            # При сбое сессии сбрасываем чат для пользователя
            user_chats.pop(user_id, None)
            bot.reply_to(message, f"Ошибка: {err}")

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    print("Бот успешно запущен!")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
