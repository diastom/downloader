import asyncio
import logging
import os
import tempfile

from aiogram import Bot

from ..config import settings
from ..utils import database, helpers
from ..utils.db_session import AsyncSessionLocal
from .celery_app import celery_app
from ..utils.video_processor import get_video_metadata, apply_watermark_to_video
from ..utils.telegram_api import upload_video
from ..utils.telegram_client import get_or_create_personal_archive

logger = logging.getLogger(__name__)

# Initialize a global bot instance for the Celery worker
# This instance will be used by tasks to communicate with Telegram
bot = Bot(token=settings.bot_token)


@celery_app.task(name="tasks.process_video_customization")
def process_video_customization_task(user_id: int, chat_id: int, personal_archive_id: int, video_file_id: str, choice: str):
    """
    A Celery task that downloads a video, applies user customizations (watermark/thumbnail),
    and uploads it. Status is reported via a single editable message.
    """
    async def _async_worker():
        status_message = None
        async with AsyncSessionLocal() as session:
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    status_message = await bot.send_message(chat_id=chat_id, text="⏳ Your video processing has started...")

                    await bot.edit_message_text("📥 Downloading the original video...", chat_id=chat_id, message_id=status_message.message_id)

                    video_file = await bot.get_file(video_file_id)
                    video_path = os.path.join(temp_dir, 'original_video.mp4')
                    await bot.download_file(video_file.file_path, destination=video_path)
                    logger.info(f"Video with file_id {video_file_id} downloaded to {video_path}")

                    final_video_path = video_path
                    custom_thumb_path = None

                    if choice in ['water', 'both']:
                        await bot.edit_message_text("💧 Applying watermark...", chat_id=chat_id, message_id=status_message.message_id)
                        watermark_settings_obj = await database.get_user_watermark_settings(session, user_id)
                        # Convert ORM object to dict for the helper
                        watermark_settings = {c.name: getattr(watermark_settings_obj, c.name) for c in watermark_settings_obj.__table__.columns}

                        final_video_path = await asyncio.to_thread(
                            video_processor.apply_watermark_to_video, video_path, watermark_settings
                        )
                        if not final_video_path:
                            raise Exception("Failed to apply watermark.")

                    if choice in ['thumb', 'both']:
                        custom_thumbnail_id = await database.get_user_thumbnail(session, user_id)
                        if custom_thumbnail_id:
                            await bot.edit_message_text("🖼️ Preparing thumbnail...", chat_id=chat_id, message_id=status_message.message_id)
                            thumb_file = await bot.get_file(custom_thumbnail_id)
                            custom_thumb_path = os.path.join(temp_dir, 'thumb.jpg')
                            await bot.download_file(thumb_file.file_path, destination=custom_thumb_path)

                personal_archive_id = await telegram_client.get_or_create_personal_archive(session, user_id, (await bot.get_me()).username)
                if not personal_archive_id:
                    raise Exception("Failed to get or create personal archive.")

                await bot.edit_message_text("📤 Uploading the final video...", chat_id=chat_id, message_id=status_message.message_id)
                duration, width, height = await asyncio.to_thread(get_video_metadata, final_video_path)

                uploaded_message_id = await upload_video(
                    bot=bot,
                    target_chat_id=personal_archive_id,
                    file_path=final_video_path,
                    thumb_path=custom_thumb_path,
                    caption=f"Edited for {user_id}",
                    duration=duration, width=width, height=height
                )
                if not uploaded_message_id:
                    raise Exception("Failed to upload the final video.")

                await bot.edit_message_text("✅ Your video is ready! Sending it now...", chat_id=chat_id, message_id=status_message.message_id)
                await bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=personal_archive_id,
                    message_id=uploaded_message_id
                )

                await bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)

            except Exception as e:
                logger.error(f"Error in video processing task for user {user_id}: {e}", exc_info=True)
                error_text = f"❌ An error occurred while processing your video:\n`{e}`"
                if status_message:
                    await bot.edit_message_text(error_text, chat_id=chat_id, message_id=status_message.message_id, parse_mode="Markdown")
                else:
                    await bot.send_message(chat_id=chat_id, text=error_text, parse_mode="Markdown")

    # Safely run the async worker from the synchronous Celery task
    helpers.run_async_in_sync(_async_worker())
