import os
import re
import time
import urllib.parse
import datetime
import threading
import logging
from flask import Flask
import telebot
from google import genai

# Отключаем лишние логи веб-сервера
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# 1. Веб-заглушка для Render Web Service 24/7
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is active 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Инициализация Telegram и Google Gemini
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

# Список актуальных моделей по приоритету
MODELS_TO_TRY = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]

user_history = {}
MAX_HISTORY = 4

def get_current_date():
    now = datetime.datetime.now()
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    return f"{now.strftime('%d.%m.%Y')}, {weekdays[now.weekday()]}"

def generate_gemini_response(prompt_text):
    """Попытка генерации с автоматическим перебором рабочих моделей при 404"""
    last_err = None
    for model_name in MODELS_TO_TRY:
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt_text
            )
            if resp and resp.text:
                return resp.text.strip()
        except Exception as e:
            last_err = e
            if "404" in str(e) or "NOT_FOUND" in str(e):
                continue  # Пробуем следующую модель
            raise e
    raise last_err

@bot.message_handler(commands=['start', 'reset'])
def send_welcome(message):
    user_history[message.chat.id] = []
    bot.reply_to(
        message,
        "Здравствуйте! Я ваш персональный ИИ-ассистент.\n\n"
        "💬 **Общение:** напишите мне любой вопрос.\n"
        "🎨 **Создание фото:** `рисуй [описание]` или `/рисуй [описание]`\n"
        "🔄 **Сброс диалога:** /reset\n\n"
        "Чем я могу вам помочь?"
    )

# 3. Генерация изображений через FLUX.1
def process_image_generation(message, prompt):
    if not prompt:
        bot.reply_to(
            message,
            "Пожалуйста, укажите описание изображения. Например:\n`рисуй спортивный автомобиль в ночном городе`",
            parse_mode="Markdown"
        )
        return

    bot.send_chat_action(message.chat.id, 'upload_photo')

    final_prompt = prompt
    try:
        task = f"Translate to English photo prompt (photorealistic, 8k, detailed lighting): '{prompt}'. Output ONLY prompt text."
        enhanced = generate_gemini_response(task)
        if enhanced:
            final_prompt = enhanced
    except Exception:
        final_prompt = prompt

    try:
        encoded_prompt = urllib.parse.quote(final_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?model=flux&width=1024&height=1024&nologo=true"
        
        bot.send_photo(
            message.chat.id,
            image_url,
            caption=f"🎨 *Ваш запрос:* {prompt}\n⚡ *Модель:* FLUX.1",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"К сожалению, произошла ошибка при генерации фото: {e}")

@bot.message_handler(commands=['рисуй', 'нарисуй', 'изобрази', 'draw', 'image'])
def handle_draw_command(message):
    prompt = re.sub(r"^/(рисуй|нарисуй|изобрази|draw|image)(@\w+)?\s*", "", message.text, flags=re.IGNORECASE).strip()
    process_image_generation(message, prompt)

# 4. Обработка текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()
    
    # Обработка команд рисования без слэша
    draw_pattern = r"^(рисуй|нарисуй|изобрази|сделай фото|сделай картинку)\s*"
    if re.match(draw_pattern, text, re.IGNORECASE):
        prompt = re.sub(draw_pattern, "", text, flags=re.IGNORECASE).strip()
        process_image_generation(message, prompt)
        return

    user_id = message.chat.id
    bot.send_chat_action(user_id, 'typing')

    if user_id not in user_history:
        user_history[user_id] = []

    user_history[user_id].append(f"User: {text}")
    if len(user_history[user_id]) > MAX_HISTORY:
        user_history[user_id] = user_history[user_id][-MAX_HISTORY:]

    system_prompt = (
        f"Ты воспитанный, тактичный и вежливый русскоязычный ИИ-ассистент. "
        f"Всегда обращайся к пользователю уважительно на 'вы'. "
        f"Отвечай емко, грамотно и по существу на чистом русском языке. "
        f"Сегодня {get_current_date()}, 2026 год.\n\n"
        + "\n".join(user_history[user_id])
        + "\nModel:"
    )

    try:
        reply_text = generate_gemini_response(system_prompt)
        user_history[user_id].append(f"Model: {reply_text}")
        bot.reply_to(message, reply_text)
    except Exception as e:
        bot.reply_to(message, f"⚠️ Ошибка API:\n`{e}`", parse_mode="Markdown")

# 5. Запуск
if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    threading.Thread(target=run_web, daemon=True).start()
    
    # Сбрасываем старые вебхуки Telegram перед стартом polling (защита от ошибки 409)
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass
    
    print("Бот успешно запущен и готов к работе!")
    bot.infinity_polling(timeout=20, long_polling_timeout=10, skip_pending=True)
