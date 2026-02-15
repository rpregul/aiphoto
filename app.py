import os
import io
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Конфиг
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот готов! Пришли фото одежды, и я примерю её на модель.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Просто сохраняем факт наличия фото (в MVP можно без сложной обработки)
    keyboard = [[InlineKeyboardButton("Женская модель", callback_data="female")],
                [InlineKeyboardButton("Мужская модель", callback_data="male")]]
    await update.message.reply_text("Выбери пол модели:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gender = "female" if query.data == "female" else "male"
    
    await query.edit_message_text("⏳ Генерирую фото... (Использую стабильный движок)")

    # Создаем промпт для генератора
    # Мы берем стабильный бесплатный сервис Pollinations.ai
    prompt = f"Professional high-fashion studio photo, {gender} fashion model wearing stylish outfit, 8k, photorealistic, cinematic lighting"
    
    # Кодируем промпт для URL
    encoded_prompt = prompt.replace(" ", "%20")
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"

    try:
        response = requests.get(image_url, timeout=30)
        if response.status_code == 200:
            await context.bot.send_photo(
                chat_id=query.message.chat.id, 
                photo=io.BytesIO(response.content), 
                caption=f"Готово! Модель: {gender}. ✨"
            )
        else:
            await query.message.reply_text("Ошибка сервиса генерации. Попробуй позже.")
    except Exception as e:
        await query.message.reply_text(f"Ошибка: {str(e)}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))
    
    print("Бот запущен на стабильном движке...")
    app.run_polling(drop_pending_updates=True)
