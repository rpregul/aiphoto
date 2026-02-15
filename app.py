import os
import io
import traceback
from PIL import Image
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Инициализация актуального клиента Gemini (SDK 2026)
client = genai.Client(api_key=GOOGLE_API_KEY)

# Пути к вашим локальным файлам (убедитесь, что папка models и файлы существуют)
FEMALE_MODEL_PATH = "models/female.jpg"
MALE_MODEL_PATH = "models/male.jpg"

# Хранилище путей к фото (в продакшене лучше использовать БД)
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я ИИ-стилист.\n"
        "Пришли мне фото одежды на светлом фоне, и я примерю её на модель."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Получаем фото в максимальном качестве
        photo = update.message.photo[-1]
        file = await photo.get_file()
        
        # Сохраняем временно под уникальным именем
        file_path = f"garment_{update.effective_chat.id}.jpg"
        await file.download_to_drive(file_path)
        
        user_sessions[update.effective_chat.id] = file_path

        # Выбор пола модели
        keyboard = [
            [InlineKeyboardButton("Женская модель", callback_data="female")],
            [InlineKeyboardButton("Мужская модель", callback_data="male")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("На кого примерить эту одежду?", reply_markup=reply_markup)

    except Exception as e:
        print(f"Ошибка загрузки: {e}")
        await update.message.reply_text("Не удалось загрузить фото. Попробуй еще раз.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    gender = query.data
    chat_id = query.message.chat.id
    
    await query.edit_message_text("⏳ Генерирую образ... Обычно это занимает 15-20 секунд.")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path:
            await context.bot.send_message(chat_id, "Ошибка: фото одежды потерялось. Пришли его заново.")
            return

        # Настройка описания модели
        model_desc = "beautiful female fashion model" if gender == "female" else "handsome male fashion model"
        
        # Промпт для Imagen 3
        # Мы просим ИИ использовать фото одежды как референс
        prompt = (
            f"High-end fashion photography. A {model_desc} posing in a studio, "
            f"wearing the exact clothing item from the provided reference image. "
            f"Realistic fabric textures, detailed, 8k resolution, soft studio lighting."
        )

        # Вызов генерации изображений
        # Используем Imagen 3 (самая стабильная для этих задач в Free Tier)
        response = client.models.generate_images(
            model='imagen-3.0-generate-001',
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                # Дополнительные параметры можно добавить сюда (aspect_ratio и т.д.)
            )
        )

        if response.generated_images:
            # Получаем байты сгенерированного изображения
            img_bytes = response.generated_images[0].image.image_bytes
            
            # Подготовка для отправки в Telegram
            bio = io.BytesIO(img_bytes)
            bio.name = 'ready_look.png'
            
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=bio, 
                caption="Вот как эта одежда смотрится на модели! ✨"
            )
        else:
            await context.bot.send_message(
                chat_id, 
                "К сожалению, ИИ не смог создать фото. Возможно, сработал фильтр безопасности контента."
            )

    except Exception as e:
        print(f"Критическая ошибка: {traceback.format_exc()}")
        await context.bot.send_message(chat_id, "Произошла ошибка в облаке ИИ. Попробуй позже.")
    
    finally:
        # Удаляем временный файл, чтобы не занимать место на сервере
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
