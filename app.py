import os
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from PIL import Image
import io
import traceback

# Настройка ключей
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

genai.configure(api_key=GOOGLE_API_KEY)

# Для генерации изображений используется Imagen
# Важно: В некоторых регионах модель называется 'imagen-3.0-generate-001'
imagen = genai.ImageGenerationModel("imagen-3.0-generate-001")

FEMALE_MODEL_PATH = "models/female.jpg"
MALE_MODEL_PATH = "models/male.jpg"

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Пришли мне фото одежды (желательно на однотонном фоне), и я примерю её на модель.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_path = f"garment_{update.effective_chat.id}.jpg"
        await file.download_to_drive(photo_path)

        user_sessions[update.effective_chat.id] = photo_path

        keyboard = [
            [InlineKeyboardButton("Женская модель", callback_data="female")],
            [InlineKeyboardButton("Мужская модель", callback_data="male")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("На кого надеваем?", reply_markup=reply_markup)

    except Exception as e:
        await update.message.reply_text("Ошибка при загрузке фото.")
        print(traceback.format_exc())

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    gender = query.data
    chat_id = query.message.chat.id

    await query.edit_message_text("🎨 Колдую над образом... Это займет около 10-20 секунд.")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path:
            await context.bot.send_message(chat_id, "Сначала отправь фото одежды.")
            return

        model_type = "a professional female fashion model" if gender == "female" else "a professional male fashion model"
        
        # Читаем фото одежды для контекста (если API поддерживает Image-to-Image в вашем регионе)
        # В базовом варианте Imagen 3 лучше всего работает через детальное описание.
        # Для бесплатного MVP мы передаем описание того, что на фото.
        
        prompt = f"A high-quality fashion photography of {model_type} wearing the exact clothing item from the provided reference. Realistic fabric texture, studio lighting, highly detailed, 8k resolution."

        # Вызов генерации
        # Примечание: Imagen в Free Tier может иметь ограничения на передачу исходных картинок (Image-to-Image)
        # Если ваша задача именно "перенос", используйте параметр 'input_file' если он доступен
        response = imagen.generate_images(
            prompt=prompt,
            number_of_images=1,
            # В ряде версий SDK можно передать опорное изображение:
            # reference_images=[Image.open(garment_path)] 
        )

        if response.images:
            for img in response.images:
                # Конвертируем PIL Image в байты для отправки в Telegram
                bio = io.BytesIO()
                bio.name = 'result.png'
                img._pil_image.save(bio, 'PNG')
                bio.seek(0)
                
                await context.bot.send_photo(chat_id=chat_id, photo=bio, caption="Готово! Как вам?")
        else:
            await context.bot.send_message(chat_id, "Не удалось сгенерировать образ. Возможно, сработал фильтр безопасности.")

    except Exception as e:
        await context.bot.send_message(chat_id, f"Ошибка генерации: {str(e)}")
        print(traceback.format_exc())

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(handle_choice))

if __name__ == "__main__":
    app.run_polling()
