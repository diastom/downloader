from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from sqlalchemy.ext.asyncio import AsyncSession
from utils import database, models

router = Router()

# --- Thumbnail FSM ---
class ThumbnailFSM(StatesGroup):
    panel = State()
    awaiting_photo = State()
    awaiting_display_name = State()
    awaiting_delete_choice = State()


async def get_thumbnail_panel(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup, list[models.Thumbnail]]:
    thumbnails = await database.get_user_thumbnails(session, user_id)
    count = len(thumbnails)

    text = (
        "برای تنظیم تامبنیل لطفاً یک عکس ارسال کنید. برای مدیریت، از دکمه‌های زیر استفاده کنید. دستور /cancel برای لغو عملیات"
        f"\n\n✅ تعداد تامبنیل‌های فعلی شما: {count} از 50"
    )

    buttons: list[list[InlineKeyboardButton]] = []
    if thumbnails:
        buttons.append([InlineKeyboardButton(text="حذف تامبنیل", callback_data="thumb_delete")])
    if count < 50:
        buttons.append([InlineKeyboardButton(text="اضافه کردن تامبنیل", callback_data="thumb_add")])
    if not buttons:
        buttons.append([InlineKeyboardButton(text="اضافه کردن تامبنیل", callback_data="thumb_add")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return text, keyboard, thumbnails

@router.message(Command("thumb"))
async def thumb_entry(message: types.Message, state: FSMContext, session: AsyncSession):
    """Entry point for setting a custom thumbnail."""
    if not await database.has_feature_access(session, message.from_user.id, 'thumbnail'):
        await message.answer("You do not have permission to use the thumbnail feature.")
        return

    text, keyboard, _ = await get_thumbnail_panel(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)
    await state.set_state(ThumbnailFSM.panel)


@router.callback_query(ThumbnailFSM.panel, F.data == "thumb_add")
async def thumb_add(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    thumbnails = await database.get_user_thumbnails(session, query.from_user.id)
    if len(thumbnails) >= 50:
        await query.answer("شما نمی‌توانید بیش از ۵۰ تامبنیل فعال داشته باشید.", show_alert=True)
        return

    await state.set_state(ThumbnailFSM.awaiting_photo)
    await query.message.edit_text("لطفاً یک عکس ارسال کنید تا به لیست تامبنیل‌ها اضافه شود. برای لغو /cancel را ارسال کنید.")
    await query.answer()


@router.callback_query(ThumbnailFSM.panel, F.data == "thumb_delete")
async def thumb_delete(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    _, _, thumbnails = await get_thumbnail_panel(session, query.from_user.id)
    if not thumbnails:
        await query.answer("شما هیچ تامبنیلی برای حذف ندارید.", show_alert=True)
        return

    buttons = []
    for index, thumb in enumerate(thumbnails):
        name = thumb.display_name or f"تامبنیل {index + 1}"
        buttons.append([InlineKeyboardButton(text=name, callback_data=f"thumb_del_{thumb.id}")])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="thumb_del_back")])

    await state.set_state(ThumbnailFSM.awaiting_delete_choice)
    await query.message.edit_text(
        "لطفاً تامبنیل مورد نظر برای حذف را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await query.answer()

async def _finalize_thumbnail_creation(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    display_name: str | None,
):
    data = await state.get_data()
    file_id = data.get("pending_thumbnail_file_id")
    if not file_id:
        await message.answer("⚠️ خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        await state.set_state(ThumbnailFSM.panel)
        text, keyboard, _ = await get_thumbnail_panel(session, message.from_user.id)
        await message.answer(text, reply_markup=keyboard)
        return

    try:
        thumbnail = await database.set_user_thumbnail(
            session,
            user_id=message.from_user.id,
            file_id=file_id,
            display_name=display_name,
        )
        name_text = f" ({thumbnail.display_name})" if thumbnail.display_name else ""
        await message.answer(f"✅ تامبنیل جدید{name_text} با موفقیت اضافه شد.")
    except ValueError:
        await message.answer("⚠️ شما به حداکثر تعداد مجاز (۵۰) تامبنیل رسیده‌اید.")

    await state.update_data(pending_thumbnail_file_id=None)
    text, keyboard, _ = await get_thumbnail_panel(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)
    await state.set_state(ThumbnailFSM.panel)


@router.message(ThumbnailFSM.awaiting_photo, F.photo)
async def receive_thumbnail(message: types.Message, state: FSMContext, session: AsyncSession):
    """Receives the photo and requests a display name for it."""
    file_id = message.photo[-1].file_id
    await state.update_data(pending_thumbnail_file_id=file_id)
    await state.set_state(ThumbnailFSM.awaiting_display_name)
    await message.answer(
        "لطفاً یک نام نمایشی برای این تامبنیل ارسال کنید تا در لیست قابل شناسایی باشد."
        "\nدر صورت عدم تمایل، دستور /skip را بفرستید.")

@router.message(ThumbnailFSM.awaiting_photo)
async def incorrect_thumbnail_input(message: types.Message):
    """Handles cases where the user sends something other than a photo."""
    await message.answer("ورودی نامعتبر است. لطفاً یک عکس ارسال کنید یا با /cancel عملیات را لغو کنید.")


@router.message(ThumbnailFSM.awaiting_display_name, Command("skip"))
async def skip_thumbnail_name(message: types.Message, state: FSMContext, session: AsyncSession):
    await _finalize_thumbnail_creation(message, state, session, None)


@router.message(ThumbnailFSM.awaiting_display_name, F.text)
async def receive_thumbnail_name(message: types.Message, state: FSMContext, session: AsyncSession):
    display_name = message.text.strip()
    if not display_name:
        await message.answer("نام نمایشی نمی‌تواند خالی باشد. لطفاً یک نام وارد کنید یا /skip را ارسال کنید.")
        return

    await _finalize_thumbnail_creation(message, state, session, display_name)


@router.message(ThumbnailFSM.awaiting_display_name)
async def invalid_thumbnail_name(message: types.Message):
    await message.answer("لطفاً تنها متن ارسال کنید یا برای رد شدن /skip را بزنید.")


@router.callback_query(ThumbnailFSM.awaiting_delete_choice, F.data == "thumb_del_back")
async def thumb_delete_back(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    text, keyboard, _ = await get_thumbnail_panel(session, query.from_user.id)
    await state.set_state(ThumbnailFSM.panel)
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()


@router.callback_query(ThumbnailFSM.awaiting_delete_choice, F.data.startswith("thumb_del_"))
async def thumb_delete_confirm(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    thumb_id_str = query.data.replace("thumb_del_", "")
    try:
        thumb_id = int(thumb_id_str)
    except ValueError:
        await query.answer("شناسه تامبنیل نامعتبر است.", show_alert=True)
        return

    deleted = await database.delete_user_thumbnail(session, query.from_user.id, thumb_id)
    if not deleted:
        await query.answer("این تامبنیل پیدا نشد یا قبلاً حذف شده است.", show_alert=True)
        return

    await query.answer("تامبنیل حذف شد.")
    text, keyboard, _ = await get_thumbnail_panel(session, query.from_user.id)
    await state.set_state(ThumbnailFSM.panel)
    await query.message.edit_text(text, reply_markup=keyboard)


# --- Watermark FSM ---
class WatermarkFSM(StatesGroup):
    panel = State()
    awaiting_text = State()
    awaiting_color = State()
    awaiting_display_name = State()


async def get_watermark_panel(
    session: AsyncSession,
    user_id: int,
    selected_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup, list[models.WatermarkSetting], models.WatermarkSetting | None]:
    """Builds the panel text and keyboard for managing watermark profiles."""

    watermarks = await database.get_user_watermarks(session, user_id)
    selected = None
    selected_index = 0
    if watermarks:
        if selected_id is not None:
            for idx, wm in enumerate(watermarks):
                if wm.id == selected_id:
                    selected = wm
                    selected_index = idx
                    break
        if selected is None:
            selected = watermarks[0]
            selected_index = 0

    count = len(watermarks)
    text_lines = [
        "⚙️ **پنل مدیریت واترمارک**",
        "",
        f"✅ تعداد واترمارک‌های فعلی شما: {count} از 50",
    ]

    position_text_map = {
        "top_left": "بالا چپ",
        "top_right": "بالا راست",
        "bottom_left": "پایین چپ",
        "bottom_right": "پایین راست",
    }

    if selected:
        status_text = "فعال" if selected.enabled else "غیرفعال"
        status_emoji = "✅" if selected.enabled else "❌"
        display_name = selected.display_name or f"واترمارک {selected_index + 1}"
        pos_text = position_text_map.get(selected.position, selected.position)
        text_lines.extend([
            "",
            f"▪️ واترمارک انتخاب‌شده: **{display_name}**",
            f"▪️ وضعیت: {status_emoji} **{status_text}**",
            f"▪️ متن: `{selected.text}`",
            f"▪️ موقعیت: **{pos_text}**",
            f"▪️ اندازه فونت: **{selected.size}**",
            f"▪️ رنگ: `{selected.color}`",
            f"▪️ ضخامت دورخط: **{selected.stroke}**",
        ])
    else:
        text_lines.append("")
        text_lines.append("برای شروع روی «افزودن واترمارک جدید» بزنید.")

    buttons: list[list[InlineKeyboardButton]] = []
    buttons.append([InlineKeyboardButton(text="➕ افزودن واترمارک جدید", callback_data="wm_add")])

    if selected:
        if count > 1:
            buttons.append([InlineKeyboardButton(text="🔁 انتخاب واترمارک", callback_data="wm_choose")])
        buttons.append([InlineKeyboardButton(text="🗑 حذف واترمارک", callback_data="wm_delete")])
        status_emoji = "✅" if selected.enabled else "❌"
        buttons.append([InlineKeyboardButton(text=f"تغییر وضعیت {status_emoji}", callback_data="wm_toggle")])
        buttons.append([InlineKeyboardButton(text="📝 ویرایش متن", callback_data="wm_set_text")])
        buttons.append([
            InlineKeyboardButton(text="⬆️ افزایش اندازه", callback_data="wm_size_inc"),
            InlineKeyboardButton(text="⬇️ کاهش اندازه", callback_data="wm_size_dec"),
        ])
        buttons.append([
            InlineKeyboardButton(text="↖️ بالا چپ", callback_data="wm_pos_top_left"),
            InlineKeyboardButton(text="↗️ بالا راست", callback_data="wm_pos_top_right"),
        ])
        buttons.append([
            InlineKeyboardButton(text="↙️ پایین چپ", callback_data="wm_pos_bottom_left"),
            InlineKeyboardButton(text="↘️ پایین راست", callback_data="wm_pos_bottom_right"),
        ])
        buttons.append([InlineKeyboardButton(text="🎨 تغییر رنگ", callback_data="wm_set_color")])
        buttons.append([InlineKeyboardButton(text="🏷 نام نمایشی", callback_data="wm_set_name")])

    buttons.append([InlineKeyboardButton(text="بستن پنل ❌", callback_data="wm_close")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = "\n".join(text_lines)
    return text, keyboard, watermarks, selected


@router.message(Command("water"))
async def watermark_entry(message: types.Message, state: FSMContext, session: AsyncSession):
    """Entry point for the watermark settings panel."""
    if not await database.has_feature_access(session, message.from_user.id, 'watermark'):
        await message.answer("You do not have permission to use the watermark feature.")
        return

    data = await state.get_data()
    selected_id = data.get("selected_watermark_id")
    _, _, watermarks, selected = await get_watermark_panel(session, message.from_user.id, selected_id)
    if selected is None and watermarks:
        selected = watermarks[0]
    if selected:
        await state.update_data(selected_watermark_id=selected.id)
    text, keyboard, _, selected = await get_watermark_panel(
        session, message.from_user.id, selected.id if selected else None
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(WatermarkFSM.panel)


@router.callback_query(WatermarkFSM.panel, F.data.startswith("wm_select_"))
async def select_watermark(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    watermark_id_str = query.data.replace("wm_select_", "")
    try:
        watermark_id = int(watermark_id_str)
    except ValueError:
        await query.answer("شناسه واترمارک نامعتبر است.", show_alert=True)
        return

    watermarks = await database.get_user_watermarks(session, query.from_user.id)
    if not any(wm.id == watermark_id for wm in watermarks):
        await query.answer("این واترمارک موجود نیست.", show_alert=True)
        return

    await state.update_data(selected_watermark_id=watermark_id)
    text, keyboard, _, _ = await get_watermark_panel(session, query.from_user.id, watermark_id)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await query.answer("واترمارک جدید انتخاب شد.")


@router.callback_query(WatermarkFSM.panel, F.data == "wm_select_back")
async def select_watermark_back(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    selected_id = data.get("selected_watermark_id")
    text, keyboard, _, _ = await get_watermark_panel(session, query.from_user.id, selected_id)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await query.answer()


@router.callback_query(WatermarkFSM.panel, F.data.startswith("wm_"))
async def handle_watermark_callbacks(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Handles button presses on the watermark panel."""
    action = query.data.replace("wm_", "")
    user_id = query.from_user.id

    if action.startswith("select_"):
        return

    data = await state.get_data()
    selected_id = data.get("selected_watermark_id")
    text, keyboard, watermarks, selected = await get_watermark_panel(session, user_id, selected_id)

    if action == "add":
        if len(watermarks) >= 50:
            await query.answer("شما نمی‌توانید بیش از ۵۰ واترمارک ذخیره کنید.", show_alert=True)
            return
        await state.update_data(text_mode="create")
        await state.set_state(WatermarkFSM.awaiting_text)
        await query.message.edit_text(
            "لطفاً متن واترمارک جدید را ارسال کنید. برای لغو /cancel را بفرستید.")
        await query.answer()
        return

    if not selected:
        await query.answer("ابتدا یک واترمارک ایجاد کنید.", show_alert=True)
        return

    if action == "choose":
        if len(watermarks) <= 1:
            await query.answer("فقط یک واترمارک دارید.", show_alert=True)
            return
        buttons = []
        for idx, wm in enumerate(watermarks, start=1):
            name = wm.display_name or f"واترمارک {idx}"
            buttons.append([InlineKeyboardButton(text=name, callback_data=f"wm_select_{wm.id}")])
        buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="wm_select_back")])
        await query.message.edit_text(
            "لطفاً واترمارک مورد نظر خود را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
        await query.answer()
        return

    if action == "delete":
        deleted = await database.delete_user_watermark(session, user_id, selected.id)
        if not deleted:
            await query.answer("این واترمارک پیدا نشد یا قبلاً حذف شده است.", show_alert=True)
            return
        await query.answer("واترمارک حذف شد.")
        new_watermarks = await database.get_user_watermarks(session, user_id)
        new_selected = new_watermarks[0] if new_watermarks else None
        await state.update_data(selected_watermark_id=new_selected.id if new_selected else None)
        text, keyboard, _, _ = await get_watermark_panel(
            session, user_id, new_selected.id if new_selected else None
        )
        await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        return

    if action == "toggle":
        await database.update_user_watermark(session, user_id, selected.id, {"enabled": not selected.enabled})
        await query.answer("وضعیت واترمارک به‌روزرسانی شد.")
    elif action.startswith("pos_"):
        new_pos = action.replace("pos_", "")
        await database.update_user_watermark(session, user_id, selected.id, {"position": new_pos})
        await query.answer("موقعیت واترمارک تغییر کرد.")
    elif action == "size_inc":
        await database.update_user_watermark(session, user_id, selected.id, {"size": selected.size + 2})
        await query.answer(f"اندازه فونت به {selected.size + 2} تغییر کرد.")
    elif action == "size_dec":
        new_size = max(8, selected.size - 2)
        await database.update_user_watermark(session, user_id, selected.id, {"size": new_size})
        await query.answer(f"اندازه فونت به {new_size} تغییر کرد.")
    elif action == "set_text":
        await state.update_data(text_mode="edit")
        await state.set_state(WatermarkFSM.awaiting_text)
        await query.message.edit_text("متن جدید واترمارک را ارسال کنید یا /cancel را بزنید.")
        await query.answer()
        return
    elif action == "set_color":
        await state.set_state(WatermarkFSM.awaiting_color)
        await query.message.edit_text(
            "لطفاً رنگ جدید واترمارک را (نام رنگ یا کد هگز) ارسال کنید. برای لغو /cancel را بفرستید.")
        await query.answer()
        return
    elif action == "set_name":
        await state.update_data(display_name_mode="rename", pending_watermark_id=selected.id)
        await state.set_state(WatermarkFSM.awaiting_display_name)
        await query.message.edit_text(
            "لطفاً نام نمایشی جدید را ارسال کنید. برای حذف نام یا رد کردن /skip را بفرستید.")
        await query.answer()
        return
    elif action == "close":
        await query.message.delete()
        await state.clear()
        await query.answer()
        return
    else:
        await query.answer()

    updated_data = await state.get_data()
    updated_selected_id = updated_data.get("selected_watermark_id", selected.id)
    text, keyboard, _, _ = await get_watermark_panel(session, user_id, updated_selected_id)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")


@router.message(WatermarkFSM.awaiting_text, F.text)
async def receive_watermark_text(message: types.Message, state: FSMContext, session: AsyncSession):
    """Handles both creating new watermark text and editing existing ones."""
    text_value = message.text.strip()
    if not text_value:
        await message.answer("متن نمی‌تواند خالی باشد. لطفاً دوباره تلاش کنید یا /cancel را بفرستید.")
        return

    data = await state.get_data()
    mode = data.get("text_mode")

    if mode == "create":
        try:
            watermark = await database.create_user_watermark(
                session,
                user_id=message.from_user.id,
                text=text_value,
            )
        except ValueError:
            await message.answer("⚠️ شما به حداکثر تعداد مجاز (۵۰) واترمارک رسیده‌اید.")
            await state.set_state(WatermarkFSM.panel)
            text, keyboard, _, _ = await get_watermark_panel(session, message.from_user.id)
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
            return

        await state.update_data(
            text_mode=None,
            selected_watermark_id=watermark.id,
            display_name_mode="create",
            pending_watermark_id=watermark.id,
        )
        await state.set_state(WatermarkFSM.awaiting_display_name)
        await message.answer(
            "واترمارک جدید ذخیره شد. لطفاً یک نام نمایشی ارسال کنید تا در لیست قابل شناسایی باشد."
            "\nدر صورت تمایل به رد کردن، دستور /skip را بفرستید.")
        return

    selected_id = data.get("selected_watermark_id")
    if not selected_id:
        await message.answer("خطا: واترمارک انتخاب‌شده یافت نشد. لطفاً دوباره تلاش کنید.")
        await state.set_state(WatermarkFSM.panel)
        text, keyboard, _, _ = await get_watermark_panel(session, message.from_user.id)
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        return

    await database.update_user_watermark(session, message.from_user.id, selected_id, {"text": text_value})
    await message.answer("✅ متن واترمارک با موفقیت به‌روزرسانی شد.")
    await state.update_data(text_mode=None)
    await state.set_state(WatermarkFSM.panel)
    text, keyboard, _, _ = await get_watermark_panel(session, message.from_user.id, selected_id)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@router.message(WatermarkFSM.awaiting_color, F.text)
async def receive_watermark_color(message: types.Message, state: FSMContext, session: AsyncSession):
    """Receives the new color for the selected watermark."""
    color_value = message.text.strip()
    if not color_value:
        await message.answer("رنگ نمی‌تواند خالی باشد. لطفاً مقدار معتبر ارسال کنید یا /cancel را بفرستید.")
        return

    data = await state.get_data()
    selected_id = data.get("selected_watermark_id")
    if not selected_id:
        await message.answer("خطا: واترمارک انتخاب‌شده یافت نشد. لطفاً دوباره تلاش کنید.")
    else:
        await database.update_user_watermark(session, message.from_user.id, selected_id, {"color": color_value})
        await message.answer("✅ رنگ واترمارک به‌روزرسانی شد.")

    await state.set_state(WatermarkFSM.panel)
    text, keyboard, _, _ = await get_watermark_panel(session, message.from_user.id, selected_id)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


async def _finalize_watermark_display_name(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    display_name: str | None,
    skip: bool = False,
):
    data = await state.get_data()
    mode = data.get("display_name_mode")
    watermark_id = data.get("pending_watermark_id") if mode == "create" else data.get("selected_watermark_id")

    if not watermark_id:
        await message.answer("خطا: واترمارک مربوطه پیدا نشد.")
        await state.set_state(WatermarkFSM.panel)
        text, keyboard, _, _ = await get_watermark_panel(session, message.from_user.id)
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        return

    if skip:
        if mode == "rename":
            await database.update_user_watermark(
                session,
                message.from_user.id,
                watermark_id,
                {"display_name": None},
            )
            await message.answer("نام نمایشی حذف شد.")
        else:
            await message.answer("واترمارک جدید بدون نام نمایشی ذخیره شد.")
    else:
        await database.update_user_watermark(
            session,
            message.from_user.id,
            watermark_id,
            {"display_name": display_name},
        )
        await message.answer("✅ نام نمایشی با موفقیت ثبت شد.")

    await state.update_data(
        display_name_mode=None,
        pending_watermark_id=None,
        selected_watermark_id=watermark_id,
    )
    await state.set_state(WatermarkFSM.panel)
    text, keyboard, _, _ = await get_watermark_panel(session, message.from_user.id, watermark_id)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@router.message(WatermarkFSM.awaiting_display_name, Command("skip"))
async def skip_watermark_name(message: types.Message, state: FSMContext, session: AsyncSession):
    await _finalize_watermark_display_name(message, state, session, None, skip=True)


@router.message(WatermarkFSM.awaiting_display_name, F.text)
async def receive_watermark_display_name(message: types.Message, state: FSMContext, session: AsyncSession):
    display_name = message.text.strip()
    if not display_name:
        await message.answer("نام نمایشی نمی‌تواند خالی باشد. لطفاً مقدار دیگری وارد کنید یا /skip را بزنید.")
        return

    await _finalize_watermark_display_name(message, state, session, display_name)


@router.message(WatermarkFSM.awaiting_display_name)
async def invalid_watermark_display_name(message: types.Message):
    await message.answer("لطفاً تنها متن ارسال کنید یا برای رد کردن /skip را بزنید.")