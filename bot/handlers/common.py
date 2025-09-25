from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)

from sqlalchemy.ext.asyncio import AsyncSession
from utils import database

router = Router()

# --- States for the main user flow ---
class UserFlow(StatesGroup):
    main_menu = State()
    downloading = State()
    encoding = State()

def get_main_menu_keyboard():
    """Returns the main menu inline keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 دانلود", callback_data="start_download")],
        [InlineKeyboardButton(text="🎬 انکد", callback_data="start_encode")]
    ])

def get_main_reply_keyboard():
    """Returns the main persistent reply keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="راهنما 📚")]],
        resize_keyboard=True
    )

def get_task_done_keyboard():
    """Returns the keyboard for the task done message."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 دانلود", callback_data="start_download")],
        [InlineKeyboardButton(text="🎬 انکد", callback_data="start_encode")]
    ])

@router.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext, session: AsyncSession):
    """
    Handler for the /start command. Greets the user and shows the main menu.
    """
    user = message.from_user
    await database.get_or_create_user(session, user_id=user.id, username=user.username)
    await state.set_state(UserFlow.main_menu)

    start_message = "خوش آمدید!"
    await message.answer(start_message, reply_markup=get_main_reply_keyboard())

    menu_message = "لطفا یکی از گزینه های زیر را انتخاب کنید:"
    await message.answer(menu_message, reply_markup=get_main_menu_keyboard())

@router.callback_query(F.data == "start_download")
async def start_download_flow(query: types.CallbackQuery, state: FSMContext):
    """Sets the user state to downloading and asks for a link."""
    await state.set_state(UserFlow.downloading)
    await query.message.edit_text(
        "شما در حالت دانلود هستید.\n\n"
        "لطفا لینک ویدیوی مورد نظر خود را ارسال کنید."
    )
    await query.answer()

@router.callback_query(F.data == "start_encode")
async def start_encode_flow(query: types.CallbackQuery, state: FSMContext):
    """Sets the user state to encoding and asks for a video."""
    await state.set_state(UserFlow.encoding)
    await query.message.edit_text(
        "شما در حالت انکد هستید.\n\n"
        "لطفا ویدیوی خود را برای اعمال واترمارک و/یا تامبنیل ارسال کنید.\n\n"
        "توجه: شما باید از قبل با دستورات /thumb و /water تنظیمات را انجام داده باشید."
    )
    await query.answer()


@router.message(F.text == "راهنما 📚")
@router.message(Command("help"))
async def handle_help(message: types.Message, session: AsyncSession):
    """
    Handler for the /help command. Displays the help text.
    """
    help_text = await database.get_text(session, key="help_text", default="متن راهنما هنوز تنظیم نشده است.")
    await message.answer(help_text)


@router.message(Command("cancel"))
async def handle_cancel(message: types.Message, state: FSMContext):
    """
    Universal command to cancel any active FSM state and return to the main menu.
    """
    current_state = await state.get_state()
    if current_state is None or current_state == UserFlow.main_menu:
        await message.answer("در حال حاضر در هیچ عملیاتی نیستید. برای شروع /start را بزنید.", reply_markup=ReplyKeyboardRemove())
        return

    await state.set_state(UserFlow.main_menu)
    await message.answer("عملیات لغو شد. به منوی اصلی بازگشتید.", reply_markup=get_main_menu_keyboard())

# Callback handler to return to the main menu
@router.callback_query(F.data == "return_to_main_menu")
async def return_to_main_menu(query: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserFlow.main_menu)
    await query.message.edit_text(
        "به منوی اصلی بازگشتید. لطفا یک گزینه را انتخاب کنید:",
        reply_markup=get_main_menu_keyboard()
    )
    await query.answer()