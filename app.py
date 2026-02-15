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
    await update.message.reply_text("✅ Бот готов! Пришли фото одежды для генерации образа.")

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
    await query.edit_message_text("⏳ Генерирую фото через Imagen 4.0...")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path: return

        gender = "female" if query.data == "female" else "male"
        # Промпт адаптирован под Imagen 4.0
        prompt_text = f"A professional high-fashion studio photo of a {gender} model wearing the clothing item shown in the reference. Photorealistic, 8k resolution, cinematic lighting."

        # ИСПОЛЬЗУЕМ МОДЕЛЬ ИЗ ТВОЕГО СПИСКА
        # Метод generate_images — единственный верный для моделей серии imagen
        response = client.models.generate_images(
            model='imagen-4.0-generate-001',
            prompt=prompt_text,
            config={
                'number_of_images': 1,
                'aspect_ratio': "3:4",
                'safety_filter_level': "BLOCK_ONLY_HIGH" 
            }
        )

        if response and response.generated_images:
            img_bytes = response.generated_images[0].image.image_bytes
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=io.BytesIO(img_bytes), 
                caption="Готово! ✨"
            )
        else:
            await context.bot.send_message(chat_id, "ИИ не смог сгенерировать изображение.")

    except Exception as e:
        print(f"Критическая ошибка:\n{traceback.format_exc()}")
        await context.bot.send_message(chat_id, f"Ошибка: {str(e)[:100]}")
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))

    print("Бот запускается на Imagen 4.0...")
    app.run_polling(drop_pending_updates=True)
