"""Хендлеры рассылки (только для админов)."""

import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import Database


router = Router()


class BroadcastForm(StatesGroup):
    text = State()
    confirm = State()


@router.message(F.text == "/broadcast")
async def admin_broadcast_start(message: Message, state: FSMContext, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        return
    await state.set_state(BroadcastForm.text)
    await message.answer(
        "Введите текст рассылки.\n\n"
        "Он будет отправлен <b>всем пользователям</b> бота.\n"
        "Отмена: /cancel"
    )


@router.message(BroadcastForm.text, F.text)
async def admin_broadcast_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Текст не должен быть пустым. Попробуйте ещё раз.")
        return
    await state.update_data(broadcast_text=text)
    await state.set_state(BroadcastForm.confirm)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить всем", callback_data="bcast:confirm")],
        [InlineKeyboardButton(text="← Отмена", callback_data="bcast:cancel")],
    ])
    await message.answer(
        f"<b>Текст рассылки:</b>\n\n{text}\n\n"
        f"Отправить всем пользователям?",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "bcast:confirm")
async def admin_broadcast_confirm(
    callback: CallbackQuery, state: FSMContext, database: Database
) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text:
        await callback.answer("Нет текста", show_alert=True)
        return
    await callback.answer()
    await state.clear()

    user_ids = database.all_user_ids()
    total = len(user_ids)
    sent = 0
    failed = 0

    progress = await callback.message.answer(f"📤 Рассылаю... 0/{total}")

    for i, uid in enumerate(user_ids, start=1):
        try:
            await callback.bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1
        if i % 20 == 0 or i == total:
            try:
                await progress.edit_text(f"📤 Рассылаю... {i}/{total}")
            except Exception:
                pass
        await asyncio.sleep(0.05)

    await progress.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"Всего пользователей: {total}\n"
        f"Доставлено: {sent}\n"
        f"Не доставлено: {failed}",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "bcast:cancel")
async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("Рассылка отменена.")