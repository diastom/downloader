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
from utils.bot_instance import create_bot_instance

logger = logging.getLogger(__name__)

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
            auto_thumb_path = None
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

            if options.get("water") and options.get("watermark_id"):
                async with AsyncSessionLocal() as session:
                    watermark_settings = await database.get_user_watermark_by_id(
                        session, user_id, options["watermark_id"]
                    )
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

            if options.get("thumb") and options.get("thumb_id"):
                async with AsyncSessionLocal() as session:
                    thumbnail = await database.get_user_thumbnail_by_id(session, user_id, options["thumb_id"])
                thumbnail_id = thumbnail.file_id if thumbnail else None
                if thumbnail_id:
                    await bot.edit_message_text("🖼️ در حال دریافت تامبنیل...", chat_id=chat_id, message_id=status_message.message_id)
                    thumb_file = await bot.get_file(thumbnail_id)
                    custom_thumb_path = task_dir / f"thumb_{user_id}.jpg"
                    await helpers.download_or_copy_file(bot, thumb_file, custom_thumb_path)
                    thumb_ready = await asyncio.to_thread(
                        video_processor.prepare_thumbnail_image,
                        custom_thumb_path,
                    )
                    if thumb_ready:
                        applied_tasks.append("thumb")
                    else:
                        logger.warning(
                            "Custom thumbnail for user %s could not be prepared and will be skipped.",
                            user_id,
                        )
                        custom_thumb_path = None

            if not custom_thumb_path:
                auto_thumb_path = task_dir / f"auto_thumb_{user_id}.jpg"
                thumb_success = await asyncio.to_thread(
                    video_processor.generate_thumbnail_from_video,
                    str(final_video_path),
                    str(auto_thumb_path),
                )
                if thumb_success:
                    prepared = await asyncio.to_thread(
                        video_processor.prepare_thumbnail_image,
                        auto_thumb_path,
                    )
                    if prepared:
                        custom_thumb_path = auto_thumb_path
                        applied_tasks.append("thumb_auto")
                    else:
                        logger.warning(
                            "Auto-generated thumbnail for user %s could not be prepared and will be skipped.",
                            user_id,
                        )
                        if auto_thumb_path and auto_thumb_path.exists():
                            auto_thumb_path.unlink()
                        auto_thumb_path = None
                else:
                    logger.warning(
                        "Failed to auto-generate thumbnail for user %s from video %s.",
                        user_id,
                        final_video_path,
                    )
                    if auto_thumb_path and auto_thumb_path.exists():
                        auto_thumb_path.unlink()
                    auto_thumb_path = None

            await bot.edit_message_text("📤 در حال آپلود ویدیوی نهایی...", chat_id=chat_id, message_id=status_message.message_id)
            duration, width, height = await asyncio.to_thread(video_processor.get_video_metadata, str(final_video_path))

            delivery_mode = options.get("delivery_mode", "media")

            if delivery_mode == "file":
                await bot.send_document(
                    chat_id=chat_id,
                    document=FSInputFile(str(final_video_path)),
                    thumbnail=FSInputFile(str(custom_thumb_path)) if custom_thumb_path and custom_thumb_path.exists() else None,
                )
            else:
                await bot.send_video(
                    chat_id=chat_id,
                    video=FSInputFile(str(final_video_path)),
                    thumbnail=FSInputFile(str(custom_thumb_path)) if custom_thumb_path and custom_thumb_path.exists() else None,
                    duration=duration,
                    width=width,
                    height=height,
                    supports_streaming=True,
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
            if bot:
                await bot.session.close()

    helpers.run_async_in_sync(_async_worker())