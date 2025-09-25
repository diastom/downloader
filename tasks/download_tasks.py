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

from config import settings
from utils import database, helpers, telegram_api, video_processor
from utils.db_session import AsyncSessionLocal
from tasks.celery_app import celery_app
from bot.handlers.common import get_main_menu_keyboard
from utils.models import PublicArchive

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
        status_message = await bot_instance.send_message(chat_id=chat_id, text="📥 Your video download is starting...")

        if not video_info:
            info = await asyncio.to_thread(helpers.get_full_video_info, url)
            if not info:
                await bot_instance.edit_message_text(text="❌ Could not fetch video metadata.", chat_id=chat_id, message_id=status_message.message_id)
                return
            video_info.update(info)

        title = helpers.sanitize_filename(video_info.get('title', 'untitled_video'))

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                await bot_instance.edit_message_text(text=f"📥 Downloading: {title}...", chat_id=chat_id, message_id=status_message.message_id)
                raw_video_path = await asyncio.to_thread(helpers.download_video, url, temp_dir, selected_format)
                if not raw_video_path: raise Exception("Video download failed.")
                repaired_path = os.path.join(temp_dir, "repaired.mp4")
                if not await asyncio.to_thread(video_processor.repair_video, raw_video_path, repaired_path):
                     repaired_path = raw_video_path
                duration, width, height = await asyncio.to_thread(video_processor.get_video_metadata, repaired_path)
                generated_thumb_path = os.path.join(temp_dir, "generated_thumb.jpg")
                thumb_success = await asyncio.to_thread(video_processor.generate_thumbnail_from_video, repaired_path, generated_thumb_path)
                final_thumb_path = generated_thumb_path if thumb_success else None
                await bot_instance.edit_message_text(text="📤 Uploading to public archive...", chat_id=chat_id, message_id=status_message.message_id)
                public_channel_id = settings.public_archive_channel_id
                public_message_id = await telegram_api.upload_video(bot=bot_instance, target_chat_id=public_channel_id, file_path=repaired_path, thumb_path=final_thumb_path, caption=title, duration=duration, width=width, height=height)
                if not public_message_id: raise Exception("Upload to public archive failed.")
                async with AsyncSessionLocal() as session:
                    await database.add_public_archive_item(session=session, url=url, message_id=public_message_id, channel_id=public_channel_id)
                await bot_instance.edit_message_text(text="📨 Sending to you...", chat_id=chat_id, message_id=status_message.message_id)
                await bot_instance.copy_message(chat_id=chat_id, from_chat_id=public_channel_id, message_id=public_message_id)
                await bot_instance.delete_message(chat_id=chat_id, message_id=status_message.message_id)
                await bot_instance.send_message(chat_id=chat_id, text="✅ Download complete.", reply_markup=get_main_menu_keyboard())
            except Exception as e:
                logger.error(f"Celery Video Task Error: {e}", exc_info=True)
                await bot_instance.edit_message_text(text=f"❌ An error occurred during video processing: {e}", chat_id=chat_id, message_id=status_message.message_id)
                await bot_instance.send_message(chat_id=chat_id, text="Please try again or contact an admin.", reply_markup=get_main_menu_keyboard())
    helpers.run_async_in_sync(_async_worker())

@celery_app.task(name="tasks.process_erome_album_task")
def process_erome_album_task(chat_id: int, user_id: int, album_title: str, media_urls: dict, choice: str):
    async def _async_worker():
        bot = get_bot_instance()
        images_to_dl = media_urls.get('images', []) if choice in ['images', 'both'] else []
        videos_to_dl = media_urls.get('videos', []) if choice in ['videos', 'both'] else []
        with tempfile.TemporaryDirectory() as temp_dir:
            if images_to_dl:
                status_msg = await bot.send_message(chat_id=chat_id, text=f"📥 Downloading {len(images_to_dl)} images for '{album_title}'...")
                for i, img_url in enumerate(images_to_dl):
                    filename = os.path.basename(urllib.parse.urlparse(img_url).path) or f"erome_img_{i}.jpg"
                    await bot.edit_message_text(text=f"[{i+1}/{len(images_to_dl)}] 🖼️ Downloading {filename}...", chat_id=chat_id, message_id=status_msg.message_id)
                    try:
                        response = requests.get(img_url, headers=helpers.EROME_HEADERS, stream=True, timeout=60)
                        response.raise_for_status()
                        img_path = os.path.join(temp_dir, filename)
                        with open(img_path, 'wb') as f: shutil.copyfileobj(response.raw, f)
                        await bot.send_photo(chat_id=chat_id, photo=FSInputFile(img_path), caption=filename)
                    except Exception as e:
                        logger.error(f"Failed to download Erome image {img_url}: {e}")
                        await bot.send_message(chat_id=chat_id, text=f"❌ Failed to process image: {filename}")
                await bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            if videos_to_dl:
                for vid_url in videos_to_dl:
                    download_video_task.delay(chat_id=chat_id, url=vid_url, selected_format='best', video_info_json='{}', user_id=user_id)
    helpers.run_async_in_sync(_async_worker())

