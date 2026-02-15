import os
import io
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

# Список моделей для проверки (от новых к старым)
MODELS_TO_TRY = [
    "gemini-3-flash-thinking-preview", 
    "gemini-2.0-flash-lite-preview-09-2025",
    "gemini-1.5-flash-8b",
    "gemini-1.5-flash"
]

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Карусель моделей запущена! Пришли фото для анализа.")

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
    
    await query.edit_message_text("⏳ Подбираю свободную модель Gemini...")

    garment_path = user_sessions.get(chat_id)
    if not garment_path: return

    with open(garment_path, "rb") as f:
        image_bytes = f.read()

    ai_prompt = None
    
    # КАРУСЕЛЬ: Пробуем модели по очереди
    for model_name in MODELS_TO_TRY:
        try:
            print(f"Пробую модель: {model_name}")
            
            # Настройка для Thinking моделей (если модель поддерживает мысли)
            config = None
            if "thinking" in model_name:
                config = types.GenerateContentConfig(thinking_config=types.ThinkingConfig(include_thoughts=True))

            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    f"Describe this clothing item. Create a text-to-image prompt for a {gender} model wearing this. ONLY English prompt."
                ],
                config=config
            )
            
            if response.text:
                ai_prompt = response.text
                print(f"✅ Успех с моделью {model_name}")
                break # Выходим из цикла, если получили ответ
                
        except Exception as e:
            print(f"❌ Модель {model_name} выдала ошибку: {str(e)[:50]}")
            continue # Пробуем следующую

    if not ai_prompt:
        await query.message.reply_text("Все модели Google сейчас перегружены (429). Попробуй через 5 минут.")
        return

    # ОТРИСОВКА (Pollinations всегда работает)
    image_url = f"https://image.pollinations.ai/prompt/{ai_prompt.replace(' ', '%20')}?width=1024&height=1280&nologo=true"
    
    try:
        img_res = requests.get(image_url, timeout=30)
        await context.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(img_res.content), caption=f"Готово! (Использована модель: {model_name})")
    except:
        await query.message.reply_text("Ошибка генерации финальной картинки.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.run_polling(drop_pending_updates=True)
