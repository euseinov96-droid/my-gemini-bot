import os
import telebot
from google import genai
from google.genai import types

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я быстрый ИИ-ассистент на базе Gemini. Задай мне вопрос!")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        # Быстрая модель с лимитом 1500 запросов в день
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=message.text,
            config=types.GenerateContentConfig(
                system_instruction="Ты умный, эрудированный и точный AI-помощник. Текущий год — 2026. Отвечай подробно, актуально и грамотно."
            )
        )
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

print("Бот успешно запущен!")
bot.infinity_polling()
