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
    awaiting_delete_choice = State()


async def get_thumbnail_panel(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup, list[models.Thumbnail]]:
    thumbnails = await database.get_user_thumbnails(session, user_id)
    count = len(thumbnails)

    text = (
        "برای تنظیم واترمارک لطفا یک عکس بفرستید، و برای مدیریت واترمارک از دکمه های زیر استفاده کنید، دستور /cancel برای لغو عملیات"
        f"\n\n✅ تعداد تامبنیل‌های فعلی شما: {count} از 10"
    )

    buttons: list[list[InlineKeyboardButton]] = []
    if thumbnails:
        buttons.append([InlineKeyboardButton(text="حذف تامبنیل", callback_data="thumb_delete")])
    if count < 10:
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
    if len(thumbnails) >= 10:
        await query.answer("شما نمی‌توانید بیش از ۱۰ تامبنیل فعال داشته باشید.", show_alert=True)
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

    buttons = [
        [InlineKeyboardButton(text=f"تامبنیل {index + 1}", callback_data=f"thumb_del_{thumb.id}")]
        for index, thumb in enumerate(thumbnails)
    ]
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="thumb_del_back")])

    await state.set_state(ThumbnailFSM.awaiting_delete_choice)
    await query.message.edit_text(
        "لطفاً تامبنیل مورد نظر برای حذف را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await query.answer()

@router.message(ThumbnailFSM.awaiting_photo, F.photo)
async def receive_thumbnail(message: types.Message, state: FSMContext, session: AsyncSession):
    """Receives the photo and sets it as the user's thumbnail."""
    # The last photo in the list is usually the highest quality
    file_id = message.photo[-1].file_id
    try:
        await database.set_user_thumbnail(session, user_id=message.from_user.id, file_id=file_id)
        await message.answer("✅ تامبنیل جدید با موفقیت اضافه شد.")
    except ValueError:
        await message.answer("⚠️ شما به حداکثر تعداد مجاز (۱۰) تامبنیل رسیده‌اید.")

    text, keyboard, _ = await get_thumbnail_panel(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)
    await state.set_state(ThumbnailFSM.panel)

@router.message(ThumbnailFSM.awaiting_photo)
async def incorrect_thumbnail_input(message: types.Message):
    """Handles cases where the user sends something other than a photo."""
    await message.answer("ورودی نامعتبر است. لطفاً یک عکس ارسال کنید یا با /cancel عملیات را لغو کنید.")


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
    awaiting_color = State() # Added for color setting

async def get_watermark_panel(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Helper to generate the text and keyboard for the watermark panel."""
    settings = await database.get_user_watermark_settings(session, user_id)

    status_emoji = "✅" if settings.enabled else "❌"
    position_text_map = {
        "top_left": "Top Left", "top_right": "Top Right",
        "bottom_left": "Bottom Left", "bottom_right": "Bottom Right",
    }
    pos_text = position_text_map.get(settings.position, "Unknown")

    text = (
        "⚙️ **Watermark Settings Panel**\n\n"
        f"▪️ Status: **{status_emoji} {'Enabled' if settings.enabled else 'Disabled'}**\n"
        f"▪️ Text: `{settings.text}`\n"
        f"▪️ Position: **{pos_text}**\n"
        f"▪️ Font Size: **{settings.size}**\n"
        f"▪️ Color: `{settings.color}`\n"
        f"▪️ Stroke Thickness: **{settings.stroke}**\n"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Toggle Status {status_emoji}", callback_data="wm_toggle")],
        [InlineKeyboardButton(text="Edit Text 📝", callback_data="wm_set_text")],
        [
            InlineKeyboardButton(text="Top Left", callback_data="wm_pos_top_left"),
            InlineKeyboardButton(text="Top Right", callback_data="wm_pos_top_right"),
        ],
        [
            InlineKeyboardButton(text="Bottom Left", callback_data="wm_pos_bottom_left"),
            InlineKeyboardButton(text="Bottom Right", callback_data="wm_pos_bottom_right"),
        ],
        [
             InlineKeyboardButton(text="➖ Size", callback_data="wm_size_dec"),
             InlineKeyboardButton(text="➕ Size", callback_data="wm_size_inc"),
        ],
        [InlineKeyboardButton(text="Set Color", callback_data="wm_set_color")],
        [InlineKeyboardButton(text="Close Panel ❌", callback_data="wm_close")]
    ])
    return text, keyboard

@router.message(Command("water"))
async def watermark_entry(message: types.Message, state: FSMContext, session: AsyncSession):
    """Entry point for the watermark settings panel."""
    if not await database.has_feature_access(session, message.from_user.id, 'watermark'):
        await message.answer("You do not have permission to use the watermark feature.")
        return

    text, keyboard = await get_watermark_panel(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(WatermarkFSM.panel)

@router.callback_query(WatermarkFSM.panel, F.data.startswith("wm_"))
async def handle_watermark_callbacks(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Handles button presses on the watermark panel."""
    action = query.data.replace("wm_", "")
    user_id = query.from_user.id
    settings = await database.get_user_watermark_settings(session, user_id)

    if action == "toggle":
        settings.enabled = not settings.enabled
        await query.answer(f"Watermark {'Enabled' if settings.enabled else 'Disabled'}")
    elif action.startswith("pos_"):
        settings.position = action.replace("pos_", "")
        await query.answer(f"Position set to {settings.position.replace('_', ' ')}")
    elif action == "size_inc":
        settings.size += 2
        await query.answer(f"Font size increased to {settings.size}")
    elif action == "size_dec":
        settings.size = max(8, settings.size - 2)
        await query.answer(f"Font size decreased to {settings.size}")
    elif action == "set_text":
        await query.message.edit_text("Please enter the new watermark text (or /cancel):")
        await state.set_state(WatermarkFSM.awaiting_text)
        return # Do not redraw panel yet
    elif action == "set_color":
        await query.message.edit_text("Please enter the new color name (e.g., 'white', 'black', 'red') or a hex code (e.g., '#FF0000'):")
        await state.set_state(WatermarkFSM.awaiting_color)
        return # Do not redraw panel yet
    elif action == "close":
        await query.message.delete()
        await state.clear()
        return

    await session.commit()
    text, keyboard = await get_watermark_panel(session, user_id)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(WatermarkFSM.awaiting_text, F.text)
async def receive_watermark_text(message: types.Message, state: FSMContext, session: AsyncSession):
    """Receives the new text for the watermark."""
    await database.update_user_watermark_settings(session, message.from_user.id, {"text": message.text})
    await message.answer("✅ Watermark text updated.")

    text, keyboard = await get_watermark_panel(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(WatermarkFSM.panel)

@router.message(WatermarkFSM.awaiting_color, F.text)
async def receive_watermark_color(message: types.Message, state: FSMContext, session: AsyncSession):
    """Receives the new color for the watermark."""
    # Basic validation can be added here if needed
    await database.update_user_watermark_settings(session, message.from_user.id, {"color": message.text})
    await message.answer("✅ Watermark color updated.")

    text, keyboard = await get_watermark_panel(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(WatermarkFSM.panel)