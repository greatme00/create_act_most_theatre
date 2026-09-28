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

def detect_gender(full_name: str) -> str:
    """Определяет пол по ФИО. Возвращает 'm' или 'f'.

    Логика:
    - Если ФИО из 3 частей — берём отчество (3-й элемент).
      Отчество на «-овна», «-евна», «-ична», «-инична» → женский.
    - Если из 2 частей — берём имя (2-й элемент).
      Имя на «-а», «-я», «-ия», «-ья» → женский.
    - Иначе — по умолчанию 'm'.
    """
    parts = full_name.strip().split()
    if len(parts) < 2:
        return "m"

    # Если есть отчество (3 части: Фамилия Имя Отчество)
    if len(parts) >= 3:
        middle = parts[2].lower()
        female_suffixes = ("овна", "евна", "ична", "инична")
        if any(middle.endswith(suf) for suf in female_suffixes):
            return "f"
        # Отчество явно мужское (на «-ович», «-евич», «-ич»)
        if middle.endswith(("ович", "евич", "ич")):
            return "m"

    # Если 2 части (Фамилия Имя) или отчество не распознано — по имени
    first = parts[1].lower()
    if first.endswith(("а", "я", "ия", "ья")):
        return "f"
    return "m"

def load_quotes(path) -> list[tuple[str, str, str]]:
    """Читает quotes.txt. Формат строки: Тема|Текст|Источник."""
    if not path.exists():
        return []
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) < 2:
            continue
        theme = parts[0].strip()
        text = parts[1].strip()
        source = parts[2].strip() if len(parts) > 2 else ""
        if text:
            result.append((theme, text, source))
    return result


def format_quote(theme: str, text: str, source: str) -> str:
    """Формирует текст сообщения с цитатой."""
    lines = ["🎭 <b>Цитата дня</b>"]
    if theme:
        lines.append(f"\n<b>{theme}</b>")
    lines.append(f"\n«{text}»")
    if source:
        lines.append(f"\n— К.С. Станиславский, {source}")
    return "\n".join(lines)