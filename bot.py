import os
import re
import time
import urllib.parse
import datetime
import threading
import logging
from flask import Flask
import telebot
from telebot.apihelper import ApiTelegramException
import google.generativeai as genai

# Отключаем лишний шум от Flask
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# 1. Веб-сервер для удержания сервиса на Render
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is alive 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    print(f"[FLASK] Сервер запущен на порту {port}")
    app.run(host="0.0.0.0", port=port)

# 2. Инициализация Telegram и Google Gemini
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    print("[ERROR] Не задан TELEGRAM_BOT_TOKEN!")
if not GEMINI_API_KEY:
    print("[ERROR] Не задан GEMINI_API_KEY!")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-pro")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

user_history = {}
MAX_HISTORY = 4

def get_current_date():
    now = datetime.datetime.now()
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    return f"{now.strftime('%d.%m.%Y')}, {weekdays[now.weekday()]}"

@bot.message_handler(commands=['start', 'reset'])
def send_welcome(message):
    print(f"[TELEGRAM] Получена команда /start от {message.chat.id}")
    user_history[message.chat.id] = []
    bot.reply_to(
        message,
        "Здравствуйте! Я ваш персональный ИИ-ассистент.\n\n"
        "💬 **Общение:** напишите мне любой вопрос.\n"
        "🎨 **Создание фото:** `рисуй [описание]` или `/рисуй [описание]`\n"
        "🔄 **Сброс диалога:** /reset\n\n"
        "Чем я могу вам помочь?"
    )

# 3. Генерация картинок FLUX.1
def process_image_generation(message, prompt):
    if not prompt:
        bot.reply_to(
            message,
            "Пожалуйста, укажите описание изображения. Например:\n`рисуй спортивный автомобиль в ночном городе`",
            parse_mode="Markdown"
        )
        return

    print(f"[IMAGE] Генерация фото по запросу: {prompt}")
    bot.send_chat_action(message.chat.id, 'upload_photo')

    final_prompt = prompt
    try:
        task = f"Translate to English detailed photo prompt for FLUX: '{prompt}'. Output ONLY prompt text."
        resp = model.generate_content(task)
        if resp and resp.text:
            final_prompt = resp.text.strip()
    except Exception as e:
        print(f"[GEMINI PROMPT ERROR] {e}")
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
        bot.reply_to(message, f"Ошибка при отправке фото: {e}")

@bot.message_handler(commands=['рисуй', 'нарисуй', 'изобрази', 'draw', 'image'])
def handle_draw_command(message):
    prompt = re.sub(r"^/(рисуй|нарисуй|изобрази|draw|image)(@\w+)?\s*", "", message.text, flags=re.IGNORECASE).strip()
    process_image_generation(message, prompt)

# 4. Обработка текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()
    print(f"[TELEGRAM] Получено сообщение: {text}")
    
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
        response = model.generate_content(system_prompt)
        reply_text = response.text if response.text else "Прошу прощения, не удалось получить ответ."
        user_history[user_id].append(f"Model: {reply_text}")
        bot.reply_to(message, reply_text)
    except Exception as e:
        print(f"[GEMINI ERROR] {e}")
        bot.reply_to(message, f"⚠️ Ошибка API:\n`{e}`", parse_mode="Markdown")

# 5. Запуск
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_web, daemon=True)
    flask_thread.start()
    
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(1)
    except Exception as e:
        print(f"[WEBHOOK RESET ERROR] {e}")
    
    print("[BOT] Начинаю бесконечный опрос Telegram...")
    
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except ApiTelegramException as e:
            if e.error_code == 409:
                print("[409 CONFLICT] Другой инстанс еще активен, пауза 5 секунд...")
                time.sleep(5)
            else:
                print(f"[TELEGRAM API ERROR] {e}")
                time.sleep(2)
        except Exception as e:
            print(f"[UNKNOWN ERROR] {e}")
            time.sleep(2)
