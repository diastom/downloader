import asyncio
import json
import logging
import os
import shutil
import tempfile
import urllib.parse
from pathlib import Path
import concurrent.futures

from aiogram import Bot
from aiogram.types import FSInputFile

from ..config import settings
from ..utils import database, helpers, telegram_api, video_processor, telegram_client
from .celery_app import celery_app

logger = logging.getLogger(__name__)

# Global bot instance for Celery workers
bot = Bot(token=settings.bot_token)


@celery_app.task(name="tasks.download_and_upload_video")
def download_and_upload_video_task(chat_id: int, url: str, selected_format: str, video_info_json: str, user_id: int):
    """Celery task for downloading a video via yt-dlp, processing, and uploading it."""
    video_info = json.loads(video_info_json) if video_info_json else {}

    async def _async_worker():
        status_message = await bot.send_message(chat_id=chat_id, text="📥 Your download request has been received...")

        title = helpers.sanitize_filename(video_info.get('title', 'untitled_video'))
        final_filename = os.path.join(helpers.DOWNLOAD_FOLDER, f"{title}.mp4") # Assuming DOWNLOAD_FOLDER is defined in helpers

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                await bot.edit_message_text(f"📥 Downloading: {title}...", chat_id=chat_id, message_id=status_message.message_id)

                # This is a blocking process, run in a thread
                raw_video_path = await asyncio.to_thread(
                    helpers.download_video, url, temp_dir, selected_format
                )
                if not raw_video_path:
                    raise Exception("Download failed.")

                repaired_path = os.path.join(temp_dir, "repaired.mp4")
                if not await asyncio.to_thread(video_processor.repair_video, raw_video_path, repaired_path):
                     raise Exception("Video repair failed.")

                duration, width, height = await asyncio.to_thread(video_processor.get_video_metadata, repaired_path)

                # Thumbnail handling
                default_thumb_path = None
                thumbnail_url = video_info.get('thumbnail')
                if thumbnail_url:
                    try:
                        thumb_res = await asyncio.to_thread(requests.get, thumbnail_url, stream=True, timeout=20)
                        thumb_res.raise_for_status()
                        default_thumb_path = os.path.join(temp_dir, "default_thumb.jpg")
                        with open(default_thumb_path, 'wb') as f:
                            shutil.copyfileobj(thumb_res.raw, f)
                    except Exception as e:
                        logger.warning(f"Failed to download default thumbnail: {e}")

                if not default_thumb_path:
                    fallback_thumb_path = os.path.join(temp_dir, 'fallback_thumb.jpg')
                    if await asyncio.to_thread(video_processor.generate_thumbnail_from_video, repaired_path, fallback_thumb_path):
                        default_thumb_path = fallback_thumb_path

                await bot.edit_message_text("📤 Uploading to public archive...", chat_id=chat_id, message_id=status_message.message_id)
                public_upload_id = await telegram_api.upload_video(
                    bot, settings.public_archive_chat_id, repaired_path, default_thumb_path, title, duration, width, height
                )
                if not public_upload_id:
                    raise Exception("Upload to public archive failed.")

                # User-specific customizations
                custom_thumbnail_id = database.get_user_thumbnail(user_id)
                watermark_settings = database.get_user_watermark_settings(user_id)
                user_has_customization = custom_thumbnail_id or watermark_settings.get("enabled")

                if not user_has_customization:
                    database.add_to_video_cache(url, selected_format, public_upload_id)
                    await bot.edit_message_text("📨 Sending to you...", chat_id=chat_id, message_id=status_message.message_id)
                    await bot.copy_message(chat_id, settings.public_archive_chat_id, public_upload_id)
                else:
                    await bot.edit_message_text("🎨 Applying your personalizations...", chat_id=chat_id, message_id=status_message.message_id)

                    path_after_watermark = await asyncio.to_thread(
                        video_processor.apply_watermark_to_video, repaired_path, watermark_settings
                    )

                    custom_thumb_path = None
                    if custom_thumbnail_id:
                        thumb_file = await bot.get_file(custom_thumbnail_id)
                        custom_thumb_path = os.path.join(temp_dir, 'custom_thumb.jpg')
                        await bot.download_file(thumb_file.file_path, destination=custom_thumb_path)

                    personal_archive_id = await telegram_client.get_or_create_personal_archive(user_id, (await bot.get_me()).username)
                    if not personal_archive_id:
                        raise Exception("Failed to get or create personal archive.")

                    await bot.edit_message_text("📤 Uploading personalized version...", chat_id=chat_id, message_id=status_message.message_id)
                    personal_upload_id = await telegram_api.upload_video(
                        bot, personal_archive_id, path_after_watermark, custom_thumb_path, title, duration, width, height
                    )
                    if not personal_upload_id:
                        raise Exception("Upload to personal archive failed.")

                    await bot.copy_message(chat_id, personal_archive_id, personal_upload_id)

                await bot.delete_message(chat_id, status_message.message_id)

            except Exception as e:
                logger.error(f"Celery Video Task Error: {e}", exc_info=True)
                await bot.edit_message_text(f"❌ An error occurred: {e}", chat_id=chat_id, message_id=status_message.message_id)

    helpers.run_async_in_sync(_async_worker())


