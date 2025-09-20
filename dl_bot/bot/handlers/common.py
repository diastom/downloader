from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from ...utils import database

router = Router()

@router.message(CommandStart())
async def handle_start(message: types.Message):
    """
    Handler for the /start command. Greets the user and sets up the main keyboard.
    """
    user = message.from_user
    user_data = database.get_user_data(user.id)

    # Update username if it has changed
    if user_data.get('username') != user.username:
        user_data['username'] = user.username
        database.update_user_data(user.id, user_data)

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
async def handle_help(message: types.Message):
    """
    Handler for the /help command or "راهنما" button. Displays the help text.
    """
    texts_db = database.get_texts()
    help_text = texts_db.get("help_text", "متن راهنما هنوز تنظیم نشده است.")
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
