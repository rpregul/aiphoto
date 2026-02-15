import os
import traceback
from PIL import Image
from google import genai
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ====== ТОКЕНЫ ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# ====== GEMINI CLIENT ======
client = genai.Client(api_key=GOOGLE_API_KEY)

# ====== ПУТИ К МОДЕЛЯМ ======
FEMALE_MODEL_PATH = "models/female.jpg"
MALE_MODEL_PATH = "models/male.jpg"

# ====== ХРАНИЛИЩЕ СЕССИЙ ======
user_sessions = {}

# ====== START ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Отправь фото одежды, и я надену её на модель."
    )

# ====== ПОЛУЧАЕМ ФОТО ОДЕЖДЫ ======
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        garment_path = f"garment_{update.effective_chat.id}.jpg"
        await file.download_to_drive(garment_path)

        user_sessions[update.effective_chat.id] = garment_path

        # Отправляем фото моделей с кнопками
        keyboard_female = InlineKeyboardMarkup([
            [InlineKeyboardButton("Выбрать эту модель", callback_data="female")]
        ])

        keyboard_male = InlineKeyboardMarkup([
            [InlineKeyboardButton("Выбрать эту модель", callback_data="male")]
        ])

        await update.message.reply_photo(
            photo=open(FEMALE_MODEL_PATH, "rb"),
            caption="Женская модель",
            reply_markup=keyboard_female
        )

        await update.message.reply_photo(
            photo=open(MALE_MODEL_PATH, "rb"),
            caption="Мужская модель",
            reply_markup=keyboard_male
        )

    except Exception:
        await update.message.reply_text("Ошибка загрузки фото.")
        print(traceback.format_exc())

# ====== ВЫБОР МОДЕЛИ ======
async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    gender = query.data
    chat_id = query.message.chat.id

    await query.edit_message_caption("Генерирую изображение...")

    try:
        garment_path = user_sessions.get(chat_id)

        if not garment_path:
            await context.bot.send_message(chat_id, "Сначала отправьте фото одежды.")
            return

        model_path = FEMALE_MODEL_PATH if gender == "female" else MALE_MODEL_PATH

        garment_image = Image.open(garment_path)
        model_image = Image.open(model_path)

        prompt = """
        Put the clothing item from the first image onto the person in the second image.
        Keep the face and pose unchanged.
        The clothing must look realistic and properly fitted.
        Match lighting and shadows naturally.
        High realism fashion photography.
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[prompt, garment_image, model_image],
        )

        for part in response.parts:
            if part.inline_data is not None:
                image = part.as_image()
                result_path = f"result_{chat_id}.png"
                image.save(result_path)

                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=open(result_path, "rb")
                )
                return

        await context.bot.send_message(chat_id, "Модель не вернула изображение.")

    except Exception:
        await context.bot.send_message(chat_id, "Ошибка генерации.")
        print(traceback.format_exc())

# ====== ЗАПУСК ======
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(handle_choice))

app.run_polling()
