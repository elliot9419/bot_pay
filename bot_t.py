import sqlite3
from sqlite3 import Error
import asyncio
import logging
import datetime
import random
import string
import uuid
import requests
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
API_TOKEN = '7699533123:AAEgNNuijBR8xQr91ykkFNB5OLurl-a3omM'
storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=storage)

# Настройки ЮKassa
YOOKASSA_SHOP_ID = '1055055'
YOOKASSA_SECRET_KEY = 'test_V2pP5H_w_OJ2eT9e2o20vVypSw4FqRsPHsBrA7HSKwo'
YOOKASSA_API_URL = 'https://api.yookassa.ru/v3/'
YOOKASSA_RETURN_URL = 'https://t.me/marketing1su_bot'

# ID администраторов
ADMIN_IDS = [381458669, 528833058]


# Подключение к SQLite базе данных
def create_connection():
    conn = None
    try:
        conn = sqlite3.connect('subscription_bot.db')
        logger.info("Подключение к SQLite базе данных успешно")
        return conn
    except Error as e:
        logger.error(f"Ошибка подключения к SQLite: {e}")
    return conn


def init_db():
    conn = create_connection()
    if conn is not None:
        try:
            cursor = conn.cursor()

            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    phone TEXT,
                    full_name TEXT,
                    registration_date TEXT
                )
            ''')

            # Таблица подписок
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    subscription_type TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    payment_id TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Таблица платежей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    currency TEXT,
                    payment_date TEXT,
                    payment_id TEXT,
                    status TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Таблица сообщений поддержки
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS support_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message TEXT,
                    date TEXT,
                    status TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            conn.commit()
            logger.info("Таблицы успешно созданы")
        except Error as e:
            logger.error(f"Ошибка при создании таблиц: {e}")
        finally:
            conn.close()


# Инициализация базы данных при старте
init_db()

# Цены подписок согласно скриншоту
SUBSCRIPTION_PRICES = {
    '1_group_1_week': 2000,
    '1_group_1_month': 7000,
    '1_group_6_months': 36000,
    '1_group_1_year': 57500,
    '2_groups_1_week': 3500,
    '2_groups_1_month': 12000,
    '2_groups_6_months': 63000,
    '2_groups_1_year': 100000,
    '3_groups_1_week': 5000,
    '3_groups_1_month': 17500,
    '3_groups_6_months': 90000,
    '3_groups_1_year': 144000
}


class SubscriptionStates(StatesGroup):
    waiting_payment = State()
    support_message = State()
    phone_number = State()


# Функции для работы с базой данных
def add_user(user_id, username, full_name):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, full_name, registration_date)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, full_name, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except Error as e:
        logger.error(f"Ошибка при добавлении пользователя: {e}")
    finally:
        conn.close()


def add_subscription(user_id, sub_type, start_date, end_date, payment_id):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO subscriptions (user_id, subscription_type, start_date, end_date, payment_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, sub_type, start_date, end_date, payment_id))
        conn.commit()
    except Error as e:
        logger.error(f"Ошибка при добавлении подписки: {e}")
    finally:
        conn.close()


def add_payment(user_id, amount, currency, payment_date, payment_id, status):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO payments (user_id, amount, currency, payment_date, payment_id, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, amount, currency, payment_date, payment_id, status))
        conn.commit()
    except Error as e:
        logger.error(f"Ошибка при добавлении платежа: {e}")
    finally:
        conn.close()


def add_support_message(user_id, message, status='new'):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO support_messages (user_id, message, date, status)
            VALUES (?, ?, ?, ?)
        ''', (user_id, message, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status))
        conn.commit()
    except Error as e:
        logger.error(f"Ошибка при добавлении сообщения поддержки: {e}")
    finally:
        conn.close()


def get_user_subscriptions(user_id):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM subscriptions 
            WHERE user_id = ?
            ORDER BY end_date DESC
        ''', (user_id,))
        return cursor.fetchall()
    except Error as e:
        logger.error(f"Ошибка при получении подписок пользователя: {e}")
        return []
    finally:
        conn.close()


def get_active_subscriptions():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM subscriptions 
            WHERE end_date > datetime('now')
        ''')
        return cursor.fetchone()[0]
    except Error as e:
        logger.error(f"Ошибка при получении активных подписок: {e}")
        return 0
    finally:
        conn.close()


