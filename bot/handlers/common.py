from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from sqlalchemy.ext.asyncio import AsyncSession
from utils import database

router = Router()

@router.message(CommandStart())
async def handle_start(message: types.Message, session: AsyncSession):
    """
    Handler for the /start command. Greets the user and sets up the main keyboard.
    """
    user = message.from_user
    # The get_or_create_user function now also handles username updates
    await database.get_or_create_user(session, user_id=user.id, username=user.username)

    start_message = (
        "سلام! به ربات مولتی دانلودر خوش اومدید\n"
        "یک لینک از سایت های پشتیبانی شده بفرستید تا شروع به کار کنم"
    )

    user_keyboard = [
        [KeyboardButton(text="راهنما")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard=user_keyboard, resize_keyboard=True)

    await message.answer(start_message, reply_markup=reply_markup)


@router.message(Command("help"))
@router.message(lambda message: message.text == "راهنما")
async def handle_help(message: types.Message, session: AsyncSession):
    """
    Handler for the /help command or "راهنما" button. Displays the help text.
    """
    help_text = await database.get_text(session, key="help_text", default="متن راهنما هنوز تنظیم نشده است.")
    await message.answer(help_text)


@router.message(Command("cancel"))
async def handle_cancel(message: types.Message, state: FSMContext):
    """
    Universal command to cancel any active conversation (FSM).
    """
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("در حال حاضر در هیچ عملیاتی نیستید.", reply_markup=ReplyKeyboardRemove())
        return

    await state.clear()
    await message.answer("عملیات لغو شد.", reply_markup=ReplyKeyboardRemove())
