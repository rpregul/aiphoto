import os
import io
import traceback
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Инициализация клиента Gemini
client = genai.Client(api_key=GOOGLE_API_KEY)

# Временное хранилище путей к фото
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Пришли фото одежды, и я создам фото с моделью.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        
        # Сохраняем фото локально
        file_path = f"garment_{update.effective_chat.id}.jpg"
        await file.download_to_drive(file_path)
        
        user_sessions[update.effective_chat.id] = file_path

        keyboard = [
            [InlineKeyboardButton("Женская модель", callback_data="female")],
            [InlineKeyboardButton("Мужская модель", callback_data="male")]
        ]
        await update.message.reply_text("Выбери пол модели:", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        print(f"Ошибка загрузки фото: {e}")
        await update.message.reply_text("Не удалось загрузить фото.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    gender = query.data
    chat_id = query.message.chat.id
    await query.edit_message_text("⏳ Генерирую финальное фото (движок Nano Banana)...")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path or not os.path.exists(garment_path):
            await context.bot.send_message(chat_id, "Ошибка: фото не найдено. Пришли его еще раз.")
            return

        # Читаем картинку в байты
        with open(garment_path, "rb") as f:
            image_bytes = f.read()

        model_type = "female fashion model" if gender == "female" else "male fashion model"
        
        # Промпт для генерации
        prompt_text = f"Professional studio fashion photography. A {model_type} wearing the clothing item from the reference photo. Realistic textures, 8k, high quality."

        # ВЫЗОВ ГЕНЕРАЦИИ (Самый стабильный метод)
        # Мы передаем конфигурацию как простой DICT, чтобы избежать ошибок валидации
        response = client.models.generate_images(
            model='imagen-3.0-generate-001',
            prompt=prompt_text,
            config={
                'number_of_images': 1,
                'aspect_ratio': "3:4",
                'add_watermark': False
            }
        )

        if response and response.generated_images:
            # Извлекаем байты картинки
            generated_img_bytes = response.generated_images[0].image.image_bytes
            
            # Подготовка к отправке в ТГ
            bio = io.BytesIO(generated_img_bytes)
            bio.name = 'result.png'
            
            await context.bot.send_photo(chat_id=chat_id, photo=bio, caption="Результат готов! ✨")
        else:
            await context.bot.send_message(chat_id, "ИИ не смог сгенерировать картинку. Попробуй другое фото одежды.")

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Критическая ошибка:\n{error_trace}")
        await context.bot.send_message(chat_id, f"Произошла техническая ошибка. Проверь логи Railway.")
    
    finally:
        # Очистка за собой
        if chat_id in user_sessions:
            if os.path.exists(user_sessions[chat_id]):
                os.remove(user_sessions[chat_id])
            del user_sessions[chat_id]

# --- ЗАПУСК БОТА ---
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(handle_choice))

if __name__ == "__main__":
    print("Бот запущен...")
    app.run_polling()
