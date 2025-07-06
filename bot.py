import os
import json
import re
import time
from dotenv import load_dotenv
import telebot
from flask import Flask, request
from groq import Groq
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold # Import tambahan ini

# Load .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")

# Validate environment variables
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not found. Make sure Telegram Bot Token is set in .env.")
if not GROQ_API_KEY:
    raise Exception("GROQ_API_KEY not found. Make sure Groq API Key is set in .env.")
if not GEMINI_API_KEY:
    raise Exception("GEMINI_API_KEY not found. Make sure Gemini API Key is set in .env.")
if not RENDER_EXTERNAL_HOSTNAME:
    raise Exception("RENDER_EXTERNAL_HOSTNAME not found. Make sure Render environment variable is set.")

WEBHOOK_URL = f"https://{RENDER_EXTERNAL_HOSTNAME}/webhook"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Initialize Groq client for text-only queries
client_groq = Groq(api_key=GROQ_API_KEY)

# Initialize Gemini client for vision tasks
genai.configure(api_key=GEMINI_API_KEY)
vision_model = genai.GenerativeModel('gemini-1.5-flash') # Or 'gemini-1.5-pro' for potentially better understanding but higher cost/latency

app = Flask(__name__)

# --- Persistence for user_data (language and mode) ---
USER_DATA_FILE = "user_data.json"

def load_user_data():
    """Loads user data from a JSON file."""
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: {USER_DATA_FILE} is empty or corrupted. Starting with empty user data.")
                return {}
    return {}

def save_user_data(data):
    """Saves user data to a JSON file."""
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

user_data = load_user_data()

# ========== SYSTEM PROMPTS ==========
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

# --- REVISED SETUP_INSTRUCTION_ID for SINGLE SIGNAL ---
SETUP_INSTRUCTION_ID = (
    "Tolong analisis gambar chart ini dengan cermat dan identifikasi **HANYA SATU potensi peluang trading terbaik yang memiliki probabilitas tertinggi dan Risk:Reward (RR) paling optimal**. " # TEKANKAN 'HANYA SATU' dan 'terbaik'
    "Prioritaskan setup yang paling jelas dan akurat berdasarkan Smart Money Concept (SMC) dan analisis teknikal lanjutan. "
    "Berikan detail sinyal ini dalam **format JSON murni berupa SATU OBJEK TUNGGAL**. " # TEKANKAN 'SATU OBJEK TUNGGAL'
    "Pastikan semua nilai (Pair, Position, Entry, TP, SL, RR) relevan dan realistis sesuai dengan chart. "
    "Jika suatu nilai tidak dapat ditentukan secara spesifik dari gambar, gunakan 'N/A'. "
    "Hitung Risk:Reward (RR) dengan presisi dua desimal."
    "Output harus dimulai dan diakhiri dengan **SATU BLOK JSON TUNGGAL**, tanpa teks pengantar, penutup, atau penjelasan lainnya di luar JSON. "
    "Contoh format:\n"
    "```json\n"
    "{\n"
    "  \"Pair\": \"<Nama Pair/Aset>\",\n"
    "  \"Position\": \"<Long/Short>\",\n"
    "  \"Entry\": \"<Harga Entry>\",\n"
    "  \"TP\": \"<Harga Take Profit>\",\n"
    "  \"SL\": \"<Harga Stop Loss>\",\n"
    "  \"RR\": \"<Rasio Risk:Reward (misal: 1:3.5)>\",\n"
    "  \"Reason\": \"<Penjelasan singkat alasan analisis/sinyal berdasarkan konsep SMC atau teknikal lain>\"\n"
    "}\n"
    "```\n"
    "Output Anda harus murni JSON, tanpa markdown code block backticks ````json` atau teks apapun di luar blok JSON. "
    "**Penting:** Analisis ini murni bersifat edukatif dan teknikal, berdasarkan data chart yang Anda berikan. Ini BUKAN nasihat keuangan atau ajakan untuk berinvestasi. Keputusan trading sepenuhnya tanggung jawab pengguna."
)

