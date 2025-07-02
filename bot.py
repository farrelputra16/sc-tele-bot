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
USER_DATA_FILE = "user_data.json"

def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: {USER_DATA_FILE} is empty or corrupted. Starting with empty user data.")
                return {}
    return {}

def save_user_data(data):
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

user_data = load_user_data()

# ========== SYSTEM PROMPTS ==========
# Base system prompt for general trading expertise
BASE_SYSTEM_PROMPT_ID = (
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

BASE_SYSTEM_PROMPT_EN = (
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

# Specific system prompt additions for structured setup analysis
SETUP_PROMPT_ADDITION_ID = (
    "Berdasarkan gambar chart yang diberikan, identifikasi peluang trading dan berikan detail sinyal dalam format JSON berikut. "
    "Pastikan semua nilai relevan dan realistis. Jika suatu nilai tidak dapat ditentukan, gunakan 'N/A'. "
    "Hitung Risk:Reward (RR) dengan presisi dua desimal. "
    "Format JSON yang diharapkan:\n"
    "```json\n"
    "{\n"
    "  \"Pair\": \"<Nama Pair/Aset>\",\n"
    "  \"Entry\": \"<Harga Entry>\",\n"
    "  \"TP\": \"<Harga Take Profit>\",\n"
    "  \"SL\": \"<Harga Stop Loss>\",\n"
    "  \"RR\": \"<Rasio Risk:Reward (misal: 1:3.5)>\",\n"
    "  \"Reason\": \"<Alasan Analisis/Sinyal>\"\n"
    "}\n"
    "```\n"
    "Output harus murni JSON, tanpa teks pengantar atau penutup."
)

SETUP_PROMPT_ADDITION_EN = (
    "Based on the provided chart image, identify a trading opportunity and provide signal details in the following JSON format. "
    "Ensure all values are relevant and realistic. If a value cannot be determined, use 'N/A'. "
    "Calculate Risk:Reward (RR) with two decimal precision. "
    "Expected JSON format:\n"
    "```json\n"
    "{\n"
    "  \"Pair\": \"<Asset/Pair Name>\",\n"
    "  \"Entry\": \"<Entry Price>\",\n"
    "  \"TP\": \"<Take Profit Price>\",\n"
    "  \"SL\": \"<Stop Loss Price>\",\n"
    "  \"RR\": \"<Risk:Reward Ratio (e.g., 1:3.5)>\",\n"
    "  \"Reason\": \"<Analysis/Signal Reason>\"\n"
    "}\n"
    "```\n"
    "The output must be pure JSON, without any introductory or concluding text."
)

# Specific system prompt additions for general analysis
ANALYZE_PROMPT_ADDITION_ID = (
    "Berdasarkan gambar chart yang diberikan, lakukan analisis pergerakan harga. "
    "Identifikasi area-area penting seperti order block, liquidity pool, FVG, support/resistance, atau trendline. "
    "Jelaskan potensi pergerakan harga di masa depan berdasarkan area-area tersebut. "
    "Jangan berikan sinyal trading spesifik (Entry, TP, SL) atau rekomendasi beli/jual. "
    "Fokus pada penjelasan teknikal murni."
)

ANALYZE_PROMPT_ADDITION_EN = (
    "Based on the provided chart image, perform a price movement analysis. "
    "Identify important areas such as order blocks, liquidity pools, FVGs, support/resistance, or trendlines. "
    "Explain potential future price movements based on these areas. "
    "Do not provide specific trading signals (Entry, TP, SL) or buy/sell recommendations. "
    "Focus purely on technical explanations."
)

# JSON Schema for structured setup output
SETUP_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "Pair": {"type": "STRING"},
        "Entry": {"type": "STRING"},
        "TP": {"type": "STRING"},
        "SL": {"type": "STRING"},
        "RR": {"type": "STRING"},
        "Reason": {"type": "STRING"}
    },
    "required": ["Pair", "Entry", "TP", "SL", "RR", "Reason"],
    "propertyOrdering": ["Pair", "Entry", "TP", "SL", "RR", "Reason"]
}

# ========== KEYBOARD MARKUPS ==========
def get_language_keyboard():
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(
        telebot.types.InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en"),
        telebot.types.InlineKeyboardButton("Bahasa Indonesia 🇮🇩", callback_data="set_lang_id")
    )
    return keyboard

def get_mode_keyboard(lang):
    keyboard = telebot.types.InlineKeyboardMarkup()
    if lang == 'en':
        keyboard.add(
            telebot.types.InlineKeyboardButton("📚 Learn (Text)", callback_data="set_mode_learn")
        )
        keyboard.add(
            telebot.types.InlineKeyboardButton("⚙️ Setup Trade (Image)", callback_data="set_mode_setup"),
            telebot.types.InlineKeyboardButton("📈 General Analysis (Image)", callback_data="set_mode_general_analyze")
        )
    else: # id
        keyboard.add(
            telebot.types.InlineKeyboardButton("📚 Belajar (Teks)", callback_data="set_mode_learn")
        )
        keyboard.add(
            telebot.types.InlineKeyboardButton("⚙️ Setup Trading (Gambar)", callback_data="set_mode_setup"),
            telebot.types.InlineKeyboardButton("📈 Analisis Umum (Gambar)", callback_data="set_mode_general_analyze")
        )
    return keyboard

