"""Общие хендлеры: /start, /cancel, /help, кнопка «В меню»."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import Database
from keyboards import main_keyboard

router = Router()


async def show_menu(message: Message, text: str = "Что делаем?") -> None:
    await message.answer(text, reply_markup=main_keyboard())


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, database: Database) -> None:
    await state.clear()
    if not database.profile(message.from_user.id):
        from handlers.user import ProfileForm
        await state.set_state(ProfileForm.full_name)
        await message.answer(
            "Для первого акта напишите ФИО полностью. "
            "Например: Славутин Евгений Иосифович"
        )
        return
    await show_menu(
        message,
        "Привет! Я помогу вести учет спектаклей и репетиций.\n\n"
        "Выберите действие ниже.",
    )


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_menu(message, "Ладнр, ничего не сохранял.")


@router.callback_query(F.data == "menu")
async def button_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.answer("Что делаем?", reply_markup=main_keyboard())


@router.callback_query(F.data == "help")
async def help_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "• Добавляйте спектакли и репетиции по шагам.\n"
        "• «Мой месяц» показывает записи и позволяет удалить ошибочную.\n"
        "• «Скачать акт» создаёт Word-файл.\n\n"
        "В любой момент отправьте /cancel, чтобы отменить ввод.",
        reply_markup=main_keyboard(),
    )


@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery) -> None:
    await callback.answer()