def get_total_revenue():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT SUM(amount) FROM payments 
            WHERE status = 'completed'
        ''')
        return cursor.fetchone()[0] or 0
    except Error as e:
        logger.error(f"Ошибка при получении общего дохода: {e}")
        return 0
    finally:
        conn.close()


def get_subscription_stats():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT subscription_type, COUNT(*) 
            FROM subscriptions 
            GROUP BY subscription_type
        ''')
        return dict(cursor.fetchall())
    except Error as e:
        logger.error(f"Ошибка при получении статистики подписок: {e}")
        return {}
    finally:
        conn.close()


def get_recent_users(limit=5):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.user_id, u.username, u.phone, u.full_name,
                   (SELECT COUNT(*) FROM subscriptions s WHERE s.user_id = u.user_id) as sub_count,
                   (SELECT COUNT(*) FROM payments p WHERE p.user_id = u.user_id) as payment_count
            FROM users u
            ORDER BY u.registration_date DESC
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()
    except Error as e:
        logger.error(f"Ошибка при получении последних пользователей: {e}")
        return []
    finally:
        conn.close()


def update_user_phone(user_id, phone):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET phone = ? WHERE user_id = ?
        ''', (phone, user_id))
        conn.commit()
    except Error as e:
        logger.error(f"Ошибка при обновлении телефона пользователя: {e}")
    finally:
        conn.close()


def get_user_info(user_id):
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM users WHERE user_id = ?
        ''', (user_id,))
        return cursor.fetchone()
    except Error as e:
        logger.error(f"Ошибка при получении информации о пользователе: {e}")
        return None
    finally:
        conn.close()


def get_support_messages():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT sm.*, u.username, u.phone, u.full_name 
            FROM support_messages sm
            JOIN users u ON sm.user_id = u.user_id
            ORDER BY sm.date DESC
        ''')
        return cursor.fetchall()
    except Error as e:
        logger.error(f"Ошибка при получении сообщений поддержки: {e}")
        return []
    finally:
        conn.close()


def get_payment_history():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.*, u.username, u.phone, u.full_name 
            FROM payments p
            JOIN users u ON p.user_id = u.user_id
            ORDER BY p.payment_date DESC
        ''')
        return cursor.fetchall()
    except Error as e:
        logger.error(f"Ошибка при получении истории платежей: {e}")
        return []
    finally:
        conn.close()


# Генерация уникального ID платежа
def generate_payment_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))


# Функция для создания платежа в ЮKassa
async def create_yookassa_payment(amount, currency, user_id, description):
    payment_id = str(uuid.uuid4())
    headers = {
        'Idempotence-Key': payment_id,
        'Content-Type': 'application/json'
    }
    auth = (YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)

    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": currency
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL
        },
        "description": description,
        "metadata": {
            "user_id": user_id,
            "payment_id": payment_id
        }
    }

    try:
        response = requests.post(
            f"{YOOKASSA_API_URL}payments",
            headers=headers,
            auth=auth,
            data=json.dumps(payload))
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        logger.error(f"Error in create_yookassa_payment: {str(e)}")
        return None


# Проверка статуса платежа
async def check_payment_status(payment_id):
    headers = {'Content-Type': 'application/json'}
    auth = (YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)

    try:
        response = requests.get(
            f"{YOOKASSA_API_URL}payments/{payment_id}",
            headers=headers,
            auth=auth)
        if response.status_code == 200:
            return response.json().get('status'), response.json()
        return None, None
    except Exception as e:
        logger.error(f"Error in check_payment_status: {str(e)}")
        return None, None


# Главное меню
async def show_main_menu(message: types.Message):
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text='🎁 Пробная неделя'),
        KeyboardButton(text='🛒 Купить подписку')
    )
    builder.row(
        KeyboardButton(text='🔍 Проверить подписку'),
        KeyboardButton(text='📞 Поддержка')
    )
    await message.answer("Выберите действие:", reply_markup=builder.as_markup(resize_keyboard=True))


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username, message.from_user.full_name)

    await message.answer(
        f"Привет, {message.from_user.full_name}! Добро пожаловать в бота для подписки на контент.\n\n"
        "Доступные команды:\n"
        "/start - начать работу с ботом\n"
        "/stats - статистика (только для админов)")
    await show_main_menu(message)


