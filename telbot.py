import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiohttp import web

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8828706159:AAGEuelcHP8M-v22bB3oQJhCmyHb8HOJetk")
DATABASE_URL = os.environ.get("DATABASE_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

CATEGORIES = [
    "🍎 Продукты",
    "💊 Аптека",
    "🧹 Хоз. товары",
    "🍷 Алкоголь",
    "🐱 Ева",
    "🚍 Транспорт",
    "🎭 Развлечения"
]

MONTHS_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

class ExpenseState(StatesGroup):
    waiting_for_amount = State()

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    query = (
        "CREATE TABLE IF NOT EXISTS expenses ("
        "id SERIAL PRIMARY KEY, "
        "user_id BIGINT NOT NULL, "
        "category VARCHAR(100) NOT NULL, "
        "amount NUMERIC(10, 2) NOT NULL, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ");"
    )
    cur.execute(query)
    conn.commit()
    cur.close()
    conn.close()

def get_main_keyboard():
    kb = [
        [KeyboardButton(text="➕ Добавить расход")],
        [KeyboardButton(text="📊 Статистика по категориям"), KeyboardButton(text="📅 Месячный отчет")],
        [KeyboardButton(text="💰 Общий итог")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_categories_inline_keyboard():
    buttons = []
    for cat in CATEGORIES:
        buttons.append([InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    msg_text = "Привет! Я бот для совместного учета трат.\nВыберите действие из меню снизу:"
    await message.answer(msg_text, reply_markup=get_main_keyboard())

@dp.message(F.text == "➕ Добавить расход")
async def add_expense_start(message: types.Message):
    await message.answer("Выберите категорию расхода:", reply_markup=get_categories_inline_keyboard())

@dp.callback_query(F.data.startswith("cat_"))
async def process_category_click(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.split("cat_")[1]
    await state.update_data(chosen_category=category)
    prompt_text = "Категория: *" + category + "*\nВведите сумму расхода (число):"
    await callback.message.answer(prompt_text, parse_mode="Markdown")
    await state.set_state(ExpenseState.waiting_for_amount)
    await callback.answer()

@dp.message(ExpenseState.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    text = message.text.replace(",", ".")
    try:
        val = float(text)
        if val <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите корректную положительную сумму цифрами.")
        return

    data = await state.get_data()
    category = data.get("chosen_category")
    user_id = message.from_user.id

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO expenses (user_id, category, amount) VALUES (%s, %s, %s)",
        (user_id, category, val)
    )
    conn.commit()
    cur.close()
    conn.close()

    await state.clear()
    confirm_text = "✅ Успешно добавлено!\nКатегория: " + str(category) + "\nСумма: " + f"{val:.2f}"
    await message.answer(confirm_text, reply_markup=get_main_keyboard())

@dp.message(F.text == "📊 Статистика по категориям")
async def show_category_stats(message: types.Message):
    buttons = []
    for cat in CATEGORIES:
        buttons.append([InlineKeyboardButton(text=cat, callback_data=f"statcat_{cat}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Выберите категорию для просмотра трат:", reply_markup=kb)

@dp.callback_query(F.data.startswith("statcat_"))
async def process_category_stats(callback: types.CallbackQuery):
    category = callback.data.split("statcat_")[1]
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT SUM(amount) as total FROM expenses WHERE category = %s",
        (category,)
    )
    res = cur.fetchone()
    cur.close()
    conn.close()

    total = float(res['total']) if res and res['total'] else 0.0
    stat_text = "📊 Всего потрачено в категории *" + str(category) + "*: " + f"{total:.2f}"
    await callback.message.edit_text(stat_text, parse_mode="Markdown")
    await callback.answer()

@dp.message(F.text == "📅 Месячный отчет")
async def show_months_stats(message: types.Message):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    query = (
        "SELECT DISTINCT "
        "EXTRACT(YEAR FROM created_at)::INTEGER as year, "
        "EXTRACT(MONTH FROM created_at)::INTEGER as month "
        "FROM expenses "
        "ORDER BY year DESC, month DESC"
    )
    cur.execute(query)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        await message.answer("Записи пока отсутствуют.")
        return

    buttons = []
    for r in rows:
        m_num = r['month']
        y_num = r['year']
        m_name = MONTHS_RU.get(m_num, str(m_num))
        label = f"{m_name} {y_num}"
        cbd = f"statmonth_{y_num}_{m_num}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=cbd)])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Выберите месяц для детального отчета:", reply_markup=kb)

@dp.callback_query(F.data.startswith("statmonth_"))
async def process_month_stats(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    year = int(parts[1])
    month = int(parts[2])
    m_name = MONTHS_RU.get(month, str(month))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    query = (
        "SELECT category, SUM(amount) as total "
        "FROM expenses "
        "WHERE EXTRACT(YEAR FROM created_at) = %s AND EXTRACT(MONTH FROM created_at) = %s "
        "GROUP BY category "
        "ORDER BY total DESC"
    )
    cur.execute(query, (year, month))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        empty_text = "В *" + str(m_name) + " " + str(year) + "* трат не зафиксировано."
        await callback.message.edit_text(empty_text, parse_mode="Markdown")
        await callback.answer()
        return

    total_sum = sum(float(r['total']) for r in rows)
    report_text = "📅 *Отчет за " + str(m_name) + " " + str(year) + "*\n\n"
    for r in rows:
        report_text += "• " + str(r['category']) + ": " + f"{float(r['total']):.2f}\n"
    report_text += "\n*Итого за месяц:* " + f"{total_sum:.2f}"

    await callback.message.edit_text(report_text, parse_mode="Markdown")
    await callback.answer()

@dp.message(F.text == "💰 Общий итог")
async def show_grand_total(message: types.Message):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT SUM(amount) as total FROM expenses")
    res = cur.fetchone()
    cur.close()
    conn.close()

    total = float(res['total']) if res and res['total'] else 0.0
    total_text = "💰 *Общие расходы за всё время:* " + f"{total:.2f}"
    await message.answer(total_text, parse_mode="Markdown")

async def handle_ping(request):
    return web.Response(text="Bot is live!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await start_web_server()
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())