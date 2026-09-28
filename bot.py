"""Точка входа: запуск Telegram-бота."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import env  
from config import DB_FILE, QUOTES_FILE
from database import Database
from handlers import get_main_router
from utils import load_quotes, format_quote
from middlewares.activity import ActivityMiddleware


# ---------- Фоновые задачи ----------

async def reminder_loop(bot: Bot, database: Database) -> None:
    """Раз в 10 минут проверяет напоминания (в 10:00 МСК — за день до события)."""
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    timezone = ZoneInfo("Europe/Moscow")
    while True:
        try:
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
        except Exception:
            logging.exception("Ошибка в reminder_loop")
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

async def cleanup_activity_loop(database: Database) -> None:
    """Раз в сутки удаляет активность старше 4 недель (28 дней)."""
    while True:
        try:
            deleted = database.cleanup_old_activity(keep_days=28)
            if deleted:
                logging.info("Очистка активности: удалено %s записей", deleted)
        except Exception:
            logging.exception("Ошибка в cleanup_activity_loop")
        await asyncio.sleep(86400)  # раз в сутки

async def quotes_loop(bot: Bot, database: Database) -> None:
    """Раз в день в 12:00 МСК отправляет случайную цитату подписчикам."""
    timezone = ZoneInfo("Europe/Moscow")
    last_sent_day = None

    while True:
        now = datetime.now(timezone)
        today = now.date()

        # Отправляем, если уже 12:00+ и сегодня ещё не отправляли
        if now.hour >= 12 and last_sent_day != today:
            quotes = load_quotes(QUOTES_FILE)
            if not quotes:
                logging.warning("quotes.txt пуст или не найден — рассылка пропущена")
                last_sent_day = today
                await asyncio.sleep(60)
                continue

            theme, text, source = random.choice(quotes)
            message_text = format_quote(theme, text, source)

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔕 Отписаться", callback_data="quotes:unsubscribe")],
            ])

            user_ids = database.subscribed_user_ids()
            sent = 0
            failed = 0
            for uid in user_ids:
                try:
                    await bot.send_message(uid, message_text, parse_mode="HTML", reply_markup=keyboard)
                    sent += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.05)

            logging.info("Цитата дня отправлена: %s / %s", sent, failed)
            last_sent_day = today

        await asyncio.sleep(60)  # проверяем раз в минуту

# ---------- main ----------

async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token or token.startswith("вставьте"):
        raise RuntimeError("Создайте файл .env по образцу .env.example и вставьте токен BotFather.")
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
    dp.update.middleware(ActivityMiddleware())
    dp.include_router(get_main_router())

    asyncio.create_task(reminder_loop(bot, database))
    asyncio.create_task(cleanup_acts_loop())
    asyncio.create_task(cleanup_activity_loop(database))
    asyncio.create_task(quotes_loop(bot, database))

    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())