@dp.message(F.text == '🎁 Пробная неделя')
async def free_trial(message: types.Message):
    user_id = message.from_user.id
    subscriptions = get_user_subscriptions(user_id)

    # Проверяем, есть ли уже активная подписка
    if subscriptions and any(sub[2] == 'trial_week' for sub in subscriptions):
        await message.answer("❌ Вы уже использовали пробную неделю.")
        return

    # Добавляем пробную подписку
    start_date = datetime.datetime.now()
    end_date = start_date + datetime.timedelta(days=7)
    add_subscription(user_id, 'trial_week',
                     start_date.strftime("%Y-%m-%d %H:%M:%S"),
                     end_date.strftime("%Y-%m-%d %H:%M:%S"),
                     'FREE_TRIAL')

    content_link = "https://disk.yandex.ru/d/2RLiH7XsyQQa0Q"

    await message.answer(
        f"🎉 Вам активирована пробная подписка на 7 дней!\n"
        f"🔗 Ссылка на контент: {content_link}\n"
        f"📅 Подписка активна до: {end_date.strftime('%Y-%m-%d')}\n\n"
        "Через 3 дня я напомню вам о возможности оформить полную подписку.")

    # Устанавливаем напоминание через 3 дня
    reminder_date = start_date + datetime.timedelta(days=3)
    asyncio.create_task(send_trial_reminder(user_id, reminder_date))


async def send_trial_reminder(user_id: int, reminder_date: datetime.datetime):
    now = datetime.datetime.now()
    delay = (reminder_date - now).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)

    try:
        await bot.send_message(
            chat_id=user_id,
            text="⏰ Напоминаем, что ваша пробная подписка скоро закончится!\n"
                 "Вы можете оформить полную подписку прямо сейчас и получить доступ ко всем материалам.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="show_subs_after_reminder")]
            ]))
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания пользователю {user_id}: {str(e)}")


@dp.message(F.text == '🛒 Купить подписку')
async def show_subscriptions(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 группа", callback_data="select_1_group"),
        InlineKeyboardButton(text="2 группы", callback_data="select_2_groups"),
        InlineKeyboardButton(text="3 группы", callback_data="select_3_groups")
    )
    await message.answer("Выберите количество групп:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("select_"))
async def select_group_count(callback: types.CallbackQuery):
    group_count = callback.data.split('_')[1] + '_' + callback.data.split('_')[2]

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"1 неделя - {SUBSCRIPTION_PRICES[f'{group_count}_1_week']} руб",
            callback_data=f"sub_{group_count}_1_week")
    )
    builder.row(
        InlineKeyboardButton(
            text=f"1 месяц - {SUBSCRIPTION_PRICES[f'{group_count}_1_month']} руб (-12%)",
            callback_data=f"sub_{group_count}_1_month")
    )
    builder.row(
        InlineKeyboardButton(
            text=f"6 месяцев - {SUBSCRIPTION_PRICES[f'{group_count}_6_months']} руб (-25%)",
            callback_data=f"sub_{group_count}_6_months")
    )
    builder.row(
        InlineKeyboardButton(
            text=f"1 год - {SUBSCRIPTION_PRICES[f'{group_count}_1_year']} руб (-40%)",
            callback_data=f"sub_{group_count}_1_year")
    )
    builder.row(
        InlineKeyboardButton(
            text="◀️ Назад",
            callback_data="back_to_groups")
    )

    await callback.message.edit_text(
        f"Вы выбрали: {group_count.replace('_', ' ')}\n"
        "Выберите срок подписки:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_groups")
