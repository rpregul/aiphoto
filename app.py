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

# Инициализация клиента Gemini
client = genai.Client(api_key=GOOGLE_API_KEY)

# Временное хранилище путей к фото
user_sessions = {}

# 1. КОМАНДА ПРОВЕРКИ ДОСТУПНЫХ МОДЕЛЕЙ
async def check_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        models_list = client.models.list()
        # Собираем только те, что поддерживают генерацию контента
        available = [m.name for m in models_list if 'generateContent' in m.supported_methods]
        
        text = "✅ Доступные вам модели:\n\n" + "\n".join(available)
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при получении списка: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Пришли фото одежды для примерки.\n"
        "Используй /check, чтобы увидеть список доступных моделей ИИ."
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
        await update.message.reply_text("Выбери пол модели:", reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text("Ошибка при сохранении фото.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    
    await query.edit_message_text("⏳ Генерирую образ (Nano Banana)...")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path:
            return

        with open(garment_path, "rb") as f:
            image_bytes = f.read()

        gender = "female" if query.data == "female" else "male"
        prompt = f"Professional studio photography. A {gender} fashion model wearing the exact clothing from this reference image. 8k, realistic."

        # ИСПОЛЬЗУЕМ СТРУКТУРУ ИЗ GOOGLE AI STUDIO
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                types.Part.from_text(text=prompt)
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"]
            )
        )

        image_sent = False
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    img_io = io.BytesIO(part.inline_data.data)
                    img_io.name = 'result.png'
                    await context.bot.send_photo(chat_id=chat_id, photo=img_io, caption="Готово! ✨")
                    image_sent = True
                    break
        
        if not image_sent:
            await context.bot.send_message(chat_id, "ИИ не выдал изображение. Возможно, сработал фильтр контента.")

    except Exception as e:
        error_msg = str(e)
        print(f"Критическая ошибка:\n{traceback.format_exc()}")
        
        if "404" in error_msg:
            await context.bot.send_message(chat_id, "ОШИБКА 404: Модель не найдена. Напиши /check и пришли список мне.")
        elif "429" in error_msg:
            await context.bot.send_message(chat_id, "ОШИБКА 429: Лимит исчерпан. Подожди 1-2 минуты.")
        else:
            await context.bot.send_message(chat_id, f"Произошла ошибка: {error_msg[:100]}")
    
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

# --- ЗАПУСК БОТА ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_models))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))

    print("Бот запускается...")
    # drop_pending_updates=True помогает при ошибках Conflict (Повтор!)
    app.run_polling(drop_pending_updates=True)
