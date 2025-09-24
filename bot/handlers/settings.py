from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from sqlalchemy.ext.asyncio import AsyncSession
from utils import database

router = Router()

# --- Thumbnail FSM ---
class ThumbnailFSM(StatesGroup):
    awaiting_photo = State()

@router.message(Command("thumb"))
async def thumb_entry(message: types.Message, state: FSMContext, session: AsyncSession):
    """Entry point for setting a custom thumbnail."""
    if not await database.has_feature_access(session, message.from_user.id, 'thumbnail'):
        await message.answer("You do not have permission to use the thumbnail feature.")
        return

    await message.answer("Please send a photo to set as a thumbnail, or type /cancel to abort.")
    await state.set_state(ThumbnailFSM.awaiting_photo)

@router.message(ThumbnailFSM.awaiting_photo, F.photo)
async def receive_thumbnail(message: types.Message, state: FSMContext, session: AsyncSession):
    """Receives the photo and sets it as the user's thumbnail."""
    # The last photo in the list is usually the highest quality
    file_id = message.photo[-1].file_id
    await database.set_user_thumbnail(session, user_id=message.from_user.id, file_id=file_id)
    await message.answer("✅ Thumbnail set successfully!")
    await state.clear()

@router.message(ThumbnailFSM.awaiting_photo)
async def incorrect_thumbnail_input(message: types.Message):
    """Handles cases where the user sends something other than a photo."""
    await message.answer("Invalid input. Please send a photo or cancel with /cancel.")


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