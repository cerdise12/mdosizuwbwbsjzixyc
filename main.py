import telebot
from google import genai

# Настройки
TELEGRAM_TOKEN = '8535152044:AAHZ7K73QYb4YORH3o6535JKS5d_9HMPJRQ'
GEMINI_API_KEY = 'AIzaSyAI1f44jzIG-WdlVF0Axyq1BMU8KSQjD7k'

# Инициализация нового клиента Gemini
client = genai.Client(api_key=GEMINI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Использую новейший Google GenAI SDK. Чем помочь?")

@bot.message_handler(func=lambda message: True)
def get_ai_response(message):
    try:
        # Используем современный метод generate_content
        response = client.models.generate_content(
            model="gemini-2.0-flash", # или "gemini-1.5-pro"
            contents=message.text
        )
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

bot.infinity_polling()
