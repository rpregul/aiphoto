import os
import io
import time
import requests
import traceback
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PROXY_URL = "aiphoto.plotnikov-csh.workers.dev" 

client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={'api_version': 'v1beta', 'base_url': f"https://{PROXY_URL}"}
)

# Используем только 2.0 и 3.0, так как 1.5 выдает 404
MODELS_TO_TRY = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash-lite-preview-09-2025" # Иногда полные имена работают лучше
]

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💎 Бот настроен на Gemini 2.0. Пришли фото!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = f"garment_{update.effective_chat.id}.jpg"
    await file.download_to_drive(file_path)
    user_sessions[update.effective_chat.id] = file_path
    
    keyboard = [[InlineKeyboardButton("Женская модель", callback_data="female")],
                [InlineKeyboardButton("Мужская модель", callback_data="male")]]
    await update.message.reply_text("Выбери пол:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    gender = "female" if query.data == "female" else "male"
    
    await query.edit_message_text("⏳ Стучусь в Google (модели 2.0)...")

    garment_path = user_sessions.get(chat_id)
    if not garment_path: return

    with open(garment_path, "rb") as f:
        image_bytes = f.read()

    ai_prompt = None
    last_error = ""
    
    for model_id in MODELS_TO_TRY:
        try:
            print(f"Запрос к {model_id}...")
            # В SDK genai префикс models/ часто добавляется автоматически, 
            # попробуем БЕЗ него, раз 1.5 выдавали 404
            response = client.models.generate_content(
                model=model_id,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    f"Describe clothes. Give me a prompt for a {gender} model wearing this. English only."
                ]
            )
            
            if response.text:
                ai_prompt = response.text
                break
        except Exception as e:
            last_error = str(e)
            print(f"❌ {model_id} мимо: {last_error[:100]}")
            if "429" in last_error:
                time.sleep(2) # Пауза при лимитах
            continue

    if not ai_prompt:
        await query.message.reply_text(f"Google занят (429). Попробуй через пару минут.")
        return

    # ГЕНЕРАЦИЯ (Pollinations)
    try:
        clean_prompt = ai_prompt.strip().replace("\n", " ")
        image_url = f"https://image.pollinations.ai/prompt/{clean_prompt.replace(' ', '%20')}?width=1024&height=1280&seed={int(time.time())}"
        
        img_res = requests.get(image_url, timeout=30)
        await context.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(img_res.content), caption="✨ Готово!")
    except Exception as e:
        await query.message.reply_text("Картинка не прогрузилась, но описание получено.")
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.run_polling(drop_pending_updates=True)
