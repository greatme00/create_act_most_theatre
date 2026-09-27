"""Константы и настройки бота."""

import os
from pathlib import Path

# env импортируется первым, чтобы .env загрузился до чтения переменных
import env  # noqa: F401

# ---------- Пути ----------
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "data.sqlite3"
ACTS_DIR = BASE_DIR / "acts"

# ---------- Категории спектаклей (для добавления показа) ----------
SHOW_CATEGORIES = {
    "Главная роль": 1500,
    "Роль первого плана": 1250,
    "Роль второго плана": 1000,
    "Массовка": 750,
}

# ---------- Категории для меню «Мои цены» (спектакли + репетиция) ----------
PRICE_CATEGORIES = list(SHOW_CATEGORIES.keys()) + ["Репетиция"]

# ---------- Дефолтные цены ----------
DEFAULT_PRICES = {**SHOW_CATEGORIES, "Репетиция": 750}

# ---------- Супер-админы (из .env) ----------
SUPER_ADMIN_IDS = {
    int(x)
    for x in os.getenv("SUPER_ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}


def is_super_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMIN_IDS