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

# Инициализируем клиент
client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={'api_version': 'v1beta', 'base_url': f"https://{PROXY_URL}"}
)

# Список моделей с ОБЯЗАТЕЛЬНЫМ префиксом models/
MODELS_TO_TRY = [
    "models/gemini-2.0-flash", 
    "models/gemini-1.5-flash",
    "models/gemini-1.5-flash-8b"
]

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Бот обновлен (v3.0). Теперь с правильной адресацией моделей. Пришли фото!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = f"garment_{update.effective_chat.id}.jpg"
    await file.download_to_drive(file_path)
    user_sessions[update.effective_chat.id] = file_path
    
    keyboard = [[InlineKeyboardButton("Женская модель", callback_data="female")],
                [InlineKeyboardButton("Мужская модель", callback_data="male")]]
    await update.message.reply_text("Выбери пол модели:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    gender = "female" if query.data == "female" else "male"
    
    await query.edit_message_text(f"⏳ Пробую достучаться до моделей Google...")

    garment_path = user_sessions.get(chat_id)
    if not garment_path: return

    with open(garment_path, "rb") as f:
        image_bytes = f.read()

    ai_prompt = None
    last_error = ""
    
    # ПЕРЕБОР МОДЕЛЕЙ
    for model_id in MODELS_TO_TRY:
        try:
            print(f"Запрос к {model_id}...")
            response = client.models.generate_content(
                model=model_id,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    f"Describe this clothing. Generate a short English prompt for a {gender} model wearing this. Prompt only."
                ]
            )
            
            if response.text:
                ai_prompt = response.text
                print(f"✅ Успех с {model_id}")
                break
        except Exception as e:
            last_error = str(e)
            print(f"❌ Ошибка {model_id}: {last_error[:50]}")
            continue

    if not ai_prompt:
        await query.message.reply_text(f"Все модели отказали.\nПоследняя ошибка: {last_error[:100]}")
        return

    # ГЕНЕРАЦИЯ КАРТИНКИ
    try:
        # Очистка промпта от лишних символов
        clean_prompt = ai_prompt.strip().replace("\n", " ").replace('"', '')
        image_url = f"https://image.pollinations.ai/prompt/{clean_prompt.replace(' ', '%20')}?width=1024&height=1280&nologo=true"
        
        img_res = requests.get(image_url, timeout=30)
        if img_res.status_code == 200:
            await context.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(img_res.content), caption="✨ Образ готов!")
        else:
            await query.message.reply_text("Ошибка отрисовщика Pollinations.")
    except Exception as e:
        await query.message.reply_text(f"Ошибка при создании картинки: {str(e)[:50]}")
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

if __name__ == "__main__":
    # Небольшая задержка перед стартом для Railway
    time.sleep(2)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))
    
    print("Бот запущен...")
    app.run_polling(drop_pending_updates=True)
