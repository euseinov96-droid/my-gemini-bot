import os
import datetime
import telebot
from google import genai
from google.genai import types

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

# Память для каждого пользователя
user_chats = {}

def get_system_instruction():
    now = datetime.datetime.now()
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    weekday = weekdays[now.weekday()]
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")
    
    return (
        f"Ты умный, эрудированный и живой AI-собеседник. "
        f"Сегодняшняя дата: {date_str}, день недели: {weekday}, время: {time_str} UTC. "
        f"Текущий год строго 2026. "
        f"Ты отлично разбираешься в мировой географии, городах, истории, культуре и современных праздниках. "
        f"Ты помнишь всю историю диалога с пользователем. Отвечай развернуто, грамотно и интересно."
    )

def get_user_chat(user_id):
    if user_id not in user_chats:
        user_chats[user_id] = client.chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=get_system_instruction()
            )
        )
    return user_chats[user_id]

@bot.message_handler(commands=['start', 'reset'])
def send_welcome(message):
    # Создаем или сбрасываем чат-сессию
    user_chats[message.chat.id] = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=get_system_instruction()
        )
    )
    bot.reply_to(
        message, 
        "Привет! Я помню контекст нашей беседы, знаю текущую дату, города, праздники и события. Задай мне любой вопрос!\n\n"
        "*(Чтобы очистить память диалога, отправь команду /reset)*"
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        # Отправляем сообщение в сессию с памятью
        chat = get_user_chat(message.chat.id)
        response = chat.send_message(message.text)
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

print("Бот успешно запущен!")
bot.infinity_polling()
