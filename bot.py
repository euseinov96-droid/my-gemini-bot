import os
import re
import time
import urllib.parse
import threading
import logging
from flask import Flask
import telebot
from telebot.apihelper import ApiTelegramException

# Отключаем лишние логи сервера
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# 1. Веб-сервер для Render Web Service (удерживает процесс 24/7)
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is alive 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Инициализация Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(
        message,
        "Здравствуйте! Я ваш персональный ассистент.\n\n"
        "🎨 **Создание фото:** отправьте команду `рисуй [описание]` или `/рисуй [описание]`\n"
        "💬 Напишите любой запрос, и я вам помогу."
    )

# 3. Генератор картинок через FLUX.1 (работает всегда без ключей и квот)
def generate_image(message, prompt):
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
        bot.reply_to(message, f"Ошибка при отправке изображения: {e}")

@bot.message_handler(commands=['рисуй', 'нарисуй', 'draw', 'image'])
def handle_draw_cmd(message):
    prompt = re.sub(r"^/(рисуй|нарисуй|draw|image)(@\w+)?\s*", "", message.text, flags=re.IGNORECASE).strip()
    generate_image(message, prompt)

# 4. Обработка всех сообщений
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    text = message.text.strip()
    
    # Триггер рисования без слэша
    draw_pattern = r"^(рисуй|нарисуй|изобрази|сделай фото|сделай картинку)\s*"
    if re.match(draw_pattern, text, re.IGNORECASE):
        prompt = re.sub(draw_pattern, "", text, flags=re.IGNORECASE).strip()
        generate_image(message, prompt)
        return

    # Вежливый базовый ответ
    bot.reply_to(
        message,
        f"Здравствуйте! Ваше сообщение принято: «{text}».\n\n"
        f"Если вы хотите создать изображение, напишите:\n`рисуй [что нарисовать]`",
        parse_mode="Markdown"
    )

# 5. Запуск с защитой от ошибок Render и 409
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(1)
    except Exception:
        pass
    
    print("Бот успешно запущен!")
    
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=20)
        except ApiTelegramException as e:
            if e.error_code == 409:
                print("Конфликт 409: ждем освобождения сессии...")
                time.sleep(5)
            else:
                time.sleep(2)
        except Exception:
            time.sleep(2)
