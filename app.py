import os
import io
import asyncio
import traceback
from PIL import Image
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Настройка
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Инициализация нового клиента Gemini
client = genai.Client(api_key=GOOGLE_API_KEY)

FEMALE_MODEL_PATH = "models/female.jpg"
MALE_MODEL_PATH = "models/male.jpg"

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пришли фото одежды, и я примерю её на модель!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_path = f"garment_{update.effective_chat.id}.jpg"
        await file.download_to_drive(photo_path)
        
        user_sessions[update.effective_chat.id] = photo_path

        keyboard = [[InlineKeyboardButton("Женская модель", callback_data="female")],
                    [InlineKeyboardButton("Мужская модель", callback_data="male")]]
        await update.message.reply_text("На кого надеваем?", reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text("Ошибка загрузки.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    gender = query.data
    chat_id = query.message.chat.id
    await query.edit_message_text("⏳ Генерирую... Пожалуйста, подождите.")

    try:
        garment_path = user_sessions.get(chat_id)
        model_type = "female fashion model" if gender == "female" else "male fashion model"
        
        # Загружаем фото одежды для анализа (через новый метод)
        raw_image = Image.open(garment_path)
        
        # Формируем запрос для Imagen 3 через новый SDK
        prompt = f"Professional studio photo of a {model_type} wearing the clothing from the reference image. High detail, realistic fabric."
        
        # Вызов генерации (в новом SDK это делается так)
        response = client.models.generate_images(
            model='imagen-3.0-generate-001',
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                include_rai_reasoning=True
            )
        )

        if response.generated_images:
            img_data = response.generated_images[0].image.image_bytes
            bio = io.BytesIO(img_data)
            bio.name = 'out.png'
            await context.bot.send_photo(chat_id=chat_id, photo=bio, caption="Готово!")
        else:
            await context.bot.send_message(chat_id, "Изображение не создано (возможно, фильтр контента).")

    except Exception as e:
        print(traceback.format_exc())
        await context.bot.send_message(chat_id, f"Ошибка: {str(e)}")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(handle_choice))

if __name__ == "__main__":
    app.run_polling()