# --- REVISED SETUP_INSTRUCTION_EN for SINGLE SIGNAL ---
SETUP_INSTRUCTION_EN = (
    "Please meticulously analyze this chart image and identify **ONLY ONE potential trading opportunity that has the highest probability and the most optimal Risk:Reward (RR)**. " # EMPHASIZE 'ONLY ONE' and 'best'
    "Prioritize the clearest and most accurate setup based on Smart Money Concept (SMC) and advanced technical analysis. "
    "Provide this signal's details in **pure JSON format as a SINGLE OBJECT**. " # EMPHASIZE 'SINGLE OBJECT'
    "Ensure all values (Pair, Position, Entry, TP, SL, RR) are relevant and realistic according to the chart. "
    "If a value cannot be specifically determined from the image, use 'N/A'. "
    "Calculate Risk:Reward (RR) with two decimal precision. "
    "The output must start and end with a **SINGLE JSON BLOCK**, with no introductory, concluding, or other explanatory text outside the JSON. "
    "Example format:\n"
    "```json\n"
    "{\n"
    "  \"Pair\": \"<Asset/Pair Name>\",\n"
    "  \"Position\": \"<Long/Short>\",\n"
    "  \"Entry\": \"<Entry Price>\",\n"
    "  \"TP\": \"<Take Profit Price>\",\n"
    "  \"SL\": \"<Stop Loss Price>\",\n"
    "  \"RR\": \"<Risk:Reward Ratio (e.g., 1:3.5)>\",\n"
    "  \"Reason\": \"<Brief explanation for the analysis/signal based on SMC or other technical concepts>\"\n"
    "}\n"
    "```\n"
    "Your output must be pure JSON, without markdown code block backticks ````json` or any text outside the JSON block. "
    "**Important:** This analysis is purely educational and technical, based on the chart data you provide. It is NOT financial advice or an inducement to invest. Trading decisions are solely the user's responsibility."
)

ANALYZE_INSTRUCTION_ID = (
    "Tolong analisis gambar chart ini secara komprehensif dan identifikasi area-area penting seperti order block, liquidity pool, FVG, support/resistance, atau trendline. "
    "Jelaskan secara mendalam potensi pergerakan harga di masa depan berdasarkan identifikasi area-area tersebut. "
    "Fokus pada penjelasan teknikal murni dengan akurasi tinggi. "
    "Jangan berikan sinyal trading spesifik (Entry, TP, SL) atau rekomendasi beli/jual, melainkan fokus pada interpretasi kondisi pasar dari perspektif teknikal. "
    "**Penting:** Analisis ini murni bersifat edukatif dan teknikal, berdasarkan data chart yang Anda berikan. Ini BUKAN nasihat keuangan atau ajakan untuk berinvestasi. Keputusan trading sepenuhnya tanggung jawab pengguna."
)

ANALYZE_INSTRUCTION_EN = (
    "Please comprehensively analyze this chart image and identify important areas such as order blocks, liquidity pools, FVGs, support/resistance, or trendlines. "
    "Explain in detail potential future price movements based on the identification of these areas. "
    "Focus on purely technical explanations with high accuracy. "
    "Do not provide specific trading signals (Entry, TP, SL) or buy/sell recommendations. Instead, focus on interpreting market conditions from a technical perspective. "
    "**Important:** This analysis is purely educational and technical, based on the chart data you provide. It is NOT financial advice or an inducement to invest. Trading decisions are solely the user's responsibility."
)

# ========== KEYBOARD MARKUPS ==========
def get_language_keyboard():
    """Returns an inline keyboard for language selection."""
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(
        telebot.types.InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en"),
        telebot.types.InlineKeyboardButton("Bahasa Indonesia 🇮🇩", callback_data="set_lang_id")
    )
    return keyboard

def get_main_options_keyboard(lang):
    """Returns an inline keyboard for main bot options based on language."""
    keyboard = telebot.types.InlineKeyboardMarkup()
    if lang == 'en':
        keyboard.add(
            telebot.types.InlineKeyboardButton("📚 Learn (Text)", callback_data="set_mode_learn")
        )
        keyboard.add(
            telebot.types.InlineKeyboardButton("⚙️ Setup Trade (Image)", callback_data="command_setup"),
            telebot.types.InlineKeyboardButton("📈 General Analysis (Image)", callback_data="command_analyze")
        )
    else: # id
        keyboard.add(
            telebot.types.InlineKeyboardButton("📚 Belajar (Teks)", callback_data="set_mode_learn")
        )
        keyboard.add(
            telebot.types.InlineKeyboardButton("⚙️ Setup Trading (Gambar)", callback_data="command_setup"),
            telebot.types.InlineKeyboardButton("📈 Analisis Umum (Gambar)", callback_data="command_analyze")
        )
    return keyboard

