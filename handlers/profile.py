"""Хендлеры «Мой профиль»."""

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


router = Router()


class ProfileEdit(StatesGroup):
    full_name = State()
    contract_number = State()


# ---------- Меню профиля ----------

@router.callback_query(F.data == "profile")
async def profile_menu(callback: CallbackQuery, database: Database) -> None:
    await callback.answer()
    p = database.profile(callback.from_user.id)
    if not p:
        await callback.message.answer("Профиль не найден. Начните с /start.")
        return

    status_label = {
        "self_employed": "Самозанятый",
        "gph": "Физлицо по ГПХ",
    }.get(p["status"] or "self_employed", "—")

    gender_label = "Мужской" if (p["gender"] or "m") == "m" else "Женский"

    text = (
        f"👤 <b>Мой профиль</b>\n\n"
        f"ФИО: <b>{p['full_name']}</b>\n"
        f"Статус: {status_label}\n"
        f"Пол: {gender_label}\n"
        f"Договор: {p['contract_number'] or '—'}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить ФИО", callback_data="prof:name")],
        [InlineKeyboardButton(text="📝 Изменить договор", callback_data="prof:contract")],
        [InlineKeyboardButton(text="⚙️ Статус", callback_data="prof:status")],
        [InlineKeyboardButton(text="⚧ Пол", callback_data="prof:gender")],
        [InlineKeyboardButton(text="← В меню", callback_data="menu")],
    ])
    await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ---------- Изменение ФИО ----------

@router.callback_query(F.data == "prof:name")
async def prof_name_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(ProfileEdit.full_name)
    await callback.message.answer("Введите новое ФИО:")


@router.message(ProfileEdit.full_name, F.text)
async def prof_name_save(message: Message, state: FSMContext, database: Database) -> None:
    name = message.text.strip()
    if len(name.split()) < 2:
        await message.answer("Нужно как минимум имя и фамилия.")
        return
    database.set_user_name(message.from_user.id, name)
    await state.clear()
    await message.answer("✅ ФИО обновлено.")


# ---------- Изменение договора ----------

@router.callback_query(F.data == "prof:contract")
async def prof_contract_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(ProfileEdit.contract_number)
    await callback.message.answer("Введите новый номер договора (или «-» чтобы очистить):")


@router.message(ProfileEdit.contract_number, F.text)
async def prof_contract_save(message: Message, state: FSMContext, database: Database) -> None:
    text = message.text.strip()
    new_contract = None if text == "-" else text
    database.set_user_contract(message.from_user.id, new_contract)
    await state.clear()
    await message.answer("✅ Договор обновлён.")


# ---------- Изменение статуса ----------

@router.callback_query(F.data == "prof:status")
async def prof_status(callback: CallbackQuery) -> None:
    await callback.answer()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Самозанятый", callback_data="prof_set:status:self_employed")],
        [InlineKeyboardButton(text="Физлицо по ГПХ", callback_data="prof_set:status:gph")],
        [InlineKeyboardButton(text="← Назад", callback_data="profile")],
    ])
    await callback.message.answer("Выберите статус:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("prof_set:status:"))
async def prof_status_save(callback: CallbackQuery, database: Database) -> None:
    status = callback.data.split(":")[2]
    await callback.answer()
    database.set_user_status(callback.from_user.id, status)
    label = "Самозанятый" if status == "self_employed" else "Физлицо по ГПХ"
    await callback.message.edit_text(f"✅ Статус обновлён: <b>{label}</b>.", parse_mode="HTML")


# ---------- Изменение пола ----------

@router.callback_query(F.data == "prof:gender")
async def prof_gender(callback: CallbackQuery) -> None:
    await callback.answer()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мужской", callback_data="prof_set:gender:m")],
        [InlineKeyboardButton(text="Женский", callback_data="prof_set:gender:f")],
        [InlineKeyboardButton(text="← Назад", callback_data="profile")],
    ])
    await callback.message.answer("Выберите пол:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("prof_set:gender:"))
async def prof_gender_save(callback: CallbackQuery, database: Database) -> None:
    gender = callback.data.split(":")[2]
    await callback.answer()
    database.set_user_gender(callback.from_user.id, gender)
    label = "Мужской" if gender == "m" else "Женский"
    await callback.message.edit_text(f"✅ Пол обновлён: <b>{label}</b>.", parse_mode="HTML")