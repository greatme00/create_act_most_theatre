"""Редактор текстов акта (только для админов)."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import Database, DEFAULT_ACT_TEXTS


router = Router()


# ---------- Секции и блоки ----------

# Формат: секция → список (key, label, profile_scope)
# profile_scope: None — общий, "self_employed" — только для самозанятого, "gph" — только для ГПХ

SECTIONS = [
    ("Преамбула", [
        ("common.preamble_theater", "🏛 Театр", None),
        ("common.preamble_position", "🏛 Заказчик", None),
        ("__performer_label__", "🏛 Исполнитель", "dynamic"),
        ("common.preamble_footer", "🏛 Финал", None),
    ]),
    ("Договор и период", [
        ("common.contract_text", "📄 Договор (с номером)", None),
        ("common.contract_text_empty", "📄 Договор (без номера)", None),
        ("common.period_text", "📅 Период услуг", None),
    ]),
    ("Таблица", [
        ("common.service_show", "💼 Услуга: показ", None),
        ("common.service_rehearsal", "💼 Услуга: репетиция", None),
        ("common.rehearsal_theater", "🏛 Репетиции: театр", None),
    ]),
    ("После таблицы", [
        ("common.obligations", "✅ Обязательства", None),
        ("common.total_label", "💰 Сумма (префикс)", None),
        ("common.payment_terms", "💳 Условия оплаты", None),
        ("common.copies_text", "📋 Копии акта", None),
    ]),
    ("Налоги (только ГПХ)", [
        ("gph.tax_ndfl", "💸 НДФЛ 13%", "gph"),
        ("gph.insurance_fees", "💸 Страховые взносы 30%", "gph"),
        ("gph.insurance_responsibility", "💸 Обязанности по взносам", "gph"),
    ]),
    ("Подписи", [
        ("common.signature_customer_title", "✍️ Заказчик: заголовок", None),
        ("common.signature_customer_position", "✍️ Заказчик: должность", None),
        ("common.signature_customer_name", "✍️ Заказчик: ФИО", None),
        ("common.signature_performer_title", "✍️ Исполнитель: заголовок", None),
        ("__signature_performer_label__", "✍️ Исполнитель: метка", "dynamic"),
        ("common.signature_performer_name", "✍️ Исполнитель: ФИО", None),
    ]),
]


# Плейсхолдеры, доступные в конкретных блоках
BLOCK_PLACEHOLDERS = {
    "common.contract_text": "{contract_number}",
    "common.contract_text_empty": "{contract_number}",
    "common.period_text": "{period}",
    "gph.tax_ndfl": "{ndfl_amount}",
    "gph.insurance_fees": "{insurance_amount}",
    "common.signature_performer_name": "{sign_name}",
}


# Тестовые значения для предпросмотра
PREVIEW_VALUES = {
    "full_name": "Иванов Иван Иванович",
    "sign_name": "И.И. Иванов",
    "contract_number": "123-456/2026",
    "period": "с 1 сентября 2026 г. по 30 сентября 2026 г.",
    "month": "2026-09",
    "year": "2026",
    "gender_ending": "ый",
    "ndfl_amount": "1 234,56",
    "insurance_amount": "2 848,00",
}


class EditAct(StatesGroup):
    waiting_text = State()


# ---------- Вспомогательные ----------

def _get_blocks_for_profile(profile: str) -> list[tuple[str, str, str]]:
    """Возвращает плоский список блоков для профиля.
    
    Динамические блоки (__performer_label__, __signature_performer_label__) 
    разворачиваются в 2 конкретных ключа для m/f.
    """
    result = []
    for section_name, blocks in SECTIONS:
        for key, label, scope in blocks:
            if scope == "dynamic":
                if key == "__performer_label__":
                    # Разворачивается в 2 блока: m и f
                    if profile == "self_employed":
                        result.append(("self_employed.preamble_performer_label_m",
                                       f"{label} (муж.)", section_name))
                        result.append(("self_employed.preamble_performer_label_f",
                                       f"{label} (жен.)", section_name))
                    else:
                        result.append(("gph.preamble_performer_label_m",
                                       f"{label} (муж.)", section_name))
                        result.append(("gph.preamble_performer_label_f",
                                       f"{label} (жен.)", section_name))
                elif key == "__signature_performer_label__":
                    if profile == "self_employed":
                        result.append(("self_employed.signature_performer_label_m",
                                       f"{label} (муж.)", section_name))
                        result.append(("self_employed.signature_performer_label_f",
                                       f"{label} (жен.)", section_name))
                    else:
                        result.append(("gph.signature_performer_label_m",
                                       f"{label} (муж.)", section_name))
                        result.append(("gph.signature_performer_label_f",
                                       f"{label} (жен.)", section_name))
                continue
            # Обычный блок
            if scope is None or scope == profile:
                result.append((key, label, section_name))
    return result


def _build_menu(profile: str) -> InlineKeyboardMarkup:
    """Меню блоков для профиля, сгруппированное по секциям."""
    blocks = _get_blocks_for_profile(profile)

    # Переключатель профиля
    se_mark = "✅ " if profile == "self_employed" else ""
    gph_mark = "✅ " if profile == "gph" else ""
    rows = [
        [
            InlineKeyboardButton(text=f"{se_mark}Самозанятый",
                                 callback_data="acted_profile:self_employed"),
            InlineKeyboardButton(text=f"{gph_mark}ГПХ",
                                 callback_data="acted_profile:gph"),
        ]
    ]

    # Блоки по секциям
    current_section = None
    for key, label, section in blocks:
        if section != current_section:
            current_section = section
            # Заголовок секции — не кнопка, а «разделитель» (кнопка с ignore)
            rows.append([InlineKeyboardButton(text=f"── {section} ──",
                                              callback_data="ignore")])
        rows.append([InlineKeyboardButton(text=label, callback_data=f"acted:{key}")])

    rows.append([InlineKeyboardButton(text="← В админку", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _preview_text(raw: str) -> str:
    """Подставляет тестовые значения в плейсхолдеры для предпросмотра."""
    try:
        return raw.format(**PREVIEW_VALUES)
    except (KeyError, IndexError):
        return raw


# ---------- Меню ----------

@router.message(Command("edit_act"))
async def edit_act_menu(message: Message, database: Database, state: FSMContext) -> None:
    if not database.is_admin_db(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    await state.update_data(acted_profile="self_employed")
    await message.answer(
        "📝 <b>Редактор текста акта</b>\n\n"
        "Выберите профиль и блок:",
        parse_mode="HTML",
        reply_markup=_build_menu("self_employed"),
    )


@router.callback_query(F.data.startswith("acted_profile:"))
async def act_edit_switch_profile(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    profile = callback.data.split(":", 1)[1]
    await state.update_data(acted_profile=profile)
    await callback.answer()
    label = "Самозанятый" if profile == "self_employed" else "ГПХ"
    await callback.message.edit_text(
        f"📝 <b>Редактор текста акта</b>\n\nПрофиль: <b>{label}</b>\n\nВыберите блок:",
        parse_mode="HTML",
        reply_markup=_build_menu(profile),
    )


@router.callback_query(F.data == "acted_list")
async def act_edit_list(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    profile = data.get("acted_profile", "self_employed")
    await callback.answer()
    label = "Самозанятый" if profile == "self_employed" else "ГПХ"
    await callback.message.edit_text(
        f"📝 <b>Редактор текста акта</b>\n\nПрофиль: <b>{label}</b>\n\nВыберите блок:",
        parse_mode="HTML",
        reply_markup=_build_menu(profile),
    )


# ---------- Просмотр блока ----------

@router.callback_query(F.data.startswith("acted:"))
async def act_edit_view(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    key = callback.data.split(":", 1)[1]
    await callback.answer()

    current = database.get_act_text(key)
    raw_from_db = None
    try:
        with database.connect() as db:
            row = db.execute("SELECT text FROM act_texts WHERE key = ?", (key,)).fetchone()
            raw_from_db = row["text"] if row else None
    except Exception:
        pass

    is_custom = raw_from_db is not None
    status = "🔧 <b>Изменён</b>" if is_custom else "📌 <i>По умолчанию</i>"

    # Найти label для ключа
    label = key
    for _sec, blocks in SECTIONS:
        for k, lbl, _scope in blocks:
            if k == key:
                label = lbl
                break

    preview = _preview_text(current)

    ph = BLOCK_PLACEHOLDERS.get(key)
    ph_line = f"\n\n<i>Доступные плейсхолдеры: <code>{ph}</code></i>" if ph else ""

    # Обрезаем длинные тексты для отображения
    def _short(s: str, n: int = 600) -> str:
        s = s.strip()
        return s if len(s) <= n else s[:n] + "…"

    text = (
        f"<b>{label}</b>\n"
        f"Статус: {status}\n\n"
        f"<b>📌 Сырой текст:</b>\n<pre>{_short(current)}</pre>\n"
        f"<b>👁 В акте будет:</b>\n<pre>{_short(preview)}</pre>"
        f"{ph_line}"
    )

    rows = [
        [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"acted_edit:{key}")],
    ]
    if is_custom:
        rows.append([InlineKeyboardButton(text="🔄 Сбросить к дефолту",
                                          callback_data=f"acted_reset:{key}")])
    rows.append([InlineKeyboardButton(text="← К списку блоков", callback_data="acted_list")])

    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


# ---------- Редактирование ----------

@router.callback_query(F.data.startswith("acted_edit:"))
async def act_edit_start(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    key = callback.data.split(":", 1)[1]
    await callback.answer()
    await state.update_data(act_key=key)
    await state.set_state(EditAct.waiting_text)

    ph = BLOCK_PLACEHOLDERS.get(key)
    ph_line = f"\n\n<i>Плейсхолдеры, которые можно использовать: <code>{ph}</code></i>" if ph else ""

    await callback.message.answer(
        f"Пришлите новый текст для блока.\nОтмена: /cancel{ph_line}",
        parse_mode="HTML",
    )


@router.message(EditAct.waiting_text, F.text)
async def act_edit_save(message: Message, state: FSMContext, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        return

    new_text = message.text
    data = await state.get_data()
    key = data.get("act_key")
    if not key:
        await state.clear()
        await message.answer("Ошибка: не найден ключ блока.")
        return

    # Проверка плейсхолдеров
    try:
        new_text.format(**PREVIEW_VALUES)
    except (KeyError, IndexError, ValueError) as e:
        await message.answer(
            f"❌ Ошибка в тексте: <code>{e}</code>\n\n"
            f"Проверьте фигурные скобки — где-то пропущено <code>{{</code> или <code>}}</code>.",
            parse_mode="HTML",
        )
        return

    database.set_act_text(key, new_text)
    await state.clear()
    await message.answer(f"✅ Текст блока «{key}» обновлён.")


# ---------- Сброс ----------

@router.callback_query(F.data.startswith("acted_reset:"))
async def act_edit_reset(callback: CallbackQuery, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    key = callback.data.split(":", 1)[1]
    await callback.answer()
    database.reset_act_text(key)
    await callback.message.answer(f"✅ Блок «{key}» сброшен к дефолту.")


# ---------- Возврат в админку ----------

@router.callback_query(F.data == "admin_menu")
async def back_to_admin(callback: CallbackQuery, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    text = (
        "🛠 <b>Админка</b>\n\n"
        "<b>Текст акта:</b>\n"
        "/edit_act — редактор блоков акта\n\n"
        "<b>Пользователи:</b>\n"
        "/users — список\n"
        "/user [id] — подробно\n"
        "/del_user [id] — удалить\n"
        "/set_name [id] [ФИО]\n"
        "/set_contract [id] [номер]\n\n"
        "<b>Админы:</b>\n"
        "/admins — список\n"
        "/add_admin [id]\n"
        "/del_admin [id]\n\n"
        "<b>Рассылка:</b>\n"
        "/broadcast — всем"
    )
    await callback.message.answer(text, parse_mode="HTML")