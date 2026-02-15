import os
import io
import traceback
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

client = genai.Client(api_key=GOOGLE_API_KEY)
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Пришли фото одежды, и я создам фото с моделью.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_path = f"garment_{update.effective_chat.id}.jpg"
        await file.download_to_drive(file_path)
        user_sessions[update.effective_chat.id] = file_path

        keyboard = [[InlineKeyboardButton("Женская модель", callback_data="female")],
                    [InlineKeyboardButton("Мужская модель", callback_data="male")]]
        await update.message.reply_text("Выбери пол модели:", reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text("Ошибка загрузки фото.")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    gender = query.data
    chat_id = query.message.chat.id
    await query.edit_message_text("⏳ Генерирую фото... Проверяю доступность модели.")

    try:
        garment_path = user_sessions.get(chat_id)
        if not garment_path:
            return

        model_type = "female fashion model" if gender == "female" else "male fashion model"
        prompt_text = f"Professional studio photography. A {model_type} wearing the clothing item from the reference photo. 8k, realistic."

        # Решение проблемы 404: Пробуем разные варианты имен моделей
        target_model = 'imagen-3.0-alpha-generate-001' # Смена на альфа-версию (чаще работает в 2026)
        
        try:
            response = client.models.generate_images(
                model=target_model,
                prompt=prompt_text,
                config={'number_of_images': 1, 'aspect_ratio': "3:4"}
            )
        except Exception as e:
            if "404" in str(e):
                # Если 404 — пробуем самый базовый вариант
                target_model = 'imagen-3.0-generate-001' 
                response = client.models.generate_images(
                    model=target_model,
                    prompt=prompt_text,
                    config={'number_of_images': 1}
                )
            else:
                raise e

        if response and response.generated_images:
            img_bytes = response.generated_images[0].image.image_bytes
            bio = io.BytesIO(img_bytes)
            bio.name = 'result.png'
            await context.bot.send_photo(chat_id=chat_id, photo=bio, caption="Готово! ✨")
        else:
            await context.bot.send_message(chat_id, "ИИ вернул пустой ответ.")

    except Exception as e:
        print(f"Критическая ошибка:\n{traceback.format_exc()}")
        # Мы НЕ выводим ошибку пользователю, но пишем в логи для нас
        await context.bot.send_message(chat_id, "Ошибка доступа к модели. Проверьте логи.")
    
    finally:
        if chat_id in user_sessions:
            if os.path.exists(user_sessions[chat_id]):
                os.remove(user_sessions[chat_id])
            del user_sessions[chat_id]

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(handle_choice))

if __name__ == "__main__":
    app.run_polling()
