"""Хендлеры меню «Мои цены»."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import PRICE_CATEGORIES
from database import Database
from keyboards import prices_keyboard


router = Router()


class PriceForm(StatesGroup):
    amount = State()


@router.callback_query(F.data == "prices")
async def prices_menu(callback: CallbackQuery, database: Database) -> None:
    await callback.answer()
    user_prices = database.prices(callback.from_user.id)
    await callback.message.answer(
        "Текущие цены. Нажмите категорию, чтобы изменить цену:",
        reply_markup=prices_keyboard(user_prices),
    )


@router.callback_query(F.data.startswith("price:"))
async def price_pick(callback: CallbackQuery, state: FSMContext) -> None:
    index = int(callback.data.split(":")[1])
    if index < 0 or index >= len(PRICE_CATEGORIES):
        await callback.answer("Ошибка: неизвестная категория", show_alert=True)
        return
    category = PRICE_CATEGORIES[index]
    await callback.answer()
    await state.update_data(price_category=category)
    await state.set_state(PriceForm.amount)
    await callback.message.answer(f"Новая цена для «{category}» в рублях — только целое число:")


@router.message(PriceForm.amount, F.text)
async def price_save(message: Message, state: FSMContext, database: Database) -> None:
    from handlers.common import show_menu
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите положительное целое число, например 1000.")
        return
    data = await state.get_data()
    database.save_price(message.from_user.id, data["price_category"], amount)
    await state.clear()
    await show_menu(message, "✅ Цена сохранена.")