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

# Твой рабочий прокси из Cloudflare
PROXY_URL = "aiphoto.plotnikov-csh.workers.dev" 

# Инициализация клиента с проксированием
client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={'api_version': 'v1beta', 'base_url': f"https://{PROXY_URL}"}
)

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Бот готов к работе через прокси!\n\n"
        "1. Пришли фото одежды.\n"
        "2. Выбери пол модели.\n"
        "3. Получи готовый образ."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_path = f"garment_{update.effective_chat.id}.jpg"
        await file.download_to_drive(file_path)
        user_sessions[update.effective_chat.id] = file_path

        keyboard = [[InlineKeyboardButton("Женская модель", callback_data="female")],
                    [InlineKeyboardButton("Мужская модель", callback_data="male")]]
        await update.message.reply_text("Выбери пол модели для примерки:", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        print(f"Ошибка загрузки фото: {e}")
        await update.message.reply_text("Не удалось загрузить фото. Попробуй еще раз.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    
    await query.edit_message_text("⏳ Генерирую изображение... Это может занять до 30 секунд.")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path:
            await query.message.reply_text("Сначала пришли фото!")
            return

        with open(garment_path, "rb") as f:
            image_bytes = f.read()

        gender = "female" if query.data == "female" else "male"
        # Четкий промпт без лишних слов
        prompt = f"A professional high-fashion studio photography of a {gender} model wearing the exact clothing from this reference image. Photorealistic, 8k."

        # Запрос к модели gemini-2.5-flash-image
        # response_modalities=["IMAGE"] — заставляет модель выдавать только картинку
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                types.Part.from_text(text=prompt),
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            )
        )

        image_data = None
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_data = part.inline_data.data
                    break
        
        if image_data:
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=io.BytesIO(image_data), 
                caption="Ваш стильный образ готов! ✨"
            )
        else:
            # Если картинки нет, проверяем, не пришел ли текст по ошибке
            text_resp = response.candidates[0].content.parts[0].text if response.candidates else "Пустой ответ"
            await context.bot.send_message(chat_id, f"ИИ не выдал картинку. Ответ системы: {text_resp[:100]}")

    except Exception as e:
        error_log = traceback.format_exc()
        print(f"Критическая ошибка:\n{error_log}")
        
        err_str = str(e)
        if "429" in err_str:
            await context.bot.send_message(chat_id, "Ошибка: Слишком много запросов. Подождите минуту.")
        else:
            await context.bot.send_message(chat_id, f"Произошла ошибка API: {err_str[:100]}")
    
    finally:
        # Чистим временные файлы
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

# --- ЗАПУСК БОТА ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))

    print("Бот успешно запущен и готов к работе...")
    # drop_pending_updates=True помогает избежать Conflict при перезапуске
    app.run_polling(drop_pending_updates=True)
