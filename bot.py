import os
from dotenv import load_dotenv
import telebot
from flask import Flask, request
from groq import Groq

# Load .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN") or "8172517978:AAHkn3i8f_uYVb8GkN-kMB5GkNuLtNSFkn0"
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or "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"
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

# Webhook URL
if not RENDER_EXTERNAL_HOSTNAME:
    raise Exception("RENDER_EXTERNAL_HOSTNAME tidak ditemukan. Pastikan Render environment variable sudah di-set.")
WEBHOOK_URL = f"https://{RENDER_EXTERNAL_HOSTNAME}/webhook"

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)
app = Flask(__name__)

# ========= TEXT HANDLER =========
@bot.message_handler(func=lambda m: m.content_type == 'text')
def handle_text(message):
    try:
        user_input = message.text
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": user_input}],
            temperature=1,
            max_tokens=1024,
        )
        reply = completion.choices[0].message.content
        bot.reply_to(message, reply)
    except Exception as e:
        bot.reply_to(message, f"❌ Error:\n{str(e)}")

# ========= IMAGE HANDLER =========
@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    try:
        caption = message.caption or "Apa isi gambar ini?"
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"

        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": caption},
                    {"type": "image_url", "image_url": {"url": file_url}}
                ]}
            ],
            temperature=1,
            max_completion_tokens=1024,
        )
        reply = completion.choices[0].message.content
        bot.reply_to(message, reply)

    except Exception as e:
        bot.reply_to(message, f"❌ Error saat analisis gambar:\n{str(e)}")

# ========= FLASK ROUTES =========
@app.route("/")
def home():
    return "🤖 Bot is running via webhook!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "OK", 200
    return "Invalid request", 403

# ========= RUN FLASK + SET WEBHOOK =========
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