# ========== COMMAND HANDLERS ==========
@bot.message_handler(commands=['start', 'menu'])
def send_welcome_or_menu(message):
    """Handles /start and /menu commands, setting up user data if new."""
    chat_id = str(message.chat.id)

    if chat_id not in user_data:
        user_data[chat_id] = {'lang': 'en', 'mode': 'learn'} # Default mode
        save_user_data(user_data)

    lang = user_data[chat_id]['lang']

    if message.text == '/start':
        welcome_text = "Welcome! Please choose your language / Selamat datang! Silakan pilih bahasa Anda:"
        bot.send_message(chat_id, welcome_text, reply_markup=get_language_keyboard())
    elif message.text == '/menu':
        menu_text = "What would you like to do?" if lang == 'en' else "Apa yang ingin Anda lakukan?"
        bot.send_message(chat_id, menu_text, reply_markup=get_main_options_keyboard(lang))

@bot.message_handler(commands=['language'])
def send_language_menu(message):
    """Sends the language selection menu."""
    chat_id = str(message.chat.id)
    if chat_id not in user_data:
        user_data[chat_id] = {'lang': 'en', 'mode': 'learn'}
        save_user_data(user_data)

    lang = user_data[chat_id]['lang']
    text = "Please choose your language:" if lang == 'en' else "Silakan pilih bahasa Anda:"
    bot.send_message(chat_id, text, reply_markup=get_language_keyboard())

@bot.message_handler(commands=['setup'])
def set_mode_setup_command(message):
    """Sets the bot mode to 'setup' for trade signal generation."""
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
    """Sets the bot mode to 'general_analyze' for general chart analysis."""
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
    """Handles language selection from inline keyboard."""
    chat_id = str(call.message.chat.id)
    lang = call.data.split('_')[2]
    user_data[chat_id]['lang'] = lang
    save_user_data(user_data)

    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Language set to English." if lang == 'en' else "Bahasa diatur ke Bahasa Indonesia.")
    send_welcome_or_menu(call.message) # Show main options after language is set

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_mode_'))
def set_mode_callback(call):
    """Handles mode selection (currently only 'learn') from inline keyboard."""
    chat_id = str(call.message.chat.id)
    mode = call.data.split('_')[2]
    user_data[chat_id]['mode'] = mode
    save_user_data(user_data)
    lang = user_data[chat_id]['lang']

    if mode == 'learn':
        msg = "You are now in **Learn** mode. Send me your text queries about trading!" if lang == 'en' \
              else "Anda sekarang dalam mode **Belajar**. Kirimkan pertanyaan teks Anda tentang trading!"
    else:
        msg = "Invalid mode selected." if lang == 'en' else "Mode tidak valid."
    
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=msg)

@bot.callback_query_handler(func=lambda call: call.data.startswith('command_'))
def handle_command_buttons(call):
    """Handles command buttons (e.g., 'setup', 'analyze') by simulating commands."""
    chat_id = str(call.message.chat.id)
    command_name = call.data.split('_')[1]

    # Simulate typing the command to trigger actual command handlers
    if command_name == 'setup':
        call.message.text = '/setup'
        set_mode_setup_command(call.message)
    elif command_name == 'analyze':
        call.message.text = '/analyze'
        set_mode_general_analyze_command(call.message)
    
    bot.answer_callback_query(call.id) # Acknowledge the button press

