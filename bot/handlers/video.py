import logging
from pathlib import Path
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.handlers.common import UserFlow
from bot.handlers.settings import get_watermark_panel
from tasks import video_tasks
from utils import database

logger = logging.getLogger(__name__)
router = Router()

class EncodeFSM(StatesGroup):
    choosing_options = State()
    awaiting_new_name = State()
    awaiting_thumbnail = State()
    configuring_watermark = State()

# --- Helper Functions ---

async def get_encode_panel(state: FSMContext) -> tuple[str, InlineKeyboardMarkup]:
    """Generates the text and keyboard for the encoding panel."""
    data = await state.get_data()
    options = data.get("options", {})
    size_mb = data.get('file_size', 0) / (1024 * 1024)

    panel_text = (
        f"🎬 **پنل تنظیمات انکد**\n\n"
        f"🔹 **نام فایل:** `{data.get('filename')}`\n"
        f"🔹 **حجم تقریبی:** `{size_mb:.2f} MB`\n\n"
        "با کلیک روی دکمه‌ها، گزینه‌های مورد نظر را فعال/غیرفعال کنید و سپس 'شروع عملیات' را بزنید."
    )

    rename_check = "✅" if options.get("rename") else "❌"
    thumb_check = "✅" if options.get("thumb") else "❌"
    water_check = "✅" if options.get("water") else "❌"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"تغییر نام فایل {rename_check}", callback_data="enc_toggle_rename"),
            InlineKeyboardButton(text=f"اعمال تامبنیل {thumb_check}", callback_data="enc_toggle_thumb")
        ],
        [InlineKeyboardButton(text=f"اعمال واترمارک {water_check}", callback_data="enc_toggle_water")],
        [InlineKeyboardButton(text="🚀 شروع عملیات", callback_data="enc_start")],
        [InlineKeyboardButton(text="انصراف ❌", callback_data="enc_cancel")]
    ])
    return panel_text, keyboard

# --- Handlers ---

@router.message(UserFlow.encoding, F.video)
async def handle_encode_video_entry(message: types.Message, state: FSMContext):
    """Entry point for the advanced encoding panel."""
    await state.set_state(EncodeFSM.choosing_options)
    initial_data = {
        "video_file_id": message.video.file_id,
        "original_filename": message.video.file_name or "video.mp4",
        "filename": message.video.file_name or "video.mp4",
        "file_size": message.video.file_size,
        "options": {"rename": False, "thumb": False, "water": False}
    }
    panel_text, keyboard = await get_encode_panel(state)
    panel_message = await message.answer(panel_text, reply_markup=keyboard)
    initial_data["panel_message_id"] = panel_message.message_id
    await state.update_data(initial_data)

