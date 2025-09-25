import asyncio
import json
import logging
import os
import shutil
import tempfile
import urllib.parse
from pathlib import Path
import concurrent.futures
import requests

from aiogram.types import FSInputFile

from config import settings
from utils import database, helpers, telegram_api, video_processor
from utils.db_session import AsyncSessionLocal
from tasks.celery_app import celery_app
from bot.handlers.common import get_task_done_keyboard, get_main_menu_keyboard
from utils.models import PublicArchive
from utils.bot_instance import create_bot_instance

logger = logging.getLogger(__name__)

@celery_app.task(name="tasks.download_video_task")
def download_video_task(
    chat_id: int,
    url: str,
    selected_format: str,
    video_info_json: str,
    user_id: int,
    send_completion_message: bool = True,
    source_domain: str | None = None,
):
    video_info = json.loads(video_info_json) if video_info_json else {}

    async def _async_worker():
        bot = None
        bot = create_bot_instance()
        status_message = await bot.send_message(chat_id=chat_id, text="📥 Your video download is starting...") if send_completion_message else None

        video_path_to_clean = None
        if url.startswith("file://"):
            video_path_to_clean = url.replace("file://", "")

        try:
            if not video_info and not url.startswith("file://"):
                info = await asyncio.to_thread(helpers.get_full_video_info, url)
                if not info:
                    if status_message: await bot.edit_message_text(text="❌ Could not fetch video metadata.", chat_id=chat_id, message_id=status_message.message_id)
                    return
                video_info.update(info)

            title = helpers.sanitize_filename(video_info.get('title', 'untitled_video')) or Path(url).stem

            with tempfile.TemporaryDirectory() as temp_dir:
                if status_message: await bot.edit_message_text(text=f"📥 Downloading: {title}...", chat_id=chat_id, message_id=status_message.message_id)

                if url.startswith("file://"):
                    raw_video_path = url.replace("file://", "")
                else:
                    raw_video_path = await asyncio.to_thread(helpers.download_video, url, temp_dir, selected_format)

                if not raw_video_path or not os.path.exists(raw_video_path): raise Exception("Video download failed or file not found.")

                repaired_path = os.path.join(temp_dir, "repaired.mp4")
                final_video_path = repaired_path
                if not await asyncio.to_thread(video_processor.repair_video, raw_video_path, repaired_path):
                     repaired_path = raw_video_path
                     final_video_path = raw_video_path
                duration, width, height = await asyncio.to_thread(video_processor.get_video_metadata, repaired_path)
                generated_thumb_path = os.path.join(temp_dir, "generated_thumb.jpg")
                thumb_success = await asyncio.to_thread(video_processor.generate_thumbnail_from_video, repaired_path, generated_thumb_path)
                final_thumb_path = generated_thumb_path if thumb_success else None

                if status_message: await bot.edit_message_text(text="📤 Uploading to public archive...", chat_id=chat_id, message_id=status_message.message_id)
                public_channel_id = settings.public_archive_channel_id
                public_message_id = await telegram_api.upload_video(bot=bot, target_chat_id=public_channel_id, file_path=repaired_path, thumb_path=final_thumb_path, caption=title, duration=duration, width=width, height=height)
                if not public_message_id: raise Exception("Upload to public archive failed.")

                if not url.startswith("file://"):
                    async with AsyncSessionLocal() as session:
                        await database.add_public_archive_item(session, url=url, message_id=public_message_id, channel_id=public_channel_id)

                if status_message: await bot.edit_message_text(text="📨 Sending to you...", chat_id=chat_id, message_id=status_message.message_id)

                await bot.copy_message(chat_id=chat_id, from_chat_id=public_channel_id, message_id=public_message_id)

                if status_message: await bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)

                derived_domain = source_domain or (urllib.parse.urlparse(url).netloc.lower().replace('www.', '') if not url.startswith("file://") else "local_file")
                if not derived_domain:
                    derived_domain = "unknown"

                size_bytes = os.path.getsize(final_video_path) if os.path.exists(final_video_path) else 0
                try:
                    async with AsyncSessionLocal() as session:
                        await database.record_download_event(
                            session,
                            user_id=user_id,
                            domain=derived_domain,
                            size_bytes=size_bytes,
                            task_type="download",
                        )
                except Exception as log_error:
                    logger.error(f"Failed to record download event for user {user_id}: {log_error}", exc_info=True)

                if send_completion_message:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="تسک شما انجام شد ✅",
                        reply_markup=get_task_done_keyboard()
                    )

        except Exception as e:
            logger.error(f"Celery Video Task Error: {e}", exc_info=True)
            if status_message:
                await bot.edit_message_text(text=f"❌ An error occurred during video processing: {e}", chat_id=chat_id, message_id=status_message.message_id)
                if send_completion_message:
                     await bot.send_message(chat_id=chat_id, text="Please try again or contact an admin.", reply_markup=get_main_menu_keyboard())
        finally:
            if video_path_to_clean and os.path.exists(video_path_to_clean):
                try:
                    os.remove(video_path_to_clean)
                    logger.info(f"Cleaned up temporary video file: {video_path_to_clean}")
                except OSError as e:
                    logger.error(f"Error cleaning up file {video_path_to_clean}: {e}", exc_info=True)
            if bot:
                await bot.session.close()

    helpers.run_async_in_sync(_async_worker())