@celery_app.task(name="tasks.process_gallery_dl")
def process_gallery_dl_task(chat_id: int, url: str, create_zip: bool):
    """Celery task for downloading from gallery-dl supported sites."""
    async def _async_worker():
        status_message = await bot.send_message(chat_id=chat_id, text=f"📥 Request for '{urllib.parse.urlparse(url).netloc}' received...")

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                downloaded_files, error = await helpers.run_gallery_dl_download(url, temp_dir)
                if error or not downloaded_files:
                    raise Exception(error or "No files were downloaded.")

                if create_zip:
                    await bot.edit_message_text("🗜️ Creating ZIP file...", chat_id=chat_id, message_id=status_message.message_id)
                    zip_path = os.path.join(temp_dir, "archive.zip")
                    await asyncio.to_thread(helpers.create_zip_from_folder, temp_dir, zip_path)

                    await bot.edit_message_text("📤 Uploading ZIP...", chat_id=chat_id, message_id=status_message.message_id)
                    await bot.send_document(chat_id, FSInputFile(zip_path))
                else:
                    total = len(downloaded_files)
                    for i, file_path in enumerate(downloaded_files):
                        filename = os.path.basename(file_path)
                        await bot.edit_message_text(f"📤 Uploading {i+1}/{total}: {filename}", chat_id=chat_id, message_id=status_message.message_id)
                        # Simple check for media type based on extension
                        ext = os.path.splitext(filename)[1].lower()
                        if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                            await bot.send_photo(chat_id, FSInputFile(file_path), caption=filename)
                        elif ext in ['.mp4', '.mkv', '.webm']:
                            await bot.send_video(chat_id, FSInputFile(file_path), caption=filename)
                        else:
                            await bot.send_document(chat_id, FSInputFile(file_path), caption=filename)

                await bot.edit_message_text("✅ All files sent successfully.", chat_id=chat_id, message_id=status_message.message_id)

            except Exception as e:
                logger.error(f"Celery Gallery-DL Task Error: {e}", exc_info=True)
                await bot.edit_message_text(f"❌ An error occurred: {e}", chat_id=chat_id, message_id=status_message.message_id)

    helpers.run_async_in_sync(_async_worker())

@celery_app.task(name="tasks.process_manhwa_task")
def process_manhwa_task(chat_id: int, manhwa_title: str, chapters_to_download: list, create_zip: bool, site_key: str):
    """
    A generic Celery task to download chapters from various manhwa/comic sites.
    It uses a site_key to determine which helper functions to use.
    """
    site_configs = {
        'toonily.com': {'get_images': helpers.get_chapter_image_urls_com, 'needs_selenium': True, 'headers': {'Referer': 'https://toonily.com/'}},
        'toonily.me': {'get_images': helpers.mn2_get_chapter_images, 'needs_selenium': False, 'headers': {'Referer': f'https://{helpers.TOONILY_ME_DOMAIN}/'}},
        'manhwaclan.com': {'get_images': helpers.mc_get_chapter_image_urls, 'needs_selenium': False, 'headers': {}},
        'mangadistrict.com': {'get_images': helpers.md_get_chapter_image_urls, 'needs_selenium': False, 'headers': {}},
        'comick.io': {'get_images': helpers.cm_get_chapter_image_urls, 'needs_selenium': True, 'headers': {'Referer': f'https://{helpers.COMICK_DOMAIN}/'}},
    }
    config = site_configs.get(site_key)
    if not config:
        logger.error(f"No config found for site_key: {site_key}")
        return

    async def _async_worker():
        status_message = await bot.send_message(chat_id=chat_id, text=f"📥 Request for '{manhwa_title}' received...")

        manhwa_folder = Path(tempfile.gettempdir()) / helpers.sanitize_filename(manhwa_title)
        manhwa_folder.mkdir(parents=True, exist_ok=True)

        driver = None
        try:
            if config['needs_selenium']:
                driver = await asyncio.to_thread(helpers.setup_chrome_driver if site_key != 'comick.io' else helpers.setup_firefox_driver)
                if not driver: raise Exception("Failed to start Selenium driver.")

            total = len(chapters_to_download)
            for i, chapter in enumerate(chapters_to_download):
                await bot.edit_message_text(f"[{i+1}/{total}] 📥 Downloading: {chapter['name']}...", chat_id=chat_id, message_id=status_message.message_id)

                chapter_folder = manhwa_folder / helpers.sanitize_filename(chapter['name'])
                chapter_folder.mkdir(exist_ok=True)

                image_urls = await asyncio.to_thread(config['get_images'], chapter['url'], driver) if driver else await asyncio.to_thread(config['get_images'], chapter['url'])

                dl_tasks = [(url, os.path.join(chapter_folder, f"{j+1:03d}.jpg"), config['headers']) for j, url in enumerate(image_urls)]

                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    executor.map(helpers.download_single_image, dl_tasks)

                if create_zip:
                    zip_path = manhwa_folder / f"{manhwa_title} - {chapter['name']}.zip"
                    await asyncio.to_thread(helpers.create_zip_from_folder, str(chapter_folder), str(zip_path))
                    await bot.send_document(chat_id, FSInputFile(zip_path))
                    os.remove(zip_path)
                else:
                    for img in sorted(os.listdir(chapter_folder)):
                        await bot.send_photo(chat_id, FSInputFile(chapter_folder / img))

                shutil.rmtree(chapter_folder)

            await bot.edit_message_text(f"✅ Download complete for '{manhwa_title}'.", chat_id=chat_id, message_id=status_message.message_id)

        except Exception as e:
            logger.error(f"Celery Manhwa Task Error for {site_key}: {e}", exc_info=True)
            await bot.edit_message_text(f"❌ An error occurred: {e}", chat_id=chat_id, message_id=status_message.message_id)
        finally:
            if driver: driver.quit()
            if manhwa_folder.exists(): shutil.rmtree(manhwa_folder)

    asyncio.run(_async_worker())
