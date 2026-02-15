import os
import io
import traceback
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

client = genai.Client(api_key=GOOGLE_API_KEY)
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот запущен! Пришли фото одежды.")

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
        await update.message.reply_text("Ошибка при загрузке фото.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    await query.edit_message_text("⏳ Генерирую через Imagen 4.0... Пожалуйста, подождите.")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path: return

        gender = "female" if query.data == "female" else "male"
        prompt_text = f"Full body professional fashion photography. A {gender} model wearing the clothing from the reference image. Studio background, 8k resolution."

        # МАКСИМАЛЬНО ЧИСТЫЙ ЗАПРОС БЕЗ ЛИШНИХ ПАРАМЕТРОВ
        # Убираем все фильтры безопасности, чтобы не ловить ошибку 400
        response = client.models.generate_images(
            model='imagen-4.0-generate-001',
            prompt=prompt_text
        )

        if response and response.generated_images:
            img_bytes = response.generated_images[0].image.image_bytes
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=io.BytesIO(img_bytes), 
                caption="Ваш результат готов! ✨"
            )
        else:
            await context.bot.send_message(chat_id, "ИИ не вернул изображение. Попробуйте другой промпт.")

    except Exception as e:
        print(f"Критическая ошибка:\n{traceback.format_exc()}")
        await context.bot.send_message(chat_id, f"Ошибка API: {str(e)[:100]}")
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))

    print("Бот запущен на Imagen 4.0...")
    app.run_polling(drop_pending_updates=True)