async def back_to_groups(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 группа", callback_data="select_1_group"),
        InlineKeyboardButton(text="2 группы", callback_data="select_2_groups"),
        InlineKeyboardButton(text="3 группы", callback_data="select_3_groups")
    )

    await callback.message.edit_text(
        "Выберите количество групп:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@dp.message(F.text == '🛒 Купить подписку')
async def show_subscriptions(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 группа", callback_data="select_1_group"),
        InlineKeyboardButton(text="2 группы", callback_data="select_2_groups"),
        InlineKeyboardButton(text="3 группы", callback_data="select_3_groups")
    )
    await message.answer("Выберите количество групп:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("select_"))
async def select_group_count(callback: types.CallbackQuery):
    group_count = callback.data.split('_')[1] + '_' + callback.data.split('_')[2]

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"1 неделя - {SUBSCRIPTION_PRICES[f'{group_count}_1_week']} руб",
            callback_data=f"sub_{group_count}_1_week")
    )
    builder.row(
        InlineKeyboardButton(
            text=f"1 месяц - {SUBSCRIPTION_PRICES[f'{group_count}_1_month']} руб (-12%)",
            callback_data=f"sub_{group_count}_1_month")
    )
    builder.row(
        InlineKeyboardButton(
            text=f"6 месяцев - {SUBSCRIPTION_PRICES[f'{group_count}_6_months']} руб (-25%)",
            callback_data=f"sub_{group_count}_6_months")
    )
    builder.row(
        InlineKeyboardButton(
            text=f"1 год - {SUBSCRIPTION_PRICES[f'{group_count}_1_year']} руб (-40%)",
            callback_data=f"sub_{group_count}_1_year")
    )
    builder.row(
        InlineKeyboardButton(
            text="◀️ Назад",
            callback_data="back_to_groups")
    )

    await callback.message.edit_text(
        f"Вы выбрали: {group_count.replace('_', ' ')}\n"
        "Выберите срок подписки:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("sub_"))
async def process_subscription(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split('_')
    group_count = parts[1] + '_' + parts[2]
    period = parts[3] + '_' + parts[4]
    sub_type = f"{group_count}_{period}"
    price = SUBSCRIPTION_PRICES[sub_type]

    await state.update_data(
        sub_type=sub_type,
        price=price,
        group_count=group_count
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📄 Договор оферты",
            url="https://disk.yandex.ru/i/tapIlxjn1tF2LQ")
    )
    builder.row(
        InlineKeyboardButton(
            text="🔒 Политика конфиденциальности",
            url="https://disk.yandex.ru/i/_SX5Q-50rbM6dA")
    )
    builder.row(
        InlineKeyboardButton(
            text="✅ Я согласен с условиями",
            callback_data="accept_terms")
    )
    builder.row(
        InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=f"back_to_{group_count}")
    )

    await callback.message.edit_text(
        f"Перед оплатой подписки {sub_type.replace('_', ' ')} пожалуйста ознакомьтесь с:\n\n"
        "1. Договором публичной оферты\n"
        "2. Политикой конфиденциальности\n\n"
        "Нажимая кнопку 'Я согласен с условиями', вы подтверждаете что ознакомились "
        "и согласны со всеми условиями.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@dp.callback_query(F.data == "accept_terms")
async def accept_terms(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sub_type = data['sub_type']
    price = data['price']
    user_id = callback.from_user.id

    description = f"Подписка {sub_type.replace('_', ' ')} для пользователя {user_id}"
    payment_data = await create_yookassa_payment(price, 'RUB', user_id, description)

    if payment_data:
        await state.update_data(
            yookassa_payment_id=payment_data['id'],
            payment_id=payment_data['metadata']['payment_id']
        )

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="💳 Оплатить",
                url=payment_data['confirmation']['confirmation_url']),
            InlineKeyboardButton(
                text="✅ Я оплатил",
                callback_data=f"check_payment_{payment_data['id']}")
        )
        builder.row(
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel_payment")
        )

        await callback.message.edit_text(
            f"Вы выбрали подписку: {sub_type.replace('_', ' ')}\n"
            f"Сумма к оплате: {price} руб\n\n"
            "Для оплаты нажмите кнопку ниже и следуйте инструкциям.\n"
            "После оплаты нажмите '✅ Я оплатил' для проверки платежа.",
            reply_markup=builder.as_markup())

        await state.set_state(SubscriptionStates.waiting_payment)
    else:
        await callback.message.answer("Произошла ошибка при создании платежа. Пожалуйста, попробуйте позже.")
    await callback.answer()


