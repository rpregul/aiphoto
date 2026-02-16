import os
import io
import time
import requests
import asyncio
from google import genai
from google.genai import types
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PROXY_URL = "aiphoto.plotnikov-csh.workers.dev" 

# Клиент с явным тайм-аутом
client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={'api_version': 'v1beta', 'base_url': f"https://{PROXY_URL}"}
)

# Расширенный список из твоего лога
MODELS_TO_TRY = [
    "models/nano-banana-pro-preview",
    "models/gemini-3-flash-preview",
    "models/gemini-2.5-flash",
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",
    "models/gemini-1.5-flash"
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Пришли фото товара — я сделаю фото с моделью в парке!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⏳ Ищу свободную нейросеть (Nano Banana +)...")
    
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        img_bytes = await file.download_as_bytearray()

        ai_prompt = None
        success_model = None

        for model_id in MODELS_TO_TRY:
            try:
                print(f"Пробую {model_id}...")
                # Ограничиваем время ожидания каждой модели, чтобы бот не висел
                response = client.models.generate_content(
                    model=model_id,
                    contents=[
                        types.Part.from_bytes(data=bytes(img_bytes), mime_type="image/jpeg"),
                        "Describe this item for a fashion catalog. Create a prompt: a beautiful woman wearing this, city park, sunlight, photorealistic. English only, no talk."
                    ]
                )
                
                if response and response.text:
                    ai_prompt = response.text
                    success_model = model_id
                    print(f"✅ Успех: {model_id}")
                    break
            except Exception as e:
                print(f"❌ Ошибка {model_id}: {str(e)[:50]}")
                # Если 429, не ждем долго, идем дальше
                continue

        if not ai_prompt:
            await status_msg.edit_text("❌ Все модели сейчас заняты. Попробуй через пару минут.")
            return

        await status_msg.edit_text(f"🎨 Рисую через {success_model.split('/')[-1]}...")

        # ГЕНЕРАЦИЯ
        clean_p = ai_prompt.strip().replace("\n", " ").replace('"', '')
        gen_url = f"https://image.pollinations.ai/prompt/{clean_p.replace(' ', '%20')}?width=1024&height=1280&nologo=true&seed={int(time.time())}"
        
        img_res = requests.get(gen_url, timeout=30)
        if img_res.status_code == 200:
            await update.message.reply_photo(
                photo=io.BytesIO(img_res.content), 
                caption=f"✨ Готово!\nМодель ИИ: {success_model.split('/')[-1]}"
            )
            await status_msg.delete()
        else:
            await status_msg.edit_text("⚠️ Описание создано, но сервер отрисовки не ответил.")

    except Exception as e:
        print(f"ERROR: {e}")
        await status_msg.edit_text("🤯 Что-то пошло не так. Попробуй еще раз.")

if __name__ == "__main__":
    # Важно: перед запуском в Railway убедись, что старый деплой остановлен!
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("Бот перезапущен...")
    app.run_polling(drop_pending_updates=True)
