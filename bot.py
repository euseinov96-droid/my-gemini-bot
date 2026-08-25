import os
import urllib.parse
import datetime
import threading
from flask import Flask
import telebot
from google import genai
from google.genai import types

# 1. Веб-заглушка для Render 24/7
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

user_memory = {}
MAX_MESSAGES = 4

def get_current_date():
    now = datetime.datetime.now()
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    return f"{now.strftime('%d.%m.%Y')}, {weekdays[now.weekday()]}"

@bot.message_handler(commands=['start', 'reset'])
def send_welcome(message):
    user_memory[message.chat.id] = []
    bot.reply_to(
        message, 
        "Привет! Я умный ИИ-помощник.\n\n"
        "💬 **Текст и поиск:** просто напиши любой вопрос.\n"
        "🎨 **Генерация фото:** отправь `/draw твой запрос` (например: `/draw футуристичный город на закате`)\n"
        "🔄 **Сброс диалога:** команда /reset"
    )

# 3. Команда генерации изображений (без ключа)
@bot.message_handler(commands=['draw', 'image'])
def generate_image(message):
    prompt = message.text.replace("/draw", "").replace("/image", "").strip()
    
    if not prompt:
        bot.reply_to(message, "Пожалуйста, укажи описание картинки после команды. Пример:\n`/draw неоновый кот в очках`", parse_mode="Markdown")
        return
    
    bot.send_chat_action(message.chat.id, 'upload_photo')
    try:
        # Кодируем запрос и получаем изображение через Pollinations API
        encoded_prompt = urllib.parse.quote(prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
        
        bot.send_photo(message.chat.id, image_url, caption=f"🖼 Результат по запросу: *{prompt}*", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"Не удалось сгенерировать изображение: {e}")

# 4. Обработка текстовых запросов через Gemini с поиском Google
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.chat.id
    bot.send_chat_action(user_id, 'typing')
    
    if user_id not in user_memory:
        user_memory[user_id] = []
    
    user_memory[user_id].append(f"User: {message.text}")
    if len(user_memory[user_id]) > MAX_MESSAGES:
        user_memory[user_id] = user_memory[user_id][-MAX_MESSAGES:]
    
    prompt = (
        f"Системная инструкция: Сегодня {get_current_date()}. Текущий год 2026. "
        f"Используй встроенный поиск Google для поиска актуальных фактов при необходимости. "
        f"Отвечай кратко, грамотно и по делу.\n\n"
        + "\n".join(user_memory[user_id])
        + "\nModel:"
    )
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        reply_text = response.text if response.text else "Не удалось сформировать ответ."
        user_memory[user_id].append(f"Model: {reply_text}")
        bot.reply_to(message, reply_text)
    except Exception as e:
        err = str(e)
        if "429" in err:
            bot.reply_to(message, "⚠️ Сработал лимит запросов. Подождите 1 минуту.")
        else:
            bot.reply_to(message, f"Ошибка: {err}")

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    print("Бот успешно запущен!")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
