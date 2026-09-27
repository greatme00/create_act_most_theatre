"""Загрузка переменных окружения из .env."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def load_env() -> None:
    """Читает .env и кладёт переменные в os.environ (не перезаписывая уже заданные)."""
    file = BASE_DIR / ".env"
    if not file.exists():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Загружаем сразу при импорте модуля
load_env()