import os
import json
from dotenv import load_dotenv
import telebot
from flask import Flask, request
from groq import Groq

# Load .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN") or "8172517978:AAHkn3i8f_uYVb8GkN-kMB5GkNuLtNSFkn0"
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or "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"
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

if not RENDER_EXTERNAL_HOSTNAME:
    raise Exception("RENDER_EXTERNAL_HOSTNAME not found. Make sure Render environment variable is set.")
WEBHOOK_URL = f"https://{RENDER_EXTERNAL_HOSTNAME}/webhook"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
client = Groq(api_key=GROQ_API_KEY)
app = Flask(__name__)

# --- Persistence for user_data (language and mode) ---
# This will save to a file. On ephemeral filesystems like Render,
# this data will be lost when the dyno restarts.
# For true persistence on Render, you'd need an external database.
USER_DATA_FILE = "user_data.json"

def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {} # Return empty if file is corrupted
    return {}

def save_user_data(data):
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(data, f)

# Dictionary to store user's language preference and current mode (learn/analyze)
user_data = load_user_data() # Load data on startup

# ========== SYSTEM PROMPTS ==========
SYSTEM_PROMPT_ID = (
    "Kamu adalah asisten pribadi ahli trading berpengalaman lebih dari 10 tahun. "
    "Kuasai semua aspek trading crypto, forex, saham, dan komoditas. "
    "Spesialisasimu meliputi:\n"
    "- Smart Money Concept (SMC), order block, liquidity, inducement, FVG\n"
    "- Teknik entry presisi berdasarkan timing dan volume sweep\n"
    "- Analisis fundamental koin micin Solana & token DeFi\n"
    "- Risk management dan strategi cuan jangka pendek maupun panjang\n"
    "- Tools trading seperti Fibonacci, EMA 9/20, RSI, stochastic\n"
    "- Membantu pengguna membangun trading journal dan mengevaluasi kesalahan entry\n"
    "Jawabanmu harus jelas, taktis, mendalam, dan mudah dipahami bahkan oleh pemula.\n"
    "Jika user menanyakan hal diluar konteks trading, jawab singkat atau arahkan kembali ke topik trading."
)

SYSTEM_PROMPT_EN = (
    "You are a personal assistant, an expert trader with over 10 years of experience. "
    "You are proficient in all aspects of crypto, forex, stock, and commodity trading. "
    "Your specializations include:\n"
    "- Smart Money Concept (SMC), order block, liquidity, inducement, FVG\n"
    "- Precise entry techniques based on timing and volume sweep\n"
    "- Fundamental analysis of Solana memecoins & DeFi tokens\n"
    "- Risk management and short-term and long-term profit strategies\n"
    "- Trading tools such as Fibonacci, EMA 9/20, RSI, stochastic\n"
    "- Assisting users in building a trading journal and evaluating entry mistakes\n"
    "Your answers must be clear, tactical, in-depth, and easy to understand even for beginners.\n"
    "If a user asks something outside the trading context, answer briefly or redirect them back to the trading topic."
)

# ========== KEYBOARD MARKUPS ==========
def get_language_keyboard():
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(
        telebot.types.InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en"),
        telebot.types.InlineKeyboardButton("Bahasa Indonesia 🇮🇩", callback_data="set_lang_id")
    )
    return keyboard

def get_main_menu_keyboard(lang):
    keyboard = telebot.types.InlineKeyboardMarkup()
    if lang == 'en':
        keyboard.add(
            telebot.types.InlineKeyboardButton("📚 Learn (Text)", callback_data="set_mode_learn"),
            telebot.types.InlineKeyboardButton("📊 Analyze (Image)", callback_data="set_mode_analyze")
        )
    else: # id
        keyboard.add(
            telebot.types.InlineKeyboardButton("📚 Belajar (Teks)", callback_data="set_mode_learn"),
            telebot.types.InlineKeyboardButton("📊 Analisis (Gambar)", callback_data="set_mode_analyze")
        )
    return keyboard

# ========== COMMAND HANDLERS ==========
@bot.message_handler(commands=['start', 'settings'])
def send_welcome_or_settings(message):
    chat_id = str(message.chat.id) # Convert to string for JSON keys

    if chat_id not in user_data:
        user_data[chat_id] = {'lang': 'en', 'mode': 'learn'} # Default
        save_user_data(user_data) # Save initial data

    lang = user_data[chat_id]['lang']

    if message.text == '/start':
        welcome_text = "Welcome! Please choose your language / Selamat datang! Silakan pilih bahasa Anda:"
        bot.send_message(chat_id, welcome_text, reply_markup=get_language_keyboard())
    elif message.text == '/settings':
        settings_text = "Language & Mode Settings:" if lang == 'en' else "Pengaturan Bahasa & Mode:"
        bot.send_message(chat_id, settings_text, reply_markup=get_language_keyboard())
        send_main_menu(chat_id) # Also show mode options

