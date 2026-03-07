import os
import time
import asyncio
import sqlite3
import requests

# 1. Библиотеки Google (Новый SDK для Veo и Gemini)
from google import genai
from google.genai import types as g_types
from aiogram.types import FSInputFile

# 2. Библиотека Telegram (aiogram)
from aiogram import Bot, Dispatcher, types, F
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command

# --- НАСТРОЙКИ ---
# Если используешь Vertex AI через JSON, оставь это. 
# Если только прямой Gemini API Key — эту строку можно удалить.
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "test-2nd-prjct-889205dda2af.json"
os.environ["PYTHONUTF8"] = "1"

AMPLITUDE_API_KEY = "89c822d5fd2e7e775b178494786ecc36" 
TG_TOKEN = '8653895075:AAFa-k-Nh4YeU80w7eJCsPjHCjYcdHlsjS8'
GEMINI_API_KEY = "AIzaSyCYUr78S7g4RLKHQ7IQla1QMASi_i3YeCo"
ADMIN_IDS = [5317755790, 91140569]
FREE_START = 3

# Инициализация клиентов (делаем один раз)
# Если используешь Google Cloud Project, добавь vertexai=True сюда
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={"api_version": "v1beta"}
)
bot = Bot(token=TG_TOKEN)
dp = Dispatcher()

def log_event(user_id, event_type, properties=None):
    url = "https://api.eu.amplitude.com/2/httpapi"
    payload = {
        "api_key": AMPLITUDE_API_KEY,
        "events": [{
            "user_id": str(user_id),
            "event_type": event_type,
            "event_properties": properties or {},
            "platform": "Telegram Bot",
            "os_name": "Linux Server"
        }]
    }
    try:
        r = requests.post(url, json=payload, timeout=5)
        if r.status_code != 200:
            print(f"Amplitude Error: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Amplitude Network Error: {e}")

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                    (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 3, 
                    total_spent INTEGER DEFAULT 0, buy_count INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    res = cur.fetchone()
    if not res:
        cur.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, FREE_START))
        conn.commit()
        res = (FREE_START,)
    conn.close()
    return res[0]

def update_balance_db(user_id, amount, money=0):
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    if money > 0:
        cur.execute("UPDATE users SET balance = balance + ?, total_spent = total_spent + ?, buy_count = buy_count + 1 WHERE user_id = ?", 
                    (amount, money, user_id))
    else:
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# --- СОСТОЯНИЯ ---
class BotStates(StatesGroup):
    wait_free_photo = State()   
    wait_free_prompt = State()  
    wait_interior_photo = State() 
    wait_interior_scene = State() 
    wait_ref_product = State()
    wait_ref_example = State()
    wait_ref_comment = State()
    wait_info_source = State()
    wait_info_product = State()
    wait_info_details = State()
    wait_info_prompt = State()
    wait_bg_photo = State()      # Ждем фото для удаления фона
    wait_custom_bg = State()     # Ждем описание цвета фона от юзера
    wait_video_photo = State()    # Ждем фото для видео
    wait_video_comment = State()  # Ждем комментарий к видео

# --- КЛАВИАТУРЫ ---
def get_main_inline_kb(user_id):
    balance = get_user_data(user_id)
    builder = InlineKeyboardBuilder()
    builder.button(text=f"💰 Купить генерации (Баланс: {balance})", callback_data="open_buy")
    builder.button(text="📸 Предметная съемка", callback_data="open_shooting")
    builder.button(text="📊 Инфографика", callback_data="open_infographics")
    builder.button(text="💃 Съемка на модели", callback_data="dev_status")
    builder.button(text="🎬 Видео и обложки", callback_data="dev_status")
    builder.button(text="🐞 Нашли ошибку? Подарим бесплатные генерации", callback_data="error_report")
    builder.button(text="🎬 Видеообложки для МП", callback_data="mode_video_cover")
    builder.adjust(1)
    return builder.as_markup()

def get_bg_selection_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="⚪️ Чисто белый", callback_data="bg_pure_white")
    builder.button(text="☁️ Белый с легкой тенью", callback_data="bg_shadow")
    builder.button(text="🔘 Серый градиент (циклорама)", callback_data="bg_gradient")
    builder.button(text="🎨 Свой цвет/фон", callback_data="bg_custom")
    builder.button(text="⬅️ Назад", callback_data="open_shooting")
    builder.adjust(1)
    return builder.as_markup()

