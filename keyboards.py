"""Клавиатуры (inline-кнопки) для бота."""

import calendar

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import SHOW_CATEGORIES, PRICE_CATEGORIES


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить спектакль", callback_data="add:show")],
        [InlineKeyboardButton(text="➕ Добавить репетицию", callback_data="add:rehearsal")],
        [InlineKeyboardButton(text="📅 Мой месяц", callback_data="month:menu")],
        [InlineKeyboardButton(text="📄 Скачать акт", callback_data="act:current")],
        [InlineKeyboardButton(text="💳 Мои цены", callback_data="prices")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ])


def month_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Текущий месяц", callback_data=f"{action}:0"),
         InlineKeyboardButton(text="Прошлый месяц", callback_data=f"{action}:-1")],
        [InlineKeyboardButton(text="Ввести другой месяц", callback_data=f"{action}:custom")],
        [InlineKeyboardButton(text="← В меню", callback_data="menu")],
    ])


def calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    names = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
             "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")
    buttons = [[
        InlineKeyboardButton(text="‹", callback_data=f"calnav:{year}:{month}:-1"),
        InlineKeyboardButton(text=f"{names[month - 1]} {year}", callback_data="ignore"),
        InlineKeyboardButton(text="›", callback_data=f"calnav:{year}:{month}:1"),
    ], [InlineKeyboardButton(text=weekday, callback_data="ignore")
        for weekday in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")]]
    for week in calendar.monthcalendar(year, month):
        buttons.append([InlineKeyboardButton(
            text=str(day) if day else "·",
            callback_data=f"calday:{year}-{month:02d}-{day:02d}" if day else "ignore",
        ) for day in week])
    buttons.append([InlineKeyboardButton(text="Отмена", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def hour_keyboard(kind: str) -> InlineKeyboardMarkup:
    if kind == "show":
        hours = list(range(10, 22))           # 10:00 – 21:00
    elif kind == "start":
        hours = list(range(10, 23))           # 10:00 – 22:00
    else:  # end — окончание репетиции
        # 10:00 ... 23:00, 00:00, 01:00
        hours = list(range(10, 24)) + [0, 1]

    rows = []
    for i in range(0, len(hours), 6):
        row = [InlineKeyboardButton(text=f"{h:02d}", callback_data=f"timehour:{kind}:{h:02d}")
               for h in hours[i:i + 6]]
        rows.append(row)
    if kind != "show":
        rows.append([InlineKeyboardButton(text="Не указывать", callback_data=f"timeskip:{kind}")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def minute_keyboard(kind: str, hour: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=minute, callback_data=f"timemin:{kind}:{hour}:{minute}")
         for minute in ("00", "15", "30", "45")],
        [InlineKeyboardButton(text="← Выбрать другой час", callback_data=f"timeback:{kind}")],
        [InlineKeyboardButton(text="Отмена", callback_data="menu")],
    ])


def show_category_keyboard(user_prices: dict[str, int]) -> InlineKeyboardMarkup:
    """Кнопки выбора категории спектакля с актуальными ценами пользователя."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{name} — {user_prices.get(name, price)} ₽",
            callback_data=f"category:{index}",
        )]
        for index, (name, price) in enumerate(SHOW_CATEGORIES.items())
    ])


def prices_keyboard(user_prices: dict[str, int]) -> InlineKeyboardMarkup:
    """Меню «Мои цены» — 5 категорий + кнопка «В меню»."""
    rows = [
        [InlineKeyboardButton(
            text=f"{category}: {user_prices[category]} ₽",
            callback_data=f"price:{index}",
        )]
        for index, category in enumerate(PRICE_CATEGORIES)
    ]
    rows.append([InlineKeyboardButton(text="← В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)