@dp.callback_query(F.data.startswith("back_to_"))
async def back_to_group_selection(callback: types.CallbackQuery):
    group_count = callback.data.split('_')[2]

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"1 неделя - {SUBSCRIPTION_PRICES[f'{group_count}_1_week']} руб",
            callback_data=f"sub_{group_count}_1_week")
    )
    builder.row(
        InlineKeyboardButton(
            text=f"1 месяц - {SUBSCRIPTION_PRICES[f'{group_count}_1_month']} руб (-12%)",
            callback_data=f"sub_{group_count}_1_month")
    )
    builder.row(
        InlineKeyboardButton(
            text=f"6 месяцев - {SUBSCRIPTION_PRICES[f'{group_count}_6_months']} руб (-25%)",
            callback_data=f"sub_{group_count}_6_months")
    )
    builder.row(
        InlineKeyboardButton(
            text=f"1 год - {SUBSCRIPTION_PRICES[f'{group_count}_1_year']} руб (-40%)",
            callback_data=f"sub_{group_count}_1_year")
    )
    builder.row(
        InlineKeyboardButton(
            text="◀️ Назад",
            callback_data="back_to_groups")
    )

    await callback.message.edit_text(
        f"Вы выбрали: {group_count.replace('_', ' ')}\n"
        "Выберите срок подписки:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_groups")
