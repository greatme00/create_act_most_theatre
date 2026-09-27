"""Утилиты: даты, парсинг, форматирование."""

from datetime import date, datetime


def month_now(offset: int = 0) -> str:
    """Возвращает текущий месяц в формате ГГГГ-ММ. offset=-1 — прошлый месяц."""
    current = date.today()
    number = current.year * 12 + current.month - 1 + offset
    return f"{number // 12:04d}-{number % 12 + 1:02d}"


def parse_time(text: str) -> str | None:
    """Принимает '19' или '19:30'. Если только час — минуты 00."""
    text = text.strip()
    if text.isdigit():
        hour = int(text)
        if 0 <= hour <= 23:
            return f"{hour:02d}:00"
        return None
    try:
        return datetime.strptime(text, "%H:%M").strftime("%H:%M")
    except ValueError:
        return None


def rehearsal_units(start: str | None, end: str | None) -> int:
    """До 3 часов — 1 единица, свыше 3 — 2, свыше 9 — 3."""
    if not start or not end:
        return 1
    start_time = datetime.strptime(start, "%H:%M")
    end_time = datetime.strptime(end, "%H:%M")
    hours = (end_time - start_time).total_seconds() / 3600
    if hours < 0:
        hours += 24
    return 3 if hours > 9 else 2 if hours > 3 else 1


def friendly_day(value: str) -> str:
    """'2026-09-30' → '30.09.2026'."""
    return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")