@celery_app.task(name="tasks.process_erome_album_task")
def process_erome_album_task(chat_id: int, user_id: int, album_title: str, media_urls: dict, choice: str):
    async def _async_worker():
        bot = create_bot_instance()
        try:
            status_msg = await bot.send_message(chat_id=chat_id, text=f"📥 Starting download for '{album_title}'...")
            with tempfile.TemporaryDirectory() as temp_dir:
                images_to_dl = media_urls.get('images', []) if choice in ['images', 'both'] else []
                videos_to_dl = media_urls.get('videos', []) if choice in ['videos', 'both'] else []
                total_bytes = 0

                if images_to_dl:
                    await bot.edit_message_text(
                        text=f"📥 Downloading {len(images_to_dl)} images...",
                        chat_id=chat_id,
                        message_id=status_msg.message_id,
                    )
                    for i, img_url in enumerate(images_to_dl):
                        filename = os.path.basename(urllib.parse.urlparse(img_url).path) or f"erome_img_{i}.jpg"
                        try:
                            response = requests.get(img_url, headers=helpers.EROME_HEADERS, stream=True, timeout=60)
                            response.raise_for_status()
                            img_path = os.path.join(temp_dir, filename)
                            with open(img_path, 'wb') as f:
                                shutil.copyfileobj(response.raw, f)
                            if os.path.exists(img_path):
                                total_bytes += os.path.getsize(img_path)
                            await bot.send_photo(chat_id=chat_id, photo=FSInputFile(img_path), caption=filename)
                        except Exception as e:
                            logger.error(f"Failed to download Erome image {img_url}: {e}")

                if videos_to_dl:
                    await bot.edit_message_text(
                        text=f"📥 Queuing {len(videos_to_dl)} videos for download...",
                        chat_id=chat_id,
                        message_id=status_msg.message_id,
                    )
                    for vid_url in videos_to_dl:
                        download_video_task.delay(
                            chat_id=chat_id,
                            url=vid_url,
                            selected_format='best',
                            video_info_json='{}',
                            user_id=user_id,
                            send_completion_message=False,
                            source_domain='erome.com',
                        )

                if total_bytes > 0:
                    try:
                        async with AsyncSessionLocal() as session:
                            await database.record_download_event(
                                session,
                                user_id=user_id,
                                domain='erome.com',
                                size_bytes=total_bytes,
                                task_type='download',
                            )
                    except Exception as log_error:
                        logger.error(
                            f"Failed to record Erome image download event for user {user_id}: {log_error}",
                            exc_info=True,
                        )
            await bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            await bot.send_message(chat_id=chat_id, text="تسک شما کامل شد✅", reply_markup=get_main_menu_keyboard())
        finally:
            if bot:
                await bot.session.close()
    helpers.run_async_in_sync(_async_worker())