# ========== CALLBACK QUERY HANDLERS ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith('set_lang_'))
def set_language_callback(call):
    chat_id = str(call.message.chat.id)
    lang = call.data.split('_')[2]
    user_data[chat_id]['lang'] = lang
    save_user_data(user_data) # Save updated data

    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Language set to English." if lang == 'en' else "Bahasa diatur ke Bahasa Indonesia.")
    send_main_menu(chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_mode_'))
def set_mode_callback(call):
    chat_id = str(call.message.chat.id)
    mode = call.data.split('_')[2]
    user_data[chat_id]['mode'] = mode
    save_user_data(user_data) # Save updated data
    lang = user_data[chat_id]['lang']

    if mode == 'learn':
        msg = "You are now in **Learn** mode. Send me your text queries about trading!" if lang == 'en' \
              else "Anda sekarang dalam mode **Belajar**. Kirimkan pertanyaan teks Anda tentang trading!"
    else: # analyze
        msg = "You are now in **Analyze** mode. Send me an image with an optional caption for analysis!" if lang == 'en' \
              else "Anda sekarang dalam mode **Analisis**. Kirimkan gambar dengan caption opsional untuk dianalisis!"

    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=msg)

def send_main_menu(chat_id):
    lang = user_data[chat_id]['lang']
    text = "Choose your interaction mode:" if lang == 'en' else "Pilih mode interaksi Anda:"
    bot.send_message(chat_id, text, reply_markup=get_main_menu_keyboard(lang))

# ========== TEXT HANDLER ==========
@bot.message_handler(func=lambda m: m.content_type == 'text')
def handle_text(message):
    chat_id = str(message.chat.id)
    chat_type = message.chat.type
    bot_username = bot.get_me().username.lower()

    # Get user's preferred language and mode
    user_settings = user_data.get(chat_id, {'lang': 'en', 'mode': 'learn'}) # Default if not set
    lang = user_settings['lang']
    mode = user_settings['mode']

    # Check if in 'learn' mode
    if mode != 'learn':
        bot.reply_to(message, "Please switch to **Learn** mode to send text queries. Use /settings to access the menu." if lang == 'en' else "Mohon beralih ke mode **Belajar** untuk mengirim pertanyaan teks. Gunakan /settings untuk mengakses menu.")
        return

    # If from group, only reply if mentioned or replied
    if chat_type in ["group", "supergroup"]:
        is_mentioned = any(
            entity.type == "mention" and message.text[entity.offset:entity.offset + entity.length].lower() == f"@{bot_username}"
            for entity in message.entities or []
        )
        is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.username == bot_username

        if not (is_mentioned or is_reply_to_bot):
            return  # Ignore if not mentioned or not replied

    try:
        user_input = message.text
        # Select system prompt based on user's language
        current_system_prompt = SYSTEM_PROMPT_EN if lang == 'en' else SYSTEM_PROMPT_ID

        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": current_system_prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=1,
            max_tokens=1024,
        )
        reply = completion.choices[0].message.content
        bot.reply_to(message, reply)
    except Exception as e:
        bot.reply_to(message, f"❌ Error:\n{str(e)}" if lang == 'en' else f"❌ Error:\n{str(e)}")

# ========== IMAGE HANDLER ==========
@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    chat_id = str(message.chat.id)
    user_settings = user_data.get(chat_id, {'lang': 'en', 'mode': 'learn'}) # Default if not set
    lang = user_settings['lang']
    mode = user_settings['mode']

    # Check if in 'analyze' mode
    if mode != 'analyze':
        bot.reply_to(message, "Please switch to **Analyze** mode to send images for analysis. Use /settings to access the menu." if lang == 'en' else "Mohon beralih ke mode **Analisis** untuk mengirim gambar untuk dianalisis. Gunakan /settings untuk mengakses menu.")
        return

    try:
        caption = message.caption or ("Analyze this image?" if lang == 'en' else "Analisis Gambar Ini?")
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"

        # Select system prompt based on user's language
        current_system_prompt = SYSTEM_PROMPT_EN if lang == 'en' else SYSTEM_PROMPT_ID

        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct", # Ensure this model supports image input
            messages=[
                {"role": "system", "content": current_system_prompt},
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
        bot.reply_to(message, f"❌ Error analyzing image:\n{str(e)}" if lang == 'en' else f"❌ Error saat analisis gambar:\n{str(e)}")

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