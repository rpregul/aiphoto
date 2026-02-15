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
    await update.message.reply_text("👋 Бот готов! Пришли фото одежды.")

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
        await update.message.reply_text("Ошибка загрузки.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    await query.edit_message_text("⏳ Генерирую (Nano Banana 2.0)...")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path: return

        with open(garment_path, "rb") as f:
            image_bytes = f.read()

        model_type = "female fashion model" if query.data == "female" else "male fashion model"
        prompt = f"High-end fashion photography. {model_type} wearing the clothing from the reference image. Studio lighting, 8k."

        # Используем Gemini 2.0 Flash — у нее больше лимитов в Free Tier
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    types.Part.from_text(text=prompt),
                ],
            ),
        ]
        
        # Конфиг для генерации именно КАРТИНКИ
        generate_content_config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        )

        image_data = None
        # Потоковое получение результата
        for chunk in client.models.generate_content_stream(
            model="gemini-2.0-flash", 
            contents=contents,
            config=generate_content_config,
        ):
            if chunk.parts:
                for part in chunk.parts:
                    if part.inline_data:
                        image_data = part.inline_data.data
                        break
        
        if image_data:
            await context.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(image_data))
        else:
            await context.bot.send_message(chat_id, "ИИ не выдал картинку. Попробуй другой ракурс.")

    except Exception as e:
        err_raw = str(e)
        if "429" in err_raw:
            await context.bot.send_message(chat_id, "Превышен лимит запросов Google. Подождите 1 минуту.")
        else:
            print(traceback.format_exc())
            await context.bot.send_message(chat_id, "Ошибка генерации.")
    
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

# --- ЗАПУСК ---
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(handle_choice))

if __name__ == "__main__":
    app.run_polling()
