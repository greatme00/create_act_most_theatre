"""Хендлеры пользователя: профиль, добавление спектакля, репетиции."""

from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import Database
from keyboards import (
    calendar_keyboard,
    hour_keyboard,
    minute_keyboard,
    show_category_keyboard,
)
from utils import detect_gender, friendly_day, parse_time, rehearsal_units


router = Router()


# ---------- FSM ----------

class ProfileForm(StatesGroup):
    full_name = State()
    status = State()
    gender = State()
    contract_number = State()


class AddShow(StatesGroup):
    title = State()
    category = State()
    time = State()


class AddRehearsal(StatesGroup):
    title = State()
    start = State()
    end = State()


# ---------- Профиль ----------

@router.message(ProfileForm.full_name, F.text)
async def profile_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name.split()) < 2:
        await message.answer("Нужно как минимум имя и фамилия. Напишите ФИО полностью.")
        return
    await state.update_data(full_name=name)
    await state.set_state(ProfileForm.status)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Самозанятый", callback_data="reg_status:self_employed")],
        [InlineKeyboardButton(text="Физлицо по ГПХ", callback_data="reg_status:gph")],
    ])
    await message.answer("Выберите ваш статус:", reply_markup=keyboard)


@router.callback_query(ProfileForm.status, F.data.startswith("reg_status:"))
async def profile_status(callback: CallbackQuery, state: FSMContext) -> None:
    status = callback.data.split(":")[1]
    await callback.answer()
    await state.update_data(status=status)
    await state.set_state(ProfileForm.gender)

    data = await state.get_data()
    detected = detect_gender(data["full_name"])

    if detected == "f":
        question = "Ваш пол женский? Я угадал? 🤔"
        yes_cb = "reg_gender:f"
        no_cb = "reg_gender:m"
        no_label = "❌ Нет, я мужчина"
    else:
        question = "Ваш пол мужской? Я угадал? 🤔"
        yes_cb = "reg_gender:m"
        no_cb = "reg_gender:f"
        no_label = "❌ Нет, я девушка"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=yes_cb)],
        [InlineKeyboardButton(text=no_label, callback_data=no_cb)],
    ])
    await callback.message.edit_text(question, reply_markup=keyboard)


@router.callback_query(ProfileForm.gender, F.data.startswith("reg_gender:"))
async def profile_gender(callback: CallbackQuery, state: FSMContext) -> None:
    gender = callback.data.split(":")[1]
    await callback.answer()
    await state.update_data(gender=gender)
    await state.set_state(ProfileForm.contract_number)
    await callback.message.edit_text(
        "Введите номер договора. Если его пока нет — отправьте минус: -"
    )


@router.message(ProfileForm.contract_number, F.text)
async def profile_contract(message: Message, state: FSMContext, database: Database) -> None:
    from handlers.common import show_menu
    data = await state.get_data()
    contract = None if message.text.strip() == "-" else message.text.strip()
    database.save_profile(
        message.from_user.id,
        data["full_name"],
        contract,
        status=data.get("status", "self_employed"),
        gender=data.get("gender", "m"),
    )
    await state.clear()
    await show_menu(
        message,
        "✅ Профиль сохранён. Номер договора можно будет добавить или изменить позже.",
    )


# ---------- Добавить спектакль ----------

@router.callback_query(F.data == "add:show")
async def add_show(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AddShow.title)
    await callback.message.answer("Введите название спектакля:\nНапример: «Гамлет»")


@router.message(AddShow.title, F.text)
async def save_show_title(message: Message, state: FSMContext, database: Database) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Название не должно быть пустым.")
        return
    await state.update_data(title=text)
    await state.set_state(AddShow.category)
    user_prices = database.prices(message.from_user.id)
    await message.answer(
        "Выберите категорию — цена подставится сама:",
        reply_markup=show_category_keyboard(user_prices),
    )


@router.callback_query(F.data.startswith("category:"))
async def save_show_category(
    callback: CallbackQuery, state: FSMContext, database: Database
) -> None:
    from config import SHOW_CATEGORIES
    index = int(callback.data.split(":")[1])
    if index < 0 or index >= len(SHOW_CATEGORIES):
        await callback.answer("Ошибка: неизвестная категория", show_alert=True)
        return
    category = list(SHOW_CATEGORIES.keys())[index]
    await callback.answer(f"{category}: {database.prices(callback.from_user.id)[category]} ₽")
    await state.update_data(category=category)
    await ask_for_day(callback.message, state)


