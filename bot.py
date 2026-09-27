"""Точка входа: запуск Telegram-бота."""

from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

import env  # noqa: F401 — загружает .env при импорте
from config import DB_FILE
from database import Database
from handlers import get_main_router


# ---------- Фоновые задачи ----------

async def reminder_loop(bot: Bot, database: Database) -> None:
    """Раз в 10 минут проверяет напоминания (в 10:00 МСК — за день до события)."""
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

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
                    await bot.send_message(
                        event["user_id"],
                        f"🔔 Напоминание: завтра{time_text} {event_name} «{event['title']}».",
                    )
                except Exception:
                    logging.exception("Could not send reminder to user %s", event["user_id"])
                else:
                    database.mark_reminder_sent(event["type"], event["id"], now.date().isoformat())
        await asyncio.sleep(600)


async def cleanup_acts_loop() -> None:
    """Раз в час удаляет акты старше 24 часов."""
    import time
    from config import ACTS_DIR

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


# ---------- main ----------

async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token or token.startswith("вставьте"):
        raise RuntimeError(
            "Создайте файл .env по образцу .env.example и вставьте токен BotFather."
        )

    proxy_url = os.getenv("PROXY_URL") or None

    database = Database(DB_FILE)
    database.initialize()

    if proxy_url:
        logging.info("Использую прокси: %s", proxy_url)
        bot = Bot(token, session=AiohttpSession(proxy=proxy_url))
    else:
        logging.info("Прокси не задан — подключаюсь напрямую")
        bot = Bot(token)

    dp = Dispatcher()
    dp["database"] = database
    dp.include_router(get_main_router())

    asyncio.create_task(reminder_loop(bot, database))
    asyncio.create_task(cleanup_acts_loop())

    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())