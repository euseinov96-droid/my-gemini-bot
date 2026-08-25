import os
import sys
import re
import time
import urllib.parse
import threading
import logging
import requests
from flask import Flask
import telebot
from telebot.apihelper import ApiTelegramException

# Отключаем лишний шум Flask
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# 1. Веб-сервер для поддержания активности Render 24/7
app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is alive and running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)

# 2. Инициализация Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not TELEGRAM_BOT_TOKEN:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_BOT_TOKEN не указан в Render Environment!")
    sys.exit(1)

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False)

# 3. Текстовый ИИ без платных ключей и лимитов
def ask_ai(prompt_text):
    system_text = "Ты умный, вежливый и полезный русскоязычный ИИ-ассистент. Отвечай емко, грамотно и точно на русском языке."
    
    # Пул открытых надежных моделей
    models = ["openai", "qwen", "mistral", "searchgpt"]
    headers = {"Content-Type": "application/json"}

    for model in models:
        try:
            url = "https://text.pollinations.ai/"
            payload = {
                "messages": [
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": prompt_text}
                ],
                "model": model,
                "jsonMode": False
            }
            res = requests.post(url, json=payload, headers=headers, timeout=12)
            if res.status_code == 200 and res.text.strip():
                return res.text.strip()
        except Exception:
            continue

    try:
        clean = urllib.parse.quote(f"{system_text}\n\nПользователь: {prompt_text}\nОтвет:")
        res = requests.get(f"https://text.pollinations.ai/{clean}?model=mistral", timeout=10)
        if res.status_code == 200 and res.text.strip():
            return res.text.strip()
    except Exception:
        pass

    return "Здравствуйте! Извините, сервера генерации сейчас под нагрузкой. Повторите ваш вопрос через пару секунд."

# 4. Команда /start
@bot.message_handler(commands=['start', 'help', 'reset'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Здравствуйте! Я ваш персональный ИИ-ассистент.\n\n"
        "💬 **Общение:** напишите мне любой текстовый запрос.\n"
        "🎨 **Создание фото:** `рисуй [описание]` или `/рисуй [описание]`\n\n"
        "Чем я могу вам помочь?"
    )

# 5. Генерация изображений FLUX.1
def process_image(message, prompt):
    if not prompt:
        bot.reply_to(
            message,
            "Пожалуйста, укажите описание изображения. Например:\n`рисуй спортивный автомобиль в неоновом городе`",
            parse_mode="Markdown"
        )
        return

    bot.send_chat_action(message.chat.id, 'upload_photo')
    try:
        encoded = urllib.parse.quote(prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded}?model=flux&width=1024&height=1024&nologo=true"
        
        bot.send_photo(
            message.chat.id,
            image_url,
            caption=f"🎨 *Запрос:* {prompt}\n⚡ *Модель:* FLUX.1",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"Ошибка отправки фото: {e}")

@bot.message_handler(commands=['рисуй', 'нарисуй', 'draw', 'image'])
def handle_draw(message):
    prompt = re.sub(r"^/(рисуй|нарисуй|draw|image)(@\w+)?\s*", "", message.text, flags=re.IGNORECASE).strip()
    process_image(message, prompt)

# 6. Обработка текста
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    text = message.text.strip()

    draw_pattern = r"^(рисуй|нарисуй|изобрази|сделай фото|сделай картинку)\s*"
    if re.match(draw_pattern, text, re.IGNORECASE):
        prompt = re.sub(draw_pattern, "", text, flags=re.IGNORECASE).strip()
        process_image(message, prompt)
        return

    bot.send_chat_action(message.chat.id, 'typing')
    answer = ask_ai(text)
    bot.reply_to(message, answer)

# 7. Запуск без конфликта 409
if __name__ == "__main__":
    # 1. Запуск Flask в отдельном потоке
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    
    # 2. Гарантированный сброс старых соединений перед стартом
    print("⏳ Очистка активных соединений Telegram...")
    try:
        bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Delete webhook info: {e}")
    time.sleep(4)  # Пауза для корректного завершения старого процесса Render

    print("🚀 Бот успешно запущен и слушает входящие сообщения!")

    # 3. Защищенный цикл поллинга
    retry_delay = 2
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=20)
            retry_delay = 2
        except ApiTelegramException as e:
            if e.error_code == 409:
                print(f"⚠️ Перехвачен 409 Conflict. Ждем {retry_delay} сек. для освобождения сессии...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)
            else:
                print(f"⚠️ Telegram API Error ({e.error_code}): {e}")
                time.sleep(3)
        except Exception as e:
            print(f"⚠️ Network exception: {e}")
            time.sleep(3)
