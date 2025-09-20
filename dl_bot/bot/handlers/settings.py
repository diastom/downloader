from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ...utils import database

router = Router()

# --- Thumbnail FSM ---
class ThumbnailFSM(StatesGroup):
    awaiting_photo = State()

@router.message(Command("thumb"))
async def thumb_entry(message: types.Message, state: FSMContext):
    """Entry point for setting a custom thumbnail."""
    await message.answer("لطفاً یک عکس برای تنظیم به عنوان تامبنیل ارسال کنید یا /cancel را بزنید.")
    await state.set_state(ThumbnailFSM.awaiting_photo)

@router.message(ThumbnailFSM.awaiting_photo, F.photo)
async def receive_thumbnail(message: types.Message, state: FSMContext):
    """Receives the photo and sets it as the user's thumbnail."""
    # The last photo in the list is the highest resolution
    file_id = message.photo[-1].file_id
    database.set_user_thumbnail(message.from_user.id, file_id)
    await message.answer("✅ تامبنیل با موفقیت تنظیم شد!")
    await state.clear()

@router.message(ThumbnailFSM.awaiting_photo)
async def incorrect_thumbnail_input(message: types.Message):
    """Handles cases where the user sends something other than a photo."""
    await message.answer("ورودی نامعتبر است. لطفاً یک عکس ارسال کنید یا با /cancel لغو کنید.")


# --- Watermark FSM ---
class WatermarkFSM(StatesGroup):
    panel = State()
    awaiting_text = State()

async def get_watermark_panel(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Helper to generate the text and keyboard for the watermark panel."""
    settings = database.get_user_watermark_settings(user_id)

    status_emoji = "✅ (فعال)" if settings["enabled"] else "❌ (غیرفعال)"
    position_text_map = {
        "top_left": "بالا چپ", "top_right": "بالا راست",
        "bottom_left": "پایین چپ", "bottom_right": "پایین راست",
    }
    pos_text = position_text_map.get(settings["position"], "نامشخص")

    text = (
        "⚙️ **پنل تنظیمات واترمارک**\n\n"
        f"▪️ وضعیت: **{status_emoji}**\n"
        f"▪️ متن: `{settings['text']}`\n"
        f"▪️ موقعیت: **{pos_text}**\n"
        f"▪️ اندازه فونت: **{settings['size']}**\n"
        f"▪️ رنگ فونت: **{settings['color']}**\n"
        f"▪️ ضخامت حاشیه: **{settings['stroke']}**\n"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(f"تغییر وضعیت {status_emoji}", callback_data="wm_toggle")],
        [InlineKeyboardButton("ویرایش متن 📝", callback_data="wm_set_text")],
        [
            InlineKeyboardButton(" موقعیت 🔼", callback_data="wm_pos_top_left"),
            InlineKeyboardButton(" موقعیت 🔼", callback_data="wm_pos_top_right"),
        ],
        [
            InlineKeyboardButton(" موقعیت 🔽", callback_data="wm_pos_bottom_left"),
            InlineKeyboardButton(" موقعیت 🔽", callback_data="wm_pos_bottom_right"),
        ],
        [
             InlineKeyboardButton("➖ اندازه", callback_data="wm_size_dec"),
             InlineKeyboardButton("➕ اندازه", callback_data="wm_size_inc"),
        ],
        [InlineKeyboardButton("بستن پنل", callback_data="wm_close")]
    ])
    return text, keyboard

@router.message(Command("water"))
async def watermark_entry(message: types.Message, state: FSMContext):
    """Entry point for the watermark settings panel."""
    text, keyboard = await get_watermark_panel(message.from_user.id)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(WatermarkFSM.panel)

@router.callback_query(WatermarkFSM.panel, F.data.startswith("wm_"))
async def handle_watermark_callbacks(query: types.CallbackQuery, state: FSMContext):
    """Handles button presses on the watermark panel."""
    action = query.data.replace("wm_", "")
    user_id = query.from_user.id
    settings = database.get_user_watermark_settings(user_id)

    if action == "toggle":
        settings["enabled"] = not settings["enabled"]
    elif action.startswith("pos_"):
        settings["position"] = action.replace("pos_", "")
    elif action == "size_inc":
        settings["size"] += 2
    elif action == "size_dec":
        settings["size"] = max(8, settings["size"] - 2)
    elif action == "set_text":
        await query.message.edit_text("لطفاً متن جدید واترمارک را وارد کنید:")
        await state.set_state(WatermarkFSM.awaiting_text)
        return
    elif action == "close":
        await query.message.delete()
        await state.clear()
        return

    database.update_user_watermark_settings(user_id, settings)
    text, keyboard = await get_watermark_panel(user_id)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await query.answer("تنظیمات به‌روزرسانی شد.")

@router.message(WatermarkFSM.awaiting_text, F.text)
async def receive_watermark_text(message: types.Message, state: FSMContext):
    """Receives the new text for the watermark."""
    user_id = message.from_user.id
    settings = database.get_user_watermark_settings(user_id)
    settings["text"] = message.text
    database.update_user_watermark_settings(user_id, settings)

    await message.answer("✅ متن واترمارک با موفقیت به‌روزرسانی شد.")

    # Return to the panel
    text, keyboard = await get_watermark_panel(user_id)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(WatermarkFSM.panel)
