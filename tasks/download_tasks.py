import asyncio
import json
import logging
import os
import tempfile

from aiogram.types import FSInputFile
from config import settings
from utils import database, helpers, telegram_api, video_processor
from utils.db_session import AsyncSessionLocal
from utils.models import PublicArchive
from tasks.celery_app import celery_app
from bot.handlers.common import get_main_menu_keyboard

logger = logging.getLogger(__name__)

# Global bot instance for Celery workers
from utils.bot_instance import bot

def get_bot_instance():
    """Creates an aiogram Bot instance for Celery tasks."""
    return bot

@celery_app.task(name="tasks.download_video_task")
def download_video_task(chat_id: int, url: str, selected_format: str, video_info_json: str, user_id: int):
    """
    A simplified task that downloads a video, archives it, and sends it to the user.
    """
    video_info = json.loads(video_info_json) if video_info_json else {}

    async def _async_worker():
        bot_instance = get_bot_instance()
        status_message = await bot_instance.send_message(chat_id=chat_id, text="📥 دانلود ویدیوی شما در حال شروع است...")

        # Ensure video_info is populated if it's empty
        if not video_info:
            try:
                info = await asyncio.to_thread(helpers.get_full_video_info, url)
                if not info:
                    await bot_instance.edit_message_text(text="❌ امکان دریافت متادیتای ویدیو وجود نداشت.", chat_id=chat_id, message_id=status_message.message_id)
                    return
                video_info.update(info)
            except Exception as e:
                logger.error(f"Failed to get video info for {url}: {e}")
                await bot_instance.edit_message_text(text=f"❌ خطا در دریافت اطلاعات ویدیو: {e}", chat_id=chat_id, message_id=status_message.message_id)
                return

        title = helpers.sanitize_filename(video_info.get('title', 'untitled_video'))

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                await bot_instance.edit_message_text(text=f"📥 در حال دانلود: {title}...", chat_id=chat_id, message_id=status_message.message_id)

                raw_video_path = await asyncio.to_thread(helpers.download_video, url, temp_dir, selected_format)
                if not raw_video_path: raise Exception("دانلود ویدیو ناموفق بود.")

                # Video repair is often necessary
                repaired_path = os.path.join(temp_dir, "repaired.mp4")
                if not await asyncio.to_thread(video_processor.repair_video, raw_video_path, repaired_path):
                     repaired_path = raw_video_path # Fallback to original if repair fails

                duration, width, height = await asyncio.to_thread(video_processor.get_video_metadata, repaired_path)

                # Generate a thumbnail from the video itself
                generated_thumb_path = os.path.join(temp_dir, "generated_thumb.jpg")
                thumb_success = await asyncio.to_thread(
                    video_processor.generate_thumbnail_from_video, repaired_path, generated_thumb_path
                )
                final_thumb_path = generated_thumb_path if thumb_success else None

                # --- Upload to Public Archive ---
                await bot_instance.edit_message_text(text="📤 در حال آپلود در آرشیو عمومی...", chat_id=chat_id, message_id=status_message.message_id)
                public_channel_id = settings.public_archive_channel_id

                public_message_id = await telegram_api.upload_video(
                    bot=bot_instance,
                    target_chat_id=public_channel_id,
                    file_path=repaired_path,
                    thumb_path=final_thumb_path,
                    caption=title,
                    duration=duration,
                    width=width,
                    height=height
                )
                if not public_message_id:
                    raise Exception("آپلود در آرشیو عمومی ناموفق بود.")

                # --- Save to Database ---
                async with AsyncSessionLocal() as session:
                    await database.add_public_archive_item(
                        session=session,
                        url=url,
                        message_id=public_message_id,
                        channel_id=public_channel_id
                    )

                # --- Send to User ---
                await bot_instance.edit_message_text(text="📨 در حال ارسال برای شما...", chat_id=chat_id, message_id=status_message.message_id)
                await bot_instance.copy_message(
                    chat_id=chat_id,
                    from_chat_id=public_channel_id,
                    message_id=public_message_id
                )

                await bot_instance.delete_message(chat_id=chat_id, message_id=status_message.message_id)
                await bot_instance.send_message(chat_id=chat_id, text="✅ دانلود شما با موفقیت انجام شد.", reply_markup=get_main_menu_keyboard())

            except Exception as e:
                logger.error(f"Celery Video Task Error: {e}", exc_info=True)
                await bot_instance.edit_message_text(
                    text=f"❌ خطایی در حین پردازش ویدیو رخ داد: {e}",
                    chat_id=chat_id,
                    message_id=status_message.message_id
                )
                await bot_instance.send_message(
                    chat_id=chat_id, text="لطفاً دوباره امتحان کنید یا با ادمین تماس بگیرید.", reply_markup=get_main_menu_keyboard()
                )

    helpers.run_async_in_sync(_async_worker())