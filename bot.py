import os
import re
import urllib.parse
import datetime
import threading
from flask import Flask
import telebot
from google import genai
from google.genai import types

# 1. Заглушка для Render Web Service 24/7
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Инициализация
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

user_history = {}
MAX_HISTORY = 2

def get_current_date():
    now = datetime.datetime.now()
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    return f"{now.strftime('%d.%m.%Y')}, {weekdays[now.weekday()]}"

@bot.message_handler(commands=['start', 'reset'])
def send_welcome(message):
    user_history[message.chat.id] = []
    bot.reply_to(
        message,
        "Здравствуйте! Рад приветствовать вас. Я ваш персональный ИИ-ассистент.\n\n"
        "💬 **Общение и вопросы:** просто напишите мне любое сообщение.\n"
        "🎨 **Создание фото:** напишите `рисуй [описание]` или `/рисуй [описание]`\n"
        "🔄 **Сброс контекста:** /reset\n\n"
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
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Translate to English photo prompt (photorealistic, lighting, details): '{prompt}'. Output ONLY prompt."
        )
        if resp.text:
            final_prompt = resp.text.strip()
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

# 4. Текстовые ответы с вежливым тоном и контролем квоты
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
        f"Ты воспитанный, вежливый и дружелюбный русскоязычный ИИ-ассистент. "
        f"Всегда общайся с пользователем уважительно, вежливо и тактично, обращаясь на 'вы'. "
        f"Отвечай грамотно, емко и по существу, помогая решить вопрос наилучшим образом. "
        f"Сегодня {get_current_date()}, 2026 год.\n\n"
        + "\n".join(user_history[user_id])
        + "\nModel:"
    )

    need_search = any(k in text.lower() for k in ["сегодня", "новости", "курс", "погода", "кто такой", "когда", "сейчас", "2026"])

    try:
        config = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]) if need_search else None

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=system_prompt,
            config=config
        )
        reply_text = response.text if response.text else "Прошу прощения, не удалось сформировать ответ."
        user_history[user_id].append(f"Model: {reply_text}")
        bot.reply_to(message, reply_text)

    except Exception:
        try:
            fallback_response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=system_prompt
            )
            reply = fallback_response.text if fallback_response.text else "Готово."
            bot.reply_to(message, reply)
        except Exception:
            bot.reply_to(message, "Пожалуйста, подождите около минуты — сейчас наблюдается временная нагрузка на сервер Google API.")

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    print("Бот успешно запущен!")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
