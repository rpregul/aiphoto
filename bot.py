import os
import io
import base64
import requests
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, CallbackQueryHandler, filters

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Модели
ANALYSIS_MODEL = "google/gemma-3-12b-it:free"
DRAW_MODEL = "blackforest/flux.2-pro"

# Состояние пользователя
user_bouquet_state = {}

# --- Анализ фото ---
async def analyze_bouquet(photo_bytes: bytes):
    image = Image.open(io.BytesIO(photo_bytes))
    image.thumbnail((1024, 1024))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    img_base64 = base64.b64encode(buf.getvalue()).decode()

    prompt = (
        "Ты - профессиональный флорист-аналитик. Проанализируй фото букета и дай коротко несколько ответов по фотографии.\n"
        "Ты НЕ ведешь диалог. ты НЕ используешь приветствие. Ты НЕ обращаешься к пользователю. ты НЕ задаешь вопросов, НЕ используешь слова (возможно) (надеюсь). Ты отвечаешь строго по шаблону:\n"
        "ЦВЕТЫ:\n"
        "Тип: (твой ответ)\n"
        "Вероятный сорт: (твой ответ)\n"
        "Цвет: (твой ответ)\n"
        "Количество: (твой ответ, сколько бутонов каждого типа + перенос через 1 строку)\n"
        "ЗЕЛЕНЬ: (этот пункт только если в букете есть зелень, а она несть не всегда, иначе вообще не пиши строчки про зелень)\n"
        "Вид: (твой ответ)\n"
        "Сорт: (твой ответ)\n"
        "Цвет: (твой ответ + перенос через 1 строку)\n"
        "УПАКОВКА: (из упаковки считывай ТОЛЬКО упаковочную бумагу, в которую обернут букет, и ленту, которой он  перевязан. Ничего другого в виде надписей и открыток или еще чего-то, считывать не нужно)\n"
        "Цвет: (твой ответ + материал/ фаткруа, например матовая или прозрачная; или пишешь, что ее нет)\n"
        "Лента: (твой ответ, если видишь ее + перенос через 1 строку)\n"
        "КОММЕНТАРИЙ:\n"
        "(как профессиональный флорист ты проанализировал букет и пишешь краткое его описание и настроение):\n"
        "Используй эмодзи, делай текст лёгким, доброжелательным, ты милая девушка флорист. Важно использовать форматирование, как я тебе описал выше, чтобы текст легко читался и воспринимался.\n"
        "Когда будешь писать свой анализ, помни, что ты профессиональный флорист и фильтруй и осознавай, что ты пишешь, чтобы не написать какой-нибудь бред, проверяй сам себя, верность твоего ответа очень важна."
        "Помни, что в плотных пышных букетах иногда видно не все количество цветов, если он сфотографирвован под углом. Если понимаешь, что букет плотный и пышный и сфотографирован под углом, умножь видимое число цветков процентов на 30\n"
        "Так же помни: принято, чтобы в букетах суммарно было нечетное количество цветков (зелень если есть, считается отдельно):\n"
    )

    payload = {
        "model": ANALYSIS_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                ]
            }
        ]
    }

    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=90)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]

# --- Генерация изображения ---
async def generate_bouquet_image(bouquet_text: str):
    # Для Flux 2 Pro делаем тот же чат-запрос, но текст только про генерацию картинки
    prompt = f"🎨 Сгенерируй реалистичное изображение букета по составу:\n{bouquet_text}"
    payload = {
        "model": DRAW_MODEL,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    }
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()

    content = data["choices"][0]["message"]["content"]
    if "data:image" in content:
        header, img_base64 = content.split(",", 1)
        img_bytes = base64.b64decode(img_base64)
        return io.BytesIO(img_bytes)
    else:
        # Если модель вернула текст вместо картинки, создаём пустое изображение
        img = Image.new("RGB", (512, 512), color=(255, 255, 255))
        return img

# --- Обработка фото ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("🔍 Анализирую фото и подбираю цветы…")
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()

        text = await analyze_bouquet(photo_bytes)
        user_bouquet_state[update.message.from_user.id] = text

        keyboard = [
            [InlineKeyboardButton("💐 Сделать букет меньше ~20%", callback_data="smaller")],
            [InlineKeyboardButton("💐 Собрать пышнее и больше ~20%", callback_data="bigger")],
            [InlineKeyboardButton("🎨 Нарисовать примерный букет", callback_data="draw")],
            [InlineKeyboardButton("🛒 Оформить заказ", callback_data="order")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"{text}", reply_markup=reply_markup)

    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

# --- Обработка кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    current_bouquet = user_bouquet_state.get(user_id, "")

    try:
        if query.data in ["smaller", "bigger"]:
            if query.data == "smaller":
                msg = "🔽 Собираю для вас чуть меньший букет (~20%), сохраняя его стиль и концепцию 🌸"
                instruction = "уменьши букет на ~20%, сохрани концепцию и изюминку"
            else:
                msg = "🔼 Собираю для вас более пышный букет (~20%), сохраняя его стиль и концепцию 🌸"
                instruction = "увеличь букет на ~20%, сохрани концепцию и изюминку"

            await query.edit_message_text(msg)

            prompt = f"Коротко и понятно пересоставь букет, {instruction}:\n{current_bouquet}"
            payload = {
                "model": ANALYSIS_MODEL,
                "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
            }
            headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
            response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            data = response.json()
            new_bouquet = data["choices"][0]["message"]["content"]
            user_bouquet_state[user_id] = new_bouquet

            keyboard = [
                [InlineKeyboardButton("🎨 Нарисовать примерный букет", callback_data="draw")],
                [InlineKeyboardButton("🛒 Оформить заказ", callback_data="order")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(f"{new_bouquet}", reply_markup=reply_markup)

        elif query.data == "draw":
            await query.edit_message_text("🎨 Рисую ваш букет…")
            img_io = await generate_bouquet_image(current_bouquet)
            if isinstance(img_io, io.BytesIO):
                await query.message.reply_photo(photo=InputFile(img_io, filename="bouquet.png"))
            else:
                await query.message.reply_text("Не удалось сгенерировать картинку, попробуйте позже.")

            keyboard = [[InlineKeyboardButton("🛒 Отправить флористу и внести предоплату", callback_data="order")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Что делать дальше?", reply_markup=reply_markup)

        elif query.data == "order":
            await query.edit_message_text("✅ Заказ оформлен! Передала ваш букет на сборку флористам в магазин, они начнут собирать его после предоплаты ❤️")

    except Exception as e:
        await query.message.reply_text(f"Ошибка при обработке кнопки: {str(e)}")

# --- Обработка текста ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Пришлите фото желаемого букета")

# --- Запуск бота ---
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT, handle_text))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
