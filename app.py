import os
import io
import requests
import traceback
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PROXY_URL = "aiphoto.plotnikov-csh.workers.dev" 

client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={'api_version': 'v1beta', 'base_url': f"https://{PROXY_URL}"}
)

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот запущен! Пришли фото одежды, и ИИ создаст образ на модели.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = f"garment_{update.effective_chat.id}.jpg"
    await file.download_to_drive(file_path)
    user_sessions[update.effective_chat.id] = file_path
    
    keyboard = [[InlineKeyboardButton("Женская модель", callback_data="female")],
                [InlineKeyboardButton("Мужская модель", callback_data="male")]]
    await update.message.reply_text("Выбери пол модели:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    gender = "female" if query.data == "female" else "male"
    
    await query.edit_message_text("⏳ Анализирую одежду и генерирую образ...")

    try:
        path = user_sessions.get(chat_id)
        if not path: return

        with open(path, "rb") as f:
            img_bytes = f.read()

        # 1. Gemini анализирует фото (это бесплатно и работает!)
        analysis_prompt = (
            f"Describe the clothing in this image in detail. "
            f"Then create a high-fashion photography prompt for a {gender} model wearing this exact clothing. "
            f"Return ONLY the prompt in English, no talk."
        )
        
        response = client.models.generate_content(
            model="gemini-2.0-flash", # Используем стабильную 2.0
            contents=[{"inline_data": {"data": img_bytes, "mime_type": "image/jpeg"}}, analysis_prompt]
        )
        
        ai_prompt = response.text if response.text else f"A {gender} model wearing stylish clothes"

        # 2. Генерируем саму картинку через бесплатный Pollinations
        image_gen_url = f"https://image.pollinations.ai/prompt/{ai_prompt.replace(' ', '%20')}?width=1024&height=1280&nologo=true"
        
        img_res = requests.get(image_gen_url)
        
        if img_res.status_code == 200:
            await context.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(img_res.content), caption="✨ Ваш образ готов!")
        else:
            await context.bot.send_message(chat_id, "Ошибка отрисовки. Попробуйте еще раз.")

    except Exception as e:
        print(traceback.format_exc())
        await context.bot.send_message(chat_id, f"Ошибка: {str(e)[:100]}")
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.run_polling(drop_pending_updates=True)
