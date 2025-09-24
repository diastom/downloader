import logging
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.common import UserFlow, get_main_menu_keyboard
from tasks import video_tasks
from utils import database

logger = logging.getLogger(__name__)
router = Router()

@router.message(UserFlow.encoding, F.video)
async def handle_encode_video(message: types.Message, state: FSMContext, session: AsyncSession):
    """
    Handles a video sent by the user during the encoding flow.
    It retrieves the user's settings and starts the encoding task.
    """
    user_id = message.from_user.id

    # Check if the user has any customization settings enabled
    watermark_settings = await database.get_user_watermark_settings(session, user_id)
    thumbnail_id = await database.get_user_thumbnail(session, user_id)

    if not watermark_settings.enabled and not thumbnail_id:
        await message.answer(
            "شما هیچ تنظیمات واترمارک یا تامبنیلی را فعال نکرده‌اید. "
            "لطفاً با استفاده از دستورات /water و /thumb تنظیمات را انجام دهید و سپس دوباره تلاش کنید.",
            reply_markup=get_main_menu_keyboard()
        )
        await state.set_state(UserFlow.main_menu)
        return

    await message.answer("✅ ویدیوی شما دریافت شد و به صف انکد اضافه گردید. لطفاً منتظر بمانید...")

    # Dispatch the background task to Celery
    video_tasks.encode_video_task.delay(
        user_id=user_id,
        username=message.from_user.username or "N/A",
        chat_id=message.chat.id,
        video_file_id=message.video.file_id,
        video_filename=message.video.file_name or "encoded_video.mp4"
    )

    # Return user to the main menu after starting the task
    await state.set_state(UserFlow.main_menu)