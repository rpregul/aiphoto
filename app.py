import os
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ТОЛЬКО ТОКЕН
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь фото одежды, и я попробую создать образ.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Уникальный номер, чтобы картинки не кешировались
    seed = int(time.time())
    
    # Твой идеальный промпт
    prompt = "Professional fashion photo, beautiful woman wearing stylish clothes, city park, sunlight, photorealistic, 8k"
    encoded_prompt = prompt.replace(" ", "%20")
    
    # Прямая ссылка на картинку
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1280&nologo=true&seed={seed}"

    try:
        # Мы не скачиваем картинку сами! Мы даем ссылку Телеграму, пусть он мучается с загрузкой
        await update.message.reply_photo(
            photo=image_url, 
            caption="Готово! Если картинка не та — попробуй еще раз (каждый раз будет новый вариант)."
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка Телеграма: {str(e)}")

if __name__ == "__main__":
    # Запуск с игнорированием старых сообщений
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("Бот запущен. Если видишь Conflict — убей старые процессы!")
    app.run_polling(drop_pending_updates=True)