@router.callback_query(EncodeFSM.choosing_options, F.data.startswith("enc_toggle_"))
async def handle_toggle_option(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Toggles the selected option and redraws the panel."""
    action = query.data.replace("enc_toggle_", "")
    user_id = query.from_user.id

    # Check for subscription access before toggling the option
    if action == "thumb":
        if not await database.has_feature_access(session, user_id, 'thumbnail'):
            await query.answer("اشتراک شما شامل قابلیت تامبنیل نمی‌شود.", show_alert=True)
            return
    elif action == "water":
        if not await database.has_feature_access(session, user_id, 'watermark'):
            await query.answer("اشتراک شما شامل قابلیت واترمارک نمی‌شود.", show_alert=True)
            return

    data = await state.get_data()
    options = data.get("options", {})
    options[action] = not options.get(action, False)
    await state.update_data(options=options)

    if action == "rename" and options[action]:
        await state.set_state(EncodeFSM.awaiting_new_name)
        await query.message.edit_text("لطفاً نام جدید فایل را (بدون پسوند) ارسال کنید:", reply_markup=None)
    else:
        panel_text, keyboard = await get_encode_panel(state)
        await query.message.edit_text(panel_text, reply_markup=keyboard)
    await query.answer()

@router.callback_query(EncodeFSM.choosing_options, F.data == "enc_start")
async def handle_start_button(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Checks prerequisites and starts the encoding task if they are met."""
    data = await state.get_data()
    options = data.get("options", {})
    user_id = query.from_user.id

    if options.get("thumb") and not await database.get_user_thumbnail(session, user_id):
        await state.set_state(EncodeFSM.awaiting_thumbnail)
        await query.message.edit_text("شما گزینه تامبنیل را انتخاب کرده‌اید اما تامبنیلی تنظیم نکرده‌اید. لطفاً یک عکس برای تامبنیل ارسال کنید.")
        return await query.answer()

    watermark_settings = await database.get_user_watermark_settings(session, user_id)
    if options.get("water") and not watermark_settings.enabled:
        await state.set_state(EncodeFSM.configuring_watermark)
        text, keyboard = await get_watermark_panel(session, user_id)
        await query.message.edit_text(
            "شما گزینه واترمارک را انتخاب کرده‌اید اما واترمارک شما غیرفعال است. لطفاً آن را فعال کرده و سپس 'Close Panel' را بزنید تا به این پنل بازگردید.",
            reply_markup=keyboard
        )
        return await query.answer()

    await query.message.edit_text("✅ درخواست شما به صف انکد اضافه شد...")
    video_tasks.encode_video_task.delay(
        user_id=user_id,
        username=query.from_user.username or "N/A",
        chat_id=query.message.chat.id,
        video_file_id=data['video_file_id'],
        options=options,
        new_filename=data.get('filename')
    )
    await state.clear()
    await query.answer()

@router.message(EncodeFSM.awaiting_new_name, F.text)
async def receive_new_filename(message: types.Message, state: FSMContext):
    """Receives the new filename and returns to the panel."""
    data = await state.get_data()
    original_ext = Path(data['original_filename']).suffix
    new_filename = f"{message.text.strip()}{original_ext}"
    await state.update_data(filename=new_filename)

    await state.set_state(EncodeFSM.choosing_options)
    panel_text, keyboard = await get_encode_panel(state)
    # Re-show the panel by editing the original prompt message
    panel_message_id = data.get("panel_message_id")
    if panel_message_id:
        try:
            await message.bot.edit_message_text(chat_id=message.chat.id, message_id=panel_message_id, text=panel_text, reply_markup=keyboard)
        except Exception: pass # Ignore if message is not modified
    await message.delete() # Delete the user's text message for cleanliness

@router.message(EncodeFSM.awaiting_thumbnail, F.photo)
async def receive_thumbnail_and_return(message: types.Message, state: FSMContext, session: AsyncSession):
    """Receives the thumbnail and returns the user to the main panel."""
    await database.set_user_thumbnail(session, user_id=message.from_user.id, file_id=message.photo[-1].file_id)
    await message.answer("✅ تامبنیل تنظیم شد. به پنل انکد بازگشتید.")

    await state.set_state(EncodeFSM.choosing_options)
    panel_text, keyboard = await get_encode_panel(state)
    data = await state.get_data()
    panel_message_id = data.get("panel_message_id")
    if panel_message_id:
        await message.bot.edit_message_text(chat_id=message.chat.id, message_id=panel_message_id, text=panel_text, reply_markup=keyboard)

@router.callback_query(EncodeFSM.configuring_watermark, F.data == "wm_close")
async def return_from_watermark(query: types.CallbackQuery, state: FSMContext):
    """Returns the user to the encoding panel after they close the watermark panel."""
    await query.answer("بازگشت به پنل انکد...")
    await state.set_state(EncodeFSM.choosing_options)
    panel_text, keyboard = await get_encode_panel(state)
    await query.message.edit_text(panel_text, reply_markup=keyboard)

@router.callback_query(EncodeFSM.choosing_options, F.data == "enc_cancel")
async def handle_cancel_encoding(query: types.CallbackQuery, state: FSMContext):
    await query.message.delete()
    await state.clear()
    await query.answer("عملیات لغو شد.")