import asyncio
import logging
import os
import shutil
from pathlib import Path

from aiogram.types import FSInputFile
from config import settings
from utils import database, helpers, video_processor, telegram_api
from utils.db_session import AsyncSessionLocal
from tasks.celery_app import celery_app
from bot.handlers.common import get_main_menu_keyboard
from aiogram.types import File

logger = logging.getLogger(__name__)

# --- Configuration for Local Bot API ---
LOCAL_BOT_API_ENABLED = True
LOCAL_BOT_API_SERVER_DATA_DIR = "/root/api"

# Global bot instance for Celery workers
from utils.bot_instance import bot

def get_bot_instance():
    return bot

async def download_or_copy_file(file: File, destination: Path):
    bot_instance = get_bot_instance()
    if LOCAL_BOT_API_ENABLED:
        source_path = Path(LOCAL_BOT_API_SERVER_DATA_DIR) / file.file_path
        logger.info(f"Local Bot API enabled. Copying file from {source_path} to {destination}")
        if not source_path.exists():
            alt_source_path = Path(file.file_path)
            if not alt_source_path.exists():
                 raise FileNotFoundError(f"Source file not found at {source_path} or {alt_source_path}.")
            source_path = alt_source_path
        shutil.copy(source_path, destination)
    else:
        logger.info(f"Default Telegram API. Downloading file to {destination}")
        await bot_instance.download_file(file.file_path, destination=str(destination))

@celery_app.task(name="tasks.encode_video_task")
def encode_video_task(user_id: int, username: str, chat_id: int, video_file_id: str, video_filename: str):
    async def _async_worker():
        bot_instance = get_bot_instance()
        status_message = await bot_instance.send_message(chat_id=chat_id, text="⏳ پردازش ویدیوی شما شروع شد...")

        task_dir = Path("encode") / f"task_{user_id}_{os.urandom(4).hex()}"
        task_dir.mkdir(parents=True, exist_ok=True)

        try:
            await bot_instance.edit_message_text("📥 در حال دریافت ویدیوی اصلی...", chat_id=chat_id, message_id=status_message.message_id)
            video_file = await bot_instance.get_file(video_file_id)
            original_video_path = task_dir / video_filename
            await download_or_copy_file(video_file, original_video_path)

            final_video_path = original_video_path
            custom_thumb_path = None
            applied_tasks = []

            async with AsyncSessionLocal() as session:
                watermark_settings = await database.get_user_watermark_settings(session, user_id)
                if watermark_settings and watermark_settings.enabled:
                    await bot_instance.edit_message_text("💧 در حال اعمال واترمارک...", chat_id=chat_id, message_id=status_message.message_id)
                    watermarked_path = task_dir / f"watermarked_{video_filename}"
                    success = await asyncio.to_thread(
                        video_processor.apply_watermark_to_video,
                        str(final_video_path), str(watermarked_path), watermark_settings
                    )
                    if success:
                        final_video_path = watermarked_path
                        applied_tasks.append("water")

                thumbnail_id = await database.get_user_thumbnail(session, user_id)
                if thumbnail_id:
                    await bot_instance.edit_message_text("🖼️ در حال دریافت تامبنیل...", chat_id=chat_id, message_id=status_message.message_id)
                    thumb_file = await bot_instance.get_file(thumbnail_id)
                    custom_thumb_path = task_dir / f"thumb_{user_id}.jpg"
                    await download_or_copy_file(thumb_file, custom_thumb_path)
                    applied_tasks.append("thumb")

            await bot_instance.edit_message_text("📤 در حال آپلود ویدیوی نهایی...", chat_id=chat_id, message_id=status_message.message_id)
            duration, width, height = await asyncio.to_thread(video_processor.get_video_metadata, str(final_video_path))

            # Send to user with the main menu keyboard attached
            await bot_instance.send_video(
                chat_id=chat_id,
                video=FSInputFile(str(final_video_path)),
                thumbnail=FSInputFile(str(custom_thumb_path)) if custom_thumb_path and custom_thumb_path.exists() else None,
                caption=f"✅ ویدیوی انکد شده شما: {video_filename}",
                duration=duration, width=width, height=height,
                reply_markup=get_main_menu_keyboard() # Attach keyboard here
            )

            # Send to private archive (without keyboard)
            private_archive_caption = f"the user: @{username} | {user_id}\n" f"the task: {'/'.join(applied_tasks) or 'none'}"
            await telegram_api.upload_video(
                bot=bot_instance, target_chat_id=settings.private_archive_channel_id, file_path=str(final_video_path),
                thumb_path=str(custom_thumb_path) if custom_thumb_path and custom_thumb_path.exists() else None,
                caption=private_archive_caption,
                duration=duration, width=width, height=height
            )

            await bot_instance.delete_message(chat_id=chat_id, message_id=status_message.message_id)

        except Exception as e:
            logger.error(f"Error in encode_video_task for user {user_id}: {e}", exc_info=True)
            await bot_instance.edit_message_text(
                text=f"❌ خطایی در حین پردازش ویدیو رخ داد: {e}",
                chat_id=chat_id, message_id=status_message.message_id
            )
            await bot_instance.send_message(chat_id=chat_id, text="لطفا دوباره تلاش کنید.", reply_markup=get_main_menu_keyboard())
        finally:
            if task_dir.exists():
                shutil.rmtree(task_dir)

    helpers.run_async_in_sync(_async_worker())