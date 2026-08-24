import os
import datetime
import telebot
from google import genai
from google.genai import types

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

# Храним только последние 3 пары сообщений на пользователя
user_histories = {}
MAX_MESSAGES_COUNT = 6  # 3 вопроса + 3 ответа

def get_system_instruction():
    now = datetime.datetime.now()
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    weekday = weekdays[now.weekday()]
    date_str = now.strftime("%d.%m.%Y")
    
    return (
        f"Ты полезный и умный AI-собеседник. Сегодня {date_str}, {weekday}. "
        f"Текущий год строго 2026. Отвечай кратко, по делу и информативно."
    )

@bot.message_handler(commands=['start', 'reset'])
def send_welcome(message):
    user_histories[message.chat.id] = []
    bot.reply_to(
        message, 
        "Привет! Я готов к общению. Память оптимизирована для экономии лимитов.\n"
        "Чтобы очистить историю, отправь /reset."
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.chat.id
    
    if user_id not in user_histories:
        user_histories[user_id] = []
    
    # Добавляем вопрос пользователя
    user_histories[user_id].append(
        types.Content(role="user", parts=[types.Part.from_text(text=message.text)])
    )
    
    # Оставляем строго не более 6 последних элементов (3 диалога)
    if len(user_histories[user_id]) > MAX_MESSAGES_COUNT:
        user_histories[user_id] = user_histories[user_id][-MAX_MESSAGES_COUNT:]
        
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_histories[user_id],
            config=types.GenerateContentConfig(
                system_instruction=get_system_instruction()
            )
        )
        
        # Сохраняем ответ модели
        if response.text:
            user_histories[user_id].append(
                types.Content(role="model", parts=[types.Part.from_text(text=response.text)])
            )
            bot.reply_to(message, response.text)
        else:
            bot.reply_to(message, "Не удалось получить ответ, попробуйте еще раз.")
            
    except Exception as e:
        err_text = str(e)
        if "429" in err_text:
            bot.reply_to(message, "⚠️ Сработал лимит запросов. Подождите 30 секунд перед следующим сообщением.")
        else:
            bot.reply_to(message, f"Ошибка: {err_text}")

print("Бот успешно запущен!")
bot.infinity_polling()
