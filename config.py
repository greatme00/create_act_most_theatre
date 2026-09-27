"""Константы и настройки бота."""

import os
from pathlib import Path

# env импортируется первым, чтобы .env загрузился до чтения переменных
import env  # noqa: F401

# ---------- Пути ----------
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "data.sqlite3"
ACTS_DIR = BASE_DIR / "acts"
QUOTES_FILE = BASE_DIR / "quotes.txt"

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

# ---------- Короткие названия категорий (для кнопок) ----------
CATEGORY_SHORT = {
    "Главная роль": "гл. роль",
    "Роль первого плана": "1й план",
    "Роль второго плана": "2й план",
    "Массовка": "масс",
}


def short_category(category: str) -> str:
    """Короткое название категории для кнопок. Если нет маппинга — вернёт как есть."""
    return CATEGORY_SHORT.get(category, category)

# ---------- Настройки отображения кнопок ----------
SHOW_TITLE_MAX = 13          # обрезать название спектакля
REHEARSAL_TITLE_MAX = 13     # обрезать название репетиции
BUTTON_MAX_LENGTH = 60       # максимальная длина текста кнопки (Telegram)

EMOJI_SHOW = "🎭"
EMOJI_REHEARSAL = "🎬"


def truncate(text: str, limit: int) -> str:
    """Обрезает текст до limit символов, добавляя …"""
    if len(text) <= limit:
        return text
    return text[:limit] + "…"