@celery_app.task(name="tasks.process_gallery_dl_task")
def process_gallery_dl_task(chat_id: int, url: str, create_zip: bool, user_id: int):
    async def _async_worker():
        bot = create_bot_instance()
        status_message = None
        zip_path = None
        try:
            status_message = await bot.send_message(chat_id=chat_id, text=f"📥 Request for '{urllib.parse.urlparse(url).netloc}' received...")
            with tempfile.TemporaryDirectory() as temp_dir:
                downloaded_files, error = await helpers.run_gallery_dl_download(url, temp_dir)
                if error or not downloaded_files:
                    raise Exception(error or "No files were downloaded.")

                domain_name = urllib.parse.urlparse(url).netloc.lower().replace('www.', '') or 'gallery_dl'
                total_bytes = 0
                recorded = False

                if create_zip:
                    await bot.edit_message_text(text="🗜️ Creating ZIP file...", chat_id=chat_id, message_id=status_message.message_id)
                    zip_name = f"{helpers.sanitize_filename(urllib.parse.urlparse(url).netloc)}_gallery.zip"
                    zip_path = os.path.join(os.path.dirname(temp_dir), zip_name)
                    await asyncio.to_thread(helpers.create_zip_from_folder, temp_dir, zip_path)
                    await bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)
                    await bot.send_document(chat_id=chat_id, document=FSInputFile(zip_path), caption=zip_name, reply_markup=get_main_menu_keyboard())
                    if os.path.exists(zip_path):
                        total_bytes += os.path.getsize(zip_path)
                    recorded = True
                else:
                    total = len(downloaded_files)
                    for i, file_path in enumerate(downloaded_files):
                        filename = os.path.basename(file_path)
                        await bot.edit_message_text(text=f"📤 Processing {i+1}/{total}: {filename}", chat_id=chat_id, message_id=status_message.message_id)
                        ext = os.path.splitext(filename)[1].lower()
                        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                        if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                            total_bytes += file_size
                            await bot.send_photo(chat_id=chat_id, photo=FSInputFile(file_path), caption=filename)
                        elif ext in ['.mp4', '.mkv', '.webm', '.mov']:
                            try:
                                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=tempfile.gettempdir()) as temp_vid:
                                    shutil.move(file_path, temp_vid.name)
                                    download_video_task.delay(
                                        chat_id=chat_id,
                                        url=f"file://{temp_vid.name}",
                                        selected_format='best',
                                        video_info_json=f'{{"title": "{filename}"}}',
                                        user_id=user_id,
                                        send_completion_message=False,
                                        source_domain=domain_name,
                                    )
                            except Exception as e:
                                logger.error(f"Failed to move and queue video {filename}: {e}", exc_info=True)
                                await bot.send_message(chat_id=chat_id, text=f"⚠️ Could not process video: {filename}")
                        else:
                            total_bytes += file_size
                            await bot.send_document(chat_id=chat_id, document=FSInputFile(file_path), caption=filename)
                    await bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)
                    await bot.send_message(chat_id=chat_id, text="تسک شما کامل شد✅", reply_markup=get_task_done_keyboard())
                    recorded = True

                if recorded and total_bytes > 0:
                    try:
                        async with AsyncSessionLocal() as session:
                            await database.record_download_event(
                                session,
                                user_id=user_id,
                                domain=domain_name,
                                size_bytes=total_bytes,
                                task_type='download',
                            )
                    except Exception as log_error:
                        logger.error(f"Failed to record gallery download event for user {user_id}: {log_error}", exc_info=True)
        except Exception as e:
            logger.error(f"Celery Gallery-DL Task Error: {e}", exc_info=True)
            if status_message:
                await bot.edit_message_text(text=f"❌ An error occurred: {e}", chat_id=chat_id, message_id=status_message.message_id)
        finally:
            if zip_path and os.path.exists(zip_path): os.remove(zip_path)
            if bot:
                await bot.session.close()
    helpers.run_async_in_sync(_async_worker())

@celery_app.task(name="tasks.process_manhwa_task")
def process_manhwa_task(chat_id: int, manhwa_title: str, chapters_to_download: list, create_zip: bool, site_key: str, user_id: int):
    site_configs = {'toonily.com': {'get_images': helpers.get_chapter_image_urls_com, 'needs_selenium': True}, 'toonily.me': {'get_images': helpers.mn2_get_chapter_images, 'needs_selenium': False}, 'manhwaclan.com': {'get_images': helpers.mc_get_chapter_image_urls, 'needs_selenium': False}, 'mangadistrict.com': {'get_images': helpers.md_get_chapter_image_urls, 'needs_selenium': False}, 'comick.io': {'get_images': helpers.cm_get_chapter_image_urls, 'needs_selenium': False}}
    config = site_configs.get(site_key)
    async def _async_worker():
        bot = create_bot_instance()
        status_message = None
        driver = None
        try:
            if not config:
                await bot.send_message(chat_id=chat_id, text=f"Internal error: No config for {site_key}.")
                return
            status_message = await bot.send_message(chat_id=chat_id, text=f"📥 Request for '{manhwa_title}' processing...")
            with tempfile.TemporaryDirectory() as base_temp_dir:
                if config['needs_selenium']:
                    driver = await asyncio.to_thread(helpers.setup_chrome_driver)
                total_chapters = len(chapters_to_download)
                total_bytes = 0
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
                        if zip_path.exists():
                            total_bytes += os.path.getsize(zip_path)
                    else:
                        for image_file in sorted(chapter_temp_folder.glob('*.jpg')):
                            if image_file.exists():
                                total_bytes += os.path.getsize(image_file)
                            await bot.send_photo(chat_id=chat_id, photo=FSInputFile(image_file))

                await bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)
                await bot.send_message(chat_id=chat_id, text="تسک شما انجام شد✅", reply_markup=get_task_done_keyboard())
                if total_bytes > 0:
                    try:
                        async with AsyncSessionLocal() as session:
                            await database.record_download_event(
                                session,
                                user_id=user_id,
                                domain=site_key,
                                size_bytes=total_bytes,
                                task_type='download',
                            )
                    except Exception as log_error:
                        logger.error(f"Failed to record manhwa download event for user {user_id}: {log_error}", exc_info=True)
        except Exception as e:
            logger.error(f"Celery Manhwa Task Error for {site_key}: {e}", exc_info=True)
            if status_message:
                await bot.edit_message_text(text=f"❌ An error occurred during download: {e}", chat_id=chat_id, message_id=status_message.message_id)
        finally:
            if driver: driver.quit()
            if bot:
                await bot.session.close()
    helpers.run_async_in_sync(_async_worker())