import asyncio
import concurrent.futures
import logging
import time
import os
import re
import shutil
import zipfile
from datetime import datetime
from typing import Dict, List, Tuple, Coroutine
from urllib.parse import urljoin, urlparse
import json
import requests
import yt_dlp
import aiohttp
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, File
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from aiogram import Bot

from utils import database
from config import settings

logger = logging.getLogger(__name__)

# --- Async Runner (FIXED) ---
def run_async_in_sync(coro: Coroutine):
    """
    Safely runs an async coroutine from a synchronous context like Celery by
    creating a new event loop for each execution. This is the most robust way
    to prevent "Future attached to a different loop" errors.
    """
    return asyncio.run(coro)


# --- Domain Constants ---
DOWNLOAD_FOLDER = "downloads"
TOONILY_COM_DOMAIN = "toonily.com"
TOONILY_ME_DOMAIN = "toonily.me"
MANHWACLAN_DOMAIN = "manhwaclan.com"
MANGA_DISTRICT_DOMAIN = "mangadistrict.com"
COSPLAYTELE_DOMAIN = "cosplaytele.com"
COMICK_DOMAIN = "comick.io"
PORNHUB_DOMAIN = "pornhub.com"
EROME_DOMAIN = "erome.com"
EPORNER_DOMAIN = "eporner.com"
GALLERY_DL_SITES = ["rule34.xyz", "coomer.st", "aryion.com", "kemono.cr", "tapas.io", "tsumino.com", "danbooru.donmai.us", "e621.net"]
GALLERY_DL_ZIP_SITES = ["mangadex.org", "e-hentai.org"]

ALL_SUPPORTED_SITES = {
    "Manhwa/Webtoon": [TOONILY_COM_DOMAIN, TOONILY_ME_DOMAIN, MANHWACLAN_DOMAIN, MANGA_DISTRICT_DOMAIN, COMICK_DOMAIN],
    "Gallery/Hentai": GALLERY_DL_SITES + GALLERY_DL_ZIP_SITES,
    "Album": [EROME_DOMAIN],
    "Cosplay": [COSPLAYTELE_DOMAIN],
    "Video": [PORNHUB_DOMAIN, EPORNER_DOMAIN]
}

COOKIES_FILE_PATH = "pornhub_cookies.txt"

# --- General Helpers ---

def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "-", name).strip()

def create_zip_from_folder(folder_path: str, zip_output_path: str):
    with zipfile.ZipFile(zip_output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(folder_path):
            for file in sorted(files):
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, os.path.dirname(folder_path))
                zipf.write(full_path, relative_path)

def check_dependencies():
    all_ok = True
    if not shutil.which("ffmpeg"):
        logger.error("Dependency `ffmpeg` not found.")
        all_ok = False
    if not shutil.which("gallery-dl"):
        logger.error("Dependency `gallery-dl` not found.")
        all_ok = False
    try:
        ChromeDriverManager().install()
        logger.info("[Selenium] Chrome driver is correctly installed.")
    except Exception as e:
        logger.error(f"[Selenium] Error setting up WebDriver: {e}")
        all_ok = False
    return all_ok

async def check_subscription(session: AsyncSession, user_id: int, domain: str) -> Tuple[bool, str]:
    user = await database.get_or_create_user(session, user_id)
    if user.is_admin:
        return True, "Admin access granted."

    if not user.sub_is_active:
        return False, "Your subscription is not active."

    if user.sub_expiry_date and user.sub_expiry_date < datetime.now():
        return False, "Your subscription has expired."

    if not user.sub_allowed_sites.get(domain, False):
        return False, f"Your subscription does not include access to {domain}."

    return True, "Access granted."


# --- Selenium Drivers ---

def setup_chrome_driver():
    logger.info("[Selenium] Setting up headless Chrome driver...")
    options = ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5.37.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/5.37.36")
    try:
        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        logger.error(f"[Selenium] Failed to start Chrome driver: {e}")
        return None

def setup_firefox_driver():
    logger.info("[Selenium] Setting up headless Firefox driver...")
    options = FirefoxOptions()
    options.add_argument("--headless")
    try:
        service = FirefoxService(GeckoDriverManager().install())
        return webdriver.Firefox(service=service, options=options)
    except Exception as e:
        logger.error(f"[Selenium] Failed to start Firefox driver: {e}")
        return None


