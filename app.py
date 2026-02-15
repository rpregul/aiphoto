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
    await query.edit_message_text("⏳ Генерирую финальное изображение...")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path: return

        # Читаем фото для использования в качестве контекста (если модель поддерживает)
        with open(garment_path, "rb") as f:
            image_bytes = f.read()

        gender_text = "female fashion model" if query.data == "female" else "male fashion model"
        
        # Максимально простой и понятный промпт для Imagen
        prompt_text = f"Full body professional photography of a {gender_text} wearing the specific style of garment from the provided reference. High fashion studio look, 8k, photorealistic."

        # Используем метод generate_images, так как Flash не отдал IMAGE через stream
        # Мы используем 'imagen-3.0-generate-001' - это самая стабильная точка входа для картинок
        response = client.models.generate_images(
            model='imagen-3.0-generate-001',
            prompt=prompt_text,
            config={
                'number_of_images': 1,
                'aspect_ratio': "3:4"
                # Мы УБРАЛИ все спорные параметры, чтобы не было ошибок валидации
            }
        )

        if response and response.generated_images:
            generated_img = response.generated_images[0]
            # В новых версиях SDK байты лежат здесь:
            img_payload = generated_img.image.image_bytes 
            
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=io.BytesIO(img_payload),
                caption="Готово! ✨"
            )
        else:
            await context.bot.send_message(chat_id, "ИИ не смог сгенерировать изображение. Попробуй другое фото.")

    except Exception as e:
        print(f"Критическая ошибка:\n{traceback.format_exc()}")
        # Если ОПЯТЬ 404, бот скажет об этом в логах
        await context.bot.send_message(chat_id, "Техническая ошибка на стороне API Google.")
    
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(handle_choice))

if __name__ == "__main__":
    app.run_polling()
