import os
import io
import requests
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

# Актуальные ID моделей на февраль 2026
MODELS_TO_TRY = [
    "gemini-3-flash",      # Самая новая
    "gemini-2.5-flash",    # Текущий стандарт
    "gemini-2.5-flash-lite", # Эконом-вариант
    "gemini-2.0-flash"     # Стабильная классика
]

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Бот обновлен! Модели актуализированы. Пришли фото.")

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
    
    await query.edit_message_text("⏳ Перебираю доступные нейросети Google...")

    garment_path = user_sessions.get(chat_id)
    if not garment_path: return

    with open(garment_path, "rb") as f:
        image_bytes = f.read()

    ai_prompt = None
    success_model = None
    
    # КАРУСЕЛЬ: Пробуем только живые модели
    for model_name in MODELS_TO_TRY:
        try:
            print(f"Попытка запроса к: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    f"Create a high-fashion prompt for a {gender} model wearing this. Result only in English."
                ]
            )
            
            if response.text:
                ai_prompt = response.text
                success_model = model_name
                break 
                
        except Exception as e:
            err = str(e)
            print(f"❌ {model_name} недоступна: {err[:50]}")
            continue 

    if not ai_prompt:
        await query.message.reply_text("❌ Google отклонил все запросы (429/404). Попробуй позже.")
        return

    # ОТРИСОВКА
    image_gen_url = f"https://image.pollinations.ai/prompt/{ai_prompt.replace(' ', '%20')}?width=1024&height=1280&nologo=true"
    
    try:
        img_res = requests.get(image_gen_url, timeout=30)
        await context.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(img_res.content), 
                                     caption=f"✅ Готово!\nМодель: {success_model}")
    except:
        await query.message.reply_text("Ошибка генерации изображения.")
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.run_polling(drop_pending_updates=True)
