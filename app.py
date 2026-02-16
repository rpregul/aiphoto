import os
import io
import time
import requests
from google import genai
from google.genai import types
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PROXY_URL = "aiphoto.plotnikov-csh.workers.dev" 

client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options={'api_version': 'v1beta', 'base_url': f"https://{PROXY_URL}"}
)

# Приоритет на Nano Banana и Gemini 3
MODELS_TO_TRY = [
    "models/nano-banana-pro-preview",
    "models/gemini-3-flash-preview",
    "models/gemini-2.5-flash",
    "models/gemini-2.0-flash"
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Пришли фото товара, и я создам каталожное фото модели в городском парке!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⏳ Анализирую товар через Nano Banana...")
    
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        img_stream = io.BytesIO()
        await file.download_to_memory(img_stream)
        img_bytes = img_stream.getvalue()

        ai_prompt = None
        success_model = None

        # КАРУСЕЛЬ
        for model_id in MODELS_TO_TRY:
            try:
                print(f"Запрос к {model_id}...")
                # Инструкция для создания каталожного фото
                prompt_task = (
                    "Analyze this clothing item. Create a professional fashion photography prompt. "
                    "The scene: a beautiful young woman wearing this item, standing in a sunny city park, "
                    "soft bokeh background, high-end catalog style, 8k resolution. Return ONLY the English prompt."
                )

                response = client.models.generate_content(
                    model=model_id,
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                        prompt_task
                    ]
                )
                
                if response.text:
                    ai_prompt = response.text
                    success_model = model_id
                    break
            except Exception as e:
                print(f"❌ {model_id} ошибка: {str(e)[:50]}")
                continue

        if not ai_prompt:
            await status_msg.edit_text("❌ Все модели (включая Nano Banana) сейчас перегружены. Попробуй через пару минут.")
            return

        await status_msg.edit_text(f"🎨 Генерирую финальный кадр (модель: {success_model.split('/')[-1]})...")

        # ОТРИСОВКА
        clean_prompt = ai_prompt.strip().replace("\n", " ").replace('"', '')
        image_url = f"https://image.pollinations.ai/prompt/{clean_prompt.replace(' ', '%20')}?width=1024&height=1280&nologo=true&seed={int(time.time())}"
        
        img_res = requests.get(image_url, timeout=30)
        
        if img_res.status_code == 200:
            await update.message.reply_photo(
                photo=io.BytesIO(img_res.content), 
                caption=f"✅ Каталожное фото готово!\nДвижок: {success_model.split('/')[-1]}"
            )
            await status_msg.delete()
        else:
            await status_msg.edit_text("😕 Описание готово, но генератор картинок временно занят.")

    except Exception as e:
        print(f"Критическая ошибка: {e}")
        await update.message.reply_text("Произошла ошибка при обработке. Попробуй другое фото.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("Бот 'Nano Catalog' запущен...")
    app.run_polling(drop_pending_updates=True)
