import os
import io
import traceback
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Твой рабочий прокси
PROXY_URL = "aiphoto.plotnikov-csh.workers.dev" 

client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={'api_version': 'v1beta', 'base_url': f"https://{PROXY_URL}"}
)

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Пробуем Imagen 4.0 через прокси! Пришли фото одежды.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_path = f"garment_{update.effective_chat.id}.jpg"
        await file.download_to_drive(file_path)
        user_sessions[update.effective_chat.id] = file_path
        
        keyboard = [[InlineKeyboardButton("Женская модель", callback_data="female")],
                    [InlineKeyboardButton("Мужская модель", callback_data="male")]]
        await update.message.reply_text("Выбери пол:", reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text("Ошибка загрузки.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    await query.edit_message_text("⏳ Генерирую через Imagen 4.0 (спец. модель для фото)...")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path: return

        gender = "female" if query.data == "female" else "male"
        # Imagen 4.0 любит детальные промпты
        prompt_text = f"A professional high-fashion studio photo of a {gender} model wearing the clothing item from the reference. Photorealistic, 8k resolution, cinematic lighting."

        # ВАЖНО: Для моделей imagen используется метод generate_images
        response = client.models.generate_images(
            model='imagen-4.0-generate-001',
            prompt=prompt_text
        )

        if response and response.generated_images:
            img_bytes = response.generated_images[0].image.image_bytes
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=io.BytesIO(img_bytes), 
                caption="Готово! Imagen 4.0 на связи ✨"
            )
        else:
            await context.bot.send_message(chat_id, "ИИ не смог создать картинку. Возможно, сработал фильтр безопасности.")

    except Exception as e:
        print(traceback.format_exc())
        err_msg = str(e)
        if "400" in err_msg:
            await context.bot.send_message(chat_id, "Ошибка 400: Возможно, Imagen 4.0 всё еще требует Billing даже через прокси.")
        elif "429" in err_msg:
            await context.bot.send_message(chat_id, "Лимит исчерпан. Подожди 1-2 минуты.")
        else:
            await context.bot.send_message(chat_id, f"Ошибка: {err_msg[:100]}")
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.run_polling(drop_pending_updates=True)
