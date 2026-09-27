"""Подписка на цитаты: /subscribe, /unsubscribe, кнопка отписки."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import Database


router = Router()


def _unsub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔕 Отписаться от цитат", callback_data="quotes:unsubscribe")],
    ])


@router.message(Command("subscribe"))
async def subscribe(message: Message, database: Database) -> None:
    database.set_quotes_subscribed(message.from_user.id, True)
    await message.answer(
        "✅ Ты снова подписан на «Цитату дня».\n\n"
        "Она приходит раз в день в 12:00 по Москве.",
    )


@router.message(Command("unsubscribe"))
async def unsubscribe(message: Message, database: Database) -> None:
    database.set_quotes_subscribed(message.from_user.id, False)
    await message.answer(
        "🔕 Ты отписан от «Цитаты дня».\n\n"
        "Вернуться можно командой /subscribe.",
    )


@router.callback_query(F.data == "quotes:unsubscribe")
async def unsubscribe_callback(callback: CallbackQuery, database: Database) -> None:
    database.set_quotes_subscribed(callback.from_user.id, False)
    await callback.answer("Отписал")
    await callback.message.answer(
        "🔕 Ты отписан от «Цитаты дня».\n\n"
        "Вернуться можно командой /subscribe.",
    )