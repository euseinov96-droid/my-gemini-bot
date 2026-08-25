import os
import re
import time
import urllib.parse
import threading
import logging
import requests
from flask import Flask
import telebot
from telebot.apihelper import ApiTelegramException

# Отключаем лишний шум Flask в логах
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# 1. Веб-сервер для поддержания активности на Render 24/7
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Инициализация Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not TELEGRAM_BOT_TOKEN:
    print("❌ ОШИБКА: Добавьте TELEGRAM_BOT_TOKEN в Environment на Render!")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# 3. Безотказный генератор текстовых ответов
def ask_ai(prompt_text):
    system_text = "Ты вежливый, умный и тактичный русскоязычный ассистент. Всегда отвечай грамотно, вежливо и по существу на чистом русском языке."
    
    # Каскад надежных моделей
    models = ["openai", "mistral", "qwen", "searchgpt"]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json"
    }

    # Вариант А: JSON POST-запрос с перебором моделей
    for m in models:
        try:
            url = "https://text.pollinations.ai/"
            payload = {
                "messages": [
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": prompt_text}
                ],
                "model": m,
                "jsonMode": False
            }
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            if res.status_code == 200 and res.text.strip():
                return res.text.strip()
        except Exception:
            continue

    # Вариант Б: Прямой GET-запрос (резервный шлюз)
    try:
        clean_text = urllib.parse.quote(f"{system_text}\nВопрос: {prompt_text}\nОтвет:")
        url = f"https://text.pollinations.ai/{clean_text}?model=mistral"
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200 and res.text.strip():
            return res.text.strip()
    except Exception:
        pass

    return "Здравствуйте! Извините, сервер был временно занят. Повторите ваш вопрос, пожалуйста."

# 4. Команды старта
@bot.message_handler(commands=['start', 'help', 'reset'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Здравствуйте! Я ваш персональный ИИ-ассистент.\n\n"
        "💬 **Общение:** напишите мне любой вопрос.\n"
        "🎨 **Создание фото:** `рисуй [описание]` или `/рисуй [описание]`\n\n"
        "Чем я могу вам помочь?"
    )

# 5. Генерация фото (FLUX.1)
def process_image(message, prompt):
    if not prompt:
        bot.reply_to(
            message,
            "Пожалуйста, укажите описание изображения. Например:\n`рисуй спортивный автомобиль в ночном городе`",
            parse_mode="Markdown"
        )
        return

    bot.send_chat_action(message.chat.id, 'upload_photo')
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?model=flux&width=1024&height=1024&nologo=true"
        
        bot.send_photo(
            message.chat.id,
            image_url,
            caption=f"🎨 *Ваш запрос:* {prompt}\n⚡ *Модель:* FLUX.1",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"Ошибка отправки фото: {e}")

@bot.message_handler(commands=['рисуй', 'нарисуй', 'draw', 'image'])
def handle_draw_cmd(message):
    prompt = re.sub(r"^/(рисуй|нарисуй|draw|image)(@\w+)?\s*", "", message.text, flags=re.IGNORECASE).strip()
    process_image(message, prompt)

# 6. Обработка всех текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()

    # Проверка вызова генерации фото без команды /рисуй
    draw_pattern = r"^(рисуй|нарисуй|изобрази|сделай фото|сделай картинку)\s*"
    if re.match(draw_pattern, text, re.IGNORECASE):
        prompt = re.sub(draw_pattern, "", text, flags=re.IGNORECASE).strip()
        process_image(message, prompt)
        return

    bot.send_chat_action(message.chat.id, 'typing')
    answer = ask_ai(text)
    bot.reply_to(message, answer)

# 7. Защищенный цикл запуска (без вылетов и ошибки 409)
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    
    print("⏳ Очистка старых сессий Telegram...")
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(3)
    except Exception:
        pass

    print("🚀 Бот успешно запущен!")
    
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except ApiTelegramException as e:
            if e.error_code == 409:
                time.sleep(5)
            else:
                time.sleep(2)
        except Exception:
            time.sleep(2)
