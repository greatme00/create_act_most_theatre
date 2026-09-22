"""Дружелюбная версия Telegram-бота для журнала работы артиста."""

from __future__ import annotations

import asyncio
import calendar
import logging
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message
from docx import Document
import time

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "data.sqlite3"
ACTS_DIR = BASE_DIR / "acts"
CATEGORIES = {"Главная роль": 1500, "Роль первого плана": 1250, "Роль второго плана": 1000, "Массовка": 750}


class AddShow(StatesGroup):
    title = State()
    category = State()
    time = State()


class AddRehearsal(StatesGroup):
    title = State()
    start = State()
    end = State()


class PickMonth(StatesGroup):
    month = State()


class ProfileForm(StatesGroup):
    full_name = State()
    contract_number = State()


class PriceForm(StatesGroup):
    amount = State()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS shows (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                    title TEXT NOT NULL, role TEXT NOT NULL, category TEXT,
                    price INTEGER, day TEXT NOT NULL, show_time TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rehearsals (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                    title TEXT NOT NULL, price INTEGER NOT NULL DEFAULT 750,
                    units INTEGER NOT NULL DEFAULT 1,
                    day TEXT NOT NULL, time_start TEXT, time_end TEXT);
                CREATE INDEX IF NOT EXISTS shows_by_user_day ON shows(user_id, day);
                CREATE INDEX IF NOT EXISTS rehearsals_by_user_day ON rehearsals(user_id, day);
                CREATE TABLE IF NOT EXISTS reminder_log (
                    event_type TEXT NOT NULL, event_id INTEGER NOT NULL,
                    reminder_day TEXT NOT NULL,
                    PRIMARY KEY (event_type, event_id, reminder_day));
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    contract_number TEXT);
                CREATE TABLE IF NOT EXISTS user_prices (
                    user_id INTEGER NOT NULL, category TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    PRIMARY KEY (user_id, category));
            """)
            # This keeps databases created by the earlier V2 compatible.
            columns = {row["name"] for row in db.execute("PRAGMA table_info(rehearsals)")}
            if "units" not in columns:
                db.execute("ALTER TABLE rehearsals ADD COLUMN units INTEGER NOT NULL DEFAULT 1")

    def profile(self, user_id: int) -> sqlite3.Row | None:
        with closing(self.connect()) as db:
            return db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    def save_profile(self, user_id: int, full_name: str, contract_number: str | None) -> None:
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO users(user_id, full_name, contract_number) VALUES (?, ?, ?)", (user_id, full_name, contract_number))

    def prices(self, user_id: int) -> dict[str, int]:
        result = dict(CATEGORIES)
        with closing(self.connect()) as db:
            for row in db.execute("SELECT category, price FROM user_prices WHERE user_id = ?", (user_id,)):
                result[row["category"]] = row["price"]
        return result

    def save_price(self, user_id: int, category: str, price: int) -> None:
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO user_prices(user_id, category, price) VALUES (?, ?, ?)", (user_id, category, price))

    def add_show(self, user_id: int, data: dict[str, str]) -> None:
        price = self.prices(user_id)[data["category"]]
        with closing(self.connect()) as db, db:
            db.execute("""INSERT INTO shows (user_id, title, role, category, price, day, show_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", (user_id, data["title"], "", data["category"], price, data["day"], data.get("time", "")))

    def add_rehearsal(self, user_id: int, data: dict[str, str | None]) -> None:
        units = rehearsal_units(data["start"], data["end"])
        with closing(self.connect()) as db, db:
            db.execute("""INSERT INTO rehearsals (user_id, title, units, day, time_start, time_end)
                VALUES (?, ?, ?, ?, ?, ?)""", (user_id, data["title"], units, data["day"], data["start"], data["end"]))

    def month_rows(self, table: str, user_id: int, month: str) -> list[sqlite3.Row]:
        if table not in {"shows", "rehearsals"}:
            raise ValueError("Unknown table")
        with closing(self.connect()) as db:
            return db.execute(f"SELECT * FROM {table} WHERE user_id = ? AND day LIKE ? ORDER BY day, id", (user_id, f"{month}-%")).fetchall()

    def has_same_show(self, user_id: int, title: str, day: str) -> bool:
        with closing(self.connect()) as db:
            return db.execute("SELECT 1 FROM shows WHERE user_id = ? AND title = ? AND day = ?", (user_id, title, day)).fetchone() is not None

    def events_for_day(self, day: str) -> list[sqlite3.Row]:
        with closing(self.connect()) as db:
            return db.execute("""
                SELECT 'show' AS type, id, user_id, title, show_time AS time FROM shows WHERE day = ?
                UNION ALL
                SELECT 'rehearsal' AS type, id, user_id, title, time_start AS time FROM rehearsals WHERE day = ?
            """, (day, day)).fetchall()

    def reminder_was_sent(self, event_type: str, event_id: int, reminder_day: str) -> bool:
        with closing(self.connect()) as db:
            return db.execute("SELECT 1 FROM reminder_log WHERE event_type = ? AND event_id = ? AND reminder_day = ?", (event_type, event_id, reminder_day)).fetchone() is not None

    def mark_reminder_sent(self, event_type: str, event_id: int, reminder_day: str) -> None:
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR IGNORE INTO reminder_log(event_type, event_id, reminder_day) VALUES (?, ?, ?)", (event_type, event_id, reminder_day))

    def delete(self, table: str, record_id: int, user_id: int) -> bool:
        if table not in {"shows", "rehearsals"}:
            return False
        with closing(self.connect()) as db, db:
            return db.execute(f"DELETE FROM {table} WHERE id = ? AND user_id = ?", (record_id, user_id)).rowcount > 0


def load_env() -> None:
    file = BASE_DIR / ".env"
    if file.exists():
        for line in file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def month_now(offset: int = 0) -> str:
    current = date.today()
    number = current.year * 12 + current.month - 1 + offset
    return f"{number // 12:04d}-{number % 12 + 1:02d}"


def parse_day(text: str) -> str | None:
    for pattern in ("%d.%m.%Y", "%d.%m"):
        try:
            parsed = datetime.strptime(text.strip(), pattern)
            if pattern == "%d.%m":
                parsed = parsed.replace(year=date.today().year)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_time(text: str) -> str | None:
    try:
        return datetime.strptime(text.strip(), "%H:%M").strftime("%H:%M")
    except ValueError:
        return None


def rehearsal_units(start: str | None, end: str | None) -> int:
    """One rehearsal up to 3h inclusive, two over 3h, three over 9h."""
    if not start or not end:
        return 1
    start_time = datetime.strptime(start, "%H:%M")
    end_time = datetime.strptime(end, "%H:%M")
    hours = (end_time - start_time).total_seconds() / 3600
    if hours < 0:  # A rehearsal that crosses midnight.
        hours += 24
    return 3 if hours > 9 else 2 if hours > 3 else 1


def friendly_day(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")


def calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    """A compact Russian month calendar; all dates are selected by a button."""
    names = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")
    buttons = [[
        InlineKeyboardButton(text="‹", callback_data=f"calnav:{year}:{month}:-1"),
        InlineKeyboardButton(text=f"{names[month - 1]} {year}", callback_data="ignore"),
        InlineKeyboardButton(text="›", callback_data=f"calnav:{year}:{month}:1"),
    ], [InlineKeyboardButton(text=weekday, callback_data="ignore") for weekday in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")]]
    for week in calendar.monthcalendar(year, month):
        buttons.append([InlineKeyboardButton(
            text=str(day) if day else "·",
            callback_data=f"calday:{year}-{month:02d}-{day:02d}" if day else "ignore",
        ) for day in week])
    buttons.append([InlineKeyboardButton(text="Отмена", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def ask_for_day(message: Message, state: FSMContext) -> None:
    today = date.today()
    await state.update_data(calendar_flow="show" if await state.get_state() == AddShow.category.state else "rehearsal")
    await message.answer("Выберите дату в календаре:", reply_markup=calendar_keyboard(today.year, today.month))


def hour_keyboard(kind: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{hour:02d}", callback_data=f"timehour:{kind}:{hour:02d}") for hour in range(begin, begin + 6)] for begin in range(0, 24, 6)]
    if kind != "show":
        rows.append([InlineKeyboardButton(text="Не указывать", callback_data=f"timeskip:{kind}")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def minute_keyboard(kind: str, hour: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=minute, callback_data=f"timemin:{kind}:{hour}:{minute}") for minute in ("00", "15", "30", "45")],
        [InlineKeyboardButton(text="← Выбрать другой час", callback_data=f"timeback:{kind}")],
        [InlineKeyboardButton(text="Отмена", callback_data="menu")],
    ])


async def ask_for_time(message: Message, kind: str) -> None:
    label = {"start": "начала репетиции", "end": "окончания репетиции", "show": "начала спектакля"}[kind]
    await message.answer(f"Выберите час {label}:", reply_markup=hour_keyboard(kind))


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить спектакль", callback_data="add:show")],
        [InlineKeyboardButton(text="➕ Добавить репетицию", callback_data="add:rehearsal")],
        [InlineKeyboardButton(text="📅 Мой месяц", callback_data="month:menu")],
        [InlineKeyboardButton(text="📄 Скачать акт", callback_data="act:current")],
        [InlineKeyboardButton(text="💳 Мои цены", callback_data="prices")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ])


def month_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Текущий месяц", callback_data=f"{action}:0"), InlineKeyboardButton(text="Прошлый месяц", callback_data=f"{action}:-1")],
        [InlineKeyboardButton(text="Ввести другой месяц", callback_data=f"{action}:custom")],
        [InlineKeyboardButton(text="← В меню", callback_data="menu")],
    ])


async def show_menu(message: Message, text: str = "Что хотите сделать?") -> None:
    await message.answer(text, reply_markup=main_keyboard())


async def start(message: Message, state: FSMContext, database: Database) -> None:
    await state.clear()
    if not database.profile(message.from_user.id):
        await state.set_state(ProfileForm.full_name)
        await message.answer("Для первого акта напишите ФИО полностью. Например: Евгений Иосифович Славутин")
        return
    await show_menu(message, "Привет! Я помогу вести журнал спектаклей и репетиций.\n\nВыберите действие ниже.")


async def profile_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name.split()) < 2:
        await message.answer("Нужно как минимум имя и фамилия. Напишите ФИО полностью.")
        return
    await state.update_data(full_name=name)
    await state.set_state(ProfileForm.contract_number)
    await message.answer("Введите номер договора. Если его пока нет — отправьте минус: -")


async def profile_contract(message: Message, state: FSMContext, database: Database) -> None:
    data = await state.get_data()
    contract = None if message.text.strip() == "-" else message.text.strip()
    database.save_profile(message.from_user.id, data["full_name"], contract)
    await state.clear()
    await show_menu(message, "✅ Профиль сохранён. Номер договора можно будет добавить или изменить позже.")


async def prices_menu(callback: CallbackQuery, database: Database) -> None:
    await callback.answer()
    prices = database.prices(callback.from_user.id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{category}: {price} ₽", callback_data=f"price:{index}")] for index, (category, price) in enumerate(prices.items())] + [[InlineKeyboardButton(text="← В меню", callback_data="menu")]])
    await callback.message.answer("Текущие цены. Нажмите категорию, чтобы изменить цену:", reply_markup=keyboard)


async def price_pick(callback: CallbackQuery, state: FSMContext) -> None:
    category = list(CATEGORIES)[int(callback.data.split(":")[1])]
    await callback.answer()
    await state.update_data(price_category=category)
    await state.set_state(PriceForm.amount)
    await callback.message.answer(f"Новая цена для «{category}» в рублях — только целое число:")


async def price_save(message: Message, state: FSMContext, database: Database) -> None:
    try:
        amount = int(message.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await message.answer("Введите положительное целое число, например 1250.")
        return
    data = await state.get_data()
    database.save_price(message.from_user.id, data["price_category"], amount)
    await state.clear()
    await show_menu(message, "✅ Цена сохранена.")


async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_menu(message, "Готово, ничего не сохранил.")


async def button_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.answer("Что хотите сделать?", reply_markup=main_keyboard())


async def help_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("• Добавляйте спектакли и репетиции по шагам.\n• «Мой месяц» показывает записи и позволяет удалить ошибочную.\n• «Скачать акт» создаёт Word-файл.\n\nВ любой момент отправьте /cancel, чтобы отменить ввод.", reply_markup=main_keyboard())


async def add_show(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AddShow.title)
    await callback.message.answer("Введите название спектакля:\nНапример: «Вишнёвый сад»")


async def save_show_title(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Название не должно быть пустым.")
        return
    await state.update_data(title=text)
    await state.set_state(AddShow.category)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{name} — {price} ₽", callback_data=f"category:{index}")] for index, (name, price) in enumerate(CATEGORIES.items())])
    await message.answer("Выберите категорию — цена подставится сама:", reply_markup=keyboard)


async def save_show_category(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    index = int(callback.data.split(":")[1])
    category = list(CATEGORIES)[index]
    await callback.answer(f"{category}: {database.prices(callback.from_user.id)[category]} ₽")
    await state.update_data(category=category)
    await ask_for_day(callback.message, state)


async def save_show_time(message: Message, state: FSMContext, database: Database) -> None:
    show_time = parse_time(message.text)
    if not show_time:
        await message.answer("Не понял время. Пример: 19:30")
        return
    await state.update_data(time=show_time)
    data = await state.get_data()
    database.add_show(message.from_user.id, data)
    await state.clear()
    await show_menu(message, f"✅ Сохранил: {data['title']}, {friendly_day(data['day'])} в {show_time}. Цена — {database.prices(message.from_user.id)[data['category']]} ₽.")


async def calendar_navigate(callback: CallbackQuery) -> None:
    _, year, month, step = callback.data.split(":")
    number = int(year) * 12 + int(month) - 1 + int(step)
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=calendar_keyboard(number // 12, number % 12 + 1))


async def calendar_day(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    chosen_day = callback.data.split(":", 1)[1]
    data = await state.get_data()
    flow = data.get("calendar_flow")
    await callback.answer()
    if flow == "show":
        await state.update_data(day=chosen_day)
        if database.has_same_show(callback.from_user.id, data["title"], chosen_day):
            await state.set_state(AddShow.time)
            await callback.message.answer("В этот день такой спектакль уже есть. Выберите время второго показа.")
            await ask_for_time(callback.message, "show")
            return
        data = await state.get_data()
        database.add_show(callback.from_user.id, data)
        await state.clear()
        await show_menu(callback.message, f"✅ Сохранил: {data['title']}, {friendly_day(chosen_day)}. Цена — {database.prices(callback.from_user.id)[data['category']]} ₽.")
        return
    if flow == "rehearsal":
        await state.update_data(day=chosen_day)
        await state.set_state(AddRehearsal.start)
        await ask_for_time(callback.message, "start")


async def add_rehearsal(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AddRehearsal.title)
    await callback.message.answer("Введите название репетиции:")


async def save_rehearsal_title(message: Message, state: FSMContext) -> None:
    if not message.text.strip():
        await message.answer("Название не должно быть пустым.")
        return
    await state.update_data(title=message.text.strip())
    await ask_for_day(message, state)


async def save_rehearsal(message: Message, state: FSMContext, database: Database, telegram_user_id: int) -> None:
    data = await state.get_data()
    database.add_rehearsal(telegram_user_id, data)
    units = rehearsal_units(data.get("start"), data.get("end"))
    await state.clear()
    await show_menu(message, f"✅ Репетиция «{data['title']}» на {friendly_day(data['day'])} сохранена. Засчитано: {units}. Цена — {units * 750} ₽.")


async def time_hour(callback: CallbackQuery) -> None:
    _, kind, hour = callback.data.split(":")
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=minute_keyboard(kind, hour))


async def time_back(callback: CallbackQuery) -> None:
    _, kind = callback.data.split(":")
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=hour_keyboard(kind))


async def time_minute(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    _, kind, hour, minute = callback.data.split(":")
    value = f"{hour}:{minute}"
    await callback.answer(value)
    await state.update_data(**{kind: value})
    if kind == "start":
        await state.set_state(AddRehearsal.end)
        await ask_for_time(callback.message, "end")
        return
    if kind == "show":
        data = await state.get_data()
        database.add_show(callback.from_user.id, data)
        await state.clear()
        await show_menu(callback.message, f"✅ Сохранил второй показ: {data['title']}, {friendly_day(data['day'])} в {value}. Цена — {database.prices(callback.from_user.id)[data['category']]} ₽.")
        return
    await save_rehearsal(callback.message, state, database, callback.from_user.id)


async def time_skip(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    _, kind = callback.data.split(":")
    await callback.answer()
    if kind == "start":
        await state.update_data(start=None, end=None)
        await save_rehearsal(callback.message, state, database, callback.from_user.id)
        return
    await state.update_data(end=None)
    await save_rehearsal(callback.message, state, database, callback.from_user.id)


async def month_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("За какой месяц показать записи?", reply_markup=month_keyboard("view"))


async def view_month(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    value = callback.data.split(":")[1]
    await callback.answer()
    if value == "custom":
        await state.set_state(PickMonth.month)
        await state.update_data(purpose="view")
        await callback.message.answer("Напишите месяц в формате ГГГГ-ММ, например 2026-10")
        return
    await send_month(callback.message, callback.from_user.id, month_now(int(value)), database)


async def send_month(message: Message, user_id: int, month: str, database: Database) -> None:
    shows, rehearsals = database.month_rows("shows", user_id, month), database.month_rows("rehearsals", user_id, month)
    rehearsal_units_total = sum(row["units"] for row in rehearsals)
    total = sum(row["price"] or 0 for row in shows) + rehearsal_units_total * 750
    text = [f"📅 {month}"]
    keyboard_rows = []
    if shows:
        text.append("\nСпектакли:")
        for row in shows:
            time_text = f", {row['show_time']}" if row['show_time'] else ""
            text.append(f"• {friendly_day(row['day'])}{time_text} — {row['title']} — {row['price'] or 'цена не указана'} ₽")
            keyboard_rows.append([InlineKeyboardButton(text=f"Удалить спектакль: {row['title']}", callback_data=f"delete:shows:{row['id']}")])
    if rehearsals:
        text.append("\nРепетиции:")
        for row in rehearsals:
            clock = "" if not row["time_start"] else f" ({row['time_start']}–{row['time_end'] or '?'})"
            units = row["units"]
            text.append(f"• {friendly_day(row['day'])} — {row['title']}{clock} — {units} × 750 = {units * 750} ₽")
            keyboard_rows.append([InlineKeyboardButton(text=f"Удалить репетицию: {row['title']}", callback_data=f"delete:rehearsals:{row['id']}")])
    if not shows and not rehearsals:
        text.append("\nПока пусто. Добавьте первую запись.")
    else:
        text.append(f"\nИтого за месяц: {total} ₽")
    keyboard_rows.append([InlineKeyboardButton(text="← В меню", callback_data="menu")])
    await message.answer("\n".join(text), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))


async def custom_month(message: Message, state: FSMContext, database: Database) -> None:
    try:
        month = datetime.strptime(message.text.strip(), "%Y-%m").strftime("%Y-%m")
    except ValueError:
        await message.answer("Формат такой: 2026-10")
        return
    data = await state.get_data()
    await state.clear()
    if data["purpose"] == "view":
        await send_month(message, message.from_user.id, month, database)
    else:
        await send_act(message, message.from_user.id, month, database)


def _plural_ru(n: int, one: str, few: str, many: str) -> str:
    n = abs(n) % 100
    if 11 <= n <= 19:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


_ONES = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
         "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
         "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят",
         "семьдесят", "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
             "шестьсот", "семьсот", "восемьсот", "девятьсот"]


def _female(word: str) -> str:
    if not word:
        return word
    if word.endswith(("н", "р", "л", "м", "д", "т", "к", "в", "з", "с", "б", "п", "г", "ф")):
        return word[:-1] + "а"
    return word


def _triple(n: int, female: bool = False) -> str:
    words = []
    h, rem = divmod(n, 100)
    if h:
        words.append(_HUNDREDS[h])
    if rem >= 20:
        t, o = divmod(rem, 10)
        words.append(_TENS[t])
        if o:
            words.append(_female(_ONES[o]) if female else _ONES[o])
    elif rem:
        words.append(_female(_ONES[rem]) if female else _ONES[rem])
    return " ".join(words)


def _num_to_words(n: int) -> str:
    if n == 0:
        return "ноль"
    parts = []
    for unit, female, one, few, many in (
        (1_000_000, False, "миллион", "миллиона", "миллионов"),
        (1_000, True, "тысяча", "тысячи", "тысяч"),
        (1, False, "", "", ""),
    ):
        if n >= unit:
            chunk, n = divmod(n, unit)
            if not chunk:
                continue
            text = _triple(chunk, female)
            if unit > 1:
                text = f"{text} {_plural_ru(chunk, one, few, many)}"
            parts.append(text)
    return " ".join(p for p in parts if p).strip()


def _rubles_in_words(amount: float) -> str:
    rub = int(amount)
    kop = int(round((amount - rub) * 100))
    return (f"{_num_to_words(rub).capitalize()} "
            f"{_plural_ru(rub, 'рубль', 'рубля', 'рублей')} "
            f"{kop:02d} {_plural_ru(kop, 'копейка', 'копейки', 'копеек')}")


_MONTHS_GEN = {1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
               7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"}


def make_act(user_id: int, month: str, database: Database) -> Path:
    """Word-акт 1:1 по act_template.docx."""
    from docx import Document
    from docx.shared import Pt, Cm, Mm
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    from docx.enum.table import WD_ALIGN_VERTICAL
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    # ---------- данные ----------
    shows = database.month_rows("shows", user_id, month)
    rehearsals = database.month_rows("rehearsals", user_id, month)
    profile = database.profile(user_id)
    full_name = (profile["full_name"] if profile and profile["full_name"]
                 else "ВВЕДИТЕ ИМЯ")
    contract_number = (profile["contract_number"] if profile else None) or ""

    # ФИО для подписи: "А.Р. Бафаев" — БЕЗ пробелов между инициалами
    parts = full_name.split()
    if len(parts) >= 2:
        surname = parts[0]
        initials = "".join(f"{p[0]}." for p in parts[1:] if p)
        sign_name = f"{initials} {surname}"
    else:
        sign_name = full_name

    rehearsal_price = 750

    year, mon = int(month[:4]), int(month[5:7])
    last_day_num = calendar.monthrange(year, mon)[1]
    end_day = date(year, mon, last_day_num)
    period_text = (f"с 1 {_MONTHS_GEN[mon]} {year} г. "
                   f"по {last_day_num} {_MONTHS_GEN[mon]} {year} г.")

    # ---------- группировка показов ----------
    grouped: dict[str, dict] = {}
    for row in shows:
        key = row["title"]
        grouped.setdefault(key, {
            "title": key,
            "role": row["role"] or "Роль второго плана",
            "price": row["price"] or 0,
            "days": [],
        })
        grouped[key]["days"].append(row["day"])

    # ---------- документ ----------
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(8)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts")) or OxmlElement("w:rFonts")
    if rfonts.getparent() is None:
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), "Times New Roman")
    pf = style.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.space_after = Pt(0)
    pf.space_before = Pt(0)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for section in doc.sections:
        section.page_width = Mm(210)
        section.page_height = Mm(297)
        section.left_margin = Cm(3)
        section.right_margin = Cm(1.5)
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)

    def _p(text="", *, align=WD_ALIGN_PARAGRAPH.JUSTIFY, bold=False,
           indent=Cm(1.25), size=None, space_after=0, space_before=0):
        p = doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.first_line_indent = indent
        if text:
            r = p.add_run(text)
            r.bold = bold
            if size:
                r.font.size = Pt(size)
        return p

    # ---------- Шапка ----------
    _p("АКТ", align=WD_ALIGN_PARAGRAPH.CENTER, bold=True,
       indent=Cm(0), size=8, space_after=2)
    _p("сдачи-приемки оказанных услуг", align=WD_ALIGN_PARAGRAPH.CENTER,
       bold=True, indent=Cm(0), size=8, space_after=0)

    date_p = doc.add_paragraph()
    date_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    date_p.paragraph_format.first_line_indent = Cm(0)
    date_p.paragraph_format.space_before = Pt(8)
    date_p.paragraph_format.space_after = Pt(8)
    date_p.paragraph_format.tab_stops.add_tab_stop(Cm(16.5))
    date_p.add_run("г. Москва\t"
                   f"«{end_day.day:02d}» {_MONTHS_GEN[end_day.month]} "
                   f"{end_day.year} г.")

    # ---------- Преамбула (одна скобка!) ----------
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Cm(1.25)
    p.paragraph_format.space_after = Pt(6)

    r = p.add_run(
        "Государственное бюджетное учреждение культуры города Москвы "
        "«Государственный академический театр имени Моссовета» "
        "(ГБУК г. Москвы «Театр им. Моссовета»)"
    )
    r.bold = True
    # закрывающая скобка — в продолжении, БЕЗ лишней
    p.add_run(
        ", именуемое в дальнейшем «Заказчик», в лице директора "
        "Черепнева Алексея Анатольевича, действующего на основании Устава, "
        "с одной стороны, и "
    )
    r = p.add_run(f"самозанятое лицо {full_name}")
    r.bold = True
    p.add_run(
        ", именуемый в дальнейшем «Исполнитель», с другой стороны, совместно "
        "именуемые «Стороны», составили настоящий Акт (далее — Акт) "
        "о нижеследующем:"
    )

    # ---------- Договор ----------
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Cm(1.25)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.space_before = Pt(6)

    if contract_number:
        cnum = contract_number.rstrip()
        # гарантируем точку перед скобкой
        if not cnum.endswith("."):
            cnum += "."
        p.add_run(
            f"В соответствии с условиями Договора № {cnum} "
            f"(далее — Договор) Исполнителем оказаны услуги, а Заказчиком "
            f"приняты услуги по исполнению роли/ей в составе организуемых "
            f"Заказчиком театрально-зрелищных мероприятий (спектаклей)."
        )
    else:
        p.add_run(
            "В соответствии с условиями Договора № ____ от __________ "
            "(далее — Договор) Исполнителем оказаны услуги, а Заказчиком "
            "приняты услуги по исполнению роли/ей в составе организуемых "
            "Заказчиком театрально-зрелищных мероприятий (спектаклей)."
        )

    _p(f"За период {period_text} фактически оказаны услуги "
       f"в следующем объеме:", space_after=6)

    # ---------- Таблица ----------
    headers = ("№ п/п", "Наименование услуг", "Наименование спектакля",
               "Артистическая роль/ Вокал", "Цена за единицу, руб.",
               "Кол-во услуг", "Стоимость, руб.")

    table = doc.add_table(rows=1, cols=7)
    table.style = "Table Grid"
    table.autofit = False
    table.allow_autofit = False

    # жёстко фиксируем layout
    tblPr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)

    widths = [Cm(1.0), Cm(2.8), Cm(2.9), Cm(2.7), Cm(2.3), Cm(1.6), Cm(2.7)]

    def _set_cell(cell, text, *, align=WD_ALIGN_PARAGRAPH.LEFT, bold=False):
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = align
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        for line in str(text).split("\n"):
            if p.runs:
                p.add_run().add_break()
            r = p.add_run(line)
            r.font.name = "Times New Roman"
            r.font.size = Pt(8)
            r.bold = bold
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    def _apply_widths(row):
        for cell, w in zip(row.cells, widths):
            cell.width = w

    # шапка таблицы
    for cell, text in zip(table.rows[0].cells, headers):
        _set_cell(cell, text, align=WD_ALIGN_PARAGRAPH.CENTER, bold=True)
    _apply_widths(table.rows[0])

    # формат денег с ЗАПЯТОЙ
    def money(v: float) -> str:
        return f"{v:,.2f}".replace(",", "\u00A0").replace(".", ",")

    row_number = 0
    total = 0.0

    # Показы — по одной строке на название
    for group in grouped.values():
        row_number += 1
        count = len(group["days"])
        price = float(group["price"])
        summa = price * count
        total += summa
        dates_sorted = sorted(group["days"])
        dates_text = ", ".join(friendly_day(d) for d in dates_sorted)
        values = (
            row_number,
            "исполнение роли при проведении публичных показов спектакля",
            f"«{group['title']}»\n{dates_text}",
            group["role"],
            money(price),
            count,
            money(summa),
        )
        row = table.add_row()
        _apply_widths(row)
        for i, (cell, value) in enumerate(zip(row.cells, values)):
            align = WD_ALIGN_PARAGRAPH.CENTER if i in (0, 4, 5, 6) \
                else WD_ALIGN_PARAGRAPH.LEFT
            _set_cell(cell, value, align=align)

    # Репетиции — одной строкой
    if rehearsals:
        row_number += 1
        units = sum(r["units"] for r in rehearsals)
        summa = rehearsal_price * units
        total += summa
        days_sorted = sorted(r["day"] for r in rehearsals)
        dates_text = ", ".join(friendly_day(d) for d in days_sorted)
        values = (
            row_number,
            "участие в репетиции спектакля",
            "Репертуарные спектакли структурного подразделения — "
            f"Студия «МОСТ»\n{dates_text}",
            "",
            money(rehearsal_price),
            units,
            money(summa),
        )
        row = table.add_row()
        _apply_widths(row)
        for i, (cell, value) in enumerate(zip(row.cells, values)):
            align = WD_ALIGN_PARAGRAPH.CENTER if i in (0, 4, 5, 6) \
                else WD_ALIGN_PARAGRAPH.LEFT
            _set_cell(cell, value, align=align)

    # Итого
    total_row = table.add_row()
    _apply_widths(total_row)
    merged = total_row.cells[0].merge(total_row.cells[5])
    _set_cell(merged, "ВСЕГО", align=WD_ALIGN_PARAGRAPH.CENTER, bold=True)
    _set_cell(total_row.cells[6], money(total),
              align=WD_ALIGN_PARAGRAPH.CENTER, bold=True)

    # повтор шапки на новых страницах
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)

    # ---------- Пост-табличная часть ----------
    _p("", indent=Cm(0), space_after=6)
    _p("Обязательства по договору выполнены Исполнителем в установленные "
       "сроки. Заказчик не имеет претензий к объему и качеству оказанных "
       "услуг.", space_after=6)
    _p("", indent=Cm(0), space_after=6)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Cm(1.25)
    p.paragraph_format.space_after = Pt(6)
    p.add_run("Сумма вознаграждения, подлежащая уплате Исполнителю, "
              "за услуги, принятые по настоящему акту, составляет ")
    r = p.add_run(_rubles_in_words(total))
    r.bold = True
    p.add_run(".")

    _p("Расчет по Договору производится путем перечисления Заказчиком "
       "денежных средств на банковский счет Исполнителя согласно "
       "реквизитам, указанным в Договоре, в течение 7 (Семи) рабочих дней "
       "со дня подписания Сторонами настоящего Акта.", space_after=6)

    _p("Настоящий Акт составлен в 2 (двух) экземплярах, имеющих равную "
       "юридическую силу, по одному экземпляру для каждой из Сторон и "
       "является неотъемлемой частью Договора.", space_after=6)

    # ---------- Подписи ----------
    _p("", indent=Cm(0), space_after=12)

    sign = doc.add_table(rows=1, cols=2)
    sign.autofit = False
    sign.allow_autofit = False
    for cell, w in zip(sign.rows[0].cells, [Cm(8.25), Cm(8.25)]):
        cell.width = w

    left, right = sign.rows[0].cells

    def _fill_sign(cell, lines):
        cell.text = ""
        first = True
        for text, bold in lines:
            if first:
                p = cell.paragraphs[0]
                first = False
            else:
                p = cell.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.space_before = Pt(0)
            if text:
                r = p.add_run(text)
                r.font.name = "Times New Roman"
                r.font.size = Pt(8)
                r.bold = bold

    _fill_sign(left, [
        ("Заказчик:", True),
        ("", False),
        ("Директор", False),
        ("", False),
        ("______________ /А.А. Черепнев/", False),
        (f"«____» ______________ {end_day.year} г.", False),
        ("М.П.", False),
    ])

    _fill_sign(right, [
        ("Исполнитель:", True),
        ("", False),
        (f"самозанятое лицо {full_name}", False),
        ("", False),
        (f"______________ /{sign_name}/", False),
        (f"«____» ______________ {end_day.year} г.", False),
    ])

    # убираем границы таблицы подписей
    tbl_pr = sign._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none")
        el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        borders.append(el)
    tbl_pr.append(borders)

    ACTS_DIR.mkdir(exist_ok=True)
    path = ACTS_DIR / f"акт_{month}_{sign_name}.docx"
    doc.save(path)
    return path

async def send_act(message: Message, user_id: int, month: str, database: Database) -> None:
    path = make_act(user_id, month, database)
    await message.answer_document(FSInputFile(path), caption=f"Готово. Акт за {month}.", reply_markup=main_keyboard())


async def act_current(callback: CallbackQuery, database: Database) -> None:
    await callback.answer()
    await send_act(callback.message, callback.from_user.id, month_now(), database)


async def delete_record(callback: CallbackQuery, database: Database) -> None:
    _, table, record = callback.data.split(":")
    deleted = database.delete(table, int(record), callback.from_user.id)
    await callback.answer("Запись удалена" if deleted else "Запись уже удалена")
    if deleted:
        await callback.message.answer("✅ Удалил запись. Нажмите «Мой месяц», чтобы увидеть обновлённый список.", reply_markup=main_keyboard())


async def ignore_callback(callback: CallbackQuery) -> None:
    await callback.answer()


async def reminder_loop(bot: Bot, database: Database) -> None:
    """Notify once at 10:00 Moscow time on the calendar day before an event."""
    timezone = ZoneInfo("Europe/Moscow")
    while True:
        now = datetime.now(timezone)
        if now.hour >= 10:
            tomorrow = date.fromordinal(now.date().toordinal() + 1).isoformat()
            for event in database.events_for_day(tomorrow):
                if database.reminder_was_sent(event["type"], event["id"], now.date().isoformat()):
                    continue
                event_name = "спектакль" if event["type"] == "show" else "репетиция"
                time_text = f" в {event['time']}" if event["time"] else ""
                try:
                    await bot.send_message(event["user_id"], f"🔔 Напоминание: завтра{time_text} {event_name} «{event['title']}».")
                except Exception:
                    logging.exception("Could not send reminder to user %s", event["user_id"])
                else:
                    database.mark_reminder_sent(event["type"], event["id"], now.date().isoformat())
        await asyncio.sleep(600)

async def cleanup_acts_loop() -> None:
    """Раз в час удаляем акты старше 24 часов."""
    while True:
        try:
            if ACTS_DIR.exists():
                now = time.time()
                for path in ACTS_DIR.glob("*.docx"):
                    if now - path.stat().st_mtime > 24 * 3600:
                        path.unlink(missing_ok=True)
                        logging.info("Удалён устаревший акт: %s", path.name)
        except Exception:
            logging.exception("Ошибка при очистке актов")
        await asyncio.sleep(3600)


async def unknown(message: Message) -> None:
    await show_menu(message, "Я жду нажатия на кнопку. Если вы были в процессе ввода, используйте /cancel.")


def dispatcher(database: Database) -> Dispatcher:
    dp = Dispatcher()
    dp["database"] = database
    dp.message.register(cancel, Command("cancel"))
    dp.message.register(start, CommandStart())
    dp.message.register(profile_name, ProfileForm.full_name, F.text)
    dp.message.register(profile_contract, ProfileForm.contract_number, F.text)
    dp.message.register(price_save, PriceForm.amount, F.text)
    dp.callback_query.register(button_menu, F.data == "menu")
    dp.callback_query.register(help_handler, F.data == "help")
    dp.callback_query.register(prices_menu, F.data == "prices")
    dp.callback_query.register(price_pick, F.data.startswith("price:"))
    dp.callback_query.register(add_show, F.data == "add:show")
    dp.callback_query.register(add_rehearsal, F.data == "add:rehearsal")
    dp.callback_query.register(month_menu, F.data == "month:menu")
    dp.callback_query.register(view_month, F.data.startswith("view:"))
    dp.callback_query.register(act_current, F.data == "act:current")
    dp.callback_query.register(save_show_category, F.data.startswith("category:"))
    dp.callback_query.register(calendar_navigate, F.data.startswith("calnav:"))
    dp.callback_query.register(calendar_day, F.data.startswith("calday:"))
    dp.callback_query.register(time_hour, F.data.startswith("timehour:"))
    dp.callback_query.register(time_back, F.data.startswith("timeback:"))
    dp.callback_query.register(time_minute, F.data.startswith("timemin:"))
    dp.callback_query.register(time_skip, F.data.startswith("timeskip:"))
    dp.callback_query.register(delete_record, F.data.startswith("delete:"))
    dp.callback_query.register(ignore_callback, F.data == "ignore")
    dp.message.register(save_show_title, AddShow.title, F.text)
    dp.message.register(save_show_time, AddShow.time, F.text)
    dp.message.register(save_rehearsal_title, AddRehearsal.title, F.text)
    dp.message.register(custom_month, PickMonth.month, F.text)
    dp.message.register(unknown, F.text)
    return dp


async def main() -> None:
    load_env()
    token = os.getenv("BOT_TOKEN")
    asyncio.create_task(reminder_loop(bot, database))
    asyncio.create_task(cleanup_acts_loop())
    if not token or token.startswith("вставьте"):
        raise RuntimeError("Создайте файл .env по образцу .env.example и вставьте токен BotFather.")
    database = Database(DB_FILE)
    database.initialize()
    bot = Bot(token)
    asyncio.create_task(reminder_loop(bot, database))
    await dispatcher(database).start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