def get_shooting_inline_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✂️ Удалить фон", callback_data="mode_remove_bg")
    builder.button(text="🏠 Расположить в сцене", callback_data="open_scene_menu")
    builder.button(text="✍️ Свободный промпт", callback_data="mode_free_prompt")
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_scene_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🖼 Вписать ваш товар в фотографию (референс)", callback_data="mode_ref_start")
    builder.button(text="💡 Банк с идеями", callback_data="mode_ideas_bank")
    builder.button(text="📝 Описать сцену самостоятельно", callback_data="mode_interior")
    builder.button(text="⬅️ Назад", callback_data="open_shooting")
    builder.adjust(1)
    return builder.as_markup()

def get_info_main_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✂️ Раздел 'Удалить фон'", callback_data="mode_remove_bg")
    builder.button(text="🥈 По инфографике конкурента", callback_data="info_mode_competitor")
    builder.button(text="🖼 На основе примера", callback_data="info_mode_example")
    builder.button(text="🤖 Дизайн от нейросети", callback_data="info_mode_ai")
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_tariffs_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="10 генераций — 590₽", callback_data="buy_10_590")
    builder.button(text="30 генераций — 1290₽", callback_data="buy_30_1290")
    builder.button(text="100 генераций — 3490₽ 🔥 ХИТ", callback_data="buy_100_3490")
    builder.button(text="300 генераций — 9000₽", callback_data="buy_300_9000")
    builder.button(text="500 генераций — 14500₽", callback_data="buy_500_14500")
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_repeat_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Повторить генерацию (-1 💎)", callback_data="repeat_gen")
    builder.button(text="⬅️ В главное меню", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

# --- ОБРАБОТЧИКИ ---
@dp.message(F.text == "/start")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    init_db()
    u_id = message.from_user.id
    balance = get_user_data(u_id)
    
    # Отправка события в Amplitude (EU)
    try:
        requests.post(
            "https://api.eu.amplitude.com/2/httpapi",
            json={
                "api_key": AMPLITUDE_API_KEY,
                "events": [{
                    "user_id": str(u_id),
                    "event_type": "Start Bot",
                    "event_properties": {"balance": balance, "username": message.from_user.username},
                    "platform": "Telegram Bot"
                }]
            },
            timeout=5
        )
    except Exception as e:
        print(f"Amplitude error: {e}")

    await message.answer(f"Баланс: **{balance}** генераций\n\nВыберите задачу:", 
                         reply_markup=get_main_inline_kb(u_id), parse_mode="Markdown")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    u_id = message.chat.id
    balance = get_user_data(u_id)
    
    # Красивое оформление статистики
    text = (
        "📊 *Ваша статистика*\n\n"
        f"👤 ID: `{u_id}`\n"
        f"💎 Баланс: *{balance}* генераций\n\n"
        "💡 _1 видео = 10 генераций_"
    )
    
    await message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    balance = get_user_data(callback.from_user.id)
    try:
        await callback.message.edit_text(f"Баланс: **{balance}** генераций\n\nВыберите задачу:", 
                                         reply_markup=get_main_inline_kb(callback.from_user.id), parse_mode="Markdown")
    except TelegramBadRequest: pass

@dp.callback_query(F.data == "error_report")
async def error_report(callback: types.CallbackQuery):
    await callback.message.answer("Если вы нашли ошибку в работе бота и в каком-то меню он не выполняет свою задачу, напишите автору бота @akookoo и мы начислим вам 5 бесплатных генераций фото. Мы стремимся улучшать качество и удобство нашего бота, поэтому нам очень ценна ваша обратная связь.")
    await callback.answer()

@dp.callback_query(F.data == "open_shooting")
async def open_shooting(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("Раздел предметной съемки. Что нужно сделать?", reply_markup=get_shooting_inline_kb())
    except TelegramBadRequest: pass

@dp.callback_query(F.data == "open_scene_menu")
async def open_scene_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    text = ("💡 <b>Подсказка:</b> Для более высокого качества генерации загружайте изображение вашего товара <b>белом фоне в хорошем качестве, с ровными бликами и перспективой</b>. "
            "\n\n⚡️ Если его нет, вернитесь назад и обработайте в <b>предыдущем разделе \"Удалить фон\"</b>.")
    try:
        await callback.message.edit_text(text, reply_markup=get_scene_menu_kb(), parse_mode="HTML")
    except TelegramBadRequest: pass

@dp.callback_query(F.data == "open_infographics")
async def open_infographics(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    # ЛОГИРУЕМ КЛИК
    log_event(callback.from_user.id, "Click Button", {"button_name": "open_infographics"})
    text = ("Подсказка: Для более высокого качества генерации воспользуйтесь исходным изображением с товаром на белом фоне в хорошем качестве. "
            "Если его нет, вернитесь назад и воспользуйтесь разделом \"Предметная съемка товаров\" –> \"Удалить фон\".\n\n"
            "Как вам удобнее создать инфографику?")
    try:
        await callback.message.edit_text(text, reply_markup=get_info_main_kb())
    except TelegramBadRequest: pass

@dp.callback_query(F.data.startswith("info_mode_"))
async def info_mode_select(callback: types.CallbackQuery, state: FSMContext):
    mode = callback.data.split("_")[-1]
    await state.update_data(info_mode=mode, details=[])
    
    if mode == "competitor":
        await callback.message.answer("Пришлите инфографику конкурента, которую мы повторим визуально.")
        await state.set_state(BotStates.wait_info_source)
    elif mode == "example":
        await callback.message.answer("Пришлите инфографику, которую мы возьмем в качестве примера.")
        await state.set_state(BotStates.wait_info_source)
    else:
        await callback.message.answer("Пришлите фото вашего товара.")
        await state.set_state(BotStates.wait_info_product)
    await callback.answer()

@dp.message(BotStates.wait_info_source, F.photo)
async def process_info_source(message: types.Message, state: FSMContext):
    await state.update_data(source_photo=message.photo[-1].file_id)
    await message.answer("Пришлите фото вашего товара.")
    await state.set_state(BotStates.wait_info_product)

@dp.message(BotStates.wait_info_product, F.photo)
async def process_info_product(message: types.Message, state: FSMContext):
    await state.update_data(product_photo=message.photo[-1].file_id)
    builder = InlineKeyboardBuilder()
    builder.button(text="Далее ➡️", callback_data="info_details_done")
    await message.answer("Если необходимо, пришлите до 4х дополнительных фотографий деталей товара, которые нужно использовать в инфографике. Иначе нажмите кнопку Далее", reply_markup=builder.as_markup())
    await state.set_state(BotStates.wait_info_details)

@dp.message(BotStates.wait_info_details, F.photo)
async def process_info_details_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    details = data.get('details', [])
    if len(details) < 4:
        details.append(message.photo[-1].file_id)
        await state.update_data(details=details)
        await message.answer(f"Добавлено фото детали ({len(details)}/4). Пришлите еще или нажмите «Далее» выше.")
    else:
        await message.answer("Максимум 4 фотографии деталей добавлены. Нажмите кнопку «Далее» выше.")

@dp.callback_query(F.data == "info_details_done")
async def info_details_done(callback: types.CallbackQuery, state: FSMContext):
    msg_text = (
        "Напишите вводные для инфографики. Также укажите какие дополнительные фото вы загрузили и как их использовать. "
        "Можете воспользоваться шаблоном ниже. Присылайте ответ с указанием, где название товара, его описание и т.д.\n\n"
        "Название: Сывороточный протеин\n"
        "Описание: для набора мышечной массы и похудения\n"
        "Преимущество: европейское сырье, гарантия качества\n"
        "Вкус: молочный шоколад\n"
        "Особенности товара: 23 г белка, 6.7 г BCAA, 30 порций в упаковке. Упаковка 900 г\n"
        "Еще загрузила фото с мерной ложкой - ее можно вставить в кружок и показать на инфографике. "
        "Используй в инфографике фирменные черно-желтые цвета моего бренда."
    )
    await callback.message.answer(msg_text)
    await state.set_state(BotStates.wait_info_prompt)
    await callback.answer()

@dp.callback_query(F.data == "mode_ideas_bank")
async def mode_ideas_bank(callback: types.CallbackQuery):
    await callback.message.answer("Посмотрите примеры фотографий, на основе которых мы можем сделать снимок с вашим товаром. Сохраните понравившееся изображение и воспользуйтесь им как референсом в разделе выше *Вписать ваш товар в пример (референс)*. Примеры: https://pin.it/5YtCLsYJZ")
    await callback.answer()

@dp.callback_query(F.data == "open_buy")
async def open_buy(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("Выберите пакет генераций:", reply_markup=get_tariffs_kb())
    except TelegramBadRequest: pass

@dp.callback_query(F.data == "dev_status")
async def dev_status(callback: types.CallbackQuery):
    await callback.answer("Этот раздел находится в разработке", show_alert=True)

# 1. При входе в раздел сразу выдаем 4 кнопки
@dp.callback_query(F.data == "mode_remove_bg")
async def start_remove_bg(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите, какой результат вы хотите получить:", 
        reply_markup=get_bg_selection_kb()
    )
    await callback.answer()

# 4. Получение фото и мгновенный запуск Gemini
@dp.message(BotStates.wait_bg_photo, F.photo)
async def process_bg_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    # Запускаем генерацию, так как мы уже знаем тип фона из шага №2
    await handle_gemini_request(message, state, is_bg_mode=True)

# 2. Обработка выбора кнопки (до отправки фото)
@dp.callback_query(F.data.startswith("bg_"))
async def select_bg_type(callback: types.CallbackQuery, state: FSMContext):
    bg_type = callback.data
    await state.update_data(bg_type=bg_type)
    
    if bg_type == "bg_custom":
        await callback.message.answer("Опишите текстом желаемый фон (например: 'светло-бежевый песок'):")
        await state.set_state(BotStates.wait_custom_bg)
    else:
        # Для Белого, Тени и Градиента — просто просим фото
        await callback.message.answer("Отлично! Теперь пришлите фото товара, и я приступлю к работе.")
        await state.set_state(BotStates.wait_bg_photo)
    await callback.answer()

# 3. Обработка текста для "Своего фона"
@dp.message(BotStates.wait_custom_bg, F.text)
async def process_custom_bg_text(message: types.Message, state: FSMContext):
    # Текст сохранили (он уже в message.text), теперь просим фото
    await state.update_data(custom_bg_text=message.text)
    await message.answer(f"Принято: '{message.text}'. Теперь пришлите фото товара.")
    await state.set_state(BotStates.wait_bg_photo)

@dp.callback_query(F.data == "mode_interior")
async def start_interior(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(BotStates.wait_interior_photo)
    await callback.message.answer("Пришли фото ОБЪЕКТА для вписывания в какую-либо сцену.")
    await callback.answer()

@dp.callback_query(F.data == "mode_free_prompt")
async def start_free_prompt(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(BotStates.wait_free_photo)
    await callback.message.answer("Пришли фотографию для обработки свободным промптом.")
    await callback.answer()

@dp.callback_query(F.data == "mode_ref_start")
async def start_ref_mode(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(BotStates.wait_ref_product)
    await callback.message.answer("Пожалуйста, пришлите фото вашего товара.")
    await callback.answer()

@dp.message(BotStates.wait_ref_product, F.photo)
async def process_ref_product(message: types.Message, state: FSMContext):
    await state.update_data(product_photo=message.photo[-1].file_id)
    await state.set_state(BotStates.wait_ref_example)
    await message.answer("Пришлите ваш референс - пример, на основе которого я сделаю фото с вашим товаром.")

@dp.message(BotStates.wait_ref_example, F.photo)
async def process_ref_example(message: types.Message, state: FSMContext):
    await state.update_data(ref_photo=message.photo[-1].file_id)
    await state.set_state(BotStates.wait_ref_comment)
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Сгенерировать", callback_data="generate_ref")
    await message.answer("Напишите, ЕСЛИ есть особенные пожелания, как именно вписать ваш предмет в референс.", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    _, count, price = callback.data.split("_")
    text = (f"Сделайте перевод {price}₽ на Сбербанк по номеру 8(926) 497-62-62 – на имя Ольга.\n\n"
            f"После оплаты нажмите кнопку ниже. Подтверждение произойдет в течение 15 минут. Для дополнительной связи и вопросов: @akookoo\n\n Так же возможна реализация потоковой обработки или интеграция ИИ в действующий бизнес. Пишите @akookoo")
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Перевод сделан", callback_data=f"paydone_{count}_{price}")
    await callback.message.answer(text, reply_markup=builder.as_markup())
    await callback.answer()

# --- КНОПКА ВЫБОРА РЕЖИМА ВИДЕО ---
@dp.callback_query(F.data == "mode_video_cover")
async def start_video_mode(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(BotStates.wait_video_photo) # ИСПРАВЛЕНО: BotStates вместо States
    log_event(callback.from_user.id, "Click Button", {"button_name": "Video Cover Start"})
    await callback.message.edit_text(
        "🎬 **Режим видеообложки**\n\nПришлите фото товара, которое нужно оживить. "
        "Я сделаю из него короткое видео 3:4 для WB/Ozon.",
        parse_mode="Markdown"
    )

# --- ПРИЕМ ФОТО ДЛЯ ВИДЕО ---
@dp.message(BotStates.wait_video_photo, F.photo) # ИСПРАВЛЕНО: BotStates вместо States
async def handle_video_photo(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    await state.update_data(video_photo_id=photo.file_id)
    await state.set_state(BotStates.wait_video_comment) # ИСПРАВЛЕНО: BotStates вместо States
    await message.answer("Отлично! ЕСЛИ есть, напиши пожелание \n\n(например: 'плавный наезд камеры' или 'блики света') или нажми /skip, чтобы использовать стандартный эффект.")

# --- ЗАПУСК ГЕНЕРАЦИИ ВИДЕО ---
@dp.message(BotStates.wait_video_comment)
async def process_video_generation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    u_id = message.from_user.id
    
    # Проверка баланса перед видео (берем 10 токенов)
    balance = get_user_data(u_id)
    if balance < 10:
        await message.answer("❌ Недостаточно генераций. Для видео нужно 10 токенов.")
        await state.clear()
        return

    status_msg = await message.answer(
        "🎬 Генерирую видео...\n\n"
        "🟩⬜⬜⬜⬜⬜⬜⬜⬜⬜ 10%"
    )
    
    try:
        # Скачиваем фото
        file = await bot.get_file(data['video_photo_id'])
        ext = file.file_path.split('.')[-1]
        photo_path = f"input_for_video.{ext}"
        await bot.download_file(file.file_path, photo_path)
        
        # Вызываем функцию (она должна быть объявлена ВЫШЕ этого места или просто в коде)
        # Создаем "Мастер-Промпт"
        raw_text = message.text if message.text != "/skip" else "product presentation"

        # Наслаиваем качественные характеристики (как мы делали для фото)
        master_video_prompt = (
            f"Professional product commercial video. {raw_text}. "
            "High-end studio lighting, cinematic camera motion, 8k resolution, "
            "highly detailed, photorealistic, elegant atmosphere."
        )
        video_file_path = await generate_video_veo(photo_path, user_comment)
        try:
            await status_msg.edit_text(
                "🎬 Генерирую видео...\n\n"
                "🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 100%\n\n"
                "Готово!"
            )
        except:
            pass
        
        # Отправляем готовое видео
        await bot.send_video(
            u_id, 
            video=FSInputFile(video_file_path), # Просто FSInputFile без приставок
            caption="🎥 Ваша видеообложка готова! Идеально для маркетплейсов."
        )
        
        update_balance_db(u_id, -10) 
        log_event(u_id, "Video Generation Success")

    except Exception as e:
        await message.answer(f"⚠️ Ошибка генерации видео: {e}")
    finally:
        await status_msg.delete()
        await state.clear()

@dp.message(BotStates.wait_free_photo, F.photo)
async def process_free_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(BotStates.wait_free_prompt)
    await message.answer("Теперь напишите текстом, что именно нужно сделать?")

@dp.message(BotStates.wait_interior_photo, F.photo)
async def process_interior_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(BotStates.wait_interior_scene)
    await message.answer(
        "Теперь подробно опишите СЦЕНУ.\n\n"
        "**Пример:**\n"
        "Уютная гостиная. В центре кадра расположен мой стол. На фоне мы видим бежевый диван, шторы. "
        "Пол деревянный, прикрыт ковром. Освещение естественное, падает сбоку и создает выразительные "
        "тени на поверхности столика. Цветовая палитра приглушенная, преобладают нейтральные оттенки.\n\n"
        "Опишите интерьер, ракурс, освещение и цвета. Так вырастет качество и контроль над генерацией.",
        parse_mode="Markdown"
    )

# --- ГЛАВНЫЙ ОБРАБОТЧИК GEMINI ---

@dp.message(F.photo)
@dp.message(BotStates.wait_free_prompt)
@dp.message(BotStates.wait_interior_scene)
@dp.message(BotStates.wait_ref_comment)
@dp.message(BotStates.wait_info_prompt)
async def handle_gemini_request(message: types.Message, state: FSMContext, is_ref_button=False, is_bg_mode=False):
    # Правильное определение ID: всегда берем ID чата, в котором произошло событие.
    # В личных сообщениях с ботом chat.id всегда равен ID пользователя.
    u_id = message.chat.id
    
    # 2. Проверка баланса
    balance = get_user_data(u_id)
    if balance <= 0:
        await message.answer("❌ Закончились генерации. Пополните ваш баланс.")
        await state.clear()
        return

    current_state = await state.get_state()
    data = await state.get_data()
    contents = []

    # Качественная надстройка
    quality_boost = (
        "\n\nSTYLE INSTRUCTION: High-end commercial photography, 8k resolution, "
        "professional studio lighting, sharp focus, clean composition, "
        "highly detailed textures, masterpiece quality."
    )

    # --- ЛОГИКА ОПРЕДЕЛЕНИЯ КОНТЕНТА ---

    # А. Режим замены фона (Улучшенный ретушер)
    if current_state == BotStates.wait_bg_photo or is_bg_mode:
        photo_id = data.get('photo_id')
        bg_type = data.get('bg_type')
        custom_text = data.get('custom_bg_text', '') 

        # СУПЕР ПРОМПТ ДЛЯ ТОПОВОГО КАТАЛОГА
        base_quality = (
            "TASK: Professional E-commerce retouching. "
            "1. PERSPECTIVE: Fix lens distortion. Align the object perfectly straight and centered. "
            "Ensure vertical lines are parallel (85mm lens effect). Correct any camera tilt. "
            "2. LIGHTING: Remove messy room reflections and greasy highlights. "
            "Redraw lighting using professional softbox studio setups. Add clean, elegant specular highlights. "
            "3. TEXTURE: Preserve original labels and branding, but enhance material look (matte stays matte, metal looks premium). "
            "5. TRANSPARENCY: If the object contains transparent or translucent parts (glass, clear plastic, liquid), preserve their transparency."
            "The new background must be visible through these parts with realistic refraction and light bending."
        )

        if bg_type == "bg_pure_white":
            bg_instruction = "Place on a 100% solid pure white background (#FFFFFF) with NO shadows. Isolated object."
        elif bg_type == "bg_shadow":
            bg_instruction = "Place the subject against a pure white background. Add a very soft, natural shadow and a subtle drop shadow to create depth. The shadow should make the subject appear to be standing against the pure white background."
        elif bg_type == "bg_gradient":
            bg_instruction = (
                "ENVIRONMENT: Place the product on a luxury, seamless light-grey studio cyclorama. "
                "Освещение создает драматическую атмосферу, мягкое освещение с легким контровым светом."
                "Циклорама уходит в даль и становится темнее, мы видим градиент снизу наверх от светло-серого до темно-серого цвета."
                "Так же от товара падает легкая тень, в соответствии со светом в сцене. "
            )
        else:
            bg_instruction = f"Place on a professional studio background: {custom_text}."

        # Финальная сборка с усилением качества
        final_prompt = (
            f"{base_quality}\n\n"
            f"ENVIRONMENT: {bg_instruction}\n\n"
            f"STYLE: High-end catalog photography, crisp sharp edges, color-corrected, masterpiece quality, 8k."
        )
        
        file = await bot.get_file(photo_id)
        fb = await bot.download_file(file.file_path)
        contents = [final_prompt, g_types.Part.from_bytes(data=fb.read(), mime_type="image/jpeg")]

    # Б. Режим инфографики
    elif current_state == BotStates.wait_info_prompt:
        mode = data.get('info_mode')
        user_text = message.text
        
        if mode == "ai":
            final_prompt = f"Сделай инфографику. Товар сохранить. Описание: {user_text}."
            photos_to_send = [data['product_photo']] + data.get('details', [])
        elif mode == "example":
            final_prompt = f"Стиль как на фото 1. Мой товар на фото 2. Текст: {user_text}."
            photos_to_send = [data.get('source_photo'), data['product_photo']] + data.get('details', [])
        else:
            final_prompt = f"Повтори инфографику конкурента. Текст: {user_text}."
            photos_to_send = [data.get('source_photo'), data['product_photo']] + data.get('details', [])
            
        contents.append(final_prompt + quality_boost)
        for f_id in photos_to_send:
            if f_id:
                f = await bot.get_file(f_id)
                fb = await bot.download_file(f.file_path)
                contents.append(g_types.Part.from_bytes(data=fb.read(), mime_type="image/jpeg"))

    # В. Режим референса
    elif current_state == BotStates.wait_ref_comment or is_ref_button:
        comment = message.text if not is_ref_button else "без пожеланий"
        
        final_prompt = (
            f"ГЛАВНАЯ ИНСТРУКЦИЯ: Новое изображение — коммерческая предметная фотография премиум-класса с акцентом на композицию и обилие 'воздуха' вокруг объекта. "
            f"ПЕРВОЕ ФОТО (мой ТОВАР) является **НЕПРИКОСНОВЕННЫМ ЭТАЛОНОМ ФОРМЫ**. "
            f"ВТОРОЕ ФОТО (РЕФЕРЕНС) является **ГИБКИМ ИСТОЧНИКОМ АТМОСФЕРЫ И СТИЛЯ**. "
            
            f"\n\n[ЭТАП 1: РЕТУШЬ И ФИКСАЦИЯ ТОВАРА]"
            f"\n1. **ЭТАЛОН:** Воссоздать объект с первого фото со 100% точностью пропорций. Если нужно для сохранения пропорций — можно слегка уменьшить размер."
            f"\n2. **ОПТИКА:** Исправить дисторсию линзы (согласуй перспективу товара с осями референса)."
            f"\n3. **ОСВЕЩЕНИЕ:** Убрать грязные блики, отражения комнаты и засветы от телефона. Полностью перерисовать свет на товаре, используя свет в локации из референса со второго фото. Добавить благородные акцентные блики, уместные в свете в сцене."
            f"\n4. **ПРОЗРАЧНОСТЬ (TRANSPARENCY):** Если есть стекло или жидкость — сохранить прозрачность. Фон референса должен быть виден сквозь них с учетом преломления (refraction)."
            f"\n5. **КАЧЕСТВО:** Crisp edges, no artifacts, 8k resolution, premium material look."

            f"\n\n[ЭТАП 2: ПОСТРОЕНИЕ СЦЕНЫ ВОКРУГ ТОВАРА]"
            f"\nРазместить отретушированный товар в новом интерьере. Если мой товар выше или шире оригинального объекта на референсе — УМЕНЬШИ МОЙ ТОВАР или ОКРУЖАЮЩИЕ ПРЕДМЕТЫ. "
            f"\n1. **СТИЛЬ:** Определи центральный объект на референсе, удали его и поставь на это место мой товар. Мой товар должен смотреться уместно. Отдали ракурс, чтобы мой товар с первого фото отлично уместился в своих пропорциях."
            f"\n2. **ИНТЕГРАЦИЯ:** Адаптируй свет и тени из референса, чтобы они естественно падали на новую геометрию товара. Товар должен выглядеть так, будто он всегда там стоял."
            f"\n3. **ДЕКОР:** Аккуратно расставь аксессуары со второго фото вокруг товара. Измени их масштаб и положение, чтобы они физически корректно взаимодействовали с габаритами моего продукта."

            f"\n\n[ИТОГ]"
            f"\nРезультат: идеальная рекламная фотография 3:4. Товар выглядит премиально (чистые блики, ровная форма) и органично вписан в атмосферную сцену референса."
            f"\nДополнительный комментарий: {comment}"
        )

# Безопасное получение фото из памяти (защита от KeyError)
        product_photo_id = data.get('product_photo')
        ref_photo_id = data.get('ref_photo')

        if not product_photo_id or not ref_photo_id:
            await message.answer(
                "❌ **Нейросеть потеряла соединение.** Пожалуйста, начните заново: загрузите фото товара, а затем выберите референс.\n"
                "Это происходит, если впн потерял соединение с интернетом."
            )
            await state.clear()
            return

        # Загрузка файлов
        p_file = await bot.get_file(product_photo_id)
        r_file = await bot.get_file(ref_photo_id)
        
        p_bytes = await bot.download_file(p_file.file_path)
        r_bytes = await bot.download_file(r_file.file_path)
        
        # Формирование контента для Gemini
        contents = [
            final_prompt, 
            g_types.Part.from_bytes(data=p_bytes.read(), mime_type="image/jpeg"), 
            g_types.Part.from_bytes(data=r_bytes.read(), mime_type="image/jpeg")
        ]

    # Г. Режим интерьера
    elif current_state == BotStates.wait_interior_scene:
        final_prompt = f"Create professional scene for product. Description: {message.text}." + quality_boost
        file = await bot.get_file(data.get('photo_id'))
        fb = await bot.download_file(file.file_path)
        contents = [final_prompt, g_types.Part.from_bytes(data=fb.read(), mime_type="image/jpeg")]

    # Д. Свободный промпт
    else:
        photo_id = data.get('photo_id') if current_state == BotStates.wait_free_prompt else message.photo[-1].file_id
        user_prompt = message.text if current_state == BotStates.wait_free_prompt else "Remove background, pure white"
        final_prompt = f"INSTRUCTION: {user_prompt}." + quality_boost
        file = await bot.get_file(photo_id)
        fb = await bot.download_file(file.file_path)
        contents = [final_prompt, g_types.Part.from_bytes(data=fb.read(), mime_type="image/jpeg")]

    # --- ОТПРАВКА В GEMINI (ИСПРАВЛЕННАЯ ВЕРСИЯ) ---
    msg = await (message.answer("⏳ Ретушер работает...") if not is_ref_button else message.reply("⏳ Ретушер работает..."))
    
    # Это позволяет боту обрабатывать запросы с мака и телефона ПАРАЛЛЕЛЬНО
    loop = asyncio.get_event_loop()

    try:
        response = await loop.run_in_executor(
            None, 
            lambda: client.models.generate_content(
                model="gemini-3.1-flash-image-preview", 
                contents=contents,
                config=g_types.GenerateContentConfig(
                    temperature=0.4,
                    top_p=0.3,
                    image_config=g_types.ImageConfig(aspect_ratio="3:4", image_size="2K")
                )
            )
        )

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    # Отправляем результат (теперь с поддержкой жирного текста)
                    await bot.send_document(
                        u_id, 
                        types.BufferedInputFile(part.inline_data.data, filename="result.png"),
                        caption="<b>✅ Готово! Качество: 2K (3:4).</b>",
                        parse_mode="HTML"
                    )

                    log_event(u_id, "Generation Success", {"mode": str(current_state)})
                    
                    # Кнопка повтора
                    await bot.send_message(
                        u_id, 
                        "<b>Результат готов!</b>\nМожно повторить генерацию с теми же фото или вернуться в меню:", 
                        reply_markup=get_repeat_kb(),
                        parse_mode="HTML"
                    )
                    update_balance_db(u_id, -1)
                    break
    except Exception as e:
        await bot.send_message(u_id, f"❌ Ошибка API: {str(e)[:100]}")
        await state.clear() 
    
    finally:
        try:
            await msg.delete()
        except:
            pass

# --- ОБРАБОТЧИК КНОПКИ ПОВТОРА (Вставляем ПЕРЕД запуском) ---
@dp.callback_query(F.data == "repeat_gen")
async def repeat_generation(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        await callback.message.answer("❌ Данные потеряны. Начните заново.")
        return
    
    # Определяем, был ли это режим референса
    is_ref = "ref_photo" in data
    await handle_gemini_request(callback.message, state, is_ref_button=is_ref)
    await callback.answer()

import time
import os
from google import genai
from google.genai import types

# Настройки видео (строго по правилам Google)
video_config = {
    "aspect_ratio": "9:16",
    "duration_seconds": 4,
     "resolution": "720p"
}

async def generate_video_veo(photo_path, text_from_user):
    # 1. Настройки
    video_config = {
        "aspect_ratio": "9:16",
        "duration_seconds": 5,
        "resolution": "720p"
    }

    with open(photo_path, "rb") as f:
        img_payload = f.read()

    # 2. Собираем промпт, используя локальное имя text_from_user
    subject_text = text_from_user if text_from_user != "/skip" else "commercial product"
    
    veo_master_prompt = (
        "Professional commercial product presentation video, shot on iPhone 15 Pro, "
        "highly detailed, masterpiece quality. Subtle and elegant motion. "
        f"Focused on: {subject_text}. " 
        "Gentle breeze, light reflections shifting. Cinematic smooth camera motion. "
        "Professional softbox lighting. Photorealistic."
    )

    print(f"🎬 [TEST BOT] Запуск Veo. Объект: {subject_text}")

    # 3. Запрос к API
    try:
        operation = client.models.generate_videos(
            model="veo-3.1-generate-preview",
            prompt=veo_master_prompt,
            image=g_types.Image(image_bytes=img_payload, mime_type="image/jpeg"),
            config=video_config
        )
    except Exception as e:
        print(f"Ошибка API (метод 1): {e}")
        operation = client.models.generate_videos(
            model="veo-3.1-generate-preview",
            source={
                "prompt": veo_master_prompt,
                "image": {"image_bytes": img_payload, "mime_type": "image/jpeg"}
            },
            config=video_config
        )

    # 4. Ожидание
    while not operation.done:
        print("⏳ [TEST BOT] Рендеринг... (15 сек)")
        await asyncio.sleep(15)
        operation = client.operations.get(operation)

    # 5. Сохранение под уникальным именем для теста
    video_item = operation.result.generated_videos[0]
    test_output_path = f"test_video_{int(time.time())}.mp4"
    
    video_data = client.files.download(file=video_item.video)
    with open(test_output_path, "wb") as f:
        f.write(video_data)
        
    return test_output_path

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
