import os
import io
import traceback
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- КОНФИГУРАЦИЯ ---
# Railway подтянет эти переменные из раздела Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Инициализация клиента (актуальный SDK google-genai)
client = genai.Client(api_key=GOOGLE_API_KEY)

# Временное хранилище путей к фото
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь фото одежды, и я примерю её на модель!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        
        # Сохраняем файл локально для передачи в ИИ
        file_path = f"temp_{update.effective_chat.id}.jpg"
        await file.download_to_drive(file_path)
        
        user_sessions[update.effective_chat.id] = file_path

        keyboard = [
            [InlineKeyboardButton("Женская модель", callback_data="female")],
            [InlineKeyboardButton("Мужская модель", callback_data="male")]
        ]
        await update.message.reply_text("Выбери пол модели:", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        print(f"Ошибка загрузки: {e}")
        await update.message.reply_text("Ошибка при получении фото.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    gender = query.data
    chat_id = query.message.chat.id
    await query.edit_message_text("⏳ Генерирую фото... Это бесплатно и займет около 20 секунд.")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path:
            await context.bot.send_message(chat_id, "Ошибка: пришли фото заново.")
            return

        # Подготовка промпта
        model_type = "female fashion model" if gender == "female" else "male fashion model"
        prompt = f"A professional studio photo of a {model_type} wearing the exact clothing from the reference image. High quality, realistic."

        # Генерация изображения (Imagen 3 — самая стабильная бесплатная модель)
        # В API v1beta она работает через generate_images
        response = client.models.generate_images(
            model='imagen-3.0-generate-001',
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="3:4"
            )
        )

        if response.generated_images:
            # Получаем байты напрямую из ответа
            img_bytes = response.generated_images[0].image.image_bytes
            
            # Отправляем в Telegram
            img_io = io.BytesIO(img_bytes)
            img_io.name = 'result.png'
            await context.bot.send_photo(chat_id=chat_id, photo=img_io, caption="Готово!")
        else:
            await context.bot.send_message(chat_id, "ИИ не смог создать картинку. Попробуй другое фото.")

    except Exception as e:
        print(traceback.format_exc())
        await context.bot.send_message(chat_id, "Произошла ошибка в API Gemini. Проверь лимиты или ключ.")
    
    finally:
        # Удаляем временный файл
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
    print("Бот запущен...")
    app.run_polling()
