"""Сборка всех роутеров в один."""

from aiogram import Router

from handlers import (
    common,
    user,
    prices,
    month,
    admin,
    broadcast,
    profile,
    fallback,
)


def get_main_router() -> Router:
    """Возвращает главный роутер с подключёнными подроутерами.

    fallback подключается последним, чтобы не перехватывать сообщения,
    которые должны обрабатывать FSM-хендлеры.
    """
    main = Router()
    main.include_router(common.router)
    main.include_router(user.router)
    main.include_router(prices.router)
    main.include_router(month.router)
    main.include_router(admin.router)
    main.include_router(broadcast.router)
    main.include_router(profile.router)
    main.include_router(fallback.router)
    return main