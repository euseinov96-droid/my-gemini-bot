import os
import re
import time
import urllib.parse
import datetime
import threading
import logging
import requests
from flask import Flask
import telebot
from telebot.apihelper import ApiTelegramException

# Отключаем лишний шум логов Flask
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

user_history = {}
MAX_HISTORY = 6

def get_current_date():
    now = datetime.datetime.now()
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    return f"{now.strftime('%d.%m.%Y')}, {weekdays[now.weekday()]}"

# 3. Безотказный русскоязычный ИИ с тройным каскадом серверов
def ask_ai(prompt_text):
    system_text = "Ты вежливый, умный и тактичный русскоязычный ассистент. Всегда обращайся на 'вы'. Отвечай четко, грамотно и по делу на чистом русском языке."
    
    # Сервер 1: Прямой шлюз через DuckDuckGo AI (Qwen/Llama)
    try:
        url = "https://text.pollinations.ai/openai"
        headers = {"Content-Type": "application/json"}
        payload = {
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": prompt_text}
            ],
            "model": "qwen",
            "jsonMode": False
        }
        res = requests.post(url, json=payload, headers=headers, timeout=12)
        if res.status_code == 200 and res.text.strip():
            return res.text.strip()
    except Exception:
        pass

    # Сервер 2: Резервный шлюз (Mistral)
    try:
        clean_prompt = urllib.parse.quote(f"{system_text}\n\nПользователь: {prompt_text}\nОтвет:")
        url = f"https://text.pollinations.ai/{clean_prompt}?model=mistral"
        res = requests.get(url, timeout=12)
        if res.status_code == 200 and res.text.strip():
            return res.text.strip()
    except Exception:
        pass

    # Сервер 3: Резервный шлюз SearchGPT
    try:
        url = f"https://text.pollinations.ai/{urllib.parse.quote(prompt_text)}?model=searchgpt"
        res = requests.get(url, timeout=12)
        if res.status_code == 200 and res.text.strip():
            return res.text.strip()
    except Exception:
        pass

    return "Здравствуйте! Извините за небольшую задержку. Пожалуйста, напишите ваш вопрос еще раз."

# 4. Приветствие
@bot.message_handler(commands=['start', 'help', 'reset'])
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

# 5. Генерация картинок через FLUX.1
def process_image(message, prompt):
    if not prompt:
        bot.reply_to(
            message,
            "Пожалуйста, укажите описание изображения. Например:\n`рисуй спортивный автомобиль в ночном городе`",
            parse_mode="Markdown"
        )
        return

    bot.send_chat_action(message.chat.id, 'upload_photo')

    # Оптимизация промпта
    final_prompt = prompt
    try:
        enhanced = ask_ai(f"Translate this prompt into English for photorealistic FLUX generation. Output ONLY the translated prompt: '{prompt}'")
        if enhanced and len(enhanced) < 300 and not enhanced.startswith("Здравствуйте"):
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
        bot.reply_to(message, f"Ошибка при отправке фото: {e}")

@bot.message_handler(commands=['рисуй', 'нарисуй', 'draw', 'image'])
def handle_draw_cmd(message):
    prompt = re.sub(r"^/(рисуй|нарисуй|draw|image)(@\w+)?\s*", "", message.text, flags=re.IGNORECASE).strip()
    process_image(message, prompt)

# 6. Обработка текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()

    # Проверка на генерацию картинок
    draw_pattern = r"^(рисуй|нарисуй|изобрази|сделай фото|сделай картинку)\s*"
    if re.match(draw_pattern, text, re.IGNORECASE):
        prompt = re.sub(draw_pattern, "", text, flags=re.IGNORECASE).strip()
        process_image(message, prompt)
        return

    user_id = message.chat.id
    bot.send_chat_action(user_id, 'typing')

    answer = ask_ai(text)
    bot.reply_to(message, answer)

# 7. Запуск бота
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(2)
    except Exception:
        pass

    print("🚀 Бот успешно запущен!")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
