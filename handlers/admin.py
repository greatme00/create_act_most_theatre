"""Хендлеры админки: пользователи, админы."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import SUPER_ADMIN_IDS
from database import Database


router = Router()


class AdminSetValue(StatesGroup):
    name = State()
    contract = State()


# ---------- Меню админки ----------

@router.message(Command("admin"))
async def admin_menu(message: Message, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    text = (
        "🛠 <b>Админка</b>\n\n"
        "<b>Текст акта:</b>\n"
        "/edit_act — редактировать блоки акта\n\n"
        "<b>Пользователи:</b>\n"
        "/users — список всех пользователей\n"
        "/user [id] — подробно про пользователя\n"
        "/del_user [id] — удалить пользователя\n"
        "/set_name [id] [ФИО] — изменить ФИО\n"
        "/set_contract [id] [номер] — изменить договор\n\n"
        "<b>Администраторы:</b>\n"
        "/admins — список админов\n"
        "/add_admin [id] — добавить админа\n"
        "/del_admin [id] — удалить админа\n\n"
        "<b>Рассылка:</b>\n"
        "/broadcast — отправить сообщение всем пользователям\n"
    )
    await message.answer(text, parse_mode="HTML")


# ---------- Список пользователей (карточки с кнопками) ----------

@router.message(Command("users"))
async def admin_users(message: Message, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        return
    users = database.list_users()
    if not users:
        await message.answer("Пользователей в базе нет.")
        return

    await message.answer("👥 <b>Пользователи:</b>", parse_mode="HTML")

    for u in users:
        contract = u["contract_number"] or "—"
        text = (
            f"👤 <b>{u['full_name']}</b>\n"
            f"ID: <code>{u['user_id']}</code>\n"
            f"Договор: {contract}\n"
            f"Показов: {u['shows_count']}, репетиций: {u['rehearsals_count']}"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ ФИО", callback_data=f"adm:name:{u['user_id']}"),
                InlineKeyboardButton(text="📝 Договор", callback_data=f"adm:contract:{u['user_id']}"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Статус", callback_data=f"adm:status:{u['user_id']}"),
                InlineKeyboardButton(text="⚧ Пол", callback_data=f"adm:gender:{u['user_id']}"),
            ],
            [
                InlineKeyboardButton(text="📊 Подробнее", callback_data=f"adm:info:{u['user_id']}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:del:{u['user_id']}"),
            ],
        ])
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ---------- Команды управления пользователями ----------

@router.message(Command("user"))
async def admin_user(message: Message, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("Формат: /user [id]")
        return
    uid = int(parts[1].strip())
    user = database.get_user(uid)
    if not user:
        await message.answer(f"Пользователь {uid} не найден.")
        return
    contract = user["contract_number"] or "—"
    stats = database.user_stats(uid)
    await message.answer(
        f"👤 <b>{user['full_name']}</b>\n"
        f"ID: <code>{uid}</code>\n"
        f"Договор: {contract}\n"
        f"Показов: {stats['shows']}\n"
        f"Репетиций: {stats['rehearsals']}",
        parse_mode="HTML",
    )


@router.message(Command("del_user"))
async def admin_del_user(message: Message, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("Формат: /del_user [id]")
        return
    uid = int(parts[1].strip())
    if database.delete_user(uid):
        await message.answer(f"✅ Пользователь {uid} и все его данные удалены.")
    else:
        await message.answer(f"Пользователь {uid} не найден.")


@router.message(Command("set_name"))
async def admin_set_name(message: Message, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].strip().isdigit():
        await message.answer("Формат: /set_name [id] [ФИО]")
        return
    uid = int(parts[1].strip())
    new_name = parts[2].strip()
    if database.set_user_name(uid, new_name):
        await message.answer(f"✅ ФИО пользователя {uid} изменено на «{new_name}».")
    else:
        await message.answer(f"Пользователь {uid} не найден.")


@router.message(Command("set_contract"))
async def admin_set_contract(message: Message, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].strip().isdigit():
        await message.answer("Формат: /set_contract [id] [номер]")
        return
    uid = int(parts[1].strip())
    new_contract = parts[2].strip()
    if database.set_user_contract(uid, new_contract):
        await message.answer(f"✅ Договор пользователя {uid} изменён на «{new_contract}».")
    else:
        await message.answer(f"Пользователь {uid} не найден.")


# ---------- Управление админами ----------

@router.message(Command("admins"))
async def admin_list_admins(message: Message, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        return
    admins = database.list_admins()
    lines = ["👑 <b>Администраторы:</b>\n"]
    for sid in SUPER_ADMIN_IDS:
        lines.append(f"• <code>{sid}</code> — супер-админ (нельзя удалить)")
    for row in admins:
        lines.append(f"• <code>{row['user_id']}</code> — добавлен {row['added_at']}")
    if not admins:
        lines.append("\nОбычных админов нет.")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("add_admin"))
async def admin_add_admin(message: Message, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("Формат: /add_admin [id]")
        return
    uid = int(parts[1].strip())
    if uid in SUPER_ADMIN_IDS:
        await message.answer("Это супер-админ, он и так админ.")
        return
    if database.add_admin(uid, message.from_user.id):
        await message.answer(f"✅ Пользователь <code>{uid}</code> теперь админ.", parse_mode="HTML")
    else:
        await message.answer(f"Пользователь <code>{uid}</code> уже админ.", parse_mode="HTML")


@router.message(Command("del_admin"))
async def admin_del_admin(message: Message, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("Формат: /del_admin [id]")
        return
    uid = int(parts[1].strip())
    if uid in SUPER_ADMIN_IDS:
        await message.answer("Супер-админа удалить нельзя.")
        return
    if database.remove_admin(uid):
        await message.answer(f"✅ Пользователь <code>{uid}</code> больше не админ.", parse_mode="HTML")
    else:
        await message.answer(f"Пользователь <code>{uid}</code> не был админом.", parse_mode="HTML")


# ---------- Кнопки на карточках пользователей ----------

@router.callback_query(F.data.startswith("adm:name:"))
async def admin_cb_name(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.split(":")[2])
    await callback.answer()
    await state.update_data(admin_target_uid=uid)
    await state.set_state(AdminSetValue.name)
    await callback.message.answer(
        f"Введите новое ФИО для пользователя <code>{uid}</code>:",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("adm:contract:"))
async def admin_cb_contract(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.split(":")[2])
    await callback.answer()
    await state.update_data(admin_target_uid=uid)
    await state.set_state(AdminSetValue.contract)
    await callback.message.answer(
        f"Введите новый номер договора для пользователя <code>{uid}</code>:\n"
        f"Если нужно очистить — отправьте минус: -",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("adm:info:"))
async def admin_cb_info(callback: CallbackQuery, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.split(":")[2])
    await callback.answer()
    user = database.get_user(uid)
    if not user:
        await callback.message.answer(f"Пользователь {uid} не найден.")
        return
    stats = database.user_stats(uid)
    contract = user["contract_number"] or "—"
    status_label = {
        "self_employed": "Самозанятый",
        "gph": "Физлицо по ГПХ",
    }.get(user["status"] or "self_employed", "—")
    gender_label = "Мужской" if (user["gender"] or "m") == "m" else "Женский"
    await callback.message.answer(
        f"👤 <b>{user['full_name']}</b>\n"
        f"ID: <code>{uid}</code>\n"
        f"Статус: {status_label}\n"
        f"Пол: {gender_label}\n"
        f"Договор: {contract}\n"
        f"Показов: {stats['shows']}\n"
        f"Репетиций: {stats['rehearsals']}",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("adm:del:"))
async def admin_cb_delete(callback: CallbackQuery, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.split(":")[2])
    await callback.answer()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"adm:confirm_del:{uid}"),
        InlineKeyboardButton(text="← Отмена", callback_data="adm:cancel"),
    ]])
    await callback.message.answer(
        f"⚠️ Удалить пользователя <code>{uid}</code> со всеми данными?",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("adm:confirm_del:"))
async def admin_cb_confirm_delete(callback: CallbackQuery, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.split(":")[2])
    if database.delete_user(uid):
        await callback.answer("Удалено", show_alert=True)
        await callback.message.edit_text(f"✅ Пользователь <code>{uid}</code> удалён.", parse_mode="HTML")
    else:
        await callback.answer("Не найден", show_alert=True)
        await callback.message.edit_text(f"Пользователь <code>{uid}</code> не найден.", parse_mode="HTML")


@router.callback_query(F.data == "adm:cancel")
async def admin_cb_cancel(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text("Отменено.")


# ---------- Статус пользователя ----------

@router.callback_query(F.data.startswith("adm:status:"))
async def admin_cb_status(callback: CallbackQuery, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.split(":")[2])
    await callback.answer()
    p = database.get_user(uid)
    current = (p["status"] if p else None) or "—"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Самозанятый", callback_data=f"adm_set:status:{uid}:self_employed")],
        [InlineKeyboardButton(text="Физлицо по ГПХ", callback_data=f"adm_set:status:{uid}:gph")],
        [InlineKeyboardButton(text="← Отмена", callback_data="adm:cancel")],
    ])
    await callback.message.answer(
        f"Текущий статус: <b>{current}</b>\nВыберите новый:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("adm_set:status:"))
async def admin_set_status(callback: CallbackQuery, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, _, uid, status = callback.data.split(":")
    uid = int(uid)
    if database.set_user_status(uid, status):
        label = "Самозанятый" if status == "self_employed" else "Физлицо по ГПХ"
        await callback.answer("Обновлено", show_alert=True)
        await callback.message.edit_text(
            f"✅ Статус пользователя <code>{uid}</code>: <b>{label}</b>.",
            parse_mode="HTML",
        )
    else:
        await callback.answer("Не найден", show_alert=True)


# ---------- Пол пользователя ----------

@router.callback_query(F.data.startswith("adm:gender:"))
async def admin_cb_gender(callback: CallbackQuery, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.split(":")[2])
    await callback.answer()
    p = database.get_user(uid)
    current = (p["gender"] if p else None) or "—"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мужской", callback_data=f"adm_set:gender:{uid}:m")],
        [InlineKeyboardButton(text="Женский", callback_data=f"adm_set:gender:{uid}:f")],
        [InlineKeyboardButton(text="← Отмена", callback_data="adm:cancel")],
    ])
    await callback.message.answer(
        f"Текущий пол: <b>{current}</b>\nВыберите новый:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("adm_set:gender:"))
async def admin_set_gender(callback: CallbackQuery, database: Database) -> None:
    if not database.is_admin_db(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, _, uid, gender = callback.data.split(":")
    uid = int(uid)
    if database.set_user_gender(uid, gender):
        label = "Мужской" if gender == "m" else "Женский"
        await callback.answer("Обновлено", show_alert=True)
        await callback.message.edit_text(
            f"✅ Пол пользователя <code>{uid}</code>: <b>{label}</b>.",
            parse_mode="HTML",
        )
    else:
        await callback.answer("Не найден", show_alert=True)


# ---------- Ввод значений от админа ----------

@router.message(AdminSetValue.name, F.text)
async def admin_input_name(message: Message, state: FSMContext, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        return
    data = await state.get_data()
    uid = data.get("admin_target_uid")
    new_name = message.text.strip()
    if len(new_name.split()) < 2:
        await message.answer("Нужно как минимум имя и фамилия. Попробуйте ещё раз.")
        return
    if database.set_user_name(uid, new_name):
        await state.clear()
        await message.answer(
            f"✅ ФИО пользователя <code>{uid}</code> изменено на «{new_name}».",
            parse_mode="HTML",
        )
    else:
        await state.clear()
        await message.answer(f"Пользователь <code>{uid}</code> не найден.", parse_mode="HTML")


@router.message(AdminSetValue.contract, F.text)
async def admin_input_contract(message: Message, state: FSMContext, database: Database) -> None:
    if not database.is_admin_db(message.from_user.id):
        return
    data = await state.get_data()
    uid = data.get("admin_target_uid")
    text = message.text.strip()
    new_contract = None if text == "-" else text
    if database.set_user_contract(uid, new_contract):
        await state.clear()
        await message.answer(
            f"✅ Договор пользователя <code>{uid}</code> "
            f"{'очищен' if new_contract is None else f'изменён на «{new_contract}»'}.",
            parse_mode="HTML",
        )
    else:
        await state.clear()
        await message.answer(f"Пользователь <code>{uid}</code> не найден.", parse_mode="HTML")