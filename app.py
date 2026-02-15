import os
import io
import traceback
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

client = genai.Client(api_key=GOOGLE_API_KEY)
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Пришли фото одежды.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_path = f"garment_{update.effective_chat.id}.jpg"
        await file.download_to_drive(file_path)
        user_sessions[update.effective_chat.id] = file_path
        
        keyboard = [[InlineKeyboardButton("Женская модель", callback_data="female")],
                    [InlineKeyboardButton("Мужская модель", callback_data="male")]]
        await update.message.reply_text("Выбери пол:", reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text("Ошибка загрузки фото.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    await query.edit_message_text("⏳ Генерирую (использую Gemini Preview Image)...")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path: return

        with open(garment_path, "rb") as f:
            image_bytes = f.read()

        gender = "female" if query.data == "female" else "male"
        prompt = f"Generate a realistic photo of a {gender} fashion model wearing the exact clothes from this image. High resolution, studio lighting."

        # Используем логику из Студии, но с моделью Flash (она стабильнее в Free Tier)
        # Если gemini-2.0-flash выдаст 404, заменим на gemini-2.0-flash-exp
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                types.Part.from_text(text=prompt)
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"]
            )
        )

        image_sent = False
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    img_io = io.BytesIO(part.inline_data.data)
                    img_io.name = 'result.png'
                    await context.bot.send_photo(chat_id=chat_id, photo=img_io, caption="Готово!")
                    image_sent = True
                    break
        
        if not image_sent:
            await context.bot.send_message(chat_id, "ИИ не смог создать картинку. Возможно, сработал фильтр безопасности.")

    except Exception as e:
        print(f"Критическая ошибка:\n{traceback.format_exc()}")
        await context.bot.send_message(chat_id, f"Ошибка API: {str(e)[:100]}")
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

# --- ЗАПУСК ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Пытаемся немного "почистить" Conflict перед стартом
    # (Это не панацея, но иногда помогает)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))

    print("Бот запускается...")
    app.run_polling(drop_pending_updates=True) # Игнорируем старые сообщения при старте
