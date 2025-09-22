import logging
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from sqlalchemy.ext.asyncio import AsyncSession
from dl_bot.tasks import video_tasks # Import the task module
from dl_bot.utils import database

logger = logging.getLogger(__name__)
router = Router()

# --- FSM States ---
class VideoEditFSM(StatesGroup):
    awaiting_choice = State()

# --- FSM Handlers ---
@router.message(F.video)
async def handle_user_video(message: types.Message, state: FSMContext, session: AsyncSession):
    """
    Entry point for the video editing flow. Triggers when a user sends a video.
    """
    user = await database.get_or_create_user(session, user_id=message.from_user.id)

    # We need the personal archive to upload the customized video to.
    # The creation logic is called inside the task if it doesn't exist.
    personal_archive_id = user.personal_archive_id

    # Store the video's file_id in the FSM state for later retrieval
    await state.update_data(video_file_id=message.video.file_id, personal_archive_id=personal_archive_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🖼️ تنظیم تامبنیل", callback_data="vid_edit_thumb")],
        [InlineKeyboardButton("💧 تنظیم واترمارک", callback_data="vid_edit_water")],
        [InlineKeyboardButton("🖼️💧 تنظیم هر دو", callback_data="vid_edit_both")],
        [InlineKeyboardButton("❌ لغو", callback_data="vid_edit_cancel")],
    ])

    await message.answer("می‌خواهید با این ویدیو چه کاری انجام دهید؟", reply_markup=keyboard)
    await state.set_state(VideoEditFSM.awaiting_choice)


@router.callback_query(VideoEditFSM.awaiting_choice, F.data.startswith("vid_edit_"))
async def process_video_edit_choice(query: types.CallbackQuery, state: FSMContext):
    """
    Handles the user's choice for video customization and dispatches the Celery task.
    """
    choice = query.data.replace("vid_edit_", "")

    if choice == 'cancel':
        await query.message.edit_text("عملیات لغو شد.")
        await state.clear()
        return

    state_data = await state.get_data()
    video_file_id = state_data.get('video_file_id')
    personal_archive_id = state_data.get('personal_archive_id') # Will be created if None inside the task

    if not video_file_id:
        await query.message.edit_text("خطا: اطلاعات ویدیو یافت نشد. لطفاً دوباره تلاش کنید.")
        await state.clear()
        return

    await query.message.edit_text("✅ درخواست شما به صف پردازش اضافه شد. لطفاً منتظر بمانید...")

    # Dispatch the background task to Celery
    video_tasks.process_video_customization_task.delay(
        user_id=query.from_user.id,
        chat_id=query.message.chat.id,
        personal_archive_id=personal_archive_id,
        video_file_id=video_file_id,
        choice=choice
    )

    # Clear the state after dispatching the task
    await state.clear()
    await query.answer()
