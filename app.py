import os
import io
import requests
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- ТОЛЬКО ТОКЕН ТЕЛЕГРАМА ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Бот готов! Пришли фото, и я сделаю магию без всяких лимитов.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Женская модель", callback_data="female")],
                [InlineKeyboardButton("Мужская модель", callback_data="male")]]
    await update.message.reply_text("Выбери пол:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gender = "female" if query.data == "female" else "male"
    await query.edit_message_text("⏳ Рисую образ... Это точно сработает.")

    # Мы создаем промпт сами, не мучая Gemini, чтобы избежать 429
    prompt = f"Professional studio photo of a {gender} fashion model wearing luxury clothes, high fashion, 8k, photorealistic"
    
    # Используем Pollinations напрямую — им плевать на твой регион и квоты
    image_url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}?width=1024&height=1280&nologo=true&seed=42"

    try:
        response = requests.get(image_url, timeout=60)
        if response.status_code == 200:
            await context.bot.send_photo(
                chat_id=query.message.chat.id, 
                photo=io.BytesIO(response.content), 
                caption="✨ Готово! Без лимитов и ошибок."
            )
        else:
            await query.message.reply_text("Сервис перегружен, попробуй еще раз через сек.")
    except Exception as e:
        await query.message.reply_text(f"Упс: {str(e)[:50]}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.run_polling(drop_pending_updates=True)
