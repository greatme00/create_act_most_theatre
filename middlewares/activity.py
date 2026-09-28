"""Middleware: логирует активность пользователей."""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from database import Database


class ActivityMiddleware(BaseMiddleware):
    """Пишет в user_activity каждое сообщение и callback."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        database: Database = data["database"]
        user = data.get("event_from_user")
        if user:
            action = type(event).__name__.lower()
            try:
                database.log_activity(user.id, action)
            except Exception:
                pass  # логирование не должно ломать обработку
        return await handler(event, data)