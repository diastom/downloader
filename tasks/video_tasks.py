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
from bot.handlers.common import get_task_done_keyboard
from aiogram.types import File

logger = logging.getLogger(__name__)

from utils.bot_instance import create_bot_instance

@celery_app.task(name="tasks.encode_video_task")
def encode_video_task(user_id: int, username: str, chat_id: int, video_file_id: str, options: dict, new_filename: str | None):
    """
    A Celery task that performs encoding based on user-selected options.
    """
    async def _async_worker():
        bot = create_bot_instance()
        status_message = None
        task_dir = Path("encode") / f"task_{user_id}_{os.urandom(4).hex()}"
        task_dir.mkdir(parents=True, exist_ok=True)

        try:
            status_message = await bot.send_message(chat_id=chat_id, text="⏳ پردازش ویدیوی شما شروع شد...")
            video_file = await bot.get_file(video_file_id)

            final_filename = new_filename if options.get("rename") and new_filename else (video_file.file_path.split('/')[-1] if video_file.file_path else "video.mp4")
            original_video_path = task_dir / final_filename

            await bot.edit_message_text("📥 در حال دریافت ویدیوی اصلی...", chat_id=chat_id, message_id=status_message.message_id)
            await helpers.download_or_copy_file(bot, video_file, original_video_path)

            final_video_path = original_video_path
            custom_thumb_path = None
            applied_tasks = []

            if options.get("selected_quality") and options["selected_quality"] != "original":
                await bot.edit_message_text(f"🌇 در حال تغییر کیفیت به {options['selected_quality']}p...", chat_id=chat_id, message_id=status_message.message_id)
                transcoded_path = task_dir / f"transcoded_{final_filename}"
                success = await asyncio.to_thread(
                    video_processor.transcode_video,
                    str(final_video_path),
                    str(transcoded_path),
                    int(options["selected_quality"])
                )
                if success:
                    final_video_path = transcoded_path
                    applied_tasks.append(f"{options['selected_quality']}p")
                else:
                    await bot.edit_message_text(f"⚠️ اخطار: تغییر کیفیت انجام نشد، از کیفیت اصلی استفاده می‌شود.", chat_id=chat_id, message_id=status_message.message_id)


            if options.get("water"):
                async with AsyncSessionLocal() as session:
                    watermark_settings = await database.get_user_watermark_settings(session, user_id)
                if watermark_settings and watermark_settings.enabled:
                    await bot.edit_message_text("💧 در حال اعمال واترمارک...", chat_id=chat_id, message_id=status_message.message_id)
                    watermarked_path = task_dir / f"watermarked_{final_filename}"
                    success = await asyncio.to_thread(
                        video_processor.apply_watermark_to_video,
                        str(final_video_path), str(watermarked_path), watermark_settings
                    )
                    if success:
                        final_video_path = watermarked_path
                        applied_tasks.append("water")

            if options.get("thumb"):
                async with AsyncSessionLocal() as session:
                    thumbnail_id = await database.get_user_thumbnail(session, user_id)
                if thumbnail_id:
                    await bot.edit_message_text("🖼️ در حال دریافت تامبنیل...", chat_id=chat_id, message_id=status_message.message_id)
                    thumb_file = await bot.get_file(thumbnail_id)
                    custom_thumb_path = task_dir / f"thumb_{user_id}.jpg"
                    await helpers.download_or_copy_file(bot, thumb_file, custom_thumb_path)
                    applied_tasks.append("thumb")

            await bot.edit_message_text("📤 در حال آپلود ویدیوی نهایی...", chat_id=chat_id, message_id=status_message.message_id)
            duration, width, height = await asyncio.to_thread(video_processor.get_video_metadata, str(final_video_path))

            await bot.send_video(
                chat_id=chat_id,
                video=FSInputFile(str(final_video_path)),
                thumbnail=FSInputFile(str(custom_thumb_path)) if custom_thumb_path and custom_thumb_path.exists() else None,
                duration=duration, width=width, height=height
            )
            await bot.send_message(
                chat_id=chat_id,
                text="تسک شما انجام شد✅",
                reply_markup=get_task_done_keyboard()
            )

            private_archive_caption = f"the user: @{username} | {user_id}\n" f"the task: {'/'.join(applied_tasks) or 'none'}"
            await telegram_api.upload_video(
                bot=bot, target_chat_id=settings.private_archive_channel_id, file_path=str(final_video_path),
                thumb_path=str(custom_thumb_path) if custom_thumb_path and custom_thumb_path.exists() else None,
                caption=private_archive_caption,
                duration=duration, width=width, height=height
            )

            await bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)

        except Exception as e:
            logger.error(f"Error in encode_video_task for user {user_id}: {e}", exc_info=True)
            if status_message:
                await bot.edit_message_text(
                    text=f"❌ خطایی در حین پردازش ویدیو رخ داد: {e}",
                    chat_id=chat_id, message_id=status_message.message_id
                )
                await bot.send_message(chat_id=chat_id, text="لطفا دوباره تلاش کنید.", reply_markup=get_main_menu_keyboard())
        finally:
            if task_dir.exists():
                shutil.rmtree(task_dir)
            await bot.session.close()

    helpers.run_async_in_sync(_async_worker())