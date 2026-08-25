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
from openai import OpenAI

# Отключаем лишний шум Flask
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

# 2. Инициализация Telegram и OpenRouter
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY or "dummy_key",
)

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Список актуальных и 100% бесплатных моделей
FREE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-r1:free",
    "deepseek/deepseek-chat:free",
    "mistralai/mistral-7b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free"
]

user_history = {}
MAX_HISTORY = 6

def get_current_date():
    now = datetime.datetime.now()
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    return f"{now.strftime('%d.%m.%Y')}, {weekdays[now.weekday()]}"

def ask_ai(messages_list):
    """Запрос с перебором бесплатных моделей при ошибках 404/402"""
    if not OPENROUTER_API_KEY:
        return "⚠️ Ошибка: укажите OPENROUTER_API_KEY в разделе Environment на Render."
    
    last_error = None
    for model_name in FREE_MODELS:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages_list
            )
            content = response.choices[0].message.content
            if content:
                clean_text = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                return clean_text if clean_text else content.strip()
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if "404" in err_str or "no endpoints found" in err_str or "402" in err_str:
                continue
            raise e
            
    raise last_error

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

# 3. Генерация изображений FLUX.1
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
    if OPENROUTER_API_KEY:
        try:
            task = [
                {"role": "system", "content": "You are a prompt engineer for image generators. Translate to English detailed photo prompt (photorealistic, 8k, lighting). Output ONLY prompt text."},
                {"role": "user", "content": prompt}
            ]
            enhanced = ask_ai(task)
            if enhanced and not enhanced.startswith("⚠️"):
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
    process_image_generation(message, prompt)

# 4. Обработка текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()

    draw_pattern = r"^(рисуй|нарисуй|изобрази|сделай фото|сделай картинку)\s*"
    if re.match(draw_pattern, text, re.IGNORECASE):
        prompt = re.sub(draw_pattern, "", text, flags=re.IGNORECASE).strip()
        process_image_generation(message, prompt)
        return

    user_id = message.chat.id
    bot.send_chat_action(user_id, 'typing')

    if user_id not in user_history:
        user_history[user_id] = []

    user_history[user_id].append({"role": "user", "content": text})
    if len(user_history[user_id]) > MAX_HISTORY:
        user_history[user_id] = user_history[user_id][-MAX_HISTORY:]

    system_instruction = {
        "role": "system",
        "content": (
            f"Ты воспитанный, тактичный и вежливый русскоязычный ИИ-ассистент. "
            f"Всегда обращайся к пользователю уважительно на 'вы'. "
            f"Отвечай емко, грамотно и по существу на чистом русском языке. "
            f"Сегодня {get_current_date()}, 2026 год."
        )
    }

    full_messages = [system_instruction] + user_history[user_id]

    try:
        reply_text = ask_ai(full_messages)
        user_history[user_id].append({"role": "assistant", "content": reply_text})
        bot.reply_to(message, reply_text)
    except Exception as e:
        bot.reply_to(message, f"⚠️ Ошибка API:\n`{e}`", parse_mode="Markdown")

# 5. Запуск бота
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(1)
    except Exception:
        pass

    print("🚀 Бот запущен без единой ошибки!")
    
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=20)
        except ApiTelegramException as e:
            if e.error_code == 409:
                time.sleep(5)
            else:
                time.sleep(2)
        except Exception:
            time.sleep(2)