# ========== COMMAND HANDLERS ==========
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = str(message.chat.id)

    if chat_id not in user_data:
        user_data[chat_id] = {'lang': 'en', 'mode': 'learn'} # Default
        save_user_data(user_data)

    welcome_text = "Welcome! Please choose your language / Selamat datang! Silakan pilih bahasa Anda:"
    bot.send_message(chat_id, welcome_text, reply_markup=get_language_keyboard())

@bot.message_handler(commands=['language'])
def send_language_menu(message):
    chat_id = str(message.chat.id)
    if chat_id not in user_data:
        user_data[chat_id] = {'lang': 'en', 'mode': 'learn'}
        save_user_data(user_data)

    lang = user_data[chat_id]['lang']
    text = "Please choose your language:" if lang == 'en' else "Silakan pilih bahasa Anda:"
    bot.send_message(chat_id, text, reply_markup=get_language_keyboard())

@bot.message_handler(commands=['mode'])
def send_mode_menu(message):
    chat_id = str(message.chat.id)
    if chat_id not in user_data:
        user_data[chat_id] = {'lang': 'en', 'mode': 'learn'}
        save_user_data(user_data)

    lang = user_data[chat_id]['lang']
    text = "Choose your interaction mode:" if lang == 'en' else "Pilih mode interaksi Anda:"
    bot.send_message(chat_id, text, reply_markup=get_mode_keyboard(lang))

# New command handlers for specific analysis types
@bot.message_handler(commands=['setup'])
def set_mode_setup_command(message):
    chat_id = str(message.chat.id)
    if chat_id not in user_data:
        user_data[chat_id] = {'lang': 'en', 'mode': 'learn'}
    user_data[chat_id]['mode'] = 'setup'
    save_user_data(user_data)
    lang = user_data[chat_id]['lang']
    msg = "You are now in **Setup Trade** mode. Send me a chart image for signal generation!" if lang == 'en' \
          else "Anda sekarang dalam mode **Setup Trading**. Kirimkan gambar chart untuk menghasilkan sinyal!"
    bot.send_message(chat_id, msg)

@bot.message_handler(commands=['analyze'])
def set_mode_general_analyze_command(message):
    chat_id = str(message.chat.id)
    if chat_id not in user_data:
        user_data[chat_id] = {'lang': 'en', 'mode': 'learn'}
    user_data[chat_id]['mode'] = 'general_analyze'
    save_user_data(user_data)
    lang = user_data[chat_id]['lang']
    msg = "You are now in **General Analysis** mode. Send me a chart image for market movement analysis!" if lang == 'en' \
          else "Anda sekarang dalam mode **Analisis Umum**. Kirimkan gambar chart untuk analisis pergerakan pasar!"
    bot.send_message(chat_id, msg)

# ========== CALLBACK QUERY HANDLERS ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith('set_lang_'))
def set_language_callback(call):
    chat_id = str(call.message.chat.id)
    lang = call.data.split('_')[2]
    user_data[chat_id]['lang'] = lang
    save_user_data(user_data)

    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Language set to English." if lang == 'en' else "Bahasa diatur ke Bahasa Indonesia.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_mode_'))
def set_mode_callback(call):
    chat_id = str(call.message.chat.id)
    mode = call.data.split('_')[2]
    user_data[chat_id]['mode'] = mode
    save_user_data(user_data)
    lang = user_data[chat_id]['lang']

    if mode == 'learn':
        msg = "You are now in **Learn** mode. Send me your text queries about trading!" if lang == 'en' \
              else "Anda sekarang dalam mode **Belajar**. Kirimkan pertanyaan teks Anda tentang trading!"
    elif mode == 'setup':
        msg = "You are now in **Setup Trade** mode. Send me a chart image for signal generation!" if lang == 'en' \
              else "Anda sekarang dalam mode **Setup Trading**. Kirimkan gambar chart untuk menghasilkan sinyal!"
    elif mode == 'general_analyze':
        msg = "You are now in **General Analysis** mode. Send me a chart image for market movement analysis!" if lang == 'en' \
              else "Anda sekarang dalam mode **Analisis Umum**. Kirimkan gambar chart untuk analisis pergerakan pasar!"

    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=msg)