async def back_to_groups(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 группа", callback_data="select_1_group"),
        InlineKeyboardButton(text="2 группы", callback_data="select_2_groups"),
        InlineKeyboardButton(text="3 группы", callback_data="select_3_groups")
    )
    await callback.message.edit_text(
        "Выберите количество групп:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("check_payment_"), SubscriptionStates.waiting_payment)
async def check_payment(callback: types.CallbackQuery, state: FSMContext):
    yookassa_payment_id = callback.data.split('_')[2]
    user_id = callback.from_user.id

    status, payment_data = await check_payment_status(yookassa_payment_id)

    if status == 'succeeded':
        data = await state.get_data()
        sub_type = data['sub_type']
        price = data['price']
        payment_id = data['payment_id']

        # Определяем срок подписки в днях
        period = sub_type.split('_')[-2] + '_' + sub_type.split('_')[-1]
        if period == '1_week':
            days = 7
        elif period == '1_month':
            days = 30
        elif period == '6_months':
            days = 180
        elif period == '1_year':
            days = 365

        start_date = datetime.datetime.now()
        end_date = start_date + datetime.timedelta(days=days)

        add_payment(user_id, price, 'RUB',
                    start_date.strftime("%Y-%m-%d %H:%M:%S"),
                    payment_id, 'completed')

        add_subscription(user_id, sub_type,
                         start_date.strftime("%Y-%m-%d %H:%M:%S"),
                         end_date.strftime("%Y-%m-%d %H:%M:%S"),
                         payment_id)

        content_link = "https://disk.yandex.ru/d/2RLiH7XsyQQa0Q"

        await callback.message.answer(
            f"✅ Оплата прошла успешно!\n"
            f"🔗 Ваша ссылка на контент: {content_link}\n"
            f"📅 Подписка активна до: {end_date.strftime('%Y-%m-%d')}")

        await state.clear()
        await show_main_menu(callback.message)
    elif status == 'pending':
        await callback.message.answer("Платеж еще не прошел. Попробуйте проверить статус позже.")
    else:
        await callback.message.answer(
            "Платеж не найден или произошла ошибка. Пожалуйста, попробуйте еще раз или обратитесь в поддержку.")
    await callback.answer()


@dp.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Оплата отменена.")
    await state.clear()
    await show_main_menu(callback.message)
    await callback.answer()


@dp.message(F.text == '🔍 Проверить подписку')
async def check_subscription(message: types.Message):
    user_id = message.from_user.id
    subscriptions = get_user_subscriptions(user_id)
    content_link = "https://disk.yandex.ru/d/2RLiH7XsyQQa0Q"

    if subscriptions:
        last_sub = subscriptions[0]
        end_date = datetime.datetime.strptime(last_sub[4], "%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.now()

        if now < end_date:
            days_left = (end_date - now).days
            sub_type = "Пробная неделя" if last_sub[2] == 'trial_week' else last_sub[2].replace('_', ' ')

            response = (
                f"✅ У вас активна подписка: {sub_type}\n"
                f"📅 Действует до: {end_date.strftime('%Y-%m-%d')}\n"
                f"⏳ Осталось дней: {days_left}\n\n"
                f"🔗 Ссылка на контент: {content_link}"
            )

            await message.answer(response)
        else:
            await message.answer(
                "❌ У вас нет активной подписки.\n\n"
                f"🔗 Ссылка на контент: {content_link}")
    else:
        await message.answer(
            "❌ У вас нет активной подписки.\n\n"
            f"🔗 Ссылка на контент: {content_link}")

    await show_main_menu(message)


@dp.callback_query(F.data == "show_subs_after_reminder")
async def show_subs_after_reminder(callback: types.CallbackQuery):
    await show_subscriptions(callback.message)
    await callback.answer()


@dp.message(F.text == '📞 Поддержка')
async def support_menu(message: types.Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Написать в поддержку", callback_data="write_to_support"))
    await message.answer(
        "Если у вас возникли вопросы или проблемы, напишите нам.\n"
        "Мы постараемся ответить как можно скорее.",
        reply_markup=builder.as_markup())


@dp.callback_query(F.data == "write_to_support")
async def write_to_support(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Пожалуйста, введите ваш номер телефона для связи:")
    await state.set_state(SubscriptionStates.phone_number)
    await callback.answer()


@dp.message(SubscriptionStates.phone_number)
async def process_phone_number(message: types.Message, state: FSMContext):
    phone = message.text
    user_id = message.from_user.id

    update_user_phone(user_id, phone)

    await message.answer("Теперь напишите ваше сообщение для поддержки:")
    await state.set_state(SubscriptionStates.support_message)


@dp.message(SubscriptionStates.support_message)
async def process_support_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    add_support_message(user_id, message.text)

    user_info = get_user_info(user_id)
    phone = user_info[2] if user_info else 'не указан'
    username = user_info[1] if user_info else 'нет'

    try:
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"📩 Новое обращение в поддержку\n\n"
                         f"👤 Пользователь: {message.from_user.full_name}\n"
                         f"🆔 ID: {user_id}\n"
                         f"📱 Телефон: {phone}\n"
                         f"👤 Логин: @{username}\n"
                         f"📝 Сообщение:\n{message.text}")
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения админу {admin_id}: {str(e)}")

        await message.answer("✅ Ваше сообщение отправлено в поддержку. Мы ответим вам в ближайшее время.")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения поддержки: {str(e)}")
        await message.answer("⚠ Произошла ошибка при отправке сообщения. Пожалуйста, попробуйте позже.")

    await state.clear()
    await show_main_menu(message)


@dp.message(Command("stats"))
async def show_stats_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Эта команда доступна только администраторам.")
        return

    total_users = len(get_recent_users(1000))  # Получаем всех пользователей
    active_subs = get_active_subscriptions()
    total_revenue = get_total_revenue()
    sub_stats = get_subscription_stats()
    recent_users = get_recent_users(5)

    stats_text = (
        "📊 <b>Статистика бота</b>:\n\n"
        f"👥 Всего пользователей: <code>{total_users}</code>\n"
        f"✅ Активных подписок: <code>{active_subs}</code>\n"
        f"💰 Общий доход: <code>{total_revenue} руб</code>\n\n"
        "📈 <b>Статистика по подпискам</b>:\n"
    )

    for sub_type, count in sub_stats.items():
        stats_text += f"- {sub_type.replace('_', ' ')}: <code>{count}</code>\n"

    stats_text += "\n<b>Последние пользователи:</b>\n"
    for user in recent_users:
        stats_text += (
            f"\n👤 ID: {user[0]}\n"
            f"👤 Логин: @{user[1] if user[1] else 'нет'}\n"
            f"📱 Телефон: {user[2] if user[2] else 'не указан'}\n"
            f"👤 Имя: {user[3]}\n"
            f"📅 Подписок: {user[4]}\n"
            f"💳 Платежей: {user[5]}\n"
        )

    await message.answer(stats_text, parse_mode="HTML")


async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())