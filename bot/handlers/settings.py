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
    # Check for feature access before proceeding
    if not await database.has_feature_access(session, message.from_user.id, 'thumbnail'):
        await message.answer("You do not have permission to use the thumbnail feature.")
        return
    
    await message.answer("Please send a photo to set as a thumbnail, or type /cancel to abort.")
    await state.set_state(ThumbnailFSM.awaiting_photo)

@router.message(ThumbnailFSM.awaiting_photo, F.photo)
async def receive_thumbnail(message: types.Message, state: FSMContext, session: AsyncSession):
    """Receives the photo and sets it as the user's thumbnail."""
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

async def get_watermark_panel(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Helper to generate the text and keyboard for the watermark panel."""
    settings = await database.get_user_watermark_settings(session, user_id)

    status_emoji = "✅ (Enabled)" if settings.enabled else "❌ (Disabled)"
    position_text_map = {
        "top_left": "Top Left", "top_right": "Top Right",
        "bottom_left": "Bottom Left", "bottom_right": "Bottom Right",
    }
    pos_text = position_text_map.get(settings.position, "Unknown")

    text = (
        "⚙️ **Watermark Settings Panel**\n\n"
        f"▪️ Status: **{status_emoji}**\n"
        f"▪️ Text: `{settings.text}`\n"
        f"▪️ Position: **{pos_text}**\n"
        f"▪️ Font Size: **{settings.size}**\n"
        f"▪️ Color: **{settings.color}**\n"
        f"▪️ Stroke Thickness: **{settings.stroke}**\n"
    )

    # --- START OF CORRECTION ---
    # Added 'text=' keyword argument to all InlineKeyboardButton calls
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Toggle Status {status_emoji}", callback_data="wm_toggle")],
        [InlineKeyboardButton(text="Edit Text 📝", callback_data="wm_set_text")],
        [
            InlineKeyboardButton(text="Position 🔼 (Top Left)", callback_data="wm_pos_top_left"),
            InlineKeyboardButton(text="Position 🔼 (Top Right)", callback_data="wm_pos_top_right"),
        ],
        [
            InlineKeyboardButton(text="Position 🔽 (Bottom Left)", callback_data="wm_pos_bottom_left"),
            InlineKeyboardButton(text="Position 🔽 (Bottom Right)", callback_data="wm_pos_bottom_right"),
        ],
        [
             InlineKeyboardButton(text="➖ Size", callback_data="wm_size_dec"),
             InlineKeyboardButton(text="➕ Size", callback_data="wm_size_inc"),
        ],
        [InlineKeyboardButton(text="Close Panel", callback_data="wm_close")]
    ])
    # --- END OF CORRECTION ---
    return text, keyboard

@router.message(Command("water"))
async def watermark_entry(message: types.Message, state: FSMContext, session: AsyncSession):
    """Entry point for the watermark settings panel."""
    # Check for feature access before proceeding
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
    elif action.startswith("pos_"):
        settings.position = action.replace("pos_", "")
    elif action == "size_inc":
        settings.size += 2
    elif action == "size_dec":
        settings.size = max(8, settings.size - 2)
    elif action == "set_text":
        await query.message.edit_text("Please enter the new watermark text:")
        await state.set_state(WatermarkFSM.awaiting_text)
        return
    elif action == "close":
        await query.message.delete()
        await state.clear()
        return

    await session.commit()
    text, keyboard = await get_watermark_panel(session, user_id)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await query.answer("Settings updated.")

@router.message(WatermarkFSM.awaiting_text, F.text)
async def receive_watermark_text(message: types.Message, state: FSMContext, session: AsyncSession):
    """Receives the new text for the watermark."""
    user_id = message.from_user.id
    settings = await database.get_user_watermark_settings(session, user_id)
    settings.text = message.text
    await session.commit()

    await message.answer("✅ Watermark text updated successfully.")

    # Return to the panel
    text, keyboard = await get_watermark_panel(session, user_id)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(WatermarkFSM.panel)

