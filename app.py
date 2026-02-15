import os
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from PIL import Image
import traceback

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

FEMALE_MODEL_PATH = "models/female.jpg"
MALE_MODEL_PATH = "models/male.jpg"

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь фото одежды.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        await file.download_to_drive("garment.jpg")

        user_sessions[update.effective_chat.id] = "garment.jpg"

        keyboard = [
            [InlineKeyboardButton("Женская модель", callback_data="female")],
            [InlineKeyboardButton("Мужская модель", callback_data="male")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выбери модель:", reply_markup=reply_markup)

    except Exception as e:
        await update.message.reply_text("Ошибка при загрузке фото.")
        print(traceback.format_exc())

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    gender = query.data
    chat_id = query.message.chat.id

    await query.edit_message_text("Генерирую изображение...")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path:
            await context.bot.send_message(chat_id, "Сначала отправь фото одежды.")
            return

        model_path = FEMALE_MODEL_PATH if gender == "female" else MALE_MODEL_PATH

        if not os.path.exists(model_path):
            await context.bot.send_message(chat_id, "Файл модели не найден.")
            return

        garment_img = Image.open(garment_path)
        model_img = Image.open(model_path)

        prompt = """
        Dress the model in the provided clothing item.
        Keep the face and pose unchanged.
        Make it realistic with proper shadows and lighting.
        """

        response = model.generate_content(
            [prompt, model_img, garment_img]
        )

        image_sent = False

        for part in response.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                await context.bot.send_photo(chat_id=chat_id, photo=part.inline_data.data)
                image_sent = True
                break

        if not image_sent:
            await context.bot.send_message(chat_id, "Gemini не вернул изображение.")

    except Exception as e:
        await context.bot.send_message(chat_id, "Ошибка генерации.")
        print(traceback.format_exc())

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(handle_choice))

app.run_polling()
