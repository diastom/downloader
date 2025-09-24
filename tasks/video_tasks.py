import asyncio
import logging
import os
import tempfile

from config import settings
from utils import database, helpers, video_processor, telegram_api
from utils.db_session import AsyncSessionLocal
from tasks.celery_app import celery_app
from bot.handlers.common import get_main_menu_keyboard

logger = logging.getLogger(__name__)

# Global bot instance for Celery workers
from utils.bot_instance import bot

def get_bot_instance():
    """Creates an aiogram Bot instance for Celery tasks."""
    return bot

@celery_app.task(name="tasks.encode_video_task")
def encode_video_task(user_id: int, username: str, chat_id: int, video_file_id: str, video_filename: str):
    """
    A Celery task that downloads a video sent by a user, applies their saved
    watermark and/or thumbnail, sends it back, and archives it.
    """
    async def _async_worker():
        bot_instance = get_bot_instance()
        status_message = await bot_instance.send_message(chat_id=chat_id, text="⏳ پردازش ویدیوی شما شروع شد...")

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # 1. Download the source video from Telegram
                await bot_instance.edit_message_text("📥 در حال دانلود ویدیوی اصلی...", chat_id=chat_id, message_id=status_message.message_id)
                video_file = await bot_instance.get_file(video_file_id)
                original_video_path = os.path.join(temp_dir, video_filename)

                # FIX: Clean up the file path from a local Bot API server
                clean_file_path = video_file.file_path.lstrip('/')

                await bot_instance.download_file(clean_file_path, destination=original_video_path)

                final_video_path = original_video_path
                custom_thumb_path = None
                applied_tasks = []

                async with AsyncSessionLocal() as session:
                    # 2. Apply Watermark if enabled
                    watermark_settings = await database.get_user_watermark_settings(session, user_id)
                    if watermark_settings and watermark_settings.enabled:
                        await bot_instance.edit_message_text("💧 در حال اعمال واترمارک...", chat_id=chat_id, message_id=status_message.message_id)
                        watermarked_path = os.path.join(temp_dir, f"watermarked_{video_filename}")
                        success = await asyncio.to_thread(
                            video_processor.apply_watermark_to_video,
                            final_video_path,
                            watermarked_path,
                            watermark_settings
                        )
                        if success:
                            final_video_path = watermarked_path
                            applied_tasks.append("water")
                        else:
                            logger.warning(f"Watermark application failed for user {user_id}")

                    # 3. Download custom thumbnail if it exists
                    thumbnail_id = await database.get_user_thumbnail(session, user_id)
                    if thumbnail_id:
                        await bot_instance.edit_message_text("🖼️ در حال آماده‌سازی تامبنیل...", chat_id=chat_id, message_id=status_message.message_id)
                        thumb_file = await bot_instance.get_file(thumbnail_id)
                        custom_thumb_path = os.path.join(temp_dir, f"thumb_{user_id}.jpg")

                        # FIX: Clean up the file path from a local Bot API server
                        clean_thumb_path = thumb_file.file_path.lstrip('/')

                        await bot_instance.download_file(clean_thumb_path, destination=custom_thumb_path)
                        applied_tasks.append("thumb")

                # 4. Upload the processed video back to the user
                await bot_instance.edit_message_text("📤 در حال آپلود ویدیوی نهایی...", chat_id=chat_id, message_id=status_message.message_id)
                duration, width, height = await asyncio.to_thread(video_processor.get_video_metadata, final_video_path)

                # Send to user first
                await telegram_api.upload_video(
                    bot=bot_instance,
                    target_chat_id=chat_id,
                    file_path=final_video_path,
                    thumb_path=custom_thumb_path,
                    caption=f"✅ ویدیوی انکد شده شما: {video_filename}",
                    duration=duration, width=width, height=height
                )

                # 5. Upload to the private archive channel
                private_archive_caption = (
                    f"the user: @{username} | {user_id}\n"
                    f"the task: {'/'.join(applied_tasks) or 'none'}"
                )
                await telegram_api.upload_video(
                    bot=bot_instance,
                    target_chat_id=settings.private_archive_channel_id,
                    file_path=final_video_path,
                    thumb_path=custom_thumb_path,
                    caption=private_archive_caption,
                    duration=duration, width=width, height=height
                )

                await bot_instance.delete_message(chat_id=chat_id, message_id=status_message.message_id)
                await bot_instance.send_message(chat_id=chat_id, text="به منوی اصلی بازگشتید.", reply_markup=get_main_menu_keyboard())

            except Exception as e:
                logger.error(f"Error in encode_video_task for user {user_id}: {e}", exc_info=True)
                await bot_instance.edit_message_text(
                    text=f"❌ خطایی در حین پردازش ویدیو رخ داد: {e}",
                    chat_id=chat_id,
                    message_id=status_message.message_id
                )
                await bot_instance.send_message(chat_id=chat_id, text="لطفا دوباره تلاش کنید.", reply_markup=get_main_menu_keyboard())

    helpers.run_async_in_sync(_async_worker())