# ---------- Добавить репетицию ----------

@router.callback_query(F.data == "add:rehearsal")
async def add_rehearsal(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AddRehearsal.title)
    await callback.message.answer("Введите название репетиции:")


@router.message(AddRehearsal.title, F.text)
async def save_rehearsal_title(message: Message, state: FSMContext) -> None:
    if not message.text.strip():
        await message.answer("Название не должно быть пустым.")
        return
    await state.update_data(title=message.text.strip())
    await ask_for_day(message, state)


# ---------- Календарь ----------

async def ask_for_day(message: Message, state: FSMContext) -> None:
    today = date.today()
    await state.update_data(
        calendar_flow="show" if await state.get_state() == AddShow.category.state else "rehearsal"
    )
    await message.answer(
        "Выберите дату в календаре:",
        reply_markup=calendar_keyboard(today.year, today.month),
    )


@router.callback_query(F.data.startswith("calnav:"))
async def calendar_navigate(callback: CallbackQuery) -> None:
    _, year, month, step = callback.data.split(":")
    number = int(year) * 12 + int(month) - 1 + int(step)
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=calendar_keyboard(number // 12, number % 12 + 1)
    )


@router.callback_query(F.data.startswith("calday:"))
async def calendar_day(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    chosen_day = callback.data.split(":", 1)[1]
    data = await state.get_data()
    flow = data.get("calendar_flow")
    await callback.answer()
    if flow == "show":
        await state.update_data(day=chosen_day)
        await state.set_state(AddShow.time)
        await ask_for_time(callback.message, "show")
        return
    if flow == "rehearsal":
        await state.update_data(day=chosen_day)
        await state.set_state(AddRehearsal.start)
        await ask_for_time(callback.message, "start")


async def ask_for_time(message: Message, kind: str) -> None:
    label = {
        "start": "начала репетиции",
        "end": "окончания репетиции",
        "show": "начала спектакля",
    }[kind]
    await message.answer(f"Выберите час {label}:", reply_markup=hour_keyboard(kind))


# ---------- Время ----------

@router.callback_query(F.data.startswith("timehour:"))
async def time_hour(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    _, kind, hour = callback.data.split(":")
    await callback.answer()

    if kind == "show":
        value = f"{hour}:00"
        await state.update_data(time=value)
        data = await state.get_data()
        database.add_show(callback.from_user.id, data)
        await state.clear()
        from handlers.common import show_menu
        await show_menu(
            callback.message,
            f"✅ Сохранил: {data['title']}, {friendly_day(data['day'])} в {value}. "
            f"Цена — {database.prices(callback.from_user.id)[data['category']]} ₽.",
        )
        return

    # Репетиция (start / end) — показываем выбор минут
    await callback.message.edit_reply_markup(reply_markup=minute_keyboard(kind, hour))


@router.callback_query(F.data.startswith("timeback:"))
async def time_back(callback: CallbackQuery) -> None:
    _, kind = callback.data.split(":")
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=hour_keyboard(kind))


@router.callback_query(F.data.startswith("timemin:"))
async def time_minute(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    _, kind, hour, minute = callback.data.split(":")
    value = f"{hour}:{minute}"
    await callback.answer(value)
    await state.update_data(**{kind: value})

    if kind == "start":
        await state.set_state(AddRehearsal.end)
        await ask_for_time(callback.message, "end")
        return

    # kind == "end" — репетиция завершена
    await save_rehearsal(callback.message, state, database, callback.from_user.id)


@router.callback_query(F.data.startswith("timeskip:"))
async def time_skip(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    _, kind = callback.data.split(":")
    await callback.answer()
    if kind == "start":
        await state.update_data(start=None, end=None)
        await save_rehearsal(callback.message, state, database, callback.from_user.id)
        return
    await state.update_data(end=None)
    await save_rehearsal(callback.message, state, database, callback.from_user.id)


async def save_rehearsal(
    message: Message,
    state: FSMContext,
    database: Database,
    telegram_user_id: int,
) -> None:
    from handlers.common import show_menu
    data = await state.get_data()
    database.add_rehearsal(telegram_user_id, data)
    units = rehearsal_units(data.get("start"), data.get("end"))
    await state.clear()
    price = database.prices(telegram_user_id).get("Репетиция", 750)
    await show_menu(
        message,
        f"✅ Репетиция «{data['title']}» на {friendly_day(data['day'])} сохранена. "
        f"Засчитано: {units}. Цена — {units * price} ₽.",
    )