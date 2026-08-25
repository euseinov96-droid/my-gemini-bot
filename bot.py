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

# Отключаем лишний шум логов веб-сервера
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# 1. Веб-сервер для удержания на Render
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

# 3. Надежный текстовый ИИ через POST-запрос (без ключей и квот)
def ask_free_ai(prompt_text):
    try:
        url = "https://text.pollinations.ai/"
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "Ты вежливый, умный и тактичный русскоязычный ассистент. Отвечай грамотно, четко, понятно и по делу на чистом русском языке."
                },
                {
                    "role": "user",
                    "content": prompt_text
                }
            ],
            "model": "openai",
            "seed": 42
        }
        
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200 and response.text.strip():
            return response.text.strip()
        else:
            print(f"⚠️ Ошибка API статуса: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Ошибка запроса к ИИ: {e}")
    
    return "Извините, возникла задержка при обработке запроса. Пожалуйста, попробуйте написать еще раз."

# 4. Команда /start
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    print(f"📥 Получена команда /start от пользователя {message.chat.id}")
    bot.reply_to(
        message,
        "Здравствуйте! Я ваш персональный ИИ-ассистент.\n\n"
        "💬 **Общение:** напишите мне любой вопрос.\n"
        "🎨 **Создание фото:** `рисуй [описание]` или `/рисуй [описание]`\n\n"
        "Чем я могу вам помочь?"
    )

# 5. Генерация картинок через FLUX.1
def process_image(message, prompt):
    if not prompt:
        bot.reply_to(
            message,
            "Пожалуйста, укажите, что нарисовать. Например:\n`рисуй спортивный автомобиль в неоновом городе`",
            parse_mode="Markdown"
        )
        return

    print(f"🎨 Генерация изображения: {prompt}")
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

# 6. Обработка всех входящих текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    text = message.text.strip()
    print(f"📥 Новое сообщение: {text}")

    # Проверка на запрос картинки без слэша
    draw_pattern = r"^(рисуй|нарисуй|изобрази|сделай фото|сделай картинку)\s*"
    if re.match(draw_pattern, text, re.IGNORECASE):
        prompt = re.sub(draw_pattern, "", text, flags=re.IGNORECASE).strip()
        process_image(message, prompt)
        return

    # Текстовый диалог
    bot.send_chat_action(message.chat.id, 'typing')
    answer = ask_free_ai(text)
    bot.reply_to(message, answer)

# 7. Надежный запуск
if __name__ == "__main__":
    # Запуск веб-сервера для Render в отдельном потоке
    threading.Thread(target=run_web, daemon=True).start()
    
    # Сброс вебхука и зависших старых апдейтов
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(2)
    except Exception as e:
        print(f"⚠️ Ошибка сброса вебхука: {e}")

    print("🚀 Бот успешно запущен и слушает сообщения!")
    
    # Бесконечный опрос с авто-переподключением при любых сбоях сети
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