@celery_app.task(name="tasks.process_gallery_dl_task")
def process_gallery_dl_task(chat_id: int, url: str, create_zip: bool, user_id: int):
    async def _async_worker():
        bot = get_bot_instance()
        status_message = await bot.send_message(chat_id=chat_id, text=f"📥 Request for '{urllib.parse.urlparse(url).netloc}' received...")
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = None
            try:
                downloaded_files, error = await helpers.run_gallery_dl_download(url, temp_dir)
                if error or not downloaded_files: raise Exception(error or "No files were downloaded.")
                if create_zip:
                    await bot.edit_message_text(text="🗜️ Creating ZIP file...", chat_id=chat_id, message_id=status_message.message_id)
                    zip_name = f"{helpers.sanitize_filename(urllib.parse.urlparse(url).netloc)}_gallery.zip"
                    zip_path = os.path.join(os.path.dirname(temp_dir), zip_name)
                    await asyncio.to_thread(helpers.create_zip_from_folder, temp_dir, zip_path)
                    await bot.edit_message_text(text=f"📤 Uploading ZIP: {zip_name}", chat_id=chat_id, message_id=status_message.message_id)
                    await bot.send_document(chat_id=chat_id, document=FSInputFile(zip_path), caption=zip_name)
                else:
                    total = len(downloaded_files)
                    for i, file_path in enumerate(downloaded_files):
                        filename = os.path.basename(file_path)
                        await bot.edit_message_text(text=f"📤 Processing {i+1}/{total}: {filename}", chat_id=chat_id, message_id=status_message.message_id)
                        ext = os.path.splitext(filename)[1].lower()
                        if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                            await bot.send_photo(chat_id=chat_id, photo=FSInputFile(file_path), caption=filename)
                        elif ext in ['.mp4', '.mkv', '.webm', '.mov']:
                            # Videos from galleries are sent through the standard video download task
                            download_video_task.delay(chat_id=chat_id, url=f"file://{file_path}", selected_format='best', video_info_json='{}', user_id=user_id)
                        else:
                            await bot.send_document(chat_id=chat_id, document=FSInputFile(file_path), caption=filename)
                await bot.edit_message_text(text="✅ All files sent successfully.", chat_id=chat_id, message_id=status_message.message_id)
            except Exception as e:
                logger.error(f"Celery Gallery-DL Task Error: {e}", exc_info=True)
                await bot.edit_message_text(text=f"❌ An error occurred: {e}", chat_id=chat_id, message_id=status_message.message_id)
            finally:
                if zip_path and os.path.exists(zip_path): os.remove(zip_path)
    helpers.run_async_in_sync(_async_worker())

@celery_app.task(name="tasks.process_manhwa_task")
def process_manhwa_task(chat_id: int, manhwa_title: str, chapters_to_download: list, create_zip: bool, site_key: str):
    site_configs = {'toonily.com': {'get_images': helpers.get_chapter_image_urls_com, 'needs_selenium': True}, 'toonily.me': {'get_images': helpers.mn2_get_chapter_images, 'needs_selenium': False}, 'manhwaclan.com': {'get_images': helpers.mc_get_chapter_image_urls, 'needs_selenium': False}, 'mangadistrict.com': {'get_images': helpers.md_get_chapter_image_urls, 'needs_selenium': False}, 'comick.io': {'get_images': helpers.cm_get_chapter_image_urls, 'needs_selenium': False}}
    config = site_configs.get(site_key)
    async def _async_worker():
        bot = get_bot_instance()
        if not config:
            await bot.send_message(chat_id=chat_id, text=f"Internal error: No config for {site_key}.")
            return
        status_message = await bot.send_message(chat_id=chat_id, text=f"📥 Request for '{manhwa_title}' processing...")
        driver = None
        with tempfile.TemporaryDirectory() as base_temp_dir:
            try:
                if config['needs_selenium']:
                    driver = await asyncio.to_thread(helpers.setup_chrome_driver)
                total_chapters = len(chapters_to_download)
                for i, chapter in enumerate(chapters_to_download):
                    await bot.edit_message_text(text=f"[{i+1}/{total_chapters}] 📥 Downloading: {chapter['name']}...", chat_id=chat_id, message_id=status_message.message_id)
                    chapter_temp_folder = Path(base_temp_dir) / helpers.sanitize_filename(chapter['name'])
                    chapter_temp_folder.mkdir()
                    chapter_identifier = chapter.get('hid') if site_key == 'comick.io' else chapter['url']
                    image_urls = await asyncio.to_thread(config['get_images'], chapter_identifier, driver) if driver else await asyncio.to_thread(config['get_images'], chapter_identifier)
                    if not image_urls:
                        await bot.send_message(chat_id=chat_id, text=f"⚠️ No images found for chapter: {chapter['name']}")
                        continue
                    headers = {'Referer': f'https://{site_key}/'}
                    dl_tasks = [(url, os.path.join(chapter_temp_folder, f"{j+1:03d}.jpg"), headers) for j, url in enumerate(image_urls)]
                    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                        list(executor.map(helpers.download_single_image, dl_tasks))
                    if not os.listdir(chapter_temp_folder):
                        await bot.send_message(chat_id=chat_id, text=f"❌ Download failed for chapter: {chapter['name']}")
                        continue
                    if create_zip:
                        zip_path = Path(base_temp_dir) / f"{helpers.sanitize_filename(chapter['name'])}.zip"
                        await asyncio.to_thread(helpers.create_zip_from_folder, str(chapter_temp_folder), str(zip_path))
                        await bot.send_document(chat_id=chat_id, document=FSInputFile(zip_path), caption=zip_path.name)
                    else:
                        for img_file in sorted(os.listdir(chapter_temp_folder)):
                            await bot.send_photo(chat_id=chat_id, photo=FSInputFile(chapter_temp_folder / img_file), caption=img_file)
                await bot.edit_message_text(text=f"✅ All downloads for '{manhwa_title}' are complete.", chat_id=chat_id, message_id=status_message.message_id)
            except Exception as e:
                logger.error(f"Celery Manhwa Task Error for {site_key}: {e}", exc_info=True)
                await bot.edit_message_text(text=f"❌ An error occurred during download: {e}", chat_id=chat_id, message_id=status_message.message_id)
            finally:
                if driver: driver.quit()
    helpers.run_async_in_sync(_async_worker())