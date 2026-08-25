import os
import re
import urllib.parse
import datetime
import threading
from flask import Flask
import telebot
from google import genai
from google.genai import types

# 1. Заглушка для Render Web Service 24/7
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot with FLUX.1 generation is live!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Инициализация Telegram и Gemini
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

user_chats = {}

def get_system_instruction():
    now = datetime.datetime.now()
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    return (
        f"Системная инструкция: Ты умный русскоязычный AI-собеседник. "
        f"Всегда отвечай на чистом, естественном и грамотном русском языке. "
        f"Сегодня {now.strftime('%d.%m.%Y')}, {weekdays[now.weekday()]}. Текущий год строго 2026. "
        f"Используй встроенный Google Search для актуальных новостей, событий и фактов. "
        f"Отвечай четко, емко и по существу."
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
        "Привет! Я ИИ-ассистент с поиском Google и генератором изображений **FLUX.1**.\n\n"
        "💬 **Вопрос:** просто напиши любой текст на русском.\n"
        "🎨 **Создать фото:** напиши `рисуй [описание]`, `нарисуй [описание]` или `/рисуй`\n"
        "🔄 **Сброс контекста:** /reset",
        parse_mode="Markdown"
    )

# 3. Функция генерации ультра-качественных фото через FLUX.1
def process_image_generation(message, prompt):
    if not prompt:
        bot.reply_to(
            message,
            "Пожалуйста, укажи описание. Например:\n`рисуй портрет девушки в неоновом дождливом Токио, реализм`",
            parse_mode="Markdown"
        )
        return

    bot.send_chat_action(message.chat.id, 'upload_photo')

    # Gemini превращает краткий русский текст в профессиональный промпт для FLUX
    final_prompt = prompt
    try:
        enhance_task = (
            f"Ты профессиональный промпт-инженер для нейросети FLUX.1. "
            f"Переведи на английский и улучши запрос пользователя: '{prompt}'. "
            f"Добавь фотографический стиль, реалистичные текстуры, кинематографичное освещение, 8k resolution, photorealistic. "
            f"Выведи ТОЛЬКО готовый текст промпта без пояснений и кавычек."
        )
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=enhance_task
        )
        if resp.text:
            final_prompt = resp.text.strip()
    except Exception:
        final_prompt = prompt

    try:
        encoded_prompt = urllib.parse.quote(final_prompt)
        # Подключение модели FLUX
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?model=flux&width=1024&height=1024&nologo=true"
        
        bot.send_photo(
            message.chat.id,
            image_url,
            caption=f"🎨 *Запрос:* {prompt}\n⚡ *Модель:* FLUX.1",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"Ошибка при создании изображения: {e}")

# Команды со слэшем
@bot.message_handler(commands=['рисуй', 'нарисуй', 'изобрази', 'draw', 'image'])
def handle_draw_command(message):
    prompt = re.sub(r"^/(рисуй|нарисуй|изобрази|draw|image)(@\w+)?\s*", "", message.text, flags=re.IGNORECASE).strip()
    process_image_generation(message, prompt)

# 4. Обработка текстовых запросов
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()
    
    # Распознавание русских триггеров в начале текста
    draw_pattern = r"^(рисуй|нарисуй|изобрази|сделай фото|сделай картинку)\s*"
    if re.match(draw_pattern, text, re.IGNORECASE):
        prompt = re.sub(draw_pattern, "", text, flags=re.IGNORECASE).strip()
        process_image_generation(message, prompt)
        return

    # Обычный диалог
    user_id = message.chat.id
    bot.send_chat_action(user_id, 'typing')

    try:
        chat = get_or_create_chat(user_id)
        response = chat.send_message(message.text)
        reply_text = response.text if response.text else "Не удалось получить ответ."
        bot.reply_to(message, reply_text)
    except Exception as e:
        err = str(e)
        if "429" in err:
            bot.reply_to(message, "⚠️ Сработал лимит запросов к Google API. Подождите 1 минуту.")
        else:
            user_chats.pop(user_id, None)
            bot.reply_to(message, f"Ошибка: {err}")

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    print("Бот успешно запущен с моделью FLUX.1!")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
