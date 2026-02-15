import os
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from PIL import Image
import io

# ====== ПЕРЕМЕННЫЕ СРЕДЫ ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

genai.configure(api_key=GOOGLE_API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")

FEMALE_MODEL_PATH = "models/female.JPG"
MALE_MODEL_PATH = "models/male.JPG"

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь фото одежды (желательно на белом фоне).")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    gender = query.data
    chat_id = query.message.chat.id

    await query.edit_message_text("Генерирую изображение... Подожди 30–60 секунд.")

    garment_path = user_sessions.get(chat_id)

    model_path = FEMALE_MODEL_PATH if gender == "female" else MALE_MODEL_PATH

    garment_img = Image.open(garment_path)
    model_img = Image.open(model_path)

    prompt = """
    Dress the model in the provided clothing item.
    Make the clothing realistic, properly fitted, and natural.
    Maintain realistic lighting and shadows.
    """

    response = model.generate_content(
        [prompt, model_img, garment_img]
    )

    # Gemini возвращает изображение в response.parts
    for part in response.parts:
        if hasattr(part, "inline_data") and part.inline_data:
            image_bytes = part.inline_data.data
            await context.bot.send_photo(chat_id=chat_id, photo=image_bytes)
            return

    await context.bot.send_message(chat_id=chat_id, text="Не удалось сгенерировать изображение.")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(handle_choice))

app.run_polling()
