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
    """Returns the quick action inline keyboard for post-task prompts."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 ارسال لینک جدید", callback_data="start_download")],
        [InlineKeyboardButton(text="🎬 ارسال ویدیوی جدید", callback_data="start_encode")]
    ])

def get_main_reply_keyboard():
    """Returns the main persistent reply keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="راهنما 📚")]],
        resize_keyboard=True
    )

def get_task_done_keyboard():
    """Legacy helper kept for compatibility; no keyboard is attached now."""
    return None

@router.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext, session: AsyncSession):
    """
    Handler for the /start command. Greets the user and shows the main menu.
    """
    user = message.from_user
    await database.get_or_create_user(session, user_id=user.id, username=user.username)
    await state.set_state(UserFlow.main_menu)

    start_message = (
        "خوش آمدید!\n\n"
        "کافیست لینک یکی از سایت‌های پشتیبانی‌شده را بفرستید تا دانلود شروع شود، یا ویدیوی خود را ارسال کنید تا وارد پنل انکد شوید."
    )
    await message.answer(start_message, reply_markup=get_main_reply_keyboard())

@router.callback_query(F.data == "start_download")
async def start_download_flow(query: types.CallbackQuery, state: FSMContext):
    """Reminds the user how to begin a download."""
    await state.set_state(UserFlow.downloading)
    await query.message.edit_text(
        "برای شروع دانلود کافیست لینک خود را بفرستید."
    )
    await query.answer()

@router.callback_query(F.data == "start_encode")
async def start_encode_flow(query: types.CallbackQuery, state: FSMContext):
    """Reminds the user how to begin an encode."""
    await state.set_state(UserFlow.encoding)
    await query.message.edit_text(
        "برای ورود به پنل انکد، ویدیوی مورد نظر خود را ارسال کنید."
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
    await message.answer(
        "عملیات لغو شد. می‌توانید لینک یا ویدیوی جدیدی ارسال کنید.",
        reply_markup=get_main_menu_keyboard(),
    )

# Callback handler to return to the main menu
@router.callback_query(F.data == "return_to_main_menu")
async def return_to_main_menu(query: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserFlow.main_menu)
    await query.message.edit_text(
        "به صفحه اصلی بازگشتید. برای شروع کافیست لینک یا ویدیوی خود را بفرستید.",
        reply_markup=get_main_menu_keyboard()
    )
    await query.answer()
