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
    await update.message.reply_text("👋 Привет! Пришли фото одежды, и я сделаю примерку.")

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
    await query.edit_message_text("⏳ Генерирую образ через Gemini 2.5 Image...")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path: return

        with open(garment_path, "rb") as f:
            image_bytes = f.read()

        gender = "female" if query.data == "female" else "male"
        prompt = f"A professional photo of a {gender} model wearing the exact clothing from this image. Realistic fashion photography."

        # Используем В ТОЧНОСТИ ту модель и конфиг, что дала Студия
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                types.Part.from_text(text=prompt)
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"]
            )
        )

        image_sent = False
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    img_io = io.BytesIO(part.inline_data.data)
                    img_io.name = 'result.png'
                    await context.bot.send_photo(chat_id=chat_id, photo=img_io, caption="Готово! ✨")
                    image_sent = True
                    break
        
        if not image_sent:
            await context.bot.send_message(chat_id, "ИИ не сгенерировал картинку. Возможно, сработали фильтры безопасности Google.")

    except Exception as e:
        err_msg = str(e)
        print(f"Критическая ошибка:\n{traceback.format_exc()}")
        if "429" in err_msg:
            await context.bot.send_message(chat_id, "Ошибка: Превышен лимит запросов (Quota Exceeded). Подождите 1-2 минуты.")
        else:
            await context.bot.send_message(chat_id, f"Ошибка API: {err_msg[:50]}")
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))

    print("Бот запускается...")
    # Игнорируем накопленные сообщения, чтобы не спамить в случае Conflict
    app.run_polling(drop_pending_updates=True)
