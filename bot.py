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

# Отключаем лишний шум логов
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# 1. Веб-сервер для удержания на Render 24/7
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
    print("❌ ОШИБКА: Задайте TELEGRAM_BOT_TOKEN в Environment на Render!")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# 3. Полностью автономный текстовый ИИ (без ключей, без 401/402/404)
def ask_free_ai(prompt_text):
    """Прямой текстовый ИИ без ключей и квот"""
    try:
        sys_context = "Ты вежливый, умный и тактичный русскоязычный ассистент. Отвечай грамотно, четко и по делу на русском языке."
        full_query = f"{sys_context}\n\nВопрос: {prompt_text}\nОтвет:"
        encoded = urllib.parse.quote(full_query)
        
        url = f"https://text.pollinations.ai/{encoded}"
        response = requests.get(url, timeout=25)
        
        if response.status_code == 200 and response.text.strip():
            return response.text.strip()
    except Exception as e:
        print(f"[AI ERROR] {e}")
    
    return "Здравствуйте! Я получил ваш запрос, но сейчас возникли временные трудности со связью. Попробуйте еще раз через секунду."

# 4. Приветствие
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Здравствуйте! Я ваш персональный ИИ-ассистент.\n\n"
        "💬 **Общение:** напишите мне любой вопрос.\n"
        "🎨 **Создание фото:** `рисуй [описание]` или `/рисуй [описание]`\n\n"
        "Чем я могу вам помочь?"
    )

# 5. Генерация изображений через FLUX.1
def process_image(message, prompt):
    if not prompt:
        bot.reply_to(
            message,
            "Пожалуйста, укажите, что нарисовать. Например:\n`рисуй спортивный автомобиль в неоновом городе`",
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
        bot.reply_to(message, f"Ошибка при создании изображения: {e}")

@bot.message_handler(commands=['рисуй', 'нарисуй', 'draw', 'image'])
def draw_cmd(message):
    prompt = re.sub(r"^/(рисуй|нарисуй|draw|image)(@\w+)?\s*", "", message.text, flags=re.IGNORECASE).strip()
    process_image(message, prompt)

# 6. Обработка всех сообщений
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    text = message.text.strip()

    # Проверка на генерацию фото без слэша
    draw_pattern = r"^(рисуй|нарисуй|изобрази|сделай фото|сделай картинку)\s*"
    if re.match(draw_pattern, text, re.IGNORECASE):
        prompt = re.sub(draw_pattern, "", text, flags=re.IGNORECASE).strip()
        process_image(message, prompt)
        return

    # Текстовый диалог
    bot.send_chat_action(message.chat.id, 'typing')
    answer = ask_free_ai(text)
    bot.reply_to(message, answer)

# 7. Запуск без ошибки 409
if __name__ == "__main__":
    # Запускаем Flask в фоне
    threading.Thread(target=run_web, daemon=True).start()
    
    # Сбрасываем все прошлые зависшие сессии Telegram
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(2)
    except Exception:
        pass

    print("🚀 Бот успешно запущен и готов к работе!")
    
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=20)
        except ApiTelegramException as e:
            if e.error_code == 409:
                # Мягкая пауза для освобождения порта/сессии на Render
                time.sleep(5)
            else:
                time.sleep(2)
        except Exception:
            time.sleep(2)
