import os
import io
import traceback
from google import genai
# Мы будем передавать настройки словарями, чтобы избежать ошибок AttributeError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Инициализация клиента
client = genai.Client(api_key=GOOGLE_API_KEY)

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Пришли фото одежды, и я создам фото с моделью.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_path = f"garment_{update.effective_chat.id}.jpg"
        await file.download_to_drive(file_path)
        
        user_sessions[update.effective_chat.id] = file_path

        keyboard = [
            [InlineKeyboardButton("Женская модель", callback_data="female")],
            [InlineKeyboardButton("Мужская модель", callback_data="male")]
        ]
        await update.message.reply_text("Выбери пол модели:", reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text("Ошибка при загрузке фото.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    gender = query.data
    chat_id = query.message.chat.id
    await query.edit_message_text("🎨 ИИ генерирует изображение... Это займет около 20 секунд.")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path:
            await context.bot.send_message(chat_id, "Ошибка: фото не найдено.")
            return

        # Читаем байты одежды
        with open(garment_path, "rb") as f:
            image_bytes = f.read()

        model_desc = "female fashion model" if gender == "female" else "male fashion model"
        
        # Инструкция для модели (Nano Banana)
        prompt = f"Professional fashion photography. A {model_desc} is wearing the exact clothing item from this reference image. High quality, realistic lighting, 8k resolution."

        # Используем универсальный вызов через словарь config, чтобы избежать AttributeError
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[
                {'mime_type': 'image/jpeg', 'data': image_bytes},
                prompt
            ],
            config={
                'image_generation_config': {
                    'number_of_images': 1,
                    'aspect_ratio': "3:4"
                }
            }
        )

        image_sent = False
        if response.candidates:
            for part in response.candidates[0].content.parts:
                # В новом SDK данные изображения приходят в inline_data.data
                if part.inline_data:
                    img_io = io.BytesIO(part.inline_data.data)
                    img_io.name = 'result.png'
                    await context.bot.send_photo(chat_id=chat_id, photo=img_io, caption="Ваш образ готов!")
                    image_sent = True
                    break
        
        if not image_sent:
            await context.bot.send_message(chat_id, "ИИ не смог сгенерировать картинку (возможно, сработал фильтр безопасности). Попробуйте другое фото.")

    except Exception as e:
        print(traceback.format_exc())
        await context.bot.send_message(chat_id, f"Ошибка API: {str(e)}")
    finally:
        # Чистим временные файлы
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
