import os
import telebot
import requests
import base64
from dotenv import load_dotenv
from groq import Groq

# Load environment
load_dotenv()

# Token dan API Key langsung di-hardcode (tidak direkomendasikan untuk produksi)
BOT_TOKEN = "8172517978:AAHkn3i8f_uYVb8GkN-kMB5GkNuLtNSFkn0"
GROQ_API_KEY = "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"

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)
BOT_USERNAME = bot.get_me().username  # otomatis ambil username bot

print("🤖 Bot is running...")

# ======== TEXT HANDLER (model: llama) ========
@bot.message_handler(func=lambda message: message.content_type == "text")
def handle_text(message):
    try:
        # Jika di grup, hanya respon jika di-mention
        if message.chat.type in ["group", "supergroup"]:
            if f"@{BOT_USERNAME}" not in message.text:
                return  # jangan balas jika tidak di-mention

            # Hapus mention biar prompt bersih
            user_input = message.text.replace(f"@{BOT_USERNAME}", "").strip()
        else:
            user_input = message.text  # private chat

        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "user", "content": user_input}
            ],
            temperature=1,
            max_tokens=1024,
        )
        reply = completion.choices[0].message.content
        bot.reply_to(message, reply)
    except Exception as e:
        bot.reply_to(message, f"❌ Error saat memproses teks:\n{str(e)}")

# ======== PHOTO HANDLER (model: llama) ========
@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    try:
        # Jika di grup, hanya respon jika caption-nya ada mention bot
        if message.chat.type in ["group", "supergroup"]:
            if not message.caption or f"@{BOT_USERNAME}" not in message.caption:
                return  # jangan balas jika tidak di-mention

            caption = message.caption.replace(f"@{BOT_USERNAME}", "").strip()
        else:
            caption = message.caption if message.caption else "Apa isi gambar ini?"

        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"

        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": caption},
                        {"type": "image_url", "image_url": {"url": file_url}}
                    ]
                }
            ],
            temperature=1,
            max_completion_tokens=1024,
        )

        reply = completion.choices[0].message.content
        bot.reply_to(message, reply)

    except Exception as e:
        bot.reply_to(message, f"❌ Error saat analisis gambar:\n{str(e)}")

# ======== JALANKAN BOT ========
bot.polling(none_stop=True)
