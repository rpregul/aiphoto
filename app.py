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

# Твой рабочий прокси
PROXY_URL = "aiphoto.plotnikov-csh.workers.dev" 

client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={'api_version': 'v1beta', 'base_url': f"https://{PROXY_URL}"}
)

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✨ Бот активен! Пришли фото для примерки.")

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
    chat_id = query.message.chat.id
    await query.edit_message_text("⏳ Магия в процессе... Генерирую образ.")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path: return

        with open(garment_path, "rb") as f:
            image_bytes = f.read()

        gender = "female" if query.data == "female" else "male"
        
        # Инструкция для Gemini 2.0, чтобы она выдала именно IMAGE
        prompt = f"Create a high-quality, photorealistic image of a {gender} model wearing this clothing. Output ONLY the image."

        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                types.Part.from_text(text=prompt),
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"]
            )
        )

        image_data = None
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_data = part.inline_data.data
                    break
        
        if image_data:
            await context.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(image_data), caption="Готово! 🔥")
        else:
            # Если опять текст, выведем начало для понимания
            text_resp = response.candidates[0].content.parts[0].text if response.candidates else "No output"
            await context.bot.send_message(chat_id, f"ИИ прислал текст: {text_resp[:150]}")

    except Exception as e:
        print(traceback.format_exc())
        err_msg = str(e)
        if "429" in err_msg:
            await context.bot.send_message(chat_id, "⚠️ Лимиты Free Tier. Подожди 1 минуту.")
        else:
            await context.bot.send_message(chat_id, f"Ошибка API: {err_msg[:100]}")
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))
    # drop_pending_updates=True лечит ошибку Conflict при перезагрузке
    app.run_polling(drop_pending_updates=True)
