import os
import io
import time
import requests
import traceback
from google import genai
from google.genai import types
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

# Список моделей из твоего лога (приоритетный порядок)
MEGA_CAROUSEL = [
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-exp-1206",
    "gemma-3-27b-it",
    "gemma-3-12b-it",
    "gemini-1.5-flash-latest" # На случай если старые еще живы
]

user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎯 Мега-карусель активирована! Использую все доступные модели Google. Пришли фото.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = f"garment_{update.effective_chat.id}.jpg"
    await file.download_to_drive(file_path)
    user_sessions[update.effective_chat.id] = file_path
    
    keyboard = [[InlineKeyboardButton("Женская модель", callback_data="female")],
                [InlineKeyboardButton("Мужская модель", callback_data="male")]]
    await update.message.reply_text("Выбери пол:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    gender = "female" if query.data == "female" else "male"
    
    await query.edit_message_text("🔄 Прочесываю все доступные модели Google...")

    garment_path = user_sessions.get(chat_id)
    if not garment_path: return

    with open(garment_path, "rb") as f:
        image_bytes = f.read()

    ai_prompt = None
    success_model = None
    errors_log = []

    # ЦИКЛ ПО ВСЕМ МОДЕЛЯМ
    for model_name in MEGA_CAROUSEL:
        # Пробуем два варианта написания: с префиксом и без
        for final_name in [model_name, f"models/{model_name}"]:
            try:
                print(f"Попытка: {final_name}...")
                response = client.models.generate_content(
                    model=final_name,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        f"Detailed fashion description. Create a prompt for {gender} model wearing this. Result: English only."
                    ]
                )
                if response.text:
                    ai_prompt = response.text
                    success_model = final_name
                    break
            except Exception as e:
                err_msg = str(e)
                print(f"❌ {final_name} ошибка: {err_msg[:50]}")
                errors_log.append(f"{final_name}: {err_msg[:30]}")
                if "429" in err_msg:
                    time.sleep(1.5) # Маленькая пауза при лимите
                continue
        if ai_prompt: break

    if not ai_prompt:
        error_summary = "\n".join(errors_log[-3:]) # Показать последние 3 ошибки
        await query.message.reply_text(f"Все модели в списке отказали или перегружены.\n\nПоследние ошибки:\n{error_summary}")
        return

    # ОТРИСОВКА ЧЕРЕЗ POLLINATIONS
    try:
        clean_prompt = ai_prompt.strip().replace("\n", " ")
        image_url = f"https://image.pollinations.ai/prompt/{clean_prompt.replace(' ', '%20')}?width=1024&height=1280&nologo=true&seed={int(time.time())}"
        
        img_res = requests.get(image_url, timeout=30)
        if img_res.status_code == 200:
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=io.BytesIO(img_res.content), 
                caption=f"✨ Готово!\nМодель: {success_model}"
            )
        else:
            await query.message.reply_text(f"Описание создано ({success_model}), но сервис отрисовки временно недоступен.")
    except Exception as e:
        await query.message.reply_text(f"Ошибка финальной стадии: {str(e)[:50]}")
    finally:
        if chat_id in user_sessions and os.path.exists(user_sessions[chat_id]):
            os.remove(user_sessions[chat_id])

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_choice))
    print("Бот Мега-Карусель запущен...")
    app.run_polling(drop_pending_updates=True)