# ========== TEXT HANDLER ==========
@bot.message_handler(func=lambda m: m.content_type == 'text')
def handle_text(message):
    """Handles text messages, primarily in 'learn' mode using Groq."""
    chat_id = str(message.chat.id)
    chat_type = message.chat.type
    bot_username = bot.get_me().username.lower()

    user_settings = user_data.get(chat_id, {'lang': 'en', 'mode': 'learn'})
    lang = user_settings['lang']
    mode = user_settings['mode']

    # Ensure text messages are only handled in 'learn' mode
    if mode != 'learn':
        bot.reply_to(message, "Please switch to **Learn** mode to send text queries. Use /menu to change." if lang == 'en' else "Mohon beralih ke mode **Belajar** untuk mengirim pertanyaan teks. Gunakan /menu untuk mengubahnya.")
        return

    # Handle group chats: only respond if mentioned or replied to
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

        # Use client_groq for text-only queries
        completion = client_groq.chat.completions.create(
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
    """Handles photo messages for chart analysis using Google Gemini."""
    chat_id = str(message.chat.id)
    user_settings = user_data.get(chat_id, {'lang': 'en', 'mode': 'learn'})
    lang = user_settings['lang']
    current_mode = user_settings['mode']

    # Check if in a valid analysis mode for images
    if current_mode not in ['setup', 'general_analyze']:
        bot.reply_to(message, "Please select an analysis mode first (Setup Trade or General Analysis). Use /menu to choose." if lang == 'en' else "Mohon pilih mode analisis terlebih dahulu (Setup Trading atau Analisis Umum). Gunakan /menu untuk memilih.")
        return

    # Indicate that the bot is processing the image
    processing_message = bot.reply_to(message, "⏳ Processing image... This may take a moment." if lang == 'en' else "⏳ Memproses gambar... Ini mungkin memakan waktu sebentar.")

    temp_file_path = None
    uploaded_file = None

    try:
        caption = message.caption or ("Analyze this image?" if lang == 'en' else "Analisis Gambar Ini?")
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        
        # Download the file directly from Telegram's servers
        downloaded_file = bot.download_file(file_info.file_path)

        # Save the file temporarily to upload to Gemini File API
        temp_file_path = f"temp_{file_id}.jpg"
        with open(temp_file_path, 'wb') as f:
            f.write(downloaded_file)

        # Upload the image to Gemini File API
        uploaded_file = genai.upload_file(path=temp_file_path, display_name=f"chart_{file_id}")
        
        # Check whether the file is ready to be used.
        print(f"Uploaded file '{uploaded_file.display_name}' ({uploaded_file.uri}). Waiting for it to become active...")
        while uploaded_file.state.name == "PROCESSING":
            print('.', end='', flush=True) # Print dot and flush output immediately
            time.sleep(1) # Wait for 1 second before re-checking
            uploaded_file = genai.get_file(uploaded_file.name) # Get updated file status

        if uploaded_file.state.name == "FAILED":
            raise ValueError("File processing failed on Gemini side. Please try again.")
        
        print(f"\nFile {uploaded_file.display_name} is active.")

        # Determine the appropriate instruction text based on the current_mode
        if current_mode == 'setup':
            full_instruction_text = SETUP_INSTRUCTION_EN if lang == 'en' else SETUP_INSTRUCTION_ID
        elif current_mode == 'general_analyze':
            full_instruction_text = ANALYZE_INSTRUCTION_EN if lang == 'en' else ANALYZE_INSTRUCTION_ID
        else: # Fallback, should not happen if logic is sound
            full_instruction_text = "Please analyze this image with high accuracy, focusing on technical aspects. This is for educational purposes only and not financial advice." if lang == 'en' else "Tolong analisis gambar ini dengan akurasi tinggi, fokus pada aspek teknikal. Ini hanya untuk tujuan edukasi dan bukan nasihat keuangan."

        contents = [
            full_instruction_text,
            uploaded_file
        ]

        # Configure generation settings to constrain output
        # max_output_tokens is key here to limit verbosity and multiple signals
        generation_config = genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=300 # Reduced to encourage concise, single-signal output
        )

        # Generate content using the Gemini vision model with explicit safety settings
        gemini_response = vision_model.generate_content(
            contents=contents,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE
            },
            generation_config=generation_config # Add the generation config here
        )
        
        raw_reply = ""
        # Check if any candidate was returned, if not, it was blocked
        if not gemini_response.candidates:
            block_reason_feedback = "UNKNOWN_REASON"
            if gemini_response.prompt_feedback and gemini_response.prompt_feedback.block_reason:
                block_reason_feedback = gemini_response.prompt_feedback.block_reason.name
            
            if block_reason_feedback == "SAFETY":
                raise genai.types.BlockedPromptException(
                    "Prompt blocked due to content policy. This often occurs if the chart or request implies risky financial behavior. Please try a different chart or a more general/educational request." if lang == 'en' else
                    "Permintaan diblokir karena kebijakan konten. Ini sering terjadi jika chart atau permintaan menyiratkan perilaku keuangan berisiko. Silakan coba chart yang berbeda atau permintaan yang lebih umum/edukatif."
                )
            else:
                raise ValueError(
                    f"Gemini API did not return any candidates and was blocked for reason: {block_reason_feedback}." if lang == 'en' else
                    f"API Gemini tidak mengembalikan hasil dan diblokir karena alasan: {block_reason_feedback}."
                )
        else:
            raw_reply = gemini_response.text # Get the text from the successful candidate

        reply_text = ""
        if current_mode == 'setup':
            # Updated regex to specifically look for a single JSON object or an array of objects
            # and clean up surrounding non-JSON characters like `⁠ `
            
            # First, try to find a JSON code block (```json {...} ``` or ```json [{...},{...}] ```)
            json_match = re.search(r'```json\s*([\[\{].*?[\]\}])\s*```', raw_reply, re.DOTALL)
            json_string = None

            if json_match:
                json_string = json_match.group(1).strip()
            else:
                # Fallback: if no markdown block, try to find a direct JSON object or array
                clean_raw_reply = re.sub(r'^[^{[]*|[^}\]]*$', '', raw_reply.strip())
                if clean_raw_reply.startswith('{') and clean_raw_reply.endswith('}'):
                    json_string = clean_raw_reply
                elif clean_raw_reply.startswith('[') and clean_raw_reply.endswith(']'):
                    json_string = clean_raw_reply
                else:
                    # Final attempt: try to extract just the first object if it's not a proper array or single object
                    # This handles the "{obj1},{obj2}" case by trying to parse each individually
                    potential_objects = re.findall(r'\{[^}]*?\}', clean_raw_reply, re.DOTALL)
                    if potential_objects:
                        json_string = potential_objects[0] # Take the first detected object


            setup_data = None
            if json_string:
                try:
                    parsed_json = json.loads(json_string)
                    if isinstance(parsed_json, list): # If it's an array, take the first item
                        if parsed_json:
                            setup_data = parsed_json[0]
                        else:
                            raise json.JSONDecodeError("JSON array is empty.", json_string, 0)
                    elif isinstance(parsed_json, dict): # If it's a single object
                        setup_data = parsed_json
                    else:
                        raise json.JSONDecodeError("Parsed JSON is not an object or array.", json_string, 0)

                except json.JSONDecodeError as e:
                    reply_text = (f"❌ Error: Could not parse setup data. "
                                  f"The AI's response was not valid JSON ({e}). "
                                  f"Raw response extracted:\n`{json_string}`") if lang == 'en' \
                                 else (f"❌ Error: Tidak dapat mengurai data setup. "
                                       f"Respon AI bukan JSON yang valid ({e}). "
                                       f"Respon mentah yang diekstrak:\n`{json_string}`")
            else:
                reply_text = (f"❌ Error: Could not find valid JSON in the AI's response for trade setup. "
                              f"Raw AI response:\n`{raw_reply}`") if lang == 'en' \
                             else (f"❌ Error: Tidak dapat menemukan JSON yang valid dalam respon AI untuk setup trading. "
                                   f"Respon AI mentah:\n`{raw_reply}`")
            
            if setup_data:
                if lang == 'en':
                    reply_text = (
                        f"📊 **Trade Setup:**\n"
                        f"➡️ **Pair:** `{setup_data.get('Pair', 'N/A')}`\n"
                        f"➡️ **Position:** `{setup_data.get('Position', 'N/A')}`\n"
                        f"➡️ **Entry:** `{setup_data.get('Entry', 'N/A')}`\n"
                        f"➡️ **TP:** `{setup_data.get('TP', 'N/A')}`\n"
                        f"➡️ **SL:** `{setup_data.get('SL', 'N/A')}`\n"
                        f"➡️ **RR:** `{setup_data.get('RR', 'N/A')}`\n"
                        f"➡️ **Reason:** {setup_data.get('Reason', 'N/A')}\n\n"
                        f"_Important: This analysis is for educational purposes only and not financial advice._"
                    )
                else: # id
                    reply_text = (
                        f"📊 **Setup Trading:**\n"
                        f"➡️ **Pair:** `{setup_data.get('Pair', 'N/A')}`\n"
                        f"➡️ **Position:** `{setup_data.get('Position', 'N/A')}`\n"
                        f"➡️ **Entry:** `{setup_data.get('Entry', 'N/A')}`\n"
                        f"➡️ **TP:** `{setup_data.get('TP', 'N/A')}`\n"
                        f"➡️ **SL:** `{setup_data.get('SL', 'N/A')}`\n"
                        f"➡️ **RR:** `{setup_data.get('RR', 'N/A')}`\n"
                        f"➡️ **Alasan:** {setup_data.get('Reason', 'N/A')}\n\n"
                        f"_Penting: Analisis ini murni bersifat edukatif dan bukan nasihat keuangan._"
                    )
        else: # general_analyze
            reply_text = raw_reply + (
                "\n\n_Important: This analysis is for educational purposes only and not financial advice._" if lang == 'en' else "\n\n_Penting: Analisis ini murni bersifat edukatif dan bukan nasihat keuangan._"
            )

        bot.edit_message_text(chat_id=chat_id, message_id=processing_message.message_id, text=reply_text)

    # Specific error handling for Gemini API content blocking
    except genai.types.BlockedPromptException as e:
        block_reason = "Unknown"
        if e.response and e.response.prompt_feedback and e.response.prompt_feedback.block_reason:
            block_reason = e.response.prompt_feedback.block_reason.name
        
        detailed_msg_en = f"The input (chart or caption) was blocked due to '{block_reason}' content policy. This often occurs if the chart or request implies risky financial behavior. Please try a different chart or a more general/educational request."
        detailed_msg_id = f"Input (chart atau caption) diblokir karena kebijakan konten '{block_reason}'. Silakan coba chart yang berbeda atau modifikasi permintaan Anda agar tidak terlalu eksplisit tentang potensi risiko keuangan."
        
        final_error_msg = detailed_msg_en if lang == 'en' else detailed_msg_id
        bot.edit_message_text(chat_id=chat_id, message_id=processing_message.message_id, text=f"❌ Analysis blocked by AI:\n{final_error_msg}")

    except genai.types.StopCandidateException as e:
        block_reason_category = "UNKNOWN"
        if e.response and e.response.safety_ratings:
            for rating in e.response.safety_ratings:
                if rating.blocked:
                    block_reason_category = rating.category.name.replace("HARM_CATEGORY_", "")
                    break
        
        detailed_msg_en = f"The AI's response was blocked due to '{block_reason_category}' content policy. This can happen if the generated signal/analysis is interpreted as promoting high-risk behavior. Please try again with a different chart."
        detailed_msg_id = f"Respons AI diblokir karena kebijakan konten '{block_reason_category}'. Ini bisa terjadi jika sinyal/analisis yang dihasilkan diinterpretasikan sebagai mendorong perilaku berisiko tinggi. Silakan coba lagi dengan chart yang berbeda."
        
        final_error_msg = detailed_msg_en if lang == 'en' else detailed_msg_id
        bot.edit_message_text(chat_id=chat_id, message_id=processing_message.message_id, text=f"❌ AI response blocked:\n{final_error_msg}")

    except Exception as e:
        error_msg = f"❌ An unexpected error occurred during image analysis:\n{str(e)}" if lang == 'en' else f"❌ Terjadi error tak terduga saat analisis gambar:\n{str(e)}"
        bot.edit_message_text(chat_id=chat_id, message_id=processing_message.message_id, text=error_msg)
    finally:
        # Clean up temporary files
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            print(f"Cleaned up temporary file {temp_file_path}.")
        # Delete the uploaded file from Gemini File API
        if uploaded_file and uploaded_file.name:
            try:
                genai.delete_file(uploaded_file.name)
                print(f"Cleaned up Gemini uploaded file {uploaded_file.name}.")
            except Exception as delete_error:
                print(f"Warning: Failed to delete Gemini file {uploaded_file.name}: {delete_error}")


# ========= FLASK ROUTES =========
@app.route("/")
def home():
    """Basic home route to indicate the bot is running."""
    return "🤖 Bot is running via webhook!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Webhook endpoint for Telegram updates."""
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
    print(f"Starting Flask app on port {port} with webhook URL: {WEBHOOK_URL}")
    app.run(host="0.0.0.0", port=port)