"""Хендлеры: «Мой месяц», просмотр записей, удаление, скачивание акта."""

from datetime import datetime
import asyncio
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from act import make_act
from config import EMOJI_REHEARSAL, EMOJI_SHOW, BUTTON_MAX_LENGTH, truncate
from database import Database
from keyboards import main_keyboard, month_keyboard
from utils import friendly_day, month_now


router = Router()


class PickMonth(StatesGroup):
    month = State()


# ---------- Меню выбора месяца ----------

@router.callback_query(F.data == "month:menu")
async def month_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("За какой месяц показать записи?", reply_markup=month_keyboard("view"))


@router.callback_query(F.data.startswith("view:"))
async def view_month(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    value = callback.data.split(":")[1]
    await callback.answer()
    if value == "custom":
        await state.set_state(PickMonth.month)
        await state.update_data(purpose="view")
        await callback.message.answer("Напишите месяц в формате ГГГГ-ММ, например 2026-10")
        return
    await send_month(callback.message, callback.from_user.id, month_now(int(value)), database)


@router.message(PickMonth.month, F.text)
async def custom_month(message: Message, state: FSMContext, database: Database) -> None:
    try:
        month = datetime.strptime(message.text.strip(), "%Y-%m").strftime("%Y-%m")
    except ValueError:
        await message.answer("Формат такой: 2026-10")
        return
    data = await state.get_data()
    await state.clear()
    if data["purpose"] == "view":
        await send_month(message, message.from_user.id, month, database)
    else:
        await send_act(message, message.from_user.id, month, database)


# ---------- Формирование сообщения ----------

def _short_date(day: str) -> str:
    """'2026-09-30' → '30.09'."""
    return datetime.strptime(day, "%Y-%m-%d").strftime("%d.%m")


_MONTHS_RU_NOM = {
    "01": "Январь", "02": "Февраль", "03": "Март", "04": "Апрель",
    "05": "Май", "06": "Июнь", "07": "Июль", "08": "Август",
    "09": "Сентябрь", "10": "Октябрь", "11": "Ноябрь", "12": "Декабрь",
}


def _format_month(month: str) -> str:
    """'2026-09' → 'Сентябрь 2026'."""
    year, mon = month.split("-")
    return f"{_MONTHS_RU_NOM.get(mon, mon)} {year}"


async def send_month(message: Message, user_id: int, month: str, database: Database) -> None:
    shows = database.month_rows("shows", user_id, month)
    rehearsals = database.month_rows("rehearsals", user_id, month)
    user_prices = database.prices(user_id)

    rehearsal_units_total = sum(row["units"] for row in rehearsals)
    rehearsal_price = user_prices.get("Репетиция", 750)
    total = (
        sum(row["price"] or 0 for row in shows)
        + rehearsal_units_total * rehearsal_price
    )

    text = [f"📅 <b>{_format_month(month)}</b>", ""]
    if shows or rehearsals:
        text.append(f"💰 Заработано: <b>{total} ₽</b>")
        text.append(f"🎭 Спектаклей: {len(shows)}")
        text.append(f"🎬 Репетиций: {len(rehearsals)}")
        text.append("")
        text.append("<i>Чтобы удалить запись, нажмите на соотвествующую кнопку ниже.</i>")
    else:
        text.append("Пока пусто. Добавьте первую запись.")

    keyboard_rows = []

    if shows:
        from config import short_category
        text.append("\n<b>Спектакли:</b>")
        for row in shows:
            time_text = f", {row['show_time']}" if row["show_time"] else ""
            category = short_category(row["category"] or "Роль второго плана")
            text.append(
                f"• {friendly_day(row['day'])} — {row['title']}{time_text} — {category}"
            )
            keyboard_rows.append([_show_delete_button(row)])


    if rehearsals:
        text.append("\n<b>Репетиции:</b>")
        for row in rehearsals:
            clock = "" if not row["time_start"] else f" ({row['time_start']}–{row['time_end'] or '?'})"
            units = row["units"]
            text.append(
                f"• {friendly_day(row['day'])} — {row['title']}{clock} — "
                f"{units} × {rehearsal_price} = {units * rehearsal_price} ₽"
            )
            keyboard_rows.append([_rehearsal_delete_button(row)])

    keyboard_rows.append([InlineKeyboardButton(text="← В меню", callback_data="menu")])
    await message.answer(
        "\n".join(text),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
    )

def _show_delete_button(row) -> InlineKeyboardButton:
    from config import short_category
    title = truncate(row["title"], 12)
    time_text = f", {row['show_time']}" if row["show_time"] else ""
    category = short_category(row["category"] or "Роль второго плана")
    label = f"{EMOJI_SHOW} Спект. {title} — {_short_date(row['day'])}{time_text} — {category}"
    label = truncate(label, BUTTON_MAX_LENGTH)
    return InlineKeyboardButton(text=label, callback_data=f"delete:shows:{row['id']}")

def _rehearsal_delete_button(row) -> InlineKeyboardButton:
    title = truncate(row["title"], 12)
    clock = "" if not row["time_start"] else f" ({row['time_start']}–{row['time_end'] or '?'})"
    label = f"{EMOJI_REHEARSAL} Реп. {title} — {_short_date(row['day'])}{clock}"
    label = truncate(label, BUTTON_MAX_LENGTH)
    return InlineKeyboardButton(text=label, callback_data=f"delete:rehearsals:{row['id']}")


# ---------- Удаление ----------

@router.callback_query(F.data.startswith("delete:"))
async def delete_record(callback: CallbackQuery, database: Database) -> None:
    _, table, record = callback.data.split(":")
    deleted = database.delete(table, int(record), callback.from_user.id)
    await callback.answer("Запись удалена" if deleted else "Запись уже удалена")
    if deleted:
        await callback.message.answer(
            "✅ Удалил запись. Нажмите «Мой месяц», чтобы увидеть обновлённый список.",
            reply_markup=main_keyboard(),
        )


# ---------- Скачать акт ----------

@router.callback_query(F.data == "act:current")
async def act_current(callback: CallbackQuery, database: Database) -> None:
    await callback.answer()
    await send_act(callback.message, callback.from_user.id, month_now(), database)


async def send_act(message: Message, user_id: int, month: str, database: Database) -> None:
    path = await asyncio.to_thread(make_act, user_id, month, database)
    await message.answer_document(
        FSInputFile(path),
        caption=f"Готово. Акт за {month}.",
        reply_markup=main_keyboard(),
    )