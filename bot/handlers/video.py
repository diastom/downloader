import logging
from pathlib import Path
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.handlers.common import UserFlow
from tasks import video_tasks
from utils import database

logger = logging.getLogger(__name__)
router = Router()

class EncodeFSM(StatesGroup):
    choosing_options = State()
    awaiting_new_name = State()
    choosing_quality = State()

# --- Helper Functions ---

async def get_encode_panel(state: FSMContext) -> tuple[str, InlineKeyboardMarkup]:
    """Generates the text and keyboard for the encoding panel."""
    data = await state.get_data()
    options = data.get("options", {})
    size_mb = data.get('file_size', 0) / (1024 * 1024)

    selected_quality = options.get('selected_quality', 'original')
    quality_text = f"{selected_quality}p" if selected_quality != 'original' else "Original"

    panel_text = (
        f"🎬 **پنل تنظیمات انکد**\n\n"
        f"🔹 **نام فایل:** `{data.get('filename')}`\n"
        f"🔹 **حجم تقریبی:** `{size_mb:.2f} MB`\n"
        f"🔹 **کیفیت خروجی:** `{quality_text}`\n\n"
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
        [InlineKeyboardButton(text="🌇 انتخاب کیفیت", callback_data="enc_select_quality")],
        [InlineKeyboardButton(text="🚀 شروع عملیات", callback_data="enc_start")],
        [InlineKeyboardButton(text="انصراف ❌", callback_data="enc_cancel")]
    ])
    return panel_text, keyboard


@router.callback_query(EncodeFSM.choosing_options, F.data == "enc_select_quality")
async def handle_select_quality_button(query: types.CallbackQuery, state: FSMContext):
    """Shows the quality selection menu."""
    await state.set_state(EncodeFSM.choosing_quality)
    qualities = ["original", "1080", "720", "480", "360", "240"]

    keyboard_buttons = []
    for quality in qualities:
        text = f"{quality}p" if quality != "original" else "Original Quality"
        keyboard_buttons.append([InlineKeyboardButton(text=text, callback_data=f"enc_quality_{quality}")])

    keyboard_buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="enc_quality_back")])

    await query.message.edit_text(
        "لطفاً کیفیت مورد نظر برای خروجی را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )
    await query.answer()

@router.callback_query(EncodeFSM.choosing_quality, F.data.startswith("enc_quality_"))
async def handle_set_quality(query: types.CallbackQuery, state: FSMContext):
    """Saves the selected quality and returns to the main encode panel."""
    action = query.data.replace("enc_quality_", "")

    if action == "back":
        await state.set_state(EncodeFSM.choosing_options)
        panel_text, keyboard = await get_encode_panel(state)
        await query.message.edit_text(panel_text, reply_markup=keyboard)
        await query.answer()
        return

    data = await state.get_data()
    options = data.get("options", {})
    options['selected_quality'] = action
    await state.update_data(options=options)

    await state.set_state(EncodeFSM.choosing_options)
    panel_text, keyboard = await get_encode_panel(state)
    await query.message.edit_text(panel_text, reply_markup=keyboard)
    await query.answer(f"کیفیت خروجی روی {action}p تنظیم شد.")

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
    await state.update_data(**initial_data)
    panel_text, keyboard = await get_encode_panel(state)
    await message.answer(panel_text, reply_markup=keyboard)

@router.callback_query(EncodeFSM.choosing_options, F.data.startswith("enc_toggle_"))
async def handle_toggle_option(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Toggles the selected option and redraws the panel."""
    action = query.data.replace("enc_toggle_", "")
    user_id = query.from_user.id

    # Check for subscription access before allowing the toggle
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
        await query.answer("خطا: شما اعمال تامبنیل را انتخاب کرده‌اید اما تامبنیلی تنظیم نکرده‌اید. لطفاً با /thumb تنظیم کنید و دوباره امتحان کنید.", show_alert=True)
        return

    watermark_settings = await database.get_user_watermark_settings(session, user_id)
    if options.get("water") and not watermark_settings.enabled:
        await query.answer("خطا: شما اعمال واترمارک را انتخاب کرده‌اید اما واترمارک شما غیرفعال است. لطفاً با /water آن را فعال کنید و دوباره امتحان کنید.", show_alert=True)
        return

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

@router.message(EncodeFSM.awaiting_new_name, F.text)
async def receive_new_filename(message: types.Message, state: FSMContext):
    """Receives the new filename and returns to the panel."""
    data = await state.get_data()
    original_ext = Path(data['original_filename']).suffix
    new_filename = f"{message.text.strip()}{original_ext}"
    await state.update_data(filename=new_filename)

    await state.set_state(EncodeFSM.choosing_options)
    panel_text, keyboard = await get_encode_panel(state)
    await message.answer(panel_text, reply_markup=keyboard)
    await message.delete()

@router.callback_query(EncodeFSM.choosing_options, F.data == "enc_cancel")
async def handle_cancel_encoding(query: types.CallbackQuery, state: FSMContext):
    await query.message.delete()
    await state.clear()
    await query.answer("عملیات لغو شد.")