# ========== TEXT HANDLER ==========
@bot.message_handler(func=lambda m: m.content_type == 'text')
def handle_text(message):
    chat_id = str(message.chat.id)
    chat_type = message.chat.type
    bot_username = bot.get_me().username.lower()

    user_settings = user_data.get(chat_id, {'lang': 'en', 'mode': 'learn'})
    lang = user_settings['lang']
    mode = user_settings['mode']

    if mode != 'learn':
        bot.reply_to(message, "Please switch to **Learn** mode to send text queries. Use /mode to change." if lang == 'en' else "Mohon beralih ke mode **Belajar** untuk mengirim pertanyaan teks. Gunakan /mode untuk mengubahnya.")
        return

    if chat_type in ["group", "supergroup"]:
        is_mentioned = any(
            entity.type == "mention" and message.text[entity.offset:entity.offset + entity.length].lower() == f"@{bot_username}"
            for entity in message.entities or []
        )
        is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.username == bot_username

        if not (is_mentioned or is_reply_to_bot):
            return

    try:
        user_input = message.text
        current_system_prompt = BASE_SYSTEM_PROMPT_EN if lang == 'en' else BASE_SYSTEM_PROMPT_ID

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
    user_settings = user_data.get(chat_id, {'lang': 'en', 'mode': 'learn'})
    lang = user_settings['lang']
    mode = user_settings['mode']

    # Check if in a valid analysis mode
    if mode not in ['setup', 'general_analyze']:
        bot.reply_to(message, "Please select an analysis mode first (Setup Trade or General Analysis). Use /mode to change." if lang == 'en' else "Mohon pilih mode analisis terlebih dahulu (Setup Trading atau Analisis Umum). Gunakan /mode untuk mengubahnya.")
        return

    try:
        caption = message.caption or ("Analyze this image?" if lang == 'en' else "Analisis Gambar Ini?")
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"

        messages = []
        generation_config = {}

        if mode == 'setup':
            # For 'setup' mode, combine base prompt with setup-specific prompt and enforce JSON schema
            current_system_prompt = (BASE_SYSTEM_PROMPT_EN + "\n\n" + SETUP_PROMPT_ADDITION_EN) if lang == 'en' \
                                    else (BASE_SYSTEM_PROMPT_ID + "\n\n" + SETUP_PROMPT_ADDITION_ID)
            
            messages.append({"role": "system", "content": current_system_prompt})
            messages.append({"role": "user", "content": [
                {"type": "text", "text": caption},
                {"type": "image_url", "image_url": {"url": file_url}}
            ]})
            generation_config = {
                "responseMimeType": "application/json",
                "responseSchema": SETUP_RESPONSE_SCHEMA
            }
            model_to_use = "meta-llama/llama-4-scout-17b-16e-instruct" # Image capable model
            
        elif mode == 'general_analyze':
            # For 'general_analyze' mode, combine base prompt with general analysis prompt
            current_system_prompt = (BASE_SYSTEM_PROMPT_EN + "\n\n" + ANALYZE_PROMPT_ADDITION_EN) if lang == 'en' \
                                    else (BASE_SYSTEM_PROMPT_ID + "\n\n" + ANALYZE_PROMPT_ADDITION_ID)
            
            messages.append({"role": "system", "content": current_system_prompt})
            messages.append({"role": "user", "content": [
                {"type": "text", "text": caption},
                {"type": "image_url", "image_url": {"url": file_url}}
            ]})
            model_to_use = "meta-llama/llama-4-scout-17b-16e-instruct" # Image capable model

        completion = client.chat.completions.create(
            model=model_to_use,
            messages=messages,
            temperature=0.7, # Slightly lower temperature for more precise analysis
            max_completion_tokens=1024,
            **generation_config # Apply generation config if present (for setup mode)
        )
        
        raw_reply = completion.choices[0].message.content

        # Format the reply based on mode
        reply_text = ""
        if mode == 'setup':
            try:
                # Parse the JSON response
                setup_data = json.loads(raw_reply)
                if lang == 'en':
                    reply_text = (
                        f"📊 **Trade Setup:**\n"
                        f"➡️ **Pair:** `{setup_data.get('Pair', 'N/A')}`\n"
                        f"➡️ **Entry:** `{setup_data.get('Entry', 'N/A')}`\n"
                        f"➡️ **TP:** `{setup_data.get('TP', 'N/A')}`\n"
                        f"➡️ **SL:** `{setup_data.get('SL', 'N/A')}`\n"
                        f"➡️ **RR:** `{setup_data.get('RR', 'N/A')}`\n"
                        f"➡️ **Reason:** {setup_data.get('Reason', 'N/A')}"
                    )
                else: # id
                    reply_text = (
                        f"📊 **Setup Trading:**\n"
                        f"➡️ **Pair:** `{setup_data.get('Pair', 'N/A')}`\n"
                        f"➡️ **Entry:** `{setup_data.get('Entry', 'N/A')}`\n"
                        f"➡️ **TP:** `{setup_data.get('TP', 'N/A')}`\n"
                        f"➡️ **SL:** `{setup_data.get('SL', 'N/A')}`\n"
                        f"➡️ **RR:** `{setup_data.get('RR', 'N/A')}`\n"
                        f"➡️ **Alasan:** {setup_data.get('Reason', 'N/A')}"
                    )
            except json.JSONDecodeError:
                reply_text = f"❌ Error: Could not parse setup data. Raw response:\n`{raw_reply}`" if lang == 'en' \
                             else f"❌ Error: Tidak dapat mengurai data setup. Respon mentah:\n`{raw_reply}`"
        else: # general_analyze
            reply_text = raw_reply # For general analysis, just use the raw text reply

        bot.reply_to(message, reply_text)

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