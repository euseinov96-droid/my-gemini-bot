import os
import re
import time
import urllib.parse
import threading
import logging
import requests
from flask import Flask
import telebot

# Отключаем лишний шум логов
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# 1. Веб-сервер для удержания на Render 24/7
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is alive 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Инициализация Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not TELEGRAM_BOT_TOKEN:
    print("❌ ОШИБКА: Задайте TELEGRAM_BOT_TOKEN в Environment на Render!")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# 3. Безотказный мульти-серверный текстовый ИИ (без ключей)
def ask_free_ai(prompt_text):
    system_prompt = "Ты вежливый, умный и тактичный русскоязычный ассистент. Отвечай емко, грамотно и по существу на чистом русском языке."

    # Вариант 1: Быстрый шлюз через Pollinations с перебором моделей
    models_to_try = ["mistral", "qwen", "openai", "searchgpt"]
    for model in models_to_try:
        try:
            url = "https://text.pollinations.ai/"
            payload = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_text}
                ],
                "model": model,
                "jsonMode": False
            }
            res = requests.post(url, json=payload, timeout=12)
            if res.status_code == 200 and res.text.strip():
                return res.text.strip()
        except Exception:
            continue

    # Вариант 2: Прямой GET-запрос через fallback эндпоинт
    try:
        clean_query = urllib.parse.quote(f"{system_prompt}\nВопрос: {prompt_text}\nОтвет:")
        url = f"https://text.pollinations.ai/{clean_query}?model=mistral"
        res = requests.get(url, timeout=12)
        if res.status_code == 200 and res.text.strip():
            return res.text.strip()
    except Exception:
        pass

    return "Здравствуйте! Извините за небольшую задержку. Пожалуйста, повторите ваш вопрос еще раз."

# 4. Команды старта
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    print(f"📥 /start от {message.chat.id}")
    bot.reply_to(
        message,
        "Здравствуйте! Я ваш персональный ИИ-ассистент.\n\n"
        "💬 **Общение:** напишите мне любой вопрос.\n"
        "🎨 **Создание фото:** `рисуй [описание]` или `/рисуй [описание]`\n\n"
        "Чем я могу вам помочь?"
    )

# 5. Генерация изображений FLUX.1
def process_image(message, prompt):
    if not prompt:
        bot.reply_to(
            message,
            "Пожалуйста, укажите описание изображения. Например:\n`рисуй спорткар в неоновом городе`",
            parse_mode="Markdown"
        )
        return

    print(f"🎨 Генерация фото: {prompt}")
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
        print(f"⚠️ Ошибка отправки фото: {e}")
        bot.reply_to(message, f"Ошибка при создании изображения: {e}")

@bot.message_handler(commands=['рисуй', 'нарисуй', 'draw', 'image'])
def draw_cmd(message):
    prompt = re.sub(r"^/(рисуй|нарисуй|draw|image)(@\w+)?\s*", "", message.text, flags=re.IGNORECASE).strip()
    process_image(message, prompt)

# 6. Обработка всех сообщений
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    text = message.text.strip()
    print(f"📥 Сообщение: {text}")

    # Проверка на генерацию картинки
    draw_pattern = r"^(рисуй|нарисуй|изобрази|сделай фото|сделай картинку)\s*"
    if re.match(draw_pattern, text, re.IGNORECASE):
        prompt = re.sub(draw_pattern, "", text, flags=re.IGNORECASE).strip()
        process_image(message, prompt)
        return

    # Ответ на текст
    bot.send_chat_action(message.chat.id, 'typing')
    answer = ask_free_ai(text)
    bot.reply_to(message, answer)

# 7. Запуск
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(2)
    except Exception:
        pass

    print("🚀 Бот успешно запущен!")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
