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

# Твой прокси (обязательно оставь его, иначе будет GEO-блок)
PROXY_URL = "aiphoto.plotnikov-csh.workers.dev" 

client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={'api_version': 'v1beta', 'base_url': f"https://{PROXY_URL}"}
)

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧪 Тестируем Gemini 2.5 Flash Lite Preview!")

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
    await query.edit_message_text("⏳ Попытка генерации через Flash-Lite...")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path: return

        with open(garment_path, "rb") as f:
            image_bytes = f.read()

        gender = "female" if query.data == "female" else "male"
        prompt = f"Return a generated image of a {gender} model wearing this outfit."

        # Пробуем Lite-версию
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite-preview-09-2025", 
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
            await context.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(image_data), caption="Сработало на Lite! ✨")
        else:
            text_resp = response.candidates[0].content.parts[0].text if response.candidates else "No output"
            await context.bot.send_message(chat_id, f"Lite вернула текст вместо фото: {text_resp[:150]}")

    except Exception as e:
        print(traceback.format_exc())
        await context.bot.send_message(chat_id, f"Ошибка Lite: {str(e)[:100]}")
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.run_polling(drop_pending_updates=True)
