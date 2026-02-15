import os
import io
import traceback
import mimetypes
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
    await update.message.reply_text("👋 Привет! Пришли фото одежды, и я примерю её на модель (Nano Banana).")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_path = f"garment_{update.effective_chat.id}.jpg"
        await file.download_to_drive(file_path)
        user_sessions[update.effective_chat.id] = file_path

        keyboard = [[InlineKeyboardButton("Женская модель", callback_data="female")],
                    [InlineKeyboardButton("Мужская модель", callback_data="male")]]
        await update.message.reply_text("Выбери пол модели:", reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text("Ошибка загрузки фото.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    gender = query.data
    chat_id = query.message.chat.id
    await query.edit_message_text("⏳ Генерирую образ через Gemini 2.5 Pro Image...")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path:
            return

        with open(garment_path, "rb") as f:
            image_bytes = f.read()

        model_type = "female fashion model" if gender == "female" else "male fashion model"
        prompt = f"Professional fashion photography. A {model_type} wearing the exact clothing from this reference image. 8k, realistic."

        # ИСПОЛЬЗУЕМ СТРУКТУРУ ИЗ ГУГЛ СТУДИИ
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    types.Part.from_text(text=prompt),
                ],
            ),
        ]
        
        generate_content_config = types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        )

        image_data = None
        
        # Запускаем стрим, как в примере
        for chunk in client.models.generate_content_stream(
            model="gemini-2.5-flash-image",
            contents=contents,
            config=generate_content_config,
        ):
            if chunk.parts:
                for part in chunk.parts:
                    if part.inline_data and part.inline_data.data:
                        image_data = part.inline_data.data
                        break
        
        if image_data:
            bio = io.BytesIO(image_data)
            bio.name = 'result.png'
            await context.bot.send_photo(chat_id=chat_id, photo=bio, caption="Ваш результат готов! ✨")
        else:
            await context.bot.send_message(chat_id, "ИИ не прислал изображение. Попробуйте другое фото.")

    except Exception as e:
        print(f"Критическая ошибка:\n{traceback.format_exc()}")
        await context.bot.send_message(chat_id, "Произошла ошибка при генерации.")
    
    finally:
        if chat_id in user_sessions:
            if os.path.exists(user_sessions[chat_id]):
                os.remove(user_sessions[chat_id])
            del user_sessions[chat_id]

# --- ЗАПУСК ---
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(handle_choice))

if __name__ == "__main__":
    app.run_polling()
