"""Обработка простых текстовых сообщений (когда пользователь не в FSM)."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

router = Router()


@router.message(F.text)
async def fallback(message: Message, state: FSMContext) -> None:
    # Если пользователь в FSM-состоянии (ввод ФИО, названия и т.д.) — не перехватываем
    current = await state.get_state()
    if current is not None:
        return
    from handlers.common import show_menu
    await message.answer("Я пока не умею болтать. Работаю только по делу.")
    await show_menu(message)