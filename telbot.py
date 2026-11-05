import asyncio
import logging
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# Ваш токен от BotFather
BOT_TOKEN = "8828706159:AAGEuelcHP8M-v22bB3oQJhCmyHb8HOJetk"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Словарь месяцев для отображения
MONTH_NAMES = {
    "01": "Январь",
    "02": "Февраль",
    "03": "Март",
    "04": "Апрель",
    "05": "Май",
    "06": "Июнь",
    "07": "Июль",
    "08": "Август",
    "09": "Сентябрь",
    "10": "Октябрь",
    "11": "Ноябрь",
    "12": "Декабрь",
}


def format_month_name(yyyy_mm: str) -> str:
    """Преобразует ГГГГ-ММ в НазваниеМесяца ГГГГ (например, '2026-11' -> 'Ноябрь 2026')"""
    try:
        year, month = yyyy_mm.split("-")
        month_name = MONTH_NAMES.get(month, month)
        return f"{month_name} {year}"
    except Exception:
        return yyyy_mm


# --- БАЗА ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL
        )
    """
    )
    conn.commit()
    conn.close()


def add_expense(category: str, amount: float):
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute(
        "INSERT INTO expenses (category, amount, date) VALUES (?, ?, ?)",
        (category, amount, now),
    )
    conn.commit()
    conn.close()


def get_available_months():
    """Возвращает список уникальных месяцев (ГГГГ-ММ) из базы данных"""
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT substr(date, 1, 7) FROM expenses ORDER BY date DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


def get_expenses_filtered(category: str, month: str = None):
    """Получает траты по категории с фильтром по месяцу"""
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    query = "SELECT date, category, amount FROM expenses WHERE 1=1"
    params = []

    if category != "all":
        query += " AND category = ?"
        params.append(category)

    if month and month != "all":
        query += " AND date LIKE ?"
        params.append(f"{month}%")

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows


# --- СОСТОЯНИЯ (FSM) ---
class ExpenseState(StatesGroup):
    waiting_for_amount = State()


# --- КЛАВИАТУРЫ ---
CATEGORIES = [
    "🍎 Продукты",
    "💊 Аптека",
    "🧹 Хоз. товары",
    "🍷 Алкоголь",
    "🐱 Ева",
    "🚍 Транспорт",
    "🎭 Развлечения",
]


def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍎 Продукты"), KeyboardButton(text="💊 Аптека")],
            [
                KeyboardButton(text="🧹 Хоз. товары"),
                KeyboardButton(text="🍷 Алкоголь"),
            ],
            [
                KeyboardButton(text="🐱 Ева"),
                KeyboardButton(text="🚍 Транспорт"),
            ],
            [
                KeyboardButton(text="🎭 Развлечения"),
                KeyboardButton(text="📊 Итоги"),
            ],
        ],
        resize_keyboard=True,
    )
    return keyboard


def get_stats_inline_keyboard():
    inline_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🍎 Продукты", callback_data="stats_cat_🍎 Продукты"
                ),
                InlineKeyboardButton(
                    text="💊 Аптека", callback_data="stats_cat_💊 Аптека"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🧹 Хоз. товары", callback_data="stats_cat_🧹 Хоз. товары"
                ),
                InlineKeyboardButton(
                    text="🍷 Алкоголь", callback_data="stats_cat_🍷 Алкоголь"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🐱 Ева", callback_data="stats_cat_🐱 Ева"
                ),
                InlineKeyboardButton(
                    text="🚍 Транспорт", callback_data="stats_cat_🚍 Транспорт"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎭 Развлечения", callback_data="stats_cat_🎭 Развлечения"
                ),
                InlineKeyboardButton(
                    text="🌐 Общие итоги", callback_data="stats_cat_all"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Главное меню", callback_data="stats_back"
                )
            ],
        ]
    )
    return inline_keyboard


def get_months_inline_keyboard(category: str):
    """Генерирует кнопки месяцев с понятным текстом (например, 'Ноябрь 2026')"""
    months = get_available_months()
    buttons = []

    row = []
    for m in months:
        readable_month = format_month_name(m)
        row.append(
            InlineKeyboardButton(
                text=f"🗓 {readable_month}",
                callback_data=f"stats_month_{category}_{m}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append(
        [
            InlineKeyboardButton(
                text="📅 За всё время",
                callback_data=f"stats_month_{category}_all",
            )
        ]
    )
    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад к категориям", callback_data="stats_back_to_cats"
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- ОБРАБОТЧИКИ ---


@dp.message(Command("start"))
@dp.message(F.text == "⬅️ Главное меню")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Выберите категорию для добавления расхода:",
        reply_markup=get_main_keyboard(),
    )


@dp.message(F.text == "📊 Итоги")
async def show_stats_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Выберите категорию для просмотра сохраненных трат:",
        reply_markup=get_stats_inline_keyboard(),
    )


@dp.callback_query(F.data == "stats_back")
async def process_stats_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "Вы вернулись в главное меню:", reply_markup=get_main_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("stats_cat_"))
async def process_category_stats(callback: types.CallbackQuery):
    cat_code = callback.data.replace("stats_cat_", "")
    cat_title = "все категории" if cat_code == "all" else cat_code

    await callback.message.edit_text(
        f"Выбрано: **{cat_title}**.\nТеперь выберите месяц:",
        parse_mode="Markdown",
        reply_markup=get_months_inline_keyboard(cat_code),
    )
    await callback.answer()


@dp.callback_query(F.data == "stats_back_to_cats")
async def process_back_to_cats(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Выберите категорию для просмотра сохраненных трат:",
        reply_markup=get_stats_inline_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("stats_month_"))
async def process_month_stats(callback: types.CallbackQuery):
    _, _, cat_code, month_code = callback.data.split("_")

    records = get_expenses_filtered(category=cat_code, month=month_code)

    period_header = (
        f"за {format_month_name(month_code)}"
        if month_code != "all"
        else "за всё время"
    )

    if not records:
        cat_text = (
            f"по категории **{cat_code}**"
            if cat_code != "all"
            else "по всем категориям"
        )
        await callback.message.answer(
            f"Записей {cat_text} {period_header} не найдено.",
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    total = sum(r[2] for r in records)

    if cat_code == "all":
        text = f"🌐 **Общие итоги ({period_header}):**\n\n"
        for date_str, cat, amount in records:
            text += f"🗓 `{date_str}` | {cat} — **{amount:.2f}**\n"
    else:
        text = f"📋 **Записи по категории {cat_code} ({period_header}):**\n\n"
        for date_str, _, amount in records:
            text += f"🗓 `{date_str}` — **{amount:.2f}**\n"

    text += f"\n💰 **Всего потрачено:** `{total:.2f}`"
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


@dp.message(F.text.in_(CATEGORIES))
async def category_selected(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(ExpenseState.waiting_for_amount)
    await message.answer(f"{message.text}. Введите сумму покупки")


@dp.message(ExpenseState.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    text = message.text.replace(",", ".")

    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError

        user_data = await state.get_data()
        category = user_data.get("category")

        add_expense(category, amount)

        await message.answer(
            f"✅ Успешно записано!\nКатегория: {category}\nСумма: {amount:.2f}",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()

    except ValueError:
        await message.answer(
            "⚠️ Пожалуйста, введите корректное число (например: `150` или `45.50`).",
            parse_mode="Markdown",
        )


async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())