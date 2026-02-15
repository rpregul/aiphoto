import os
import replicate
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ВСТАВЬ СЮДА СВОИ КЛЮЧИ
TELEGRAM_TOKEN = "ТВОЙ_ТЕЛЕГРАМ_ТОКЕН"
REPLICATE_API_TOKEN = "ТВОЙ_REPLICATE_TOKEN"

os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Обрабатываю... подожди 20-40 секунд")

    photo = update.message.photo[-1]
    file = await photo.get_file()
    await file.download_to_drive("input.jpg")

    output = replicate.run(
        "cuuupid/idm-vton",
        input={
            "garm_img": open("input.jpg", "rb"),
            "model_type": "female"
        }
    )

    await update.message.reply_photo(photo=output)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

app.run_polling()
