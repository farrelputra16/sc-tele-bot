import telebot
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Inisialisasi bot
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def handle_start(message):
    chat_id = message.chat.id
    username = message.from_user.username or "Unknown"
    bot.send_message(chat_id, f"Hi @{username}! Welcome to SC Analyzer Bot! Use /help for commands.")

@bot.message_handler(commands=['help'])
def handle_help(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "This is a trading bot. Commands:\n/start - Start bot\n/help - Show help\nSay 'Ajarkan FVG' or 'Analyze H1 chart' for trading info.")

@bot.message_handler(content_types=['text'])
def handle_message(message):
    chat_id = message.chat.id
    user_message = message.text.lower()
    username = message.from_user.username or "Unknown"

    if 'ajarkan fvg' in user_message:
        prompt = "Jelaskan Fair Value Gap (FVG) dalam trading secara singkat dalam bahasa Indonesia."
    elif 'analyze h1 chart' in user_message:
        prompt = "Analisis chart H1 untuk trading forex secara singkat dalam bahasa Indonesia."
    else:
        bot.send_message(chat_id, f"@{username}, say 'Ajarkan FVG' or 'Analyze H1 chart' for trading info!")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}",
    }
    payload = {
        "model": "mixtral-8x7b-32768",
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        response = requests.post(GROQ_URL, headers=headers, json=payload)
        response.raise_for_status()
        bot_response = response.json()["choices"][0]["message"]["content"]
        formatted_response = f"@{username}, {bot_response}"
        bot.send_message(chat_id, formatted_response)
    except Exception as e:
        bot.send_message(chat_id, f"@{username}, error: {str(e)}")

# Jalankan bot
print("Bot is running...")
bot.polling(none_stop=True)