# --- Generic Downloaders ---

def get_full_video_info(url: str) -> dict | None:
    logger.info(f"[yt-dlp] Extracting info for: {url}")
    ydl_opts = {'quiet': True, 'no_warnings': True}
    if COOKIES_FILE_PATH and os.path.exists(COOKIES_FILE_PATH):
        ydl_opts['cookiefile'] = COOKIES_FILE_PATH
        logger.info(f"Using cookies from: {COOKIES_FILE_PATH}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"[yt-dlp] Error extracting video info: {e}")
        return None

def download_video(url: str, temp_dir: str, format_id: str) -> str | None:
    temp_filename = os.path.join(temp_dir, 'initial_download')
    ydl_opts = {'format': format_id, 'outtmpl': temp_filename, 'quiet': False, 'no_warnings': True, 'ignoreerrors': False}
    if COOKIES_FILE_PATH and os.path.exists(COOKIES_FILE_PATH):
        ydl_opts['cookiefile'] = COOKIES_FILE_PATH
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        actual_file = next((os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.startswith('initial_download')), None)
        if not actual_file: raise FileNotFoundError("Downloaded file not found.")
        return actual_file
    except Exception as e:
        logger.error(f"[yt-dlp] Error during download: {e}")
        return None

async def run_gallery_dl_download(url: str, temp_dir: str) -> Tuple[List[str] | None, str | None]:
    logger.info(f"[gallery-dl] Starting download: {url}")
    # Use a simple filename format to avoid issues with long names
    command = ['gallery-dl', '-D', temp_dir, '--filename', '{id}.{extension}', url]
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await process.communicate()
    if process.returncode != 0:
        error_message = stderr.decode('utf-8', errors='ignore').strip()
        return None, error_message
    return [os.path.join(root, file) for root, _, files in os.walk(temp_dir) for file in files], None

async def download_or_copy_file(bot: "Bot", file: "File", destination: Path):
    """
    Downloads a file using the standard method or copies it directly if a local
    Bot API server data directory is configured.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    if settings.local_bot_api_enabled:
        file_path = Path(file.file_path)
        base_dir = Path(settings.local_bot_api_server_data_dir) if settings.local_bot_api_server_data_dir else None

        def _token_dir_name() -> str:
            return f"bot{settings.bot_token.replace(':', '_')}"

        candidate_paths: List[Path] = []
        if file_path.is_absolute():
            candidate_paths.append(file_path)
        if base_dir:
            candidate_paths.extend([
                base_dir / file_path,
                base_dir / _token_dir_name() / file_path,
                base_dir / "bots" / _token_dir_name() / file_path,
                base_dir / "files" / file_path,
                base_dir / "files" / _token_dir_name() / file_path,
            ])

        for source_path in candidate_paths:
            logger.debug(f"Trying local Bot API copy from {source_path}")
            if source_path.exists():
                shutil.copy(source_path, destination)
                logger.info(f"Local Bot API copy succeeded from {source_path}")
                return

        api = getattr(bot.session, "api", None)
        if api is not None:
            try:
                local_url = api.file_url(bot.token, file.file_path)
                logger.info(f"Local Bot API enabled. Streaming file from {local_url}")
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600)) as session:
                    async with session.get(local_url) as response:
                        response.raise_for_status()
                        with destination.open("wb") as destination_file:
                            async for chunk in response.content.iter_chunked(1 << 16):
                                destination_file.write(chunk)
                return
            except Exception as error:
                logger.warning(
                    f"Local Bot API streaming failed ({error}). Falling back to bot.download_file.",
                    exc_info=True,
                )

    logger.info(f"Falling back to Telegram download API for {destination}")
    await bot.download_file(file.file_path, destination=str(destination))

def download_single_image(args: Tuple[str, str, dict]) -> bool:
    img_url, file_path, headers = args
    try:
        res = requests.get(img_url, stream=True, timeout=30, headers=headers)
        res.raise_for_status()
        with open(file_path, 'wb') as f:
            shutil.copyfileobj(res.raw, f)
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to download image {img_url}: {e}")
        return False

# --- Site-Specific Scrapers ---

# Toonily.com
def find_all_chapters_com(url: str, driver):
    driver.get(url)
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "ul.main.version-chap li.wp-manga-chapter"))
    )
    soup = BeautifulSoup(driver.page_source, "html.parser")
    chapters = []
    chapter_list_items = soup.select("ul.main.version-chap li.wp-manga-chapter")
    for item in chapter_list_items:
        link_tag = item.find('a')
        if link_tag and link_tag.has_attr('href'):
            chapter_name = link_tag.text.strip()
            chapter_url = link_tag['href']
            if chapter_name and chapter_url:
                chapters.append({'name': chapter_name, 'url': chapter_url})
    chapters.reverse()
    title_element = soup.select_one("div.post-title h1")
    title = title_element.text.strip() if title_element else "Untitled"
    return chapters, title

def get_chapter_image_urls_com(chapter_url: str, driver) -> List[str]:
    driver.get(chapter_url)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.reading-content img.wp-manga-chapter-img")))
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    return [img.get('data-src', '').strip() for img in soup.select('div.reading-content img.wp-manga-chapter-img')]

# Toonily.me
def mn2_get_chapters(url: str):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5.37.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/5.37.36'
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    title_element = soup.select_one(".post-title h1")
    title = title_element.text.strip() if title_element else "Untitled"
    chapters = []
    chapter_list_items = soup.select("ul.version-chap li.wp-manga-chapter")
    for item in chapter_list_items:
        link_tag = item.find('a')
        if link_tag and link_tag.has_attr('href'):
            chapter_name = link_tag.text.strip()
            chapter_url = link_tag['href']
            if chapter_name and chapter_url:
                chapters.append({'name': chapter_name, 'url': chapter_url})
    chapters.reverse()
    return chapters, title

def mn2_get_chapter_images(chapter_url: str) -> list[str]:
    res = requests.get(chapter_url)
    soup = BeautifulSoup(res.text, "html.parser")
    return [img.get('data-src') or img.get('src') for img in soup.select("div#chapter-images img")]

# ManhwaClan.com
def mc_get_chapters_and_title(url: str) -> Tuple[List[Dict], str]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5.37.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/5.37.36'
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    manhwa_title_tag = soup.select_one('.post-title h1')
    manhwa_title = manhwa_title_tag.text.strip() if manhwa_title_tag else "Untitled Manhwa"
    sanitized_title = sanitize_filename(manhwa_title)
    chapters = []
    chapter_list_ul = soup.find('ul', class_='version-chap')
    if chapter_list_ul:
        list_items = chapter_list_ul.find_all('li', class_='wp-manga-chapter')
        for item in list_items:
            link_tag = item.find('a')
            if link_tag and link_tag.has_attr('href'):
                chapter_title = link_tag.text.strip()
                chapter_url = link_tag['href']
                if chapter_title and chapter_url:
                    chapters.append({'name': sanitize_filename(chapter_title), 'url': chapter_url})
    chapters.reverse()
    return chapters, sanitized_title

def mc_get_chapter_image_urls(chapter_url: str) -> List[str]:
    headers = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5.37.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/5.37.36' }
    response = requests.get(chapter_url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    images_container = soup.find('div', class_='reading-content')
    if not images_container: return []
    image_tags = images_container.find_all('img', class_='wp-manga-chapter-img')
    return [img.get('src', '').strip() for img in image_tags if img.get('src')]

# MangaDistrict.com
def md_get_chapters_and_title(manhwa_url: str) -> Tuple[List[Dict], str]:
    res = requests.get(manhwa_url)
    soup = BeautifulSoup(res.text, 'html.parser')
    title = soup.select_one('div.post-title h1').text.strip()
    chapters = [{'name': a.text.strip(), 'url': a['href']} for a in soup.select('ul.version-chap li.wp-manga-chapter a')]
    chapters.reverse()
    return chapters, sanitize_filename(title)

def md_get_chapter_image_urls(chapter_url: str) -> List[str]:
    res = requests.get(chapter_url)
    soup = BeautifulSoup(res.text, 'html.parser')
    return [img.get('src') or img.get('data-src') for img in soup.select('div.reading-content img')]

# CosplayTele.com
def ct_analyze_and_extract_media(page_url: str) -> Dict[str, List[str]]:
    res = requests.get(page_url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    images = [urljoin(page_url, a['href']) for a in soup.select('div.gallery a[href*=".jpg"]')]
    videos = [iframe['src'] for iframe in soup.select('iframe[src*="aparat.com"]')]
    return {'images': images, 'videos': videos}

# Comick.fun
def cm_get_info_and_chapters(comic_url: str, driver) -> Tuple[str, List[Dict]]:
    driver.get(comic_url)
    script_content = driver.find_element(By.ID, '__NEXT_DATA__').get_attribute('innerHTML')
    data = json.loads(script_content)
    comic_data = data['props']['pageProps']['comic']
    title, hid = comic_data['title'], comic_data['hid']
    api_url = f"https://api.comick.fun/comic/{hid}/chapters?lang=en&limit=99999"
    chapter_data = requests.get(api_url).json()
    chapters = [{'name': f"Ch. {c.get('chap', 'N/A')}" + (f" - {c.get('title')}" if c.get('title') else ""), 'hid': c.get('hid')} for c in chapter_data['chapters']]
    chapters.sort(key=lambda x: float(x.get('chap', 0)) if str(x.get('chap', 0)).replace('.', '', 1).isdigit() else 0)
    return title, chapters

def cm_get_chapter_image_urls(chapter_hid: str) -> List[str]:
    api_url = f"https://api.comick.fun/chapter/{chapter_hid}"
    chapter_data = requests.get(api_url).json()
    return [f"https://meo.comick.pictures/{img['b2key']}" for img in chapter_data.get('chapter', {}).get('md_images', [])]

# Erome.com
EROME_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5.37.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/5.37.36',
    'Referer': 'https://www.erome.com/'
}
def er_get_album_media_selenium(album_url: str, driver) -> Tuple[str, Dict[str, List[str]]]:
    logger.info(f"[{EROME_DOMAIN}] Opening with Selenium: {album_url}")
    driver.get(album_url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "video, div.img[data-src]"))
        )
        time.sleep(2) # Wait a bit for JS to load final URLs
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        title_tag = soup.find('h1')
        album_title = title_tag.text.strip() if title_tag else "Erome Album"
        media_urls = {'images': [], 'videos': []}
        for video_tag in soup.find_all('video'):
            source_tag = video_tag.find('source')
            if source_tag and source_tag.get('src'):
                media_urls['videos'].append(source_tag['src'])
        for img_div in soup.find_all('div', class_='img'):
            if img_div.get('data-src'):
                media_urls['images'].append(img_div['data-src'])

        logger.info(f"[{EROME_DOMAIN}] Found {len(media_urls['images'])} images and {len(media_urls['videos'])} videos.")
        return sanitize_filename(album_title), media_urls
    except Exception as e:
        logger.error(f"[{EROME_DOMAIN}] Error with Selenium: {e}")
        return "Error", {}


def create_chapter_keyboard(chapters: list, selected_indices: list, page: int, prefix: str) -> InlineKeyboardMarkup:
    """Creates a paginated keyboard for chapter selection."""
    keyboard_rows = []
    items_per_page = 20
    start_index = page * items_per_page
    end_index = start_index + items_per_page

    paginated_chapters = chapters[start_index:end_index]

    row = []
    for i, chapter in enumerate(paginated_chapters):
        global_index = start_index + i
        text = f"✅ {chapter['name']}" if global_index in selected_indices else chapter['name']
        row.append(InlineKeyboardButton(text=text, callback_data=f"{prefix}_toggle_{global_index}"))
        if len(row) == 2:
            keyboard_rows.append(row)
            row = []
    if row:
        keyboard_rows.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"{prefix}_page_{page-1}"))
    if end_index < len(chapters):
        nav_row.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"{prefix}_page_{page+1}"))
    if nav_row:
        keyboard_rows.append(nav_row)

    keyboard_rows.append([
        InlineKeyboardButton(text="انتخاب همه", callback_data=f"{prefix}_select_all"),
        InlineKeyboardButton(text="حذف همه", callback_data=f"{prefix}_deselect_all")
    ])
    keyboard_rows.append([InlineKeyboardButton(text="✅ شروع دانلود", callback_data=f"{prefix}_start_download")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)