import logging
from pathlib import Path
from aiogram import Router, types, F
from aiogram.filters import StateFilter
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
    choosing_thumbnail = State()
    choosing_watermark = State()

# --- Helper Functions ---

async def get_encode_panel(state: FSMContext) -> tuple[str, InlineKeyboardMarkup]:
    """Generates the text and keyboard for the encoding panel."""
    data = await state.get_data()
    options = data.get("options", {})
    size_mb = data.get('file_size', 0) / (1024 * 1024)

    selected_quality = options.get('selected_quality', 'original')
    quality_text = f"{selected_quality}p" if selected_quality != 'original' else "Original"

    panel_lines = [
        "🎬 پنل تنظیمات انکد",
        "────────────────────",
        f"• نام فایل: `{data.get('filename')}`",
        f"• حجم تقریبی: `{size_mb:.2f} MB`",
        f"• کیفیت خروجی: `{quality_text}`",
    ]

    if options.get("thumb"):
        thumb_label = options.get("thumb_name") or (
            f"شماره {options['thumb_index']}" if options.get("thumb_index") else None
        )
        if thumb_label:
            panel_lines.append(f"🖼️ تامبنیل انتخاب شده: {thumb_label}")

    if options.get("water") and options.get("watermark_name"):
        panel_lines.append(f"💧 واترمارک انتخاب شده: {options['watermark_name']}")

    panel_lines.append("")
    panel_lines.append(
        "با دکمه‌های زیر می‌توانید هر گزینه را فعال یا غیرفعال کنید و در پایان «شروع عملیات» را بزنید."
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

    text = "\n".join(panel_lines)
    return text, keyboard

# --- Handlers ---

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

async def _enter_encode_panel(message: types.Message, state: FSMContext):
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


@router.message(StateFilter(UserFlow.encoding), F.video)
async def handle_encode_video_entry(message: types.Message, state: FSMContext):
    """Entry point for the advanced encoding panel when the user is already in encode mode."""
    await _enter_encode_panel(message, state)


@router.message(StateFilter(None, UserFlow.main_menu, UserFlow.downloading), F.video)
async def auto_start_encode(message: types.Message, state: FSMContext):
    """Automatically switches to encode mode when a video is received."""
    await state.set_state(UserFlow.encoding)
    await _enter_encode_panel(message, state)

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

    if action == "thumb":
        if options[action]:
            thumbnails = await database.get_user_thumbnails(session, user_id)
            if not thumbnails:
                options[action] = False
                await query.answer("ابتدا باید با /thumb حداقل یک تامبنیل تنظیم کنید.", show_alert=True)
            elif len(thumbnails) == 1:
                options["thumb_id"] = thumbnails[0].id
                options["thumb_index"] = 1
                options["thumb_name"] = thumbnails[0].display_name or "تامبنیل 1"
                await query.answer("تامبنیل شما فعال شد.")
            else:
                await state.update_data(options=options)
                await state.set_state(EncodeFSM.choosing_thumbnail)
                buttons = []
                for idx, thumb in enumerate(thumbnails):
                    name = thumb.display_name or f"تامبنیل {idx + 1}"
                    buttons.append([InlineKeyboardButton(text=name, callback_data=f"enc_thumb_{thumb.id}")])
                buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="enc_thumb_back")])
                await query.message.edit_text(
                    "لطفاً یکی از تامبنیل‌های خود را برای اعمال انتخاب کنید:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                )
                await query.answer("یک تامبنیل انتخاب کنید.")
                return
        else:
            options.pop("thumb_id", None)
            options.pop("thumb_index", None)
            options.pop("thumb_name", None)

    if action == "water":
        if options[action]:
            watermarks = await database.get_user_watermarks(session, user_id)
            if not watermarks:
                options[action] = False
                await query.answer("ابتدا باید با /water حداقل یک واترمارک بسازید.", show_alert=True)
            elif len(watermarks) == 1:
                options["watermark_id"] = watermarks[0].id
                options["watermark_name"] = watermarks[0].display_name or "واترمارک 1"
                if not watermarks[0].enabled:
                    await query.answer("این واترمارک غیرفعال است. برای فعال‌سازی از /water استفاده کنید.", show_alert=True)
                else:
                    await query.answer("واترمارک شما فعال شد.")
            else:
                await state.update_data(options=options)
                await state.set_state(EncodeFSM.choosing_watermark)
                buttons = []
                for idx, watermark in enumerate(watermarks, start=1):
                    name = watermark.display_name or f"واترمارک {idx}"
                    status = "✅" if watermark.enabled else "❌"
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"{status} {name}",
                            callback_data=f"enc_water_{watermark.id}"
                        )
                    ])
                buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="enc_water_back")])
                await query.message.edit_text(
                    "لطفاً یکی از واترمارک‌های خود را برای اعمال انتخاب کنید:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                )
                await query.answer("یک واترمارک انتخاب کنید.")
                return
        else:
            options.pop("watermark_id", None)
            options.pop("watermark_name", None)

    await state.update_data(options=options)

    if action == "rename" and options[action]:
        await state.set_state(EncodeFSM.awaiting_new_name)
        await query.message.edit_text("لطفاً نام جدید فایل را (بدون پسوند) ارسال کنید:", reply_markup=None)
    else:
        panel_text, keyboard = await get_encode_panel(state)
        await query.message.edit_text(panel_text, reply_markup=keyboard)
    if action != "thumb" or not options[action]:
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

    if options.get("thumb") and not options.get("thumb_id"):
        await query.answer("لطفاً یکی از تامبنیل‌های خود را انتخاب کنید.", show_alert=True)
        return

    if options.get("water"):
        watermark_id = options.get("watermark_id")
        if not watermark_id:
            await query.answer("لطفاً یکی از واترمارک‌های خود را انتخاب کنید.", show_alert=True)
            return

        watermark_settings = await database.get_user_watermark_by_id(session, user_id, watermark_id)
        if watermark_settings is None:
            await query.answer("واترمارک انتخاب‌شده پیدا نشد. لطفاً دوباره انتخاب کنید.", show_alert=True)
            return
        if not watermark_settings.enabled:
            await query.answer("واترمارک انتخاب‌شده غیرفعال است. لطفاً از /water آن را فعال کنید.", show_alert=True)
            return

    can_start, limit, used_today = await database.can_user_start_task(session, user_id, task_type="encode")
    if not can_start:
        await query.answer(database.format_task_limit_message("encode", limit, used_today), show_alert=True)
        return

    await database.record_task_usage(session, user_id, "encode")

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


@router.callback_query(EncodeFSM.choosing_thumbnail, F.data == "enc_thumb_back")
async def handle_thumbnail_back(query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    options = data.get("options", {})
    options["thumb"] = False
    options.pop("thumb_id", None)
    options.pop("thumb_index", None)
    await state.update_data(options=options)

    await state.set_state(EncodeFSM.choosing_options)
    panel_text, keyboard = await get_encode_panel(state)
    await query.message.edit_text(panel_text, reply_markup=keyboard)
    await query.answer("انتخاب تامبنیل لغو شد.")


@router.callback_query(EncodeFSM.choosing_thumbnail, F.data.startswith("enc_thumb_"))
async def handle_thumbnail_selected(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    thumb_id_str = query.data.replace("enc_thumb_", "")
    try:
        thumb_id = int(thumb_id_str)
    except ValueError:
        await query.answer("شناسه تامبنیل نامعتبر است.", show_alert=True)
        return

    thumbnails = await database.get_user_thumbnails(session, query.from_user.id)
    index = None
    for idx, thumb in enumerate(thumbnails, start=1):
        if thumb.id == thumb_id:
            index = idx
            break

    if index is None:
        await query.answer("این تامبنیل موجود نیست یا حذف شده است.", show_alert=True)
        return

    data = await state.get_data()
    options = data.get("options", {})
    options["thumb"] = True
    options["thumb_id"] = thumb_id
    options["thumb_index"] = index
    options["thumb_name"] = thumbnails[index - 1].display_name or f"تامبنیل {index}"
    await state.update_data(options=options)

    await state.set_state(EncodeFSM.choosing_options)
    panel_text, keyboard = await get_encode_panel(state)
    await query.message.edit_text(panel_text, reply_markup=keyboard)
    await query.answer("تامبنیل انتخاب شد.")


@router.callback_query(EncodeFSM.choosing_watermark, F.data == "enc_water_back")
async def handle_watermark_back(query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    options = data.get("options", {})
    options["water"] = False
    options.pop("watermark_id", None)
    options.pop("watermark_name", None)
    await state.update_data(options=options)

    await state.set_state(EncodeFSM.choosing_options)
    panel_text, keyboard = await get_encode_panel(state)
    await query.message.edit_text(panel_text, reply_markup=keyboard)
    await query.answer("انتخاب واترمارک لغو شد.")


@router.callback_query(EncodeFSM.choosing_watermark, F.data.startswith("enc_water_"))
async def handle_watermark_selected(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    watermark_id_str = query.data.replace("enc_water_", "")
    try:
        watermark_id = int(watermark_id_str)
    except ValueError:
        await query.answer("شناسه واترمارک نامعتبر است.", show_alert=True)
        return

    watermark = await database.get_user_watermark_by_id(session, query.from_user.id, watermark_id)
    if not watermark:
        await query.answer("این واترمارک موجود نیست یا حذف شده است.", show_alert=True)
        return

    data = await state.get_data()
    options = data.get("options", {})
    options["water"] = True
    options["watermark_id"] = watermark_id
    options["watermark_name"] = watermark.display_name or "واترمارک انتخابی"
    await state.update_data(options=options)

    await state.set_state(EncodeFSM.choosing_options)
    panel_text, keyboard = await get_encode_panel(state)
    await query.message.edit_text(panel_text, reply_markup=keyboard)
    if watermark.enabled:
        await query.answer("واترمارک انتخاب شد.")
    else:
        await query.answer("این واترمارک در حال حاضر غیرفعال است. لطفاً از /water آن را فعال کنید.", show_alert=True)

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
