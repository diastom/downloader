import yt_dlp
import ffmpeg
import os
from celery import Celery
from telegram.ext import ExtBot
from functools import wraps 
import subprocess
import telegram 
import shlex 
import sys
import shutil
import tempfile
import re
import logging
import asyncio
import json
import urllib.parse
import zipfile
import requests
import concurrent.futures
from telegram.error import TimedOut, NetworkError
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
from typing import Tuple, List, Dict
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.firefox import GeckoDriverManager
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import CreateChannelRequest, EditAdminRequest
from telethon.tl.types import ChatAdminRights, PeerChannel 


BOT_TOKEN = "8028761324:AAG9w1-MujBb7b2hlGvrIQU3MeIVtDXIkAw" 


API_ID = 22258582
API_HASH = "fefb9d648559a97bf26726d08be33bd4"
SESSION_STRING = "1BVtsOIsBu8OvljNYtlZFa_kc5di7w8qFGQgllt3BzoeLu_7zNE29pjCzps1mUBCyPNNgg9mw9_acllZx03jxgWXwArpf1b6UiqFoBHGF1BKPPxT8QwhjMuO2OUdl60ghsun9Yy96n1Fy-fE89CCvG8o_9iSyc8cG5G5VSgk5zzQtcreUdGY0V-aSdDC1gsB46gL5QLJ95JnU5y4nrKF1y6rWmWgmfqiQkI7cJP-z9fYQ23GmiWkNCce1fnJQKZDdR4VdE38ht2cO3Uy5Qi67XQBiEtOkhizfjBRbQdVXzX_2vHeviLUbeCYrT1XrOTp9vOQvDGK90-lQ4qWxdACcu-j8FQ1cAxA="
PUBLIC_ARCHIVE_CHAT_ID = -1003060382151
VIDEO_CACHE_DB = "VideoCache.json"

BOT_USERNAME = "OviaRobot" 

FONT_FILE = "Aviny.ttf" 
WATERMARK_DB = "WatermarkSettings.json"

TEXTS_DB_FILE = "texts.json"

ADMIN_IDS = [7922716668, 1231355433] 
USER_DB_FILE = "BotData.json"

RETRY_PARAMS = {
    'autoretry_for': (TimedOut, NetworkError),

    'retry_kwargs': {'max_retries': 3},

    'retry_backoff': True,

    'retry_backoff_max': 600,

    'retry_jitter': True
}


COOLDOWN_SECONDS = 60

DOWNLOAD_FOLDER = "Downloads"
COOKIES_CONFIG = None

GALLERY_DL_SITES = ["rule34.xyz", "coomer.st", "aryion.com", "kemono.cr", "tapas.io", "tsumino.com", "danbooru.donmai.us", "e621.net"]

GALLERY_DL_ZIP_SITES = ["mangadex.org", "e-hentai.org"]

TOONILY_COM_DOMAIN = "toonily.com"
TOONILY_ME_DOMAIN = "toonily.me"
MANHWACLAN_DOMAIN = "manhwaclan.com"
MANGA_DISTRICT_DOMAIN = "mangadistrict.com"
COSPLAYTELE_DOMAIN = "cosplaytele.com" 
COMICK_DOMAIN = "comick.io"
PORNHUB_DOMAIN = "pornhub.com"
EROME_DOMAIN = "erome.com"
EPORNER_DOMAIN = "eporner.com"
XVIDEOS_DOMAIN = "xvideos.com"

THUMBNAIL_DB = "Thumb.json"
SET_THUMBNAIL_TEXT = "🖼️ تنظیم تامبنیل"

ALL_SUPPORTED_SITES = {
    "Manhwa/Webtoon": [TOONILY_COM_DOMAIN, TOONILY_ME_DOMAIN, MANHWACLAN_DOMAIN, MANGA_DISTRICT_DOMAIN, COMICK_DOMAIN],
    "Gallery/Hentai": GALLERY_DL_SITES + GALLERY_DL_ZIP_SITES,
    "Album": [EROME_DOMAIN],
    "Cosplay": [COSPLAYTELE_DOMAIN],
    "Video": [PORNHUB_DOMAIN, EPORNER_DOMAIN, XVIDEOS_DOMAIN]
}



logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

AWAIT_THUMBNAIL = 0

COM_SELECTING_CHAPTERS, COM_AWAIT_ZIP_OPTION = range(1, 3)
ME_AWAIT_MANHWA_SEARCH, ME_SELECTING_MANHWA, ME_SELECTING_CHAPTERS, ME_AWAIT_ZIP_OPTION = range(3, 7)
MC_SELECTING_CHAPTERS, MC_AWAIT_ZIP_OPTION = range(7, 9)
MD_SELECTING_CHAPTERS, MD_AWAIT_ZIP_OPTION = range(9, 11)
CT_AWAIT_USER_CHOICE = 11
CM_SELECTING_CHAPTERS, CM_AWAIT_ZIP_OPTION = range(12, 14)
GALLERY_DL_AWAIT_ZIP_OPTION = 15
EROME_AWAIT_CHOICE = 16
ADMIN_PANEL, AWAIT_BROADCAST_MESSAGE, AWAIT_BROADCAST_FORWARD, AWAIT_SUB_USER_ID, MANAGE_USER_SUB = range(20, 25)
TEXTS_PANEL, AWAIT_HELP_TEXT = range(25, 27)
WATERMARK_PANEL, AWAIT_WATERMARK_TEXT, AWAIT_WATERMARK_SIZE, AWAIT_WATERMARK_COLOR, AWAIT_WATERMARK_STROKE = range(30, 35)
VIDEO_EDIT, AWAIT_VIDEO_CHOICE = range(40, 42)

def load_db():
    try:
        with open(THUMBNAIL_DB, 'r') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {}
def save_db(data):
    with open(THUMBNAIL_DB, 'w') as f: json.dump(data, f, indent=4)
def set_user_thumbnail(user_id, file_id):
    db = load_db()
    db[str(user_id)] = file_id
    save_db(db)
def get_user_thumbnail(user_id):
    db = load_db()
    return db.get(str(user_id))
def delete_user_thumbnail(user_id):
    db = load_db()
    if str(user_id) in db:
        del db[str(user_id)]
        save_db(db)
        return True
    return False


def load_user_db():
    """دیتابیس کاربران را از فایل JSON بارگذاری می‌کند."""
    try:
        with open(USER_DB_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_db(data):
    """دیتابیس کاربران را در فایل JSON ذخیره می‌کند."""
    with open(USER_DB_FILE, 'w') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_user_data(user_id):
    """[تابع ویرایش شده] اطلاعات کاربر را بازیابی کرده و فیلد جدید کانال شخصی را اضافه می‌کند."""
    db = load_user_db()
    user_id_str = str(user_id)
    made_change = False
    if user_id_str not in db:
        # ساخت پروفایل پیش‌فرض برای کاربر جدید
        db[user_id_str] = {
            "username": "",
            "is_admin": user_id in ADMIN_IDS,
            "subscription": {
                "is_active": False,
                "expiry_date": None,
                "allowed_sites": {site: False for category in ALL_SUPPORTED_SITES.values() for site in category},
                "download_limit": -1
            },
            "stats": {
                "last_seen": str(datetime.now()),
                "downloads_today": {"date": str(datetime.now().date()), "count": 0},
                "site_usage": {}
            },

            "personal_archive_id": None
        }
        made_change = True
    
    user_profile = db[user_id_str]
   
    if 'personal_archive_id' not in user_profile:
        user_profile['personal_archive_id'] = None
        made_change = True

    
    if 'download_limit' not in user_profile.get('subscription', {}):
        user_profile.setdefault('subscription', {})['download_limit'] = -1
        made_change = True
    if 'count' not in user_profile.get('stats', {}).get('downloads_today', {}):
         user_profile.setdefault('stats', {}).setdefault('downloads_today', {})['count'] = 0
         made_change = True

    if made_change:
        save_user_db(db)
        
    return db[user_id_str]

def update_user_data(user_id, data):
    """اطلاعات یک کاربر را در دیتابیس به‌روزرسانی می‌کند."""
    db = load_user_db()
    db[str(user_id)] = data
    save_user_db(db)



def load_texts_db():
    """دیتابیس متن‌های قابل ویرایش را بارگذاری می‌کند."""
    try:
        with open(TEXTS_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        
        return {"help_text": "راهنمای پیش‌فرض. ادمین می‌تواند این متن را تغییر دهد."}

def save_texts_db(data):
    """دیتابیس متن‌ها را ذخیره می‌کند."""
    with open(TEXTS_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

async def show_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """متن راهنما را برای کاربر ارسال می‌کند."""
    texts_db = load_texts_db()
    help_text = texts_db.get("help_text", "متن راهنما هنوز تنظیم نشده است.")
    await update.message.reply_text(help_text)

async def texts_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """پنل مدیریت متن‌های ربات را برای ادمین نمایش می‌دهد."""
    keyboard = [
        [InlineKeyboardButton("ویرایش متن راهنما", callback_data="texts_edit_help")],
        [InlineKeyboardButton("بازگشت به پنل ادمین", callback_data="texts_back_to_admin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("کدام متن را می‌خواهید ویرایش کنید؟", reply_markup=reply_markup)
    return TEXTS_PANEL

async def texts_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دکمه‌های پنل مدیریت متن‌ها را پردازش می‌کند."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "texts_edit_help":
        await query.message.edit_text("لطفاً متن جدید راهنما را ارسال کنید. برای لغو /cancel را بزنید.")
        return AWAIT_HELP_TEXT
    
    if data == "texts_back_to_admin":
        await query.message.delete()
      
        return await admin_command(update, context)

    return TEXTS_PANEL

async def await_help_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """متن جدید راهنما را از ادمین دریافت و ذخیره می‌کند."""
    new_text = update.message.text
    texts_db = load_texts_db()
    texts_db["help_text"] = new_text
    save_texts_db(texts_db)

    await update.message.reply_text("✅ متن راهنما با موفقیت به‌روزرسانی شد.")
    
    return await texts_panel_command(update, context)


async def get_or_create_personal_archive(user_id: int) -> int | None:
    """
    آیدی کانال آرشیو شخصی کاربر را بررسی می‌کند. اگر وجود نداشت،
    یک کانال جدید خصوصی می‌سازد، ربات را ادمین می‌کند و آیدی آن را ذخیره و برمی‌گرداند.
    """
    user_data = get_user_data(user_id)
    archive_id = user_data.get("personal_archive_id")
    if archive_id:
        logger.info(f"[Archive] کانال شخصی برای کاربر {user_id} از قبل وجود دارد: {archive_id}")
        return archive_id

    logger.info(f"[Archive] در حال ساخت کانال آرشیو شخصی برای کاربر {user_id}...")
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    try:
        await client.connect()
        
        result = await client(CreateChannelRequest(
            title=str(user_id),
            about=f"Personal Archive for @{BOT_USERNAME}",
            megagroup=False
        ))
        
        new_channel_id = result.chats[0].id
        full_channel_id = int(f"-100{new_channel_id}")
        
        channel_entity = await client.get_entity(PeerChannel(new_channel_id))
        
        bot_entity = await client.get_entity(BOT_USERNAME)
        admin_rights = ChatAdminRights(
            post_messages=True, edit_messages=True, delete_messages=True,
            invite_users=True, change_info=True, pin_messages=True,
            add_admins=False, ban_users=True, manage_call=True, anonymous=False, other=True
        )
        await client(EditAdminRequest(channel=channel_entity, user_id=bot_entity, admin_rights=admin_rights, rank='bot'))
        
        user_data["personal_archive_id"] = full_channel_id
        update_user_data(user_id, user_data)
        
        logger.info(f"[Archive] کانال شخصی {full_channel_id} برای کاربر {user_id} با موفقیت ساخته شد.")
        return full_channel_id

    except FloodWaitError as e:
        logger.error(f"[Archive] Flood wait error: Wait for {e.seconds} seconds.")
        await asyncio.sleep(e.seconds)
        return None  # یا retry کن
    except Exception as e:
        logger.error(f"[Archive] خطا در ساخت کانال شخصی برای کاربر {user_id}: {e}", exc_info=True)
        return None
    finally:
        if client.is_connected():
            await client.disconnect()

def load_video_cache():
    """کش ویدیوها را از فایل JSON بارگذاری می‌کند."""
    try:
        with open(VIDEO_CACHE_DB, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_video_cache(data):
    """کش ویدیوها را در فایل JSON ذخیره می‌کند."""
    with open(VIDEO_CACHE_DB, 'w') as f:
        json.dump(data, f, indent=4)

def add_to_video_cache(url: str, format_id: str, message_id: int):
    """یک ویدیوی جدید با کیفیت مشخص را به کش اضافه می‌کند."""
    cache = load_video_cache()
    if url not in cache:
        cache[url] = {}
    cache[url][format_id] = message_id
    save_video_cache(cache)
    logger.info(f"[Cache] ویدیو با لینک {url} و کیفیت {format_id} به کش اضافه شد.")

def get_from_video_cache(url: str, format_id: str) -> int | None:
    """یک ویدیو با کیفیت مشخص را از کش جستجو می‌کند."""
    cache = load_video_cache()
    url_cache = cache.get(url)
    
    if isinstance(url_cache, dict):
        return url_cache.get(format_id)
    
    return None

def log_download_activity(user_id, site_domain):
    """فعالیت دانلود کاربر را برای آمار ثبت می‌کند."""
    user_data = get_user_data(user_id)
    today_str = str(datetime.now().date())
    
    if user_data['stats']['downloads_today'].get('date') != today_str:
        user_data['stats']['downloads_today'] = {"date": today_str, "count": 0}
    
    user_data['stats']['downloads_today']['count'] += 1
    user_data['stats']['site_usage'][site_domain] = user_data['stats']['site_usage'].get(site_domain, 0) + 1
    
    update_user_data(user_id, user_data)


def load_watermark_db():
    """تنظیمات واترمارک کاربران را از فایل JSON بارگذاری می‌کند."""
    try:
        with open(WATERMARK_DB, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_watermark_db(data):
    """تنظیمات واترمارک کاربران را در فایل JSON ذخیره می‌کند."""
    with open(WATERMARK_DB, 'w') as f:
        json.dump(data, f, indent=4)

def get_user_watermark_settings(user_id: int) -> dict:
    """تنظیمات واترمارک یک کاربر را بازیابی می‌کند یا تنظیمات پیش‌فرض را برمی‌گرداند."""
    db = load_watermark_db()
    user_id_str = str(user_id)
    if user_id_str in db:
        
        defaults = {
            "enabled": False,
            "text": f"@{BOT_USERNAME}",
            "position": "top_left",
            "size": 32,
            "color": "white",
            "stroke": 2,
        }
        
        user_settings = db[user_id_str]
        for key, value in defaults.items():
            user_settings.setdefault(key, value)
        return user_settings
    else:
        
        return {
            "enabled": False,
            "text": f"@{BOT_USERNAME}",
            "position": "top_left",
            "size": 32,
            "color": "white",
            "stroke": 2,
        }

def update_user_watermark_settings(user_id: int, new_settings: dict):
    """تنظیمات واترمارک یک کاربر را به‌روزرسانی می‌کند."""
    db = load_watermark_db()
    db[str(user_id)] = new_settings
    save_watermark_db(db)


def cooldown_decorator(seconds=COOLDOWN_SECONDS):
    """
    Decorator to enforce a cooldown on users for starting new download processes.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            
            
            if user_id in ADMIN_IDS:
                return await func(update, context, *args, **kwargs)

            if 'user_cooldowns' not in context.bot_data:
                context.bot_data['user_cooldowns'] = {}

            last_call_time = context.bot_data['user_cooldowns'].get(user_id)

            if last_call_time:
                time_passed = datetime.now() - last_call_time
                if time_passed.total_seconds() < seconds:
                    remaining_time = seconds - time_passed.total_seconds()
                    message_to_send = f"لطفاً کمی صبر کنید. شما می‌توانید تا {int(remaining_time)} ثانیه دیگر دوباره درخواست دانلود دهید."
                    
                    if update.callback_query:
                        await update.callback_query.answer(text=message_to_send, show_alert=True)
                    else:
                        await update.message.reply_text(message_to_send)
                    return
            
            result = await func(update, context, *args, **kwargs)
            
            if result is not None and result != ConversationHandler.END:
                 context.bot_data['user_cooldowns'][user_id] = datetime.now()

            return result
        return wrapper
    return decorator


REDIS_URL = "redis://localhost:6379/0"
celery_app = Celery('bot_tasks', broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    broker_connection_retry_on_startup=True,
)


def get_bot_instance():
    """
    یک نمونه ExtBot برای تسک‌های Celery ایجاد می‌کند که به سرور API محلی متصل است.
    """
    
    return ExtBot(
        token=BOT_TOKEN,
        base_url="http://91.107.146.233:8081/bot",
        base_file_url="http://91.107.146.233:8081/file/bot"
    )


async def check_subscription(user_id: int, domain: str) -> Tuple[bool, str]:
    """
    [نسخه اصلاح شده با منطق Whitelist]
    وضعیت کامل اشتراک کاربر را بررسی می‌کند. دسترسی تنها در صورتی مجاز است که
    اشتراک فعال بوده و سایت مورد نظر به صراحت برای کاربر فعال شده باشد.
    """
    user_data = get_user_data(user_id)
    if user_data.get('is_admin', False):
        return True, "دسترسی ادمین تایید شد."

    sub = user_data.get('subscription', {})
    
    
    if not sub.get('is_active', False):
        return False, "اشتراک شما فعال نیست. لطفاً برای استفاده از ربات، اشتراک تهیه کنید."

    
    expiry_date_str = sub.get('expiry_date')
    if expiry_date_str:
        try:
            if datetime.fromisoformat(expiry_date_str) < datetime.now():
                user_data['subscription']['is_active'] = False
                update_user_data(user_id, user_data)
                return False, "اشتراک شما منقضی شده است. لطفاً آن را تمدید کنید."
        except (ValueError, TypeError):
            user_data['subscription']['is_active'] = False
            update_user_data(user_id, user_data)
            return False, "خطا در اطلاعات اشتراک. لطفاً با پشتیبانی تماس بگیرید."


    limit = sub.get('download_limit', -1)
    if limit != -1:
        stats = user_data.get('stats', {})
        downloads_today_data = stats.get('downloads_today', {})
        today_str = str(datetime.now().date())
        
        downloads_today_count = downloads_today_data.get('count', 0) if downloads_today_data.get('date') == today_str else 0
        if downloads_today_count >= limit:
            return False, f"شما به محدودیت دانلود روزانه خود ({limit} فایل) رسیده‌اید."


    if sub.get('allowed_sites', {}).get(domain, False):
        
        return True, "دسترسی تایید شد."
    else:
       
        return False, "این وبسایت برای شما غیرفعال است."


async def manage_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE, is_recall: bool = False, user_id_override: int = None) -> int:
    """[نسخه اصلاح شده نهایی] پنل مدیریت اشتراک با دکمه فعال/غیرفعال‌سازی همه سایت‌ها."""
    try:
        target_user_id = user_id_override if is_recall else int(update.message.text)
    except (ValueError, TypeError):
        await update.message.reply_text("Invalid User ID. Please enter a number.")
        return AWAIT_SUB_USER_ID

    context.user_data['target_user_id'] = target_user_id
    user_data = get_user_data(target_user_id)
    if not isinstance(user_data, dict):
        await update.message.reply_text("Error: User data is corrupted.")
        return ADMIN_PANEL

    sub = user_data.get('subscription', {})
    username = user_data.get('username') or "N/A"
    
    expiry_date_str = sub.get('expiry_date')
    remain_days = "Unlimited"
    if expiry_date_str:
        try:
            delta = datetime.fromisoformat(expiry_date_str) - datetime.now()
            remain_days = max(0, delta.days)
        except (ValueError, TypeError):
            remain_days = "Invalid"

    limit = sub.get('download_limit', -1)
    limit_text = "Unlimited" if limit == -1 else str(limit)

    sub_info_text = (
        f"👤 @{username}\n"
        f"• UID: {target_user_id}\n"
        f"• Remainday: {remain_days}\n"
        f"• Limit: {limit_text}/day"
    )

    keyboard = []
    
    status_text = "ACTIVE ✅" if sub.get('is_active') else "DEACTIVATED ❌"
    keyboard.append([InlineKeyboardButton(status_text, callback_data="sub_toggle_active")])

    all_sites_flat = [site for category_sites in ALL_SUPPORTED_SITES.values() for site in category_sites]
    
    
    all_sites_active = all(sub.get('allowed_sites', {}).get(site) for site in all_sites_flat)
    
    row = []
    for site in all_sites_flat:
        site_status = "☑️" if sub.get('allowed_sites', {}).get(site) else "✖️"
        row.append(InlineKeyboardButton(f"{site} {site_status}", callback_data=f"sub_toggle_site_{site}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    
    if all_sites_active:
        keyboard.append([InlineKeyboardButton("Deactivate All Sites", callback_data="sub_deactivate_all_sites")])
    else:
        keyboard.append([InlineKeyboardButton("Activate All Sites", callback_data="sub_activate_all_sites")])
    

    time_button_text = f"{remain_days} days left" if isinstance(remain_days, int) else "no time set"
    time_row = [
        InlineKeyboardButton("-10", callback_data="sub_rem_days_10"),
        InlineKeyboardButton(time_button_text, callback_data="sub_noop"),
        InlineKeyboardButton("+10", callback_data="sub_add_days_10")
    ]
    keyboard.append(time_row)

    limit_button_text = f"{limit_text} per day" if limit != -1 else "no limit"
    limit_row = [
        InlineKeyboardButton("-10", callback_data="sub_rem_limit_10"),
        InlineKeyboardButton(limit_button_text, callback_data="sub_noop"),
        InlineKeyboardButton("+10", callback_data="sub_add_limit_10")
    ]
    keyboard.append(limit_row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_to_use = update.callback_query.message if is_recall and update.callback_query else update.message
    
    if is_recall:
        try:
            await message_to_use.edit_text(sub_info_text, reply_markup=reply_markup)
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                pass
            else:
                raise
    else:
        await message_to_use.reply_text(sub_info_text, reply_markup=reply_markup)
        
    return MANAGE_USER_SUB

async def manage_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    [نسخه اصلاح شده] پاسخ دکمه‌های پنل مدیریت اشتراک را پردازش می‌کند.
    """
    query = update.callback_query
    await query.answer()
    data = query.data
    
    target_user_id = context.user_data.get('target_user_id')
    if not target_user_id:
        await query.edit_message_text("Error: User session expired. Please try again.")
        return ADMIN_PANEL

    user_data = get_user_data(target_user_id)
    sub = user_data['subscription']

    if data.startswith("sub_toggle_site_"):
        site = data.replace("sub_toggle_site_", "")
        sub['allowed_sites'][site] = not sub['allowed_sites'].get(site, False)
    
    
    elif data == "sub_activate_all_sites":
        all_sites_flat = [site for category_sites in ALL_SUPPORTED_SITES.values() for site in category_sites]
        for site in all_sites_flat:
            sub['allowed_sites'][site] = True
    elif data == "sub_deactivate_all_sites":
        all_sites_flat = [site for category_sites in ALL_SUPPORTED_SITES.values() for site in category_sites]
        for site in all_sites_flat:
            sub['allowed_sites'][site] = False
  

    elif data == "sub_toggle_active":
        sub['is_active'] = not sub['is_active']

    elif data.startswith("sub_add_days_"):
        days_to_add = int(data.split('_')[-1])
        current_expiry_str = sub.get('expiry_date')
        base_time = datetime.now()
        if current_expiry_str:
            try:
                current_expiry = datetime.fromisoformat(current_expiry_str)
                if current_expiry > base_time:
                    base_time = current_expiry
            except (ValueError, TypeError):
                pass
        sub['expiry_date'] = str(base_time + timedelta(days=days_to_add))

    elif data.startswith("sub_rem_days_"):
        days_to_rem = int(data.split('_')[-1])
        current_expiry_str = sub.get('expiry_date')
        if current_expiry_str:
            try:
                new_expiry = datetime.fromisoformat(current_expiry_str) - timedelta(days=days_to_rem)
                sub['expiry_date'] = str(max(datetime.now(), new_expiry))
            except (ValueError, TypeError):
                sub['expiry_date'] = None

    elif data.startswith("sub_add_limit_"):
        limit_to_add = int(data.split('_')[-1])
        current_limit = sub.get('download_limit', -1)
        sub['download_limit'] = limit_to_add if current_limit == -1 else current_limit + limit_to_add
            
    elif data.startswith("sub_rem_limit_"):
        limit_to_rem = int(data.split('_')[-1])
        current_limit = sub.get('download_limit', -1)
        if current_limit != -1:
            sub['download_limit'] -= limit_to_rem
            if sub['download_limit'] <= 0:
                sub['download_limit'] = -1
        
    elif data == "sub_noop":
        return MANAGE_USER_SUB

    update_user_data(target_user_id, user_data)
    await manage_subscription(update, context, is_recall=True, user_id_override=target_user_id)
    return MANAGE_USER_SUB


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نقطه ورود به پنل ادمین."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("شما اجازه دسترسی به این بخش را ندارید.")
        return ConversationHandler.END

    keyboard = [
        ["📊 آمار", "📢 همگانی"],
        ["⚙️ مدیریت اشتراک"],
        ["❌ خروج از پنل"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("به پنل ادمین خوش آمدید.", reply_markup=reply_markup)
    return ADMIN_PANEL

def check_dependencies():
    """بررسی وابستگی‌های تمام دانلودرها."""
    all_ok = True
    if not shutil.which("ffmpeg"):
        logger.error("وابستگی `ffmpeg` یافت نشد.")
        all_ok = False
    if not shutil.which("gallery-dl"):
        logger.error("وابستگی `gallery-dl` یافت نشد. لطفاً با `pip install gallery-dl` آن را نصب کنید.")
        all_ok = False
    try:
        ChromeDriverManager().install()
        logger.info("[Selenium] ✓ درایور Chrome با موفقیت بررسی شد.")
    except Exception as e:
        logger.error(f"[Selenium] ❌ خطا در تنظیم WebDriver. لطفاً مطمئن شوید Chrome نصب است. خطا: {e}")
        all_ok = False
        
    if all_ok:
        logger.info("تمام وابستگی‌ها با موفقیت بررسی شدند.")
    return all_ok

# --- توابع کمکی عمومی ---
def sanitize_filename(name: str) -> str:
    """کاراکترهای نامعتبر برای نام فایل یا پوشه را حذف یا جایگزین می‌کند."""
    return re.sub(r'[\\/*?:"<>|]', "-", name).strip()

def create_zip_from_folder(folder_path: str, zip_output_path: str):
    """یک پوشه را به فایل ZIP تبدیل می‌کند."""
    with zipfile.ZipFile(zip_output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(folder_path):
            for file in sorted(files):
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, os.path.dirname(folder_path))
                zipf.write(full_path, relative_path)


def get_full_video_info(url):
    logger.info(f"[yt-dlp] در حال استخراج اطلاعات برای لینک: {url}")
    ydl_opts = {'quiet': True, 'no_warnings': True, 'cookiesfrombrowser': COOKIES_CONFIG} if COOKIES_CONFIG else {'quiet': True, 'no_warnings': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"[yt-dlp] خطا در استخراج اطلاعات ویدیو: {e}"); return None
    
def download_video(url, temp_dir, format_id):
    temp_filename = os.path.join(temp_dir, 'initial_download')
    ydl_opts = {'format': format_id, 'outtmpl': temp_filename, 'quiet': False, 'no_warnings': True, 'ignoreerrors': False, 'progress': True}
    if COOKIES_CONFIG: ydl_opts['cookiesfrombrowser'] = COOKIES_CONFIG
    logger.info(f"[yt-dlp] شروع دانلود اولیه از {url} با کیفیت '{format_id}'")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        actual_file = next((os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.startswith('initial_download')), None)
        if not actual_file: raise FileNotFoundError("فایل دانلود شده توسط yt-dlp یافت نشد.")
        return actual_file
    except Exception as e:
        logger.error(f"[yt-dlp] خطا در حین دانلود اولیه: {e}"); return None
    
def repair_video(initial_path, repaired_path):
    logger.info("[yt-dlp] شروع تعمیر و کپی استریم‌های ویدیو...")
    try:
        ffmpeg.input(initial_path).output(repaired_path, c='copy', loglevel='error').run(overwrite_output=True)
        return True
    except ffmpeg.Error as e:
        logger.error(f"[yt-dlp] خطای ffmpeg در حین کپی استریم: {e.stderr.decode()}"); return False
    
def verify_and_finalize(repaired_path, final_output_path):
    logger.info("[yt-dlp] شروع تأیید فایل نهایی...")
    try:
        probe = ffmpeg.probe(repaired_path)
        duration = float(probe.get('format', {}).get('duration', 0))
        if duration > 0:
            os.makedirs(os.path.dirname(final_output_path), exist_ok=True)
            shutil.move(repaired_path, final_output_path)
            return final_output_path
        return None
    except (ffmpeg.Error, ValueError) as e:
        logger.error(f"[yt-dlp] خطا در حین تأیید فایل: {e}"); return None


@celery_app.task(name="tasks.process_video_customization")
def process_video_customization_task(user_id: int, chat_id: int, personal_archive_id: int, video_file_id: str, choice: str):
    """
    [نسخه بازنویسی شده نهایی با پیام وضعیت واحد]
    یک تسک Celery که ویدیو را دانلود، ویرایش و آپلود می‌کند و وضعیت را در یک پیام واحد به‌روزرسانی می‌کند.
    """
    async def _async_worker():
        bot = get_bot_instance()
        status_message = None  
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                
                status_message = await bot.send_message(chat_id=chat_id, text="⏳ پردازش ویدیوی شما شروع شد...")
                message_id_to_edit = status_message.message_id

                
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text="📥 در حال دانلود ویدیوی اصلی...")
                video_file = await bot.get_file(video_file_id)
                video_path = os.path.join(temp_dir, 'original_video.mp4')
                await video_file.download_to_drive(custom_path=video_path)
                logger.info(f"ویدیو با file_id: {video_file_id} با موفقیت در مسیر {video_path} دانلود شد.")

                
                final_video_path = video_path
                custom_thumb_path = None
                
                if choice in ['water', 'both']:
                    await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text="💧 در حال اعمال واترمارک...")
                    watermark_settings = get_user_watermark_settings(user_id)
                    final_video_path = await asyncio.to_thread(
                        apply_watermark_to_video, video_path, watermark_settings
                    )
                    if not final_video_path:
                        raise Exception("اعمال واترمارک ناموفق بود.")
                
                if choice in ['thumb', 'both']:
                    custom_thumbnail_id = get_user_thumbnail(user_id)
                    if custom_thumbnail_id:
                        await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text="🖼️ در حال آماده‌سازی تامبنیل...")
                        thumb_file = await bot.get_file(custom_thumbnail_id)
                        custom_thumb_path = os.path.join(temp_dir, 'thumb.jpg')
                        await thumb_file.download_to_drive(custom_path=custom_thumb_path)

                
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text="📤 در حال آپلود ویدیوی نهایی...")
                duration, width, height = await asyncio.to_thread(get_video_metadata, final_video_path)
                
                uploaded_message_id = await upload_video_with_bot_api(
                    bot=bot,
                    target_chat_id=personal_archive_id,
                    file_path=final_video_path,
                    thumb_path=custom_thumb_path,
                    caption=f"Edited for {user_id}",
                    duration=duration, width=width, height=height
                )
                if not uploaded_message_id:
                    raise Exception("آپلود ویدیوی نهایی ناموفق بود.")

                
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text="✅ ویدیوی شما آماده است! در حال ارسال...")
                await bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=personal_archive_id,
                    message_id=uploaded_message_id
                )
                
                
                await bot.delete_message(chat_id=chat_id, message_id=message_id_to_edit)

            except Exception as e:
                logger.error(f"خطا در تسک پردازش ویدیو برای کاربر {user_id}: {e}", exc_info=True)
                
                if status_message:
                     await bot.edit_message_text(chat_id=chat_id, message_id=status_message.message_id, text=f"❌ متاسفانه در پردازش ویدیوی شما خطایی رخ داد:\n`{e}`")
                
                else:
                     await bot.send_message(chat_id=chat_id, text=f"❌ متاسفانه در پردازش ویدیوی شما خطایی رخ داد:\n`{e}`")

    asyncio.run(_async_worker())


async def handle_user_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    [نسخه اصلاح شده نهایی]
    ویدیو را در کانال شخصی کپی کرده و file_id آن را برای تسک Celery ذخیره می‌کند.
    """
    user = update.effective_user
    if not update.message or not update.message.video:
        return ConversationHandler.END

    message = await update.message.reply_text("در حال پردازش ویدیو...")
    
    personal_archive_id = await get_or_create_personal_archive(user.id)
    if not personal_archive_id:
        await message.edit_text("خطا در دسترسی به کانال آرشیو شما. لطفاً دوباره تلاش کنید.")
        return ConversationHandler.END

    try:
       
        video_file_id = update.message.video.file_id
        context.user_data['video_to_edit_file_id'] = video_file_id
        
        
        await context.bot.copy_message(
            chat_id=personal_archive_id,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
        
        logger.info(f"ویدیو از کاربر {user.id} به کانال {personal_archive_id} کپی شد. File ID: {video_file_id}")

    except Exception as e:
        logger.error(f"خطا در کپی ویدیو به کانال شخصی برای کاربر {user.id}: {e}")
        await message.edit_text("خطا در کپی کردن ویدیو به آرشیو شما.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🖼️ تنظیم تامبنیل", callback_data="vid_edit_thumb")],
        [InlineKeyboardButton("💧 تنظیم واترمارک", callback_data="vid_edit_water")],
        [InlineKeyboardButton("🖼️💧 تنظیم هر دو", callback_data="vid_edit_both")],
        [InlineKeyboardButton("❌ لغو", callback_data="vid_edit_cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.edit_text("می‌خواهید با این ویدیو چه کاری انجام دهید؟", reply_markup=reply_markup)

    return AWAIT_VIDEO_CHOICE

async def process_video_edit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    [نسخه اصلاح شده]
    انتخاب کاربر را پردازش کرده و تسک پس‌زمینه را با file_id اجرا می‌کند.
    """
    query = update.callback_query
    await query.answer()
    choice = query.data.replace("vid_edit_", "")

    if choice == 'cancel':
        await query.edit_message_text("عملیات لغو شد.")
        return ConversationHandler.END

    user_id = query.from_user.id
    personal_archive_id = get_user_data(user_id).get("personal_archive_id")
    # --- [تغییر کلیدی] خواندن file_id از user_data ---
    video_file_id = context.user_data.get('video_to_edit_file_id')

    if not all([personal_archive_id, video_file_id]):
        await query.edit_message_text("خطا: اطلاعات ویدیو یافت نشد. لطفاً دوباره تلاش کنید.")
        return ConversationHandler.END

    await query.edit_message_text("✅ درخواست شما به صف پردازش اضافه شد. لطفاً منتظر بمانید...")

   
    process_video_customization_task.delay(
        user_id=user_id,
        chat_id=query.message.chat_id,
        personal_archive_id=personal_archive_id,
        video_file_id=video_file_id,
        choice=choice
    )
    
    context.user_data.pop('video_to_edit_file_id', None)
    return ConversationHandler.END

async def run_gallery_dl_download(url: str, temp_dir: str):
    logger.info(f"[gallery-dl] شروع دانلود از: {url}")
    command = ['gallery-dl', '-D', temp_dir, url]
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        error_message = stderr.decode('utf-8', errors='ignore').strip()
        logger.error(f"[gallery-dl] خطا در هنگام دانلود. کد خطا: {process.returncode}\n{error_message}")
        return None, error_message
    downloaded_files = [os.path.join(root, file) for root, _, files in os.walk(temp_dir) for file in files]
    return downloaded_files, None


CT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def ct_analyze_and_extract_media(page_url: str) -> Dict[str, List[str]]:
    """
    صفحه CosplayTele را تحلیل کرده و لینک مستقیم عکس‌ها و ویدیوها را استخراج می‌کند.
    """
    logger.info(f"[{COSPLAYTELE_DOMAIN}] در حال تحلیل محتوای صفحه: {page_url}")
    media_urls = {'images': [], 'videos': []}
    try:
        response = requests.get(page_url, headers=CT_HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        
        gallery = soup.find('div', class_='gallery')
        if gallery:
            image_links = gallery.find_all('a', href=re.compile(r'\.(jpg|jpeg|png|gif|webp)$', re.I))
            for link in image_links:
                media_urls['images'].append(urljoin(page_url, link['href']))

        
        video_iframes = soup.find_all('iframe', src=re.compile(r'aparat\.com|youtube\.com|cossora\.stream', re.I))
        for iframe in video_iframes:
            media_urls['videos'].append(iframe['src'])
            
        for video_tag in soup.find_all('video'):
            src = video_tag.get('src')
            if not src:
                source_tag = video_tag.find('source')
                if source_tag:
                    src = source_tag.get('src')
            if src:
                media_urls['videos'].append(urljoin(page_url, src))

        media_urls['images'] = sorted(list(dict.fromkeys(media_urls['images'])))
        media_urls['videos'] = sorted(list(dict.fromkeys(media_urls['videos'])))
        
        logger.info(f"[{COSPLAYTELE_DOMAIN}] {len(media_urls['images'])} عکس و {len(media_urls['videos'])} ویدیو یافت شد.")
        return media_urls

    except requests.exceptions.RequestException as e:
        logger.error(f"[{COSPLAYTELE_DOMAIN}] خطا در دسترسی به صفحه: {e}")
        return None
    except Exception as e:
        logger.error(f"[{COSPLAYTELE_DOMAIN}] خطای پیش‌بینی نشده در تحلیل صفحه: {e}")
        return None

def ct_download_single_image(args: Tuple[str, str]) -> bool:
    """یک تصویر را از CosplayTele دانلود می‌کند."""
    img_url, file_path = args
    try:
        res = requests.get(img_url, headers=CT_HEADERS, stream=True, timeout=30)
        res.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in res.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"[{COSPLAYTELE_DOMAIN}] خطا در دانلود تصویر {img_url}: {e}")
        return False


def setup_driver():
    logger.info("[Toonily.com] در حال تنظیم و راه‌اندازی درایور مرورگر...")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        logger.info("[Toonily.com] ✓ درایور با موفقیت راه‌اندازی شد.")
        return driver
    except Exception as e:
        logger.error(f"[Toonily.com] ❌ خطایی در راه‌اندازی درایور Selenium رخ داد: {e}")
        return None
def find_all_chapters_com(main_manhwa_url, driver):
    logger.info(f"[Toonily.com] در حال جستجو برای تمام قسمت‌ها در: {main_manhwa_url}")
    driver.get(main_manhwa_url)
    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.version-chap")))
    except Exception:
        logger.error("[Toonily.com] ❌ زمان انتظار برای یافتن لیست قسمت‌ها به پایان رسید.")
        return [], None
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    manhwa_title_tag = soup.find('div', class_='post-title')
    manhwa_title = manhwa_title_tag.h1.text.strip() if manhwa_title_tag else "Untitled_Manhwa"
    sanitized_title = sanitize_filename(manhwa_title)
    chapter_list_container = soup.find('ul', class_='version-chap')
    if not chapter_list_container: return [], None
    chapters = [{'title': item.find('a').text.strip(), 'url': item.find('a')['href']} for item in chapter_list_container.find_all('li', class_='wp-manga-chapter') if item.find('a')]
    chapters.reverse()
    logger.info(f"[Toonily.com] ✓ {len(chapters)} قسمت برای '{sanitized_title}' یافت شد.")
    return chapters, sanitized_title
def get_chapter_image_urls_com(chapter_url, driver):
    driver.get(chapter_url)
    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.reading-content img.wp-manga-chapter-img")))
    except Exception: return []
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    reading_container = soup.find('div', class_='reading-content')
    return [img.get('data-src', img.get('src', '')).strip() for img in reading_container.find_all('img', class_='wp-manga-chapter-img') if img.get('data-src') or img.get('src')]
def download_single_image_com(args):
    img_url, file_path = args
    if os.path.exists(file_path): return 'skipped'
    try:
        res = requests.get(img_url, stream=True, timeout=30, headers={'Referer': 'https://toonily.com/'})
        res.raise_for_status()
        with open(file_path, 'wb') as f: shutil.copyfileobj(res.raw, f)
        return 'downloaded'
    except requests.exceptions.RequestException: return 'failed'

def download_images_for_chapter_sync_com(chapter_info, manhwa_folder, manhwa_title, driver):
    """
    (Synchronous and Corrected Version)
    Downloads all images for a single chapter from Toonily.com.
    Uses 'name' key instead of 'title'.
    """

    chapter_title = chapter_info['name'] 
    

    safe_chapter_title = sanitize_filename(chapter_title)
    temp_folder = os.path.join(manhwa_folder, f"{manhwa_title} - {safe_chapter_title}")
    os.makedirs(temp_folder, exist_ok=True)
    
    image_urls = get_chapter_image_urls_com(chapter_info['url'], driver)
    
    if not image_urls:
        logger.warning(f"No image URLs found for chapter '{chapter_title}'")
        return None
        
    tasks = [(url, os.path.join(temp_folder, f"{i+1:03d}{os.path.splitext(urllib.parse.urlparse(url).path)[1] or '.jpg'}")) for i, url in enumerate(image_urls)]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        list(executor.map(download_single_image_com, tasks))
        
    return temp_folder


MN2_BASE_URL = f"https://{TOONILY_ME_DOMAIN}"
MN2_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
    'Accept': 'image/avif,image/webp,*/*',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': MN2_BASE_URL + '/',
}
def mn2_search(query: str) -> list[dict]:
    search_page = requests.get(f"{MN2_BASE_URL}/search?q={query}")
    search_soup = BeautifulSoup(search_page.text, "html.parser")
    items = search_soup.find_all("div", {"class": "book-item"})
    results = []
    for i in items:
        title_element = i.find("div", {"class": "title"}).find("h3").a
        name = title_element.get("title", "No Title").strip()
        url = title_element.get("href", "")
        safe_name = sanitize_filename(name)
        if name and url: results.append({"name": safe_name, "url": url})
    return results
def mn2_get_chapters(item_url: str) -> Tuple[list[dict], str]:
    item_page = requests.get(item_url)
    item_soup = BeautifulSoup(item_page.text, "html.parser")
    title = ""
    title_tag_h1 = item_soup.find("h1", class_=re.compile(r'post-title', re.I))
    if title_tag_h1:
        title = title_tag_h1.text.strip()
    if not title:
        title_tag_head = item_soup.find("title")
        if title_tag_head:
            full_title = title_tag_head.text.strip()
            title = re.sub(r'\s*(-|\|)\s*Toonily.*', '', full_title, flags=re.IGNORECASE).strip()
            title = re.sub(r'^Read\s+', '', title, flags=re.IGNORECASE).strip()
    if not title:
        title = "Untitled"
    safe_title = sanitize_filename(title)
    chapters = []
    chapter_list_tag = item_soup.find("ul", {"id": "chapter-list"})
    if chapter_list_tag:
        for li in chapter_list_tag.find_all("li"):
            a_tag = li.find('a')
            if not a_tag or not a_tag.get('href'): continue
            relative_url = a_tag.get("href")
            chapter_url = urllib.parse.urljoin(item_url, relative_url)
            chapter_name = ""
            strong_tag = a_tag.find("strong")
            if strong_tag: chapter_name = strong_tag.text.strip()
            if not chapter_name:
                clone_a_tag = BeautifulSoup(str(a_tag), 'html.parser').a
                date_tag = clone_a_tag.find("span", class_="update-on")
                if date_tag: date_tag.decompose()
                chapter_name = clone_a_tag.text.strip()
            if not chapter_name.strip(): continue
            safe_chapter_name = sanitize_filename(chapter_name)
            chapters.append({"name": safe_chapter_name, "url": chapter_url})
    chapters.reverse()
    return chapters, safe_title
def mn2_get_chapter_images(chapter_url: str) -> list[str]:
    chapter_page = requests.get(chapter_url)
    chapter_soup = BeautifulSoup(chapter_page.text, "html.parser")
    images_container = chapter_soup.find("div", {"id": "chapter-images"})
    if not images_container: return []
    image_urls = [img.get('data-src') or img.get('src') for img in images_container.find_all("img")]
    return [url.strip() for url in image_urls if url and url.strip()]
def mn2_download_image(url: str, download_path: str) -> bool:
    try:
        res = requests.get(url, headers=MN2_HEADERS, stream=True, timeout=20)
        if res.status_code != 200: return False
        with open(download_path, "wb") as file:
            for chunk in res.iter_content(10*1024): file.write(chunk)
        return True
    except requests.exceptions.RequestException: return False
def mn2_create_zip(files: list[str], output_path: Path, source_dir: Path, del_source=False):
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as file:
        for f in sorted(files):
            file_path = source_dir / f
            if file_path.exists(): file.write(file_path, arcname=f)
    if del_source: shutil.rmtree(source_dir)


MC_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
def mc_get_chapters_and_title(manhwa_url: str) -> Tuple[List[Dict], str]:
    logger.info(f"[{MANHWACLAN_DOMAIN}] در حال دریافت اطلاعات از: {manhwa_url}")
    try:
        response = requests.get(manhwa_url, headers=MC_HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        logger.error(f"[{MANHWACLAN_DOMAIN}] خطا در اتصال به {manhwa_url}: {e}")
        return [], ""

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
                    safe_chapter_title = sanitize_filename(chapter_title)
                    chapters.append({'name': safe_chapter_title, 'url': chapter_url})
    
    if chapters:
        chapters.reverse()
    
    logger.info(f"[{MANHWACLAN_DOMAIN}] {len(chapters)} چپتر برای '{sanitized_title}' یافت شد.")
    return chapters, sanitized_title
def mc_get_chapter_image_urls(chapter_url: str) -> List[str]:
    logger.info(f"[{MANHWACLAN_DOMAIN}] در حال استخراج تصاویر از: {chapter_url}")
    try:
        response = requests.get(chapter_url, headers=MC_HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException:
        return []

    images_container = soup.find('div', class_='reading-content')
    if not images_container:
        return []
    
    image_tags = images_container.find_all('img', class_='wp-manga-chapter-img')
    image_urls = [img.get('src', '').strip() for img in image_tags if img.get('src')]
    return image_urls
def mc_download_single_image(args: Tuple[str, str]) -> bool:
    img_url, file_path = args
    try:
        img_response = requests.get(img_url, headers=MC_HEADERS, stream=True, timeout=20)
        img_response.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in img_response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except requests.exceptions.RequestException:
        return False


MD_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
def md_get_chapters_and_title(manhwa_url: str) -> Tuple[List[Dict], str]:
    logger.info(f"[{MANGA_DISTRICT_DOMAIN}] در حال دریافت اطلاعات از: {manhwa_url}")
    try:
        response = requests.get(manhwa_url, headers=MD_HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        logger.error(f"[{MANGA_DISTRICT_DOMAIN}] خطا در اتصال به {manhwa_url}: {e}")
        return [], ""

    title_element = soup.select_one('div.post-title h1')
    if not title_element:
        logger.error(f"[{MANGA_DISTRICT_DOMAIN}] عنوان مانهوا پیدا نشد.")
        return [], ""
    manhwa_title = title_element.text.strip()
    sanitized_title = sanitize_filename(manhwa_title)

    chapters = []
    chapter_list_element = soup.select_one('ul.version-chap')
    if not chapter_list_element:
        logger.error(f"[{MANGA_DISTRICT_DOMAIN}] لیست چپترها پیدا نشد.")
        return [], sanitized_title

    for item in chapter_list_element.find_all('li', class_='wp-manga-chapter'):
        link = item.find('a')
        if link and link.has_attr('href'):
            chapter_title = link.text.strip()
            chapter_url = link['href']
            safe_chapter_title = sanitize_filename(chapter_title)
            chapters.append({'name': safe_chapter_title, 'url': chapter_url})
    
    if chapters:
        chapters.reverse()
    
    logger.info(f"[{MANGA_DISTRICT_DOMAIN}] {len(chapters)} چپتر برای '{sanitized_title}' یافت شد.")
    return chapters, sanitized_title
def md_get_chapter_image_urls(chapter_url: str) -> List[str]:
    logger.info(f"[{MANGA_DISTRICT_DOMAIN}] در حال استخراج تصاویر از: {chapter_url}")
    try:
        response = requests.get(chapter_url, headers=MD_HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        logger.error(f"[{MANGA_DISTRICT_DOMAIN}] خطا در دسترسی به صفحه چپتر: {e}")
        return []

    reading_content = soup.find('div', class_='reading-content')
    if not reading_content:
        logger.error(f"[{MANGA_DISTRICT_DOMAIN}] محتوای چپتر در آدرس {chapter_url} پیدا نشد.")
        return []

    image_urls = []
    for img in reading_content.find_all('img'):
        img_url = img.get('src', '').strip()
        if not img_url:
            img_url = img.get('data-src', '').strip()
        if img_url:
            image_urls.append(img_url)
    return image_urls
def md_download_single_image(args: Tuple[str, str]) -> bool:
    img_url, file_path = args
    try:
        img_response = requests.get(img_url, headers=MD_HEADERS, stream=True, timeout=20)
        img_response.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in img_response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"[{MANGA_DISTRICT_DOMAIN}] خطا در دانلود تصویر {img_url}: {e}")
        return False


EROME_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': 'https://www.erome.com/'
}

def er_get_album_media(album_url: str) -> Tuple[str, Dict[str, List[str]]]:
    """
    اطلاعات یک آلبوم از سایت Erome را استخراج می‌کند (عنوان، لینک عکس‌ها و ویدیوها).
    """
    logger.info(f"[{EROME_DOMAIN}] در حال تحلیل محتوای آلبوم: {album_url}")
    try:
        response = requests.get(album_url, headers=EROME_HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        
        title_tag = soup.find('h1')
        album_title = title_tag.text.strip() if title_tag else "Erome Album"
        sanitized_title = sanitize_filename(album_title)

        media_urls = {'images': [], 'videos': []}
        
       
        for video_tag in soup.find_all('video'):
            source_tag = video_tag.find('source')
            if source_tag and source_tag.get('src'):
                media_urls['videos'].append(source_tag['src'])

        
        for img_div in soup.find_all('div', class_='img'):
            if img_div.get('data-src'):
                media_urls['images'].append(img_div['data-src'])

        
        media_urls['images'] = sorted(list(dict.fromkeys(media_urls['images'])))
        media_urls['videos'] = sorted(list(dict.fromkeys(media_urls['videos'])))
        
        logger.info(f"[{EROME_DOMAIN}] برای '{sanitized_title}'، {len(media_urls['images'])} عکس و {len(media_urls['videos'])} ویدیو یافت شد.")
        return sanitized_title, media_urls

    except requests.exceptions.RequestException as e:
        logger.error(f"[{EROME_DOMAIN}] خطا در دسترسی به صفحه: {e}")
        return "Error", {}

async def er_get_album_media_selenium(album_url: str, driver) -> Tuple[str, Dict[str, List[str]]]:
    """
    [تابع جدید با Selenium]
    اطلاعات آلبوم را با باز کردن صفحه در یک مرورگر واقعی استخراج می‌کند
    تا لینک‌های نهایی و پرسرعت را پس از اجرای JavaScript بدست آورد.
    """
    logger.info(f"[{EROME_DOMAIN}] در حال باز کردن صفحه با Selenium برای دریافت لینک‌های نهایی: {album_url}")
    driver.get(album_url)
    
    try:
        
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "video, div.img[data-src]"))
        )
        
        
        await asyncio.sleep(2)

        
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        title_tag = soup.find('h1')
        album_title = title_tag.text.strip() if title_tag else "Erome Album"
        sanitized_title = sanitize_filename(album_title)

        media_urls = {'images': [], 'videos': []}
        
        
        for video_tag in soup.find_all('video'):
            source_tag = video_tag.find('source')
            if source_tag and source_tag.get('src'):
                media_urls['videos'].append(source_tag['src'])

        
        for img_div in soup.find_all('div', class_='img'):
            if img_div.get('data-src'):
                media_urls['images'].append(img_div['data-src'])

        media_urls['images'] = sorted(list(dict.fromkeys(media_urls['images'])))
        media_urls['videos'] = sorted(list(dict.fromkeys(media_urls['videos'])))
        
        logger.info(f"[{EROME_DOMAIN}] با Selenium، {len(media_urls['images'])} عکس و {len(media_urls['videos'])} ویدیو یافت شد.")
        return sanitized_title, media_urls

    except Exception as e:
        logger.error(f"[{EROME_DOMAIN}] خطا در هنگام کار با Selenium: {e}")
        return "Error", {}


@celery_app.task(name="tasks.process_erome_images", **RETRY_PARAMS)
def process_erome_images_task(chat_id: int, image_urls: list, album_title: str):
    """
    Celery task to download and upload images from an Erome album with retry logic.
    """
    async def _async_worker():
        bot = get_bot_instance()
        status_message = await bot.send_message(
            chat_id=chat_id,
            text=f"📥 شروع دانلود {len(image_urls)} عکس برای آلبوم '{album_title}'..."
        )
        message_id_to_edit = status_message.message_id

        with tempfile.TemporaryDirectory() as temp_dir:
            for i, url in enumerate(image_urls):
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id_to_edit,
                        text=f"[{i+1}/{len(image_urls)}] 🖼️ در حال دانلود و آپلود عکس..."
                    )
                    
                    filename = os.path.basename(urllib.parse.urlparse(url).path) or f"erome_img_{i}.jpg"
                    temp_file_path = os.path.join(temp_dir, filename)

                    
                    def _download_image_sync():
                        with requests.get(url, headers=EROME_HEADERS, stream=True, timeout=120) as r:
                            r.raise_for_status()
                            with open(temp_file_path, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=8192):
                                    f.write(chunk)
                    
                    await asyncio.to_thread(_download_image_sync)

                    with open(temp_file_path, 'rb') as photo:
                        await bot.send_photo(chat_id=chat_id, photo=photo, caption=filename)
                    
                    os.remove(temp_file_path)

                except Exception as e:
                    logger.error(f"Failed to process Erome image {url}: {e}")
                    await bot.send_message(chat_id=chat_id, text=f"❌ خطا در پردازش عکس: {filename}")
            
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id_to_edit,
                text=f"✅ آپلود تمام عکس‌های آلبوم '{album_title}' به پایان رسید."
            )

    asyncio.run(_async_worker())


@cooldown_decorator()
async def handle_erome_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip()
    user_id = update.effective_user.id

    is_allowed, message_text = await check_subscription(user_id, EROME_DOMAIN)
    if not is_allowed:
        await update.message.reply_text(message_text)
        return ConversationHandler.END

    message = await update.message.reply_text(f"دانلودر: {EROME_DOMAIN} | در حال آماده‌سازی مرورگر...")
    
    driver = await asyncio.to_thread(setup_driver)
    if not driver:
        await message.edit_text("خطا: درایور مرورگر راه‌اندازی نشد.")
        return ConversationHandler.END

    try:
        await message.edit_text(f"دانلودر: {EROME_DOMAIN} | در حال تحلیل لینک با مرورگر...")
        title, media_urls = await er_get_album_media_selenium(url, driver)

        if not media_urls or (not media_urls.get('images') and not media_urls.get('videos')):
            await message.edit_text("هیچ عکس یا ویدیویی در این آلبوم یافت نشد.")
            return ConversationHandler.END
            
        context.user_data['er_media'] = media_urls
        context.user_data['er_title'] = title
        
        num_images = len(media_urls.get('images', []))
        num_videos = len(media_urls.get('videos', []))
        
        keyboard = []
        text = f"✅ تحلیل کامل شد: آلبوم '{title}'\n\n"
        if num_images > 0:
            keyboard.append([InlineKeyboardButton(f"🖼️ دانلود {num_images} عکس", callback_data="er_choice_images")])
            text += f"- {num_images} عکس\n"
        if num_videos > 0:
            keyboard.append([InlineKeyboardButton(f"🎬 دانلود {num_videos} ویدیو", callback_data="er_choice_videos")])
            text += f"- {num_videos} ویدیو\n"
        if num_images > 0 and num_videos > 0:
            keyboard.append([InlineKeyboardButton("📥 دانلود هردو (عکس و ویدیو)", callback_data="er_choice_both")])

        if not keyboard:
            await message.edit_text("محتوای قابل دانلودی یافت نشد.")
            return ConversationHandler.END

        text += "\nکدام را می‌خواهید دانلود کنید؟"
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return EROME_AWAIT_CHOICE

    finally:
        await asyncio.to_thread(driver.quit)


async def er_run_yt_dlp_with_headers(url: str, temp_dir: str, filename: str) -> Tuple[str | None, str]:
    """
    [تابع جدید و اختصاصی]
    یک فرآیند کامل yt-dlp را برای Erome اجرا می‌کند که شامل هدرهای لازم برای جلوگیری از خطای 403 است.
    این تابع جایگزین run_yt_dlp_process عمومی می‌شود.
    """

    
    temp_filename_template = os.path.join(temp_dir, 'initial_download')
    ydl_opts = {
        'format': 'best',
        'outtmpl': temp_filename_template,
        'quiet': False,
        'no_warnings': True,
        'http_headers': EROME_HEADERS 
    }
    
    
    logger.info(f"[{EROME_DOMAIN}] شروع دانلود با yt-dlp و هدرهای سفارشی...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        initial_file = next((os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.startswith('initial_download')), None)
        if not initial_file:
            return None, "فایل دانلود شده توسط yt-dlp یافت نشد."

    except Exception as e:
        logger.error(f"[{EROME_DOMAIN}] دانلود با yt-dlp ناموفق بود: {e}")
        return None, f"خطا در دانلود اولیه: {e}"

    
    repaired_file = os.path.join(temp_dir, "repaired.mp4")
    if not repair_video(initial_file, repaired_file):
        return None, "خطا در تعمیر ویدیو."
    
    final_path = verify_and_finalize(repaired_file, os.path.join(DOWNLOAD_FOLDER, filename))
    if not final_path:
        return None, "خطا در تأیید نهایی فایل."
        
    return final_path, "موفقیت"


async def er_process_single_file(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, media_url: str, is_video: bool, temp_dir_base: str):
    """
    [تابع بازنویسی شده]
    یک فایل (عکس یا ویدیو) از Erome را پردازش می‌کند، خطای متغیر را برطرف کرده
    و منطق جدید آرشیو عمومی/شخصی را پیاده‌سازی می‌کند.
    """
    chat_id = update.callback_query.message.chat_id
    filename = media_url.split('/')[-1].split('?')[0] or f"media_{hash(media_url)}"
    
    if is_video:
        
        with tempfile.TemporaryDirectory(dir=temp_dir_base) as temp_dir:
            try:
                
                raw_video_path, status_msg = await er_run_yt_dlp_with_headers(
                    url=media_url,
                    temp_dir=temp_dir,
                    filename=filename
                )
                if not raw_video_path:
                    raise Exception(f"دانلود ناموفق بود: {status_msg}")

                duration, width, height = get_video_metadata(raw_video_path)
                
                
                public_upload_id = await upload_video_with_bot_api(
                    bot=context.bot, 
                    target_chat_id=PUBLIC_ARCHIVE_CHAT_ID, file_path=raw_video_path, thumb_path=None, caption=filename,
                    duration=duration, width=width, height=height
                )
                if not public_upload_id:
                    raise Exception("آپلود به آرشیو عمومی ناموفق بود.")

                
                custom_thumbnail_id = get_user_thumbnail(user_id)
                watermark_settings = get_user_watermark_settings(user_id)
                user_has_customization = bool(custom_thumbnail_id or watermark_settings.get("enabled"))
                
                if not user_has_customization:
                    
                    add_to_video_cache(media_url, 'erome_default', public_upload_id)
                    await context.bot.copy_message(chat_id=chat_id, from_chat_id=PUBLIC_ARCHIVE_CHAT_ID, message_id=public_upload_id)
                else:
                    
                    path_after_watermark = await asyncio.to_thread(apply_watermark_to_video, raw_video_path, watermark_settings)
                    if not path_after_watermark:
                        raise Exception("خطا در هنگام اعمال واترمارک.")
                    
                    custom_thumb_path = None
                    if custom_thumbnail_id:
                        thumb_file = await context.bot.get_file(custom_thumbnail_id)
                        custom_thumb_path = os.path.join(temp_dir, 'custom_thumb.jpg')
                        await thumb_file.download_to_drive(custom_path=custom_thumb_path)
                    
                    personal_archive_id = await get_or_create_personal_archive(user_id)
                    if not personal_archive_id:
                        raise Exception("خطا در ساخت یا دریافت آرشیو شخصی.")

                    personal_upload_id = await upload_video_with_bot_api(
                        bot=context.bot, 
                        target_chat_id=personal_archive_id, file_path=path_after_watermark, thumb_path=custom_thumb_path,
                        caption=filename, duration=duration, width=width, height=height
                    )

                    if not personal_upload_id:
                        raise Exception("آپلود به آرشیو شخصی ناموفق بود.")
                        
                    await context.bot.copy_message(chat_id=chat_id, from_chat_id=personal_archive_id, message_id=personal_upload_id)
            
            except Exception as e:
                logger.error(f"[{EROME_DOMAIN}] خطا در پردازش ویدیو {media_url}: {e}", exc_info=True)
                await context.bot.send_message(chat_id=chat_id, text=f"❌ خطا در پردازش ویدیو: {filename}")

    else: 
        with tempfile.TemporaryDirectory(dir=temp_dir_base) as temp_dir:
            temp_file_path = None
            try:
                temp_file_path = os.path.join(temp_dir, filename)
                with requests.get(media_url, headers=EROME_HEADERS, timeout=120, stream=True) as r:
                    r.raise_for_status()
                    with open(temp_file_path, 'wb') as f:
                        shutil.copyfileobj(r.raw, f)
                
                with open(temp_file_path, 'rb') as f:
                    await context.bot.send_photo(chat_id=chat_id, photo=f, caption=filename, read_timeout=120, write_timeout=120)

            except Exception as e:
                logger.error(f"[{EROME_DOMAIN}] خطا در پردازش عکس {media_url}: {e}", exc_info=True)
                await context.bot.send_message(chat_id=chat_id, text=f"❌ خطا در پردازش عکس: {filename}")


async def process_erome_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    [تابع بازنویسی شده]
    به جای استفاده از Celery، هر فایل را در یک تسک asyncio جداگانه پردازش می‌کند
    تا از مسدود شدن ربات جلوگیری شود.
    """
    query = update.callback_query
    await query.answer()
    choice = query.data
    user_id = query.from_user.id 

    media = context.user_data.get('er_media')
    
    if not media:
        await query.edit_message_text("خطا: اطلاعات دانلود منقضی شده است.")
        return ConversationHandler.END

    images_to_process = []
    videos_to_process = []

    if choice == 'er_choice_images' or choice == 'er_choice_both':
        images_to_process = media.get('images', [])
    if choice == 'er_choice_videos' or choice == 'er_choice_both':
        videos_to_process = media.get('videos', [])

    if not images_to_process and not videos_to_process:
        await query.edit_message_text("فایلی برای دانلود انتخاب نشده بود.")
        return ConversationHandler.END
    
    await query.edit_message_text(f"✅ پردازش {len(images_to_process) + len(videos_to_process)} فایل در پس‌زمینه آغاز شد...")
    
    
    with tempfile.TemporaryDirectory() as temp_dir_base:
        if images_to_process:
            for img_url in images_to_process:
                
                asyncio.create_task(er_process_single_file(
                    update, context, user_id, img_url, is_video=False, temp_dir_base=temp_dir_base
                ))
        
        if videos_to_process:
            for video_url in videos_to_process:
                
                asyncio.create_task(er_process_single_file(
                    update, context, user_id, video_url, is_video=True, temp_dir_base=temp_dir_base
                ))
                
    
    context.user_data.pop('er_media', None)
    context.user_data.pop('er_title', None)
    return ConversationHandler.END



API_BASE_URL = "https://api.comick.fun"
IMAGE_BASE_URL = "https://meo.comick.pictures"



logger = logging.getLogger(__name__)


IMAGE_DOWNLOAD_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/125.0',
    'Referer': f'https://{COMICK_DOMAIN}/'
}

def setup_firefox_driver() -> webdriver.Firefox:
    """
    وب‌درایور فایرفاکس را برای اجرای بدون رابط کاربری (Headless) راه‌اندازی و پیکربندی می‌کند.
    """
    logger.info(f"[{COMICK_DOMAIN}] در حال آماده‌سازی درایور فایرفاکس (GeckoDriver)...")
    try:
        options = FirefoxOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        
        
        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
        logger.info(f"[{COMICK_DOMAIN}] ✓ درایور فایرفاکس با موفقیت در حالت Headless راه‌اندازی شد.")
        return driver
    except Exception as e:
        logger.error(f"[{COMICK_DOMAIN}] ❌ خطا در راه‌اندازی درایور فایرفاکس: {e}")
        return None

def cm_get_info_and_chapters(comic_url: str, driver: webdriver.Firefox) -> Tuple[str, List[Dict]]:
    """
    با استفاده از Selenium، اطلاعات یک کمیک (عنوان) و لیست چپترهای آن را استخراج می‌کند.
    """
    logger.info(f"[{COMICK_DOMAIN}] در حال باز کردن صفحه کمیک با مرورگر: {comic_url}")
    driver.get(comic_url)

    try:
        
        wait = WebDriverWait(driver, 25)
        script_element = wait.until(
            EC.presence_of_element_located((By.ID, '__NEXT_DATA__'))
        )
        
        logger.info(f"[{COMICK_DOMAIN}] اطلاعات صفحه با موفقیت بارگذاری شد.")
        script_content = script_element.get_attribute('innerHTML')
        data = json.loads(script_content)
        
        comic_data = data['props']['pageProps']['comic']
        title = comic_data['title']
        hid = comic_data['hid']
        
        logger.info(f"[{COMICK_DOMAIN}] کمیک پیدا شد: '{title}' (hid: {hid})")
        logger.info(f"[{COMICK_DOMAIN}] در حال دریافت لیست چپترها از طریق API...")

        chapters_api_url = f"{API_BASE_URL}/comic/{hid}/chapters?lang=en&limit=99999"
        
        
        chapter_data = driver.execute_async_script(
            f"var callback = arguments[arguments.length - 1];"
            f"fetch('{chapters_api_url}').then(res => res.json()).then(data => callback(data)).catch(err => callback({{error: err.toString()}}));"
        )

        if 'error' in chapter_data:
            logger.error(f"[{COMICK_DOMAIN}] خطا در دریافت لیست چپترها: {chapter_data['error']}")
            return None, []

        chapters = chapter_data.get('chapters', [])

        if not chapters:
            logger.warning(f"[{COMICK_DOMAIN}] هیچ چیتری برای '{title}' یافت نشد.")
            return title, []

        
        chapters.sort(key=lambda x: float(x.get('chap', 0)) if str(x.get('chap', 0)).replace('.', '', 1).isdigit() else 0)
        
        
        adapted_chapters = [
            {'name': f"Chapter {c.get('chap', 'N/A')}" + (f" - {c.get('title')}" if c.get('title') else ""), 'hid': c.get('hid')}
            for c in chapters
        ]

        logger.info(f"[{COMICK_DOMAIN}] ✓ تعداد {len(adapted_chapters)} چپتر برای '{title}' پیدا شد.")
        return title, adapted_chapters

    except Exception as e:
        logger.error(f"[{COMICK_DOMAIN}] ❌ خطایی هنگام دریافت اطلاعات با Selenium رخ داد: {e}", exc_info=True)
        return None, []


def cm_get_chapter_image_urls(chapter_hid: str, driver: webdriver.Firefox) -> List[str]:
    """
    لیست URL تصاویر یک چپتر مشخص را با استفاده از HID آن دریافت می‌کند.
    این نسخه از Selenium برای دور زدن محدودیت‌های امنیتی (مانند 403 Forbidden) استفاده می‌کند.
    """
    logger.info(f"[{COMICK_DOMAIN}] در حال دریافت URL تصاویر برای چپتر با hid: {chapter_hid} با استفاده از مرورگر...")
    api_url = f"{API_BASE_URL}/chapter/{chapter_hid}"
    try:
        
        chapter_data = driver.execute_async_script(
            "var callback = arguments[arguments.length - 1];"
            f"fetch('{api_url}').then(res => res.json()).then(data => callback(data)).catch(err => callback({{error: err.toString()}}));"
        )

        if 'error' in chapter_data:
            logger.error(f"[{COMICK_DOMAIN}] خطا در دریافت اطلاعات چپتر {chapter_hid} از طریق مرورگر: {chapter_data['error']}")
            return []

        images = chapter_data.get('chapter', {}).get('md_images', [])
        if not images:
            logger.warning(f"[{COMICK_DOMAIN}] هیچ تصویری برای چپتر با hid: {chapter_hid} یافت نشد.")
            return []
            
        image_urls = [f"{IMAGE_BASE_URL}/{img['b2key']}" for img in images]
        logger.info(f"[{COMICK_DOMAIN}] تعداد {len(image_urls)} تصویر برای چپتر پیدا شد.")
        return image_urls

    except Exception as e:
        logger.error(f"[{COMICK_DOMAIN}] خطای نامشخص در پردازش اطلاعات تصویر برای چپتر {chapter_hid}: {e}")
        return []

def cm_download_single_image(args: Tuple[str, str]) -> bool:
    """
    یک تصویر را از URL مشخص شده در مسیر فایل مورد نظر دانلود می‌کند.
    """
    img_url, file_path = args
    try:
        img_response = requests.get(img_url, headers=IMAGE_DOWNLOAD_HEADERS, stream=True, timeout=25)
        img_response.raise_for_status()
        
        with open(file_path, 'wb') as f:
            for chunk in img_response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"[{COMICK_DOMAIN}] دانلود تصویر {img_url} ناموفق بود: {e}")
        return False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """[نسخه ویرایش شده] دستور /start با کیبورد دائمی برای کاربر."""
    user = update.effective_user
    user_data = get_user_data(user.id) 
    
    if user_data.get('username') != user.username:
        user_data['username'] = user.username
        update_user_data(user.id, user_data)
    
    start_message = (
        "سلام! به ربات مولتی دانلودر خوش اومدید\n"
        "یک لینک از سایت های پشتیبانی شده بفرستید تا شروع به کار کنم"
    )
    
    
    user_keyboard = [["راهنما"]]
    reply_markup = ReplyKeyboardMarkup(user_keyboard, resize_keyboard=True)
    
    await update.message.reply_text(start_message, reply_markup=reply_markup)


@cooldown_decorator()
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    
    if not update.message or not update.message.text:
        return
    url = update.message.text.strip()
    
    if not url.startswith("http"):
        return

    user_id = update.effective_user.id
    domain = urllib.parse.urlparse(url).netloc.lower().replace('www.', '')

    is_allowed, message = await check_subscription(user_id, domain)
    if not is_allowed:
        await update.message.reply_text(message)
        return 
        
    logger.info(f"لینک توسط کنترل‌کننده عمومی دریافت شد، ارسال به yt-dlp: {url}")
    await handle_yt_dlp_link(update, context, url)


@cooldown_decorator()
async def handle_pornhub_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles links from video sites like Pornhub and Eporner.
    This corrected version dynamically detects the domain from the URL.
    """
    if not update.message or not update.message.text:
        return
    url = update.message.text.strip()
    user_id = update.effective_user.id

    parsed_url = urllib.parse.urlparse(url)
    domain = parsed_url.netloc.lower().replace('www.', '')

    
    if domain not in [PORNHUB_DOMAIN, EPORNER_DOMAIN, XVIDEOS_DOMAIN]:
        
        logger.warning(f"Handler received an unexpected domain: {domain}")
        
        return
    
        
    is_allowed, message = await check_subscription(user_id, domain)
    if not is_allowed:
        await update.message.reply_text(message)
        return

    logger.info(f"Link from {domain} received, passing to yt-dlp handler: {url}")
    await handle_yt_dlp_link(update, context, url)




def run_yt_dlp_process(url, temp_dir, format_id, final_filename):
    initial_file = download_video(url, temp_dir, format_id)
    if not initial_file: return None, "خطا در دانلود."
    repaired_file = os.path.join(temp_dir, "repaired.mp4")
    if not repair_video(initial_file, repaired_file): return None, "خطا در تعمیر."
    final_path = verify_and_finalize(repaired_file, final_filename)
    if not final_path: return None, "خطا در تأیید."
    return final_path, "موفقیت"


def generate_thumbnail_from_video(video_path: str, output_path: str) -> bool:
    """
    یک تامبنیل از فایل ویدیویی با استفاده از ffmpeg در ثانیه اول ویدیو استخراج می‌کند.
    """
    try:
        (
            ffmpeg
            .input(video_path, ss=1)
            .output(output_path, vframes=1)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.info(f"تامبنیل با موفقیت در مسیر {output_path} ساخته شد.")
        return True
    except ffmpeg.Error as e:
        logger.error(f"خطا در ساخت تامبنیل: {e.stderr.decode()}")
        return False


@celery_app.task(name="tasks.download_and_upload_video")
def download_and_upload_video_task(chat_id: int, url: str, selected_format: str, video_info_json: str, user_id: int):
    """
    [نسخه اصلاح شده با قابلیت دانلود تامبنیل]
    این تسک اکنون تامبنیل پیش‌فرض را دانلود کرده و برای نسخه آرشیو عمومی استفاده می‌کند.
    """
    
    video_info = json.loads(video_info_json) if video_info_json else {}

    async def _async_worker():
        bot = get_bot_instance()
        status_message = await bot.send_message(chat_id=chat_id, text="📥 درخواست دانلود از صف دریافت شد...")
        message_id_to_edit = status_message.message_id

        custom_thumbnail_id = get_user_thumbnail(user_id)
        watermark_settings = get_user_watermark_settings(user_id)
        user_has_customization = bool(custom_thumbnail_id or watermark_settings.get("enabled"))
        
        title = sanitize_filename(video_info.get('title', 'untitled_video'))
        final_filename = os.path.join(DOWNLOAD_FOLDER, f"{title}.mp4")

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text=f"📥 در حال دانلود: {title}...")
                raw_video_path, status_msg = await asyncio.to_thread(
                    run_yt_dlp_process, url, temp_dir, selected_format, final_filename
                )
                if not raw_video_path:
                    raise Exception(f"دانلود ناموفق بود: {status_msg}")

                duration, width, height = await asyncio.to_thread(get_video_metadata, raw_video_path)

                
                default_thumb_path = None
                thumbnail_url = video_info.get('thumbnail')
                
                if thumbnail_url:
                    try:
                        thumb_filename = os.path.basename(urllib.parse.urlparse(thumbnail_url).path) or "default_thumb.jpg"
                        temp_thumb_path = os.path.join(temp_dir, thumb_filename)
                        
                        def _download_thumb():
                            with requests.get(thumbnail_url, stream=True, timeout=20) as r:
                                r.raise_for_status()
                                with open(temp_thumb_path, 'wb') as f:
                                    shutil.copyfileobj(r.raw, f)
                            return temp_thumb_path
                        
                        default_thumb_path = await asyncio.to_thread(_download_thumb)
                        logger.info(f"تامبنیل پیش‌فرض با موفقیت دانلود شد: {default_thumb_path}")

                    except Exception as e:
                        logger.warning(f"دانلود تامبنیل پیش‌فرض از {thumbnail_url} ناموفق بود: {e}")
                        default_thumb_path = None
                
                
                if not default_thumb_path or not os.path.exists(default_thumb_path):
                    logger.info("در حال ساخت تامبنیل از ویدیو به عنوان جایگزین...")
                    fallback_thumb_path = os.path.join(temp_dir, 'fallback_thumb.jpg')
                    thumb_generated = await asyncio.to_thread(
                        generate_thumbnail_from_video, raw_video_path, fallback_thumb_path
                    )
                    if thumb_generated:
                        default_thumb_path = fallback_thumb_path
                

                await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text="📤 در حال آپلود نسخه خام به آرشیو عمومی...")
                
                public_upload_id = await upload_video_with_bot_api(
                    bot=bot, 
                    target_chat_id=PUBLIC_ARCHIVE_CHAT_ID, 
                    file_path=raw_video_path, 
                    thumb_path=default_thumb_path,
                    caption=title,
                    duration=duration, width=width, height=height
                )
                if not public_upload_id:
                    raise Exception("آپلود به آرشیو عمومی ناموفق بود.")

                
                if not user_has_customization:
                    add_to_video_cache(url, selected_format, public_upload_id)
                    await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text="📨 در حال ارسال برای شما...")
                    await bot.copy_message(chat_id=chat_id, from_chat_id=PUBLIC_ARCHIVE_CHAT_ID, message_id=public_upload_id)
                    await bot.delete_message(chat_id=chat_id, message_id=message_id_to_edit)
                    return

                
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text="🎨 در حال اعمال تنظیمات شخصی...")
                
                path_after_watermark = await asyncio.to_thread(apply_watermark_to_video, raw_video_path, watermark_settings)
                if not path_after_watermark:
                    raise Exception("خطا در هنگام اعمال واترمارک.")

                custom_thumb_path = None
                if custom_thumbnail_id:
                    thumb_file = await bot.get_file(custom_thumbnail_id)
                    custom_thumb_path = os.path.join(temp_dir, 'custom_thumb.jpg')
                    await thumb_file.download_to_drive(custom_path=custom_thumb_path)
                
                personal_archive_id = await get_or_create_personal_archive(user_id)
                if not personal_archive_id:
                    raise Exception("خطا در ساخت یا دریافت آرشیو شخصی.")

                await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text="📤 در حال آپلود نسخه سفارشی به آرشیو شما...")
                personal_upload_id = await upload_video_with_bot_api(
                    bot=bot, 
                    target_chat_id=personal_archive_id, file_path=path_after_watermark, thumb_path=custom_thumb_path,
                    caption=title, duration=duration, width=width, height=height
                )
                
                if personal_upload_id:
                    await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text="📨 در حال ارسال برای شما...")
                    await bot.copy_message(chat_id=chat_id, from_chat_id=personal_archive_id, message_id=personal_upload_id)
                    await bot.delete_message(chat_id=chat_id, message_id=message_id_to_edit)
                else:
                    raise Exception("آپلود به آرشیو شخصی ناموفق بود.")
            
            except Exception as e:
                logger.error(f"Celery Video Task Error: {e}", exc_info=True)
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text=f"❌ خطایی در پردازش ویدیو رخ داد: {e}")
            finally:
                if os.path.exists(final_filename):
                    os.remove(final_filename)

    asyncio.run(_async_worker())


@celery_app.task(name="tasks.process_gallery_dl")
def process_gallery_dl_task(chat_id: int, download_path: str, url: str, create_zip: bool):
    """
    Celery task to download from gallery-dl supported sites and upload to Telegram.
    """
    async def _async_worker():
        bot = get_bot_instance()
        status_message = None
        
        
        async def _run_gallery_dl_command():
            logger.info(f"[gallery-dl] Starting download from: {url}")
            command = ['gallery-dl', '-D', download_path, url]
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                error_message = stderr.decode('utf-8', errors='ignore').strip()
                logger.error(f"[gallery-dl] Error during download. Code: {process.returncode}\n{error_message}")
                return None, error_message
            
            all_files = [os.path.join(root, file) for root, _, files in os.walk(download_path) for file in sorted(files)]
            return all_files, None

        try:
            status_message = await bot.send_message(
                chat_id=chat_id,
                text=f"📥 درخواست دانلود از '{urllib.parse.urlparse(url).netloc}' دریافت شد. شروع دانلود..."
            )
            message_id_to_edit = status_message.message_id

            downloaded_files, error = await _run_gallery_dl_command()

            if error or not downloaded_files:
                error_text = error or 'هیچ فایلی یافت نشد.'
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text=f"دانلود ناموفق بود: {error_text}")
                return

            if create_zip:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id_to_edit,
                    text="🗜️ در حال ساخت فایل فشرده..."
                )
                domain = urllib.parse.urlparse(url).netloc.replace('www.', '').split('.')[0]
                path_slug = urllib.parse.urlparse(url).path.strip('/').replace('/', '_')
                zip_base_name = sanitize_filename(f"{domain}_{path_slug if path_slug else 'gallery'}")
                zip_output_path = os.path.join(DOWNLOAD_FOLDER, f"{zip_base_name}.zip")
                
                await asyncio.to_thread(create_zip_from_folder, download_path, zip_output_path)
                
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id_to_edit,
                    text=f"📤 در حال آپلود: {os.path.basename(zip_output_path)}..."
                )
                with open(zip_output_path, 'rb') as doc:
                    await bot.send_document(chat_id=chat_id, document=doc, caption=os.path.basename(zip_output_path))
                os.remove(zip_output_path)
            else:
                total_files = len(downloaded_files)
                for i, file_path in enumerate(downloaded_files):
                    filename = os.path.basename(file_path)
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id_to_edit,
                        text=f"📤 در حال آپلود فایل {i+1} از {total_files}: {filename}..."
                    )
                    
                    file_ext = os.path.splitext(filename)[1].lower()
                    IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.webp']
                    VIDEO_EXTS = ['.mp4', '.mkv', '.webm']
                    
                    try:
                        with open(file_path, 'rb') as f:
                            if file_ext in IMAGE_EXTS:
                                await bot.send_photo(chat_id=chat_id, photo=f, caption=filename)
                            elif file_ext in VIDEO_EXTS:
                                await bot.send_video(chat_id=chat_id, video=f, caption=filename, supports_streaming=True)
                            else:
                                await bot.send_document(chat_id=chat_id, document=f, caption=filename)
                    except Exception as upload_error:
                        logger.error(f"Error sending file {filename}: {upload_error}")
                        await bot.send_message(chat_id=chat_id, text=f"❌ خطا در آپلود فایل: {filename}")

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id_to_edit,
                text="✅ تمام فایل‌ها با موفقیت ارسال شدند."
            )
        except Exception as e:
            logger.error(f"Celery Gallery-DL Task Error: {e}", exc_info=True)
            if status_message:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message.message_id,
                    text=f"❌ خطایی در پردازش دانلود رخ داد: {e}"
                )
        finally:
            if os.path.exists(download_path):
                shutil.rmtree(download_path)

    asyncio.run(_async_worker())


@cooldown_decorator()
async def handle_gallery_dl_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip()
    user_id = update.effective_user.id
    domain = urllib.parse.urlparse(url).netloc.lower().replace('www.', '')
    is_allowed, message_text = await check_subscription(user_id, domain)
    if not is_allowed:
        await update.message.reply_text(message_text)
        return ConversationHandler.END

    
    should_ask_for_zip = any(zip_site in domain for zip_site in GALLERY_DL_ZIP_SITES)
    
    if should_ask_for_zip:
        message = await update.message.reply_text("این سایت از دانلود به صورت فایل فشرده (ZIP) پشتیبانی می‌کند. آیا می‌خواهید فایل‌ها فشرده شوند؟")
        await message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("بله، فایل ZIP بساز", callback_data="gdl_zip_yes")],
                [InlineKeyboardButton("نه، به صورت فایل مجزا بفرست", callback_data="gdl_zip_no")]
            ])
        )
        
        context.user_data['gdl_url'] = url
        return GALLERY_DL_AWAIT_ZIP_OPTION
    else:
        
        await update.message.reply_text(f"✅ درخواست شما برای دانلود از '{domain}' به صف اضافه شد.")
        task_id = f"gdl_{update.effective_chat.id}_{update.message.message_id}"
        download_path = os.path.join(DOWNLOAD_FOLDER, task_id)
        
        process_gallery_dl_task.delay(
            chat_id=update.effective_chat.id,
            download_path=download_path,
            url=url,
            create_zip=False 
        )
        return ConversationHandler.END

async def process_gallery_dl_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    create_zip = (query.data == 'gdl_zip_yes')
    url = context.user_data.get('gdl_url')

    if not url:
        await query.edit_message_text("خطا: اطلاعات دانلود منقضی شده است. لطفاً دوباره تلاش کنید.")
        return ConversationHandler.END

    await query.edit_message_text(f"✅ درخواست شما برای دانلود از '{urllib.parse.urlparse(url).netloc}' به صف اضافه شد.")

    task_id = f"gdl_{query.message.chat.id}_{query.message.message_id}"
    download_path = os.path.join(DOWNLOAD_FOLDER, task_id)
    
    process_gallery_dl_task.delay(
        chat_id=query.message.chat.id,
        download_path=download_path,
        url=url,
        create_zip=create_zip
    )
    
    context.user_data.pop('gdl_url', None)
    return ConversationHandler.END



def create_chapter_keyboard(chapters: list, selected_indices: list, page: int, prefix: str) -> InlineKeyboardMarkup:
    keyboard_rows = []
    items_per_page = 20
    start_index = page * items_per_page
    end_index = start_index + items_per_page
    paginated_chapters = chapters[start_index:end_index]
    row = []
    for i, chapter in enumerate(paginated_chapters):
        global_index = start_index + i
        text = f"✅ {chapter['name']}" if global_index in selected_indices else chapter['name']
        row.append(InlineKeyboardButton(text, callback_data=f"{prefix}_toggle_{global_index}"))
        if len(row) == 2: keyboard_rows.append(row); row = []
    if row: keyboard_rows.append(row)
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"{prefix}_page_{page-1}"))
    if end_index < len(chapters): nav_row.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"{prefix}_page_{page+1}"))
    if nav_row: keyboard_rows.append(nav_row)
    keyboard_rows.append([InlineKeyboardButton("انتخاب همه", callback_data=f"{prefix}_select_all"), InlineKeyboardButton("حذف همه", callback_data=f"{prefix}_deselect_all")])
    keyboard_rows.append([InlineKeyboardButton("✅ شروع دانلود", callback_data=f"{prefix}_start_download")])
    return InlineKeyboardMarkup(keyboard_rows)


@celery_app.task(name="tasks.process_cosplaytele_images")
def process_cosplaytele_images_task(chat_id: int, image_urls: list, page_slug: str):
    """
    Celery task to download and upload images from a CosplayTele gallery.
    """
    async def _async_worker():
        bot = get_bot_instance()
        status_message = await bot.send_message(
            chat_id=chat_id,
            text=f"📥 درخواست دانلود {len(image_urls)} عکس از صف دریافت شد. شروع فرآیند..."
        )
        message_id_to_edit = status_message.message_id
        
        specific_folder = Path(DOWNLOAD_FOLDER) / page_slug
        specific_folder.mkdir(parents=True, exist_ok=True)
        
        try:
            def _download_all_images_sync():
                tasks = []
                for i, url in enumerate(image_urls):
                    filename = os.path.basename(urllib.parse.urlparse(url).path) or f"image_{i+1}.jpg"
                    file_path = specific_folder / filename
                    tasks.append((url, str(file_path)))
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    executor.map(ct_download_single_image, tasks)
                return tasks 

            
            downloaded_tasks = await asyncio.to_thread(_download_all_images_sync)

            total_images = len(downloaded_tasks)
            for i, (url, file_path_str) in enumerate(downloaded_tasks):
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id_to_edit,
                    text=f"[{i+1}/{total_images}] 📤 در حال آپلود عکس: {os.path.basename(file_path_str)}..."
                )
                file_path = Path(file_path_str)
                if file_path.exists():
                    try:
                        with open(file_path, 'rb') as photo:
                            await bot.send_photo(chat_id=chat_id, photo=photo, caption=file_path.name)
                    except Exception as e:
                        logger.error(f"[{COSPLAYTELE_DOMAIN}] Error uploading photo {file_path.name}: {e}")
                        await bot.send_message(chat_id=chat_id, text=f"❌ خطا در آپلود عکس: {file_path.name}")
                    finally:
                        os.remove(file_path)

            if os.path.isdir(specific_folder) and not os.listdir(specific_folder):
                os.rmdir(specific_folder)
            
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id_to_edit,
                text="✅ آپلود تمام عکس‌ها به پایان رسید."
            )
        except Exception as e:
            logger.error(f"Celery CosplayTele Task Error: {e}", exc_info=True)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id_to_edit,
                text=f"❌ خطایی در پردازش دانلود عکس‌ها رخ داد: {e}"
            )

    asyncio.run(_async_worker())


@cooldown_decorator()
async def handle_cosplaytele_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip()
    user_id = update.effective_user.id
    is_allowed, message_text = await check_subscription(user_id, COSPLAYTELE_DOMAIN)
    if not is_allowed:
        await update.message.reply_text(message_text)
        return ConversationHandler.END

    message = await update.message.reply_text(f"دانلودر: {COSPLAYTELE_DOMAIN} | در حال تحلیل لینک...")
    
    media_urls = await asyncio.to_thread(ct_analyze_and_extract_media, url)
    
    if not media_urls or (not media_urls.get('images') and not media_urls.get('videos')):
        await message.edit_text("هیچ عکس یا ویدیویی برای دانلود در این صفحه یافت نشد.")
        return ConversationHandler.END
        
    context.user_data['ct_media_urls'] = media_urls
    
    num_images = len(media_urls.get('images', []))
    num_videos = len(media_urls.get('videos', []))
    
    keyboard = []
    if num_images > 0:
        keyboard.append([InlineKeyboardButton(f"🖼️ دانلود {num_images} عکس", callback_data="ct_choice_images")])
    if num_videos > 0:
        keyboard.append([InlineKeyboardButton(f"🎬 دانلود {num_videos} ویدیو", callback_data="ct_choice_videos")])
    
    if not keyboard:
        await message.edit_text("محتوای قابل دانلودی یافت نشد.")
        return ConversationHandler.END

    page_slug = urllib.parse.urlparse(url).path.strip('/').replace('/', '-') or "gallery"
    context.user_data['ct_page_slug'] = page_slug

    await message.edit_text(
        f"✅ تحلیل کامل شد:\n- {num_images} عکس\n- {num_videos} ویدیو\n\nکدام را می‌خواهید دانلود کنید؟",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CT_AWAIT_USER_CHOICE

async def process_cosplaytele_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    choice = query.data
    
    media_urls = context.user_data.get('ct_media_urls')
    page_slug = context.user_data.get('ct_page_slug', 'cosplaytele-gallery')

    if not media_urls:
        await query.edit_message_text("خطا: اطلاعات دانلود منقضی شده است. لطفاً دوباره تلاش کنید.")
        return ConversationHandler.END

    if choice == 'ct_choice_images':
        image_urls = media_urls.get('images', [])
        if not image_urls:
            await query.edit_message_text("هیچ عکسی برای دانلود در این لینک وجود ندارد.")
        else:
            
            process_cosplaytele_images_task.delay(
                chat_id=query.message.chat_id,
                image_urls=image_urls,
                page_slug=page_slug
            )
            await query.edit_message_text(f"✅ درخواست شما برای دانلود {len(image_urls)} عکس به صف اضافه شد.")

    elif choice == 'ct_choice_videos':
        video_urls = media_urls.get('videos', [])
        if not video_urls:
            await query.edit_message_text("هیچ ویدیویی برای دانلود در این لینک وجود ندارد.")
        else:
            
            for video_url in video_urls:
                
                download_and_upload_video_task.delay(
                    chat_id=query.message.chat_id,
                    url=video_url,
                    selected_format='best', 
                    user_id=query.from_user.id,
                    video_info_json=None 
                )
            await query.edit_message_text(f"✅ درخواست شما برای دانلود {len(video_urls)} ویدیو به صف اضافه شد.")

    context.user_data.pop('ct_media_urls', None)
    context.user_data.pop('ct_page_slug', None)
    return ConversationHandler.END


@celery_app.task(name="tasks.process_mangadistrict")
def process_mangadistrict_task(chat_id: int, manhwa_title: str, chapters_to_download: list, create_zip: bool):
    """
    Celery task to download chapters from MangaDistrict.
    This runs in the background on a Celery worker.
    """
    async def _async_worker():
        bot = get_bot_instance()
        status_message = await bot.send_message(
            chat_id=chat_id, 
            text=f"📥 درخواست دانلود '{manhwa_title}' از صف دریافت شد. شروع فرآیند..."
        )
        message_id_to_edit = status_message.message_id

        manhwa_folder = Path(DOWNLOAD_FOLDER) / sanitize_filename(manhwa_title)
        manhwa_folder.mkdir(parents=True, exist_ok=True)

        try:
            total_chapters = len(chapters_to_download)
            for i, chapter in enumerate(chapters_to_download):
                await bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=message_id_to_edit, 
                    text=f"[{i+1}/{total_chapters}] 📥 در حال دانلود: {chapter['name']}..."
                )
                
                temp_images_path = manhwa_folder / (sanitize_filename(chapter['name']) + "_temp_md")
                temp_images_path.mkdir(exist_ok=True)

                
                image_urls = await asyncio.to_thread(md_get_chapter_image_urls, chapter['url'])

                if not image_urls:
                    await bot.send_message(chat_id=chat_id, text=f"❌ تصویری برای قسمت '{chapter['name']}' یافت نشد.")
                    shutil.rmtree(temp_images_path)
                    continue

                def _download_images_sync():
                    tasks = [(url, str(temp_images_path / f"{j+1:03d}{os.path.splitext(url.split('?')[0])[-1] or '.jpg'}")) for j, url in enumerate(image_urls)]
                    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                        executor.map(md_download_single_image, tasks)
                
                await asyncio.to_thread(_download_images_sync)

                downloaded_files = sorted(os.listdir(temp_images_path))
                if not downloaded_files:
                    await bot.send_message(chat_id=chat_id, text=f"❌ دانلود برای قسمت '{chapter['name']}' ناموفق بود.")
                    shutil.rmtree(temp_images_path)
                    continue

                if create_zip:
                    await bot.edit_message_text(
                        chat_id=chat_id, 
                        message_id=message_id_to_edit, 
                        text=f"[{i+1}/{total_chapters}] 🗜️ در حال فشرده‌سازی: {chapter['name']}..."
                    )
                    
                    zip_path = manhwa_folder / f"{manhwa_title} - {sanitize_filename(chapter['name'])}.zip"
                    await asyncio.to_thread(create_zip_from_folder, str(temp_images_path), str(zip_path))
                    
                    with open(zip_path, 'rb') as doc:
                        await bot.send_document(chat_id=chat_id, document=doc, caption=zip_path.name)
                    os.remove(zip_path)
                else:
                    await bot.edit_message_text(
                        chat_id=chat_id, 
                        message_id=message_id_to_edit, 
                        text=f"[{i+1}/{total_chapters}] 📤 در حال آپلود {len(downloaded_files)} عکس..."
                    )
                    for img_file in downloaded_files:
                        with open(temp_images_path / img_file, 'rb') as photo:
                            await bot.send_photo(chat_id=chat_id, photo=photo, caption=img_file)
                
                shutil.rmtree(temp_images_path)

            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=message_id_to_edit, 
                text=f"✅ تمام عملیات برای '{manhwa_title}' با موفقیت به پایان رسید."
            )
        except Exception as e:
            logger.error(f"Celery MangaDistrict Task Error: {e}", exc_info=True)
            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=message_id_to_edit, 
                text=f"❌ خطایی در پردازش دانلود رخ داد: {e}"
            )

    asyncio.run(_async_worker())

@cooldown_decorator()
async def handle_mangadistrict_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip()
    user_id = update.effective_user.id
    is_allowed, message_text = await check_subscription(user_id, MANGA_DISTRICT_DOMAIN)
    if not is_allowed:
        await update.message.reply_text(message_text)
        return ConversationHandler.END

    message = await update.message.reply_text(f"دانلودر: {MANGA_DISTRICT_DOMAIN} | در حال پردازش لینک...")
    
    
    chapters, title = await asyncio.to_thread(md_get_chapters_and_title, url)
    
    if not chapters:
        await message.edit_text("هیچ چپتری برای این لینک یافت نشد یا در دریافت اطلاعات خطایی رخ داد.")
        return ConversationHandler.END
    
    context.user_data['md_chapters'] = chapters
    context.user_data['md_title'] = title
    context.user_data['md_selected_indices'] = []
    context.user_data['md_current_page'] = 0
    
    keyboard = create_chapter_keyboard(chapters, [], 0, "md")
    await message.edit_text(
        f"✅ {len(chapters)} قسمت برای '{title}' یافت شد. لطفاً قسمت‌های مورد نظر را انتخاب کنید:",
        reply_markup=keyboard
    )
    return MD_SELECTING_CHAPTERS

async def chapter_selection_md_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    chapters = context.user_data.get('md_chapters', [])
    selected_indices = context.user_data.get('md_selected_indices', [])
    page = context.user_data.get('md_current_page', 0)

    if data.startswith("md_toggle_"):
        index = int(data.split('_')[-1])
        if index in selected_indices:
            selected_indices.remove(index)
        else:
            selected_indices.append(index)
    elif data.startswith("md_page_"):
        page = int(data.split('_')[-1])
    elif data == "md_select_all":
        selected_indices = list(range(len(chapters)))
    elif data == "md_deselect_all":
        selected_indices = []
    elif data == "md_start_download":
        if not selected_indices:
            await query.answer("لطفاً حداقل یک قسمت را انتخاب کنید.", show_alert=True)
            return MD_SELECTING_CHAPTERS
        keyboard = [
            [InlineKeyboardButton("بله، فایل ZIP بساز", callback_data="md_zip_yes")],
            [InlineKeyboardButton("نه، به صورت عکس بفرست", callback_data="md_zip_no")]
        ]
        await query.edit_message_text(
            "آیا می‌خواهید فایل‌های دانلود شده فشرده (ZIP) شوند؟",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MD_AWAIT_ZIP_OPTION
        
    context.user_data['md_selected_indices'] = selected_indices
    context.user_data['md_current_page'] = page
    keyboard = create_chapter_keyboard(chapters, selected_indices, page, "md")
    await query.edit_message_reply_markup(reply_markup=keyboard)
    return MD_SELECTING_CHAPTERS


async def process_mangadistrict_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    create_zip = (query.data == 'md_zip_yes')
    chapters_data = context.user_data.get('md_chapters', [])
    manhwa_title = context.user_data.get('md_title', 'Unknown')
    selected_indices = context.user_data.get('md_selected_indices', [])
    
    if not all([chapters_data, manhwa_title, selected_indices is not None]):
        await query.edit_message_text("خطا: اطلاعات دانلود منقضی شده است.")
        return ConversationHandler.END

    chapters_to_download = [chapters_data[i] for i in sorted(selected_indices)]

    
    process_mangadistrict_task.delay(
        chat_id=query.message.chat.id,
        manhwa_title=manhwa_title,
        chapters_to_download=chapters_to_download,
        create_zip=create_zip
    )

    await query.edit_message_text(f"✅ درخواست شما برای دانلود {len(chapters_to_download)} قسمت به صف اضافه شد.")

    
    for key in list(context.user_data.keys()):
        if key.startswith('md_'):
            context.user_data.pop(key)
            
    return ConversationHandler.END


@celery_app.task(name="tasks.process_comick")
def process_comick_task(chat_id: int, manhwa_title: str, chapters_to_download: list, create_zip: bool):
    """
    Celery task to download chapters from Comick.io using Selenium.
    This runs in the background on a Celery worker.
    """
    async def _async_worker():
        bot = get_bot_instance()
        status_message = await bot.send_message(
            chat_id=chat_id,
            text=f"📥 درخواست دانلود '{manhwa_title}' از صف دریافت شد. آماده‌سازی مرورگر..."
        )
        message_id_to_edit = status_message.message_id

        manhwa_folder = Path(DOWNLOAD_FOLDER) / sanitize_filename(manhwa_title)
        manhwa_folder.mkdir(parents=True, exist_ok=True)

        
        def _download_all_chapters_sync(loop):
            driver = None
            try:
                driver = setup_firefox_driver()
                if not driver:
                    raise Exception("Failed to initialize Firefox driver.")

                
                logger.info(f"[{COMICK_DOMAIN}] Warming up browser session...")
                driver.get(f"https://{COMICK_DOMAIN}/")
                

                total_chapters = len(chapters_to_download)
                for i, chapter in enumerate(chapters_to_download):
                    
                    async def update_status():
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id_to_edit,
                            text=f"[{i+1}/{total_chapters}] 📥 در حال دانلود: {chapter['name']}..."
                        )
                    asyncio.run_coroutine_threadsafe(update_status(), loop)

                    temp_images_path = manhwa_folder / (sanitize_filename(chapter['name']) + "_temp_cm")
                    temp_images_path.mkdir(exist_ok=True)

                    
                    image_urls = cm_get_chapter_image_urls(chapter['hid'], driver)
                    if not image_urls:
                        async def send_error():
                            await bot.send_message(chat_id=chat_id, text=f"❌ تصویری برای قسمت '{chapter['name']}' یافت نشد.")
                        asyncio.run_coroutine_threadsafe(send_error(), loop)
                        shutil.rmtree(temp_images_path)
                        continue

                    tasks = [(url, str(temp_images_path / f"{j+1:03d}{os.path.splitext(url.split('?')[0])[-1] or '.jpg'}")) for j, url in enumerate(image_urls)]
                    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                        executor.map(cm_download_single_image, tasks)

                    downloaded_files = sorted(os.listdir(temp_images_path))
                    if not downloaded_files:
                        async def send_dl_error():
                            await bot.send_message(chat_id=chat_id, text=f"❌ دانلود برای قسمت '{chapter['name']}' ناموفق بود.")
                        asyncio.run_coroutine_threadsafe(send_dl_error(), loop)
                        shutil.rmtree(temp_images_path)
                        continue

                    if create_zip:
                        async def update_zipping_status():
                            await bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=message_id_to_edit,
                                text=f"[{i+1}/{total_chapters}] 🗜️ در حال فشرده‌سازی: {chapter['name']}..."
                            )
                        asyncio.run_coroutine_threadsafe(update_zipping_status(), loop)

                        zip_path = manhwa_folder / f"{manhwa_title} - {sanitize_filename(chapter['name'])}.zip"
                        create_zip_from_folder(str(temp_images_path), str(zip_path))

                        async def upload_zip():
                            with open(zip_path, 'rb') as doc:
                                await bot.send_document(chat_id=chat_id, document=doc, caption=zip_path.name)
                            os.remove(zip_path)
                        asyncio.run_coroutine_threadsafe(upload_zip(), loop)
                    else:
                        for img_file in downloaded_files:
                            async def upload_photo():
                                with open(temp_images_path / img_file, 'rb') as photo:
                                    await bot.send_photo(chat_id=chat_id, photo=photo, caption=img_file)
                            asyncio.run_coroutine_threadsafe(upload_photo(), loop)
                    
                    shutil.rmtree(temp_images_path)
            finally:
                if driver:
                    driver.quit()

        try:
            loop = asyncio.get_running_loop()
            await asyncio.to_thread(_download_all_chapters_sync, loop)

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id_to_edit,
                text=f"✅ تمام عملیات برای '{manhwa_title}' با موفقیت به پایان رسید."
            )
        except Exception as e:
            logger.error(f"Celery Comick Task Error: {e}", exc_info=True)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id_to_edit,
                text=f"❌ خطایی در پردازش دانلود رخ داد: {e}"
            )

    asyncio.run(_async_worker())


@cooldown_decorator()
async def handle_comick_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip()
    user_id = update.effective_user.id
    is_allowed, message_text = await check_subscription(user_id, COMICK_DOMAIN)
    if not is_allowed:
        await update.message.reply_text(message_text)
        return ConversationHandler.END

    message = await update.message.reply_text(f"دانلودر: {COMICK_DOMAIN} | در حال آماده‌سازی مرورگر و پردازش لینک...")
    
    def _sync_get_info(comic_url):
        driver = None
        try:
            driver = setup_firefox_driver()
            if not driver:
                return None, []
            
            return cm_get_info_and_chapters(comic_url, driver)
        finally:
            if driver:
                driver.quit()

    title, chapters = await asyncio.to_thread(_sync_get_info, url)

    if not chapters:
        await message.edit_text("هیچ چپتری برای این لینک یافت نشد یا در دریافت اطلاعات خطایی رخ داد.")
        return ConversationHandler.END
    
    context.user_data['cm_chapters'] = chapters
    context.user_data['cm_title'] = title
    context.user_data['cm_selected_indices'] = []
    context.user_data['cm_current_page'] = 0
    
    keyboard = create_chapter_keyboard(chapters, [], 0, "cm")
    await message.edit_text(
        f"✅ {len(chapters)} قسمت برای '{title}' یافت شد. لطفاً قسمت‌های مورد نظر را انتخاب کنید:",
        reply_markup=keyboard
    )
    return CM_SELECTING_CHAPTERS

async def chapter_selection_cm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    chapters = context.user_data.get('cm_chapters', [])
    selected_indices = context.user_data.get('cm_selected_indices', [])
    page = context.user_data.get('cm_current_page', 0)
    
    if data.startswith("cm_toggle_"):
        index = int(data.split('_')[-1])
        if index in selected_indices:
            selected_indices.remove(index)
        else:
            selected_indices.append(index)
    elif data.startswith("cm_page_"):
        page = int(data.split('_')[-1])
    elif data == "cm_select_all":
        selected_indices = list(range(len(chapters)))
    elif data == "cm_deselect_all":
        selected_indices = []
    elif data == "cm_start_download":
        if not selected_indices:
            await query.answer("لطفاً حداقل یک قسمت را انتخاب کنید.", show_alert=True)
            return CM_SELECTING_CHAPTERS
        keyboard = [
            [InlineKeyboardButton("بله، فایل ZIP بساز", callback_data="cm_zip_yes")],
            [InlineKeyboardButton("نه، به صورت عکس بفرست", callback_data="cm_zip_no")]
        ]
        await query.edit_message_text(
            "آیا می‌خواهید فایل‌های دانلود شده فشرده (ZIP) شوند؟",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CM_AWAIT_ZIP_OPTION
        
    context.user_data['cm_selected_indices'] = selected_indices
    context.user_data['cm_current_page'] = page
    keyboard = create_chapter_keyboard(chapters, selected_indices, page, "cm")
    await query.edit_message_reply_markup(reply_markup=keyboard)
    return CM_SELECTING_CHAPTERS


async def process_comick_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    create_zip = (query.data == 'cm_zip_yes')
    chapters_data = context.user_data.get('cm_chapters', [])
    manhwa_title = context.user_data.get('cm_title', 'Unknown')
    selected_indices = context.user_data.get('cm_selected_indices', [])
    
    if not all([chapters_data, manhwa_title, selected_indices is not None]):
        await query.edit_message_text("خطا: اطلاعات دانلود منقضی شده است.")
        return ConversationHandler.END

    chapters_to_download = [chapters_data[i] for i in sorted(selected_indices)]

    
    process_comick_task.delay(
        chat_id=query.message.chat.id,
        manhwa_title=manhwa_title,
        chapters_to_download=chapters_to_download,
        create_zip=create_zip
    )

    await query.edit_message_text(f"✅ درخواست شما برای دانلود {len(chapters_to_download)} قسمت به صف اضافه شد.")

    
    for key in list(context.user_data.keys()):
        if key.startswith('cm_'):
            context.user_data.pop(key)
            
    return ConversationHandler.END


@celery_app.task(name="tasks.process_manhwaclan")
def process_manhwaclan_task(chat_id: int, manhwa_title: str, chapters_to_download: list, create_zip: bool):
    """
    Celery task to download chapters from ManhwaClan.
    This runs in the background on a Celery worker.
    """
    async def _async_worker():
        bot = get_bot_instance()
        status_message = await bot.send_message(
            chat_id=chat_id, 
            text=f"📥 درخواست دانلود '{manhwa_title}' از صف دریافت شد. شروع فرآیند..."
        )
        message_id_to_edit = status_message.message_id

        manhwa_folder = Path(DOWNLOAD_FOLDER) / sanitize_filename(manhwa_title)
        manhwa_folder.mkdir(parents=True, exist_ok=True)

        try:
            total_chapters = len(chapters_to_download)
            for i, chapter in enumerate(chapters_to_download):
                await bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=message_id_to_edit, 
                    text=f"[{i+1}/{total_chapters}] 📥 در حال دانلود: {chapter['name']}..."
                )
                
                temp_images_path = manhwa_folder / (sanitize_filename(chapter['name']) + "_temp_mc")
                temp_images_path.mkdir(exist_ok=True)

                # Run blocking network calls in a thread
                image_urls = await asyncio.to_thread(mc_get_chapter_image_urls, chapter['url'])

                if not image_urls:
                    await bot.send_message(chat_id=chat_id, text=f"❌ تصویری برای قسمت '{chapter['name']}' یافت نشد.")
                    shutil.rmtree(temp_images_path)
                    continue

                def _download_images_sync():
                    tasks = [(url, str(temp_images_path / f"{j+1:03d}{os.path.splitext(url)[1].split('?')[0] or '.jpg'}")) for j, url in enumerate(image_urls)]
                    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                        executor.map(mc_download_single_image, tasks)
                
                await asyncio.to_thread(_download_images_sync)

                downloaded_files = sorted(os.listdir(temp_images_path))
                if not downloaded_files:
                    await bot.send_message(chat_id=chat_id, text=f"❌ دانلود برای قسمت '{chapter['name']}' ناموفق بود.")
                    shutil.rmtree(temp_images_path)
                    continue

                if create_zip:
                    await bot.edit_message_text(
                        chat_id=chat_id, 
                        message_id=message_id_to_edit, 
                        text=f"[{i+1}/{total_chapters}] 🗜️ در حال فشرده‌سازی: {chapter['name']}..."
                    )
                    
                    zip_path = manhwa_folder / f"{manhwa_title} - {sanitize_filename(chapter['name'])}.zip"
                    await asyncio.to_thread(create_zip_from_folder, str(temp_images_path), str(zip_path))
                    
                    with open(zip_path, 'rb') as doc:
                        await bot.send_document(chat_id=chat_id, document=doc, caption=zip_path.name)
                    os.remove(zip_path)
                else:
                    await bot.edit_message_text(
                        chat_id=chat_id, 
                        message_id=message_id_to_edit, 
                        text=f"[{i+1}/{total_chapters}] 📤 در حال آپلود {len(downloaded_files)} عکس..."
                    )
                    for img_file in downloaded_files:
                        with open(temp_images_path / img_file, 'rb') as photo:
                            await bot.send_photo(chat_id=chat_id, photo=photo, caption=img_file)
                
                shutil.rmtree(temp_images_path)

            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=message_id_to_edit, 
                text=f"✅ تمام عملیات برای '{manhwa_title}' با موفقیت به پایان رسید."
            )
        except Exception as e:
            logger.error(f"Celery ManhwaClan Task Error: {e}", exc_info=True)
            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=message_id_to_edit, 
                text=f"❌ خطایی در پردازش دانلود رخ داد: {e}"
            )

    asyncio.run(_async_worker())

@cooldown_decorator()
async def handle_manhwaclan_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip()
    user_id = update.effective_user.id
    is_allowed, message_text = await check_subscription(user_id, MANHWACLAN_DOMAIN)
    if not is_allowed:
        await update.message.reply_text(message_text)
        return ConversationHandler.END

    message = await update.message.reply_text(f"دانلودر: {MANHWACLAN_DOMAIN} | در حال پردازش لینک...")
    
    
    chapters, title = await asyncio.to_thread(mc_get_chapters_and_title, url)
    
    if not chapters:
        await message.edit_text("هیچ چپتری برای این لینک یافت نشد یا در دریافت اطلاعات خطایی رخ داد.")
        return ConversationHandler.END
    
    context.user_data['mc_chapters'] = chapters
    context.user_data['mc_title'] = title
    context.user_data['mc_selected_indices'] = []
    context.user_data['mc_current_page'] = 0
    
    keyboard = create_chapter_keyboard(chapters, [], 0, "mc")
    await message.edit_text(
        f"✅ {len(chapters)} قسمت برای '{title}' یافت شد. لطفاً قسمت‌های مورد نظر را انتخاب کنید:",
        reply_markup=keyboard
    )
    return MC_SELECTING_CHAPTERS

async def chapter_selection_mc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    chapters = context.user_data.get('mc_chapters', [])
    selected_indices = context.user_data.get('mc_selected_indices', [])
    page = context.user_data.get('mc_current_page', 0)

    if data.startswith("mc_toggle_"):
        index = int(data.split('_')[-1])
        if index in selected_indices:
            selected_indices.remove(index)
        else:
            selected_indices.append(index)
    elif data.startswith("mc_page_"):
        page = int(data.split('_')[-1])
    elif data == "mc_select_all":
        selected_indices = list(range(len(chapters)))
    elif data == "mc_deselect_all":
        selected_indices = []
    elif data == "mc_start_download":
        if not selected_indices:
            await query.answer("لطفاً حداقل یک قسمت را انتخاب کنید.", show_alert=True)
            return MC_SELECTING_CHAPTERS
        keyboard = [
            [InlineKeyboardButton("بله، فایل ZIP بساز", callback_data="mc_zip_yes")],
            [InlineKeyboardButton("نه، به صورت عکس بفرست", callback_data="mc_zip_no")]
        ]
        await query.edit_message_text(
            "آیا می‌خواهید فایل‌های دانلود شده فشرده (ZIP) شوند؟",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MC_AWAIT_ZIP_OPTION
        
    context.user_data['mc_selected_indices'] = selected_indices
    context.user_data['mc_current_page'] = page
    keyboard = create_chapter_keyboard(chapters, selected_indices, page, "mc")
    await query.edit_message_reply_markup(reply_markup=keyboard)
    return MC_SELECTING_CHAPTERS


async def process_manhwaclan_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    create_zip = (query.data == 'mc_zip_yes')
    chapters_data = context.user_data.get('mc_chapters', [])
    manhwa_title = context.user_data.get('mc_title', 'Unknown')
    selected_indices = context.user_data.get('mc_selected_indices', [])
    
    if not all([chapters_data, manhwa_title, selected_indices is not None]):
        await query.edit_message_text("خطا: اطلاعات دانلود منقضی شده است.")
        return ConversationHandler.END

    chapters_to_download = [chapters_data[i] for i in sorted(selected_indices)]

    
    process_manhwaclan_task.delay(
        chat_id=query.message.chat.id,
        manhwa_title=manhwa_title,
        chapters_to_download=chapters_to_download,
        create_zip=create_zip
    )

    await query.edit_message_text(f"✅ درخواست شما برای دانلود {len(chapters_to_download)} قسمت به صف اضافه شد.")

    
    for key in list(context.user_data.keys()):
        if key.startswith('mc_'):
            context.user_data.pop(key)
            
    return ConversationHandler.END


@celery_app.task(name="tasks.process_toonily_me")
def process_toonily_me_task(chat_id: int, manhwa_title: str, chapters_to_download: list, create_zip: bool):
    
    
    async def _async_worker():
        bot = get_bot_instance()
        status_message = await bot.send_message(chat_id=chat_id, text=f"📥 شروع دانلود {len(chapters_to_download)} قسمت برای '{manhwa_title}' از صف...")
        message_id_to_edit = status_message.message_id

        manhwa_folder = Path(DOWNLOAD_FOLDER) / sanitize_filename(manhwa_title)
        
        await asyncio.to_thread(manhwa_folder.mkdir, parents=True, exist_ok=True)
        
        try:
            total_chapters = len(chapters_to_download)
            for i, chapter in enumerate(chapters_to_download):
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text=f"[{i+1}/{total_chapters}] 📥 در حال دانلود: {chapter['name']}...")
                
                temp_images_path = manhwa_folder / (sanitize_filename(chapter['name']) + "_temp_me")
                await asyncio.to_thread(temp_images_path.mkdir, exist_ok=True)

                
                image_urls = await asyncio.to_thread(mn2_get_chapter_images, chapter['url'])

                if not image_urls:
                    await bot.send_message(chat_id=chat_id, text=f"❌ تصویری برای قسمت '{chapter['name']}' یافت نشد.")
                    await asyncio.to_thread(shutil.rmtree, temp_images_path)
                    continue
                
                
                def download_all_images():
                    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                        futures = [executor.submit(mn2_download_image, url, temp_images_path / f"{j+1:03d}.jpg") for j, url in enumerate(image_urls)]
                        concurrent.futures.wait(futures)
                
                await asyncio.to_thread(download_all_images)

                downloaded_files = await asyncio.to_thread(lambda: [f for f in os.listdir(temp_images_path) if f.endswith('.jpg')])
                if not downloaded_files:
                    await bot.send_message(chat_id=chat_id, text=f"❌ دانلود برای قسمت '{chapter['name']}' ناموفق بود.")
                    await asyncio.to_thread(shutil.rmtree, temp_images_path)
                    continue

                if create_zip:
                    await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text=f"[{i+1}/{total_chapters}] 🗜️ در حال فشرده‌سازی...")
                    zip_path = manhwa_folder / f"{manhwa_title} - {chapter['name']}.zip"
                    await asyncio.to_thread(mn2_create_zip, downloaded_files, zip_path, temp_images_path, del_source=True)
                    
                    with open(zip_path, 'rb') as doc:
                        await bot.send_document(chat_id=chat_id, document=doc, caption=zip_path.name)
                    
                    await asyncio.to_thread(os.remove, zip_path)
                else:
                    await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text=f"[{i+1}/{total_chapters}] 📤 در حال آپلود {len(downloaded_files)} عکس...")
                    for img_file in sorted(downloaded_files):
                        with open(temp_images_path / img_file, 'rb') as photo:
                            await bot.send_photo(chat_id=chat_id, photo=photo)
                    await asyncio.to_thread(shutil.rmtree, temp_images_path)
            
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text=f"✅ تمام عملیات برای '{manhwa_title}' با موفقیت به پایان رسید.")
        except Exception as e:
            logger.error(f"Celery Toonily.me Error: {e}", exc_info=True)
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text=f"❌ خطایی در پردازش رخ داد: {e}")
    
    
    asyncio.run(_async_worker())


@cooldown_decorator()
async def start_manhwa_me_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    user_id = update.effective_user.id
    domain = TOONILY_ME_DOMAIN
    is_allowed, message_text = await check_subscription(user_id, domain)
    if not is_allowed:
        await update.message.reply_text(message_text)
        return ConversationHandler.END
    await update.message.reply_text(f"لطفاً نام مانهوای مورد نظر را برای جستجو در {TOONILY_ME_DOMAIN} وارد کنید:")
    return ME_AWAIT_MANHWA_SEARCH

async def receive_manhwa_me_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.message.text
    message = await update.message.reply_text(f"در حال جستجو برای '{query}'...")
    search_results = await asyncio.to_thread(mn2_search, query)
    if not search_results:
        await message.edit_text("هیچ نتیجه‌ای یافت نشد. لطفاً دوباره تلاش کنید یا /cancel را بزنید.")
        return ME_AWAIT_MANHWA_SEARCH
    context.user_data['mn2_search_results'] = search_results
    keyboard = [[InlineKeyboardButton(result['name'], callback_data=f"mn2_select_{i}")] for i, result in enumerate(search_results[:10])]
    await message.edit_text("نتایج یافت شده:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ME_SELECTING_MANHWA

async def _internal_show_me_chapters(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str, message_to_edit) -> int:
    chapters, title = await asyncio.to_thread(mn2_get_chapters, url)
    if not chapters:
        await message_to_edit.edit_text("هیچ چپتری برای این لینک یافت نشد."); return ConversationHandler.END
    context.user_data['mn2_chapters'] = chapters
    context.user_data['mn2_title'] = title
    context.user_data['mn2_selected_indices'] = []
    context.user_data['mn2_current_page'] = 0
    keyboard = create_chapter_keyboard(chapters, [], 0, "mn2")
    await message_to_edit.edit_text(
        f"✅ {len(chapters)} قسمت برای '{title}' یافت شد. لطفاً قسمت‌های مورد نظر را انتخاب کنید:",
        reply_markup=keyboard
    )
    return ME_SELECTING_CHAPTERS

@cooldown_decorator()
async def handle_manhwa_me_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    if not update.message or not update.message.text: 
        return ConversationHandler.END
    url = update.message.text.strip()
    user_id = update.effective_user.id
    domain = TOONILY_ME_DOMAIN
    is_allowed, message_text = await check_subscription(user_id, domain)
    if not is_allowed:
        await update.message.reply_text(message_text)
        return ConversationHandler.END
    message = await update.message.reply_text(f"دانلودر: {TOONILY_ME_DOMAIN} | در حال پردازش لینک مستقیم...")
    return await _internal_show_me_chapters(update, context, url, message)

async def select_manhwa_me_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    index = int(query.data.split('_')[-1])
    search_results = context.user_data.get('mn2_search_results')
    if not search_results or index >= len(search_results):
        await query.edit_message_text("خطا: نتایج جستجو منقضی شده یا نامعتبر است.")
        return ConversationHandler.END
    selected_manhwa = search_results[index]
    await query.edit_message_text(f"شما '{selected_manhwa['name']}' را انتخاب کردید. در حال دریافت لیست چپترها...")
    return await _internal_show_me_chapters(update, context, selected_manhwa['url'], query.message)

async def chapter_selection_me_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    chapters = context.user_data.get('mn2_chapters', [])
    selected_indices = context.user_data.get('mn2_selected_indices', [])
    page = context.user_data.get('mn2_current_page', 0)
    if data.startswith("mn2_toggle_"):
        index = int(data.split('_')[-1])
        if index in selected_indices: selected_indices.remove(index)
        else: selected_indices.append(index)
    elif data.startswith("mn2_page_"):
        page = int(data.split('_')[-1])
    elif data == "mn2_select_all":
        selected_indices = list(range(len(chapters)))
    elif data == "mn2_deselect_all":
        selected_indices = []
    elif data == "mn2_start_download":
        if not selected_indices:
            await context.bot.answer_callback_query(query.id, "لطفاً حداقل یک قسمت را انتخاب کنید.", show_alert=True)
            return ME_SELECTING_CHAPTERS
        keyboard = [[InlineKeyboardButton("بله، فایل ZIP بساز", callback_data="mn2_zip_yes")], [InlineKeyboardButton("نه، به صورت عکس بفرست", callback_data="mn2_zip_no")]]
        await query.edit_message_text("آیا می‌خواهید فایل‌های دانلود شده فشرده (ZIP) شوند؟", reply_markup=InlineKeyboardMarkup(keyboard))
        return ME_AWAIT_ZIP_OPTION
    context.user_data['mn2_selected_indices'] = selected_indices
    context.user_data['mn2_current_page'] = page
    keyboard = create_chapter_keyboard(chapters, selected_indices, page, "mn2")
    await query.edit_message_reply_markup(reply_markup=keyboard)
    return ME_SELECTING_CHAPTERS

async def process_manhwa_me_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    create_zip = (query.data == 'mn2_zip_yes')
    chapters_data = context.user_data.get('mn2_chapters', [])
    manhwa_title = context.user_data.get('mn2_title', 'Unknown')
    selected_indices = context.user_data.get('mn2_selected_indices', [])
    
    if not all([chapters_data, manhwa_title, selected_indices is not None]):
        await query.edit_message_text("خطا: اطلاعات دانلود منقضی شده است.")
        return ConversationHandler.END

    chapters_to_download = [chapters_data[i] for i in sorted(selected_indices)]

    
    process_toonily_me_task.delay(
        chat_id=query.message.chat.id,
        manhwa_title=manhwa_title,
        chapters_to_download=chapters_to_download,
        create_zip=create_zip
    )

    await query.edit_message_text(f"✅ درخواست شما برای دانلود {len(chapters_to_download)} قسمت به صف اضافه شد.")

    
    for key in list(context.user_data.keys()):
        if key.startswith('mn2_'):
            context.user_data.pop(key)
            
    return ConversationHandler.END


@celery_app.task(name="tasks.process_toonily_com")
def process_toonily_com_task(chat_id: int, manhwa_title: str, chapters_to_download: list, create_zip: bool):
    """
    Celery task to download chapters from Toonily.com using Selenium.
    This runs in the background on a Celery worker.
    """
    async def _async_worker():
        bot = get_bot_instance()
        status_message = await bot.send_message(
            chat_id=chat_id, 
            text=f"📥 درخواست دانلود '{manhwa_title}' از صف دریافت شد. آماده‌سازی مرورگر..."
        )
        message_id_to_edit = status_message.message_id

        manhwa_folder = Path(DOWNLOAD_FOLDER) / sanitize_filename(manhwa_title)
        manhwa_folder.mkdir(parents=True, exist_ok=True)
        
        
        def _download_all_chapters_sync(loop): 
            driver = None
            try:
                driver = setup_driver()
                if not driver:
                    raise Exception("Failed to initialize Selenium driver.")
                
                total_chapters = len(chapters_to_download)
                for i, chapter in enumerate(chapters_to_download):
                    
                    async def update_status():
                        await bot.edit_message_text(
                            chat_id=chat_id, 
                            message_id=message_id_to_edit, 
                            text=f"[{i+1}/{total_chapters}] 📥 در حال دانلود: {chapter['name']}..."
                        )
                    
                    asyncio.run_coroutine_threadsafe(update_status(), loop)

                    downloaded_folder = download_images_for_chapter_sync_com(chapter, str(manhwa_folder), manhwa_title, driver)
                    
                    if not downloaded_folder or not os.listdir(downloaded_folder):
                        async def send_error():
                            await bot.send_message(chat_id=chat_id, text=f"❌ دانلود برای قسمت '{chapter['name']}' ناموفق بود یا تصویری یافت نشد.")
                        
                        asyncio.run_coroutine_threadsafe(send_error(), loop)
                        if downloaded_folder:
                             shutil.rmtree(downloaded_folder)
                        continue

                    if create_zip:
                        async def update_zipping_status():
                            await bot.edit_message_text(
                                chat_id=chat_id, 
                                message_id=message_id_to_edit, 
                                text=f"[{i+1}/{total_chapters}] 🗜️ در حال فشرده‌سازی: {chapter['name']}..."
                            )
                        
                        asyncio.run_coroutine_threadsafe(update_zipping_status(), loop)
                        
                        zip_path = manhwa_folder / f"{manhwa_title} - {sanitize_filename(chapter['name'])}.zip"
                        create_zip_from_folder(downloaded_folder, str(zip_path))
                        
                        async def upload_zip():
                            with open(zip_path, 'rb') as doc:
                                await bot.send_document(chat_id=chat_id, document=doc, caption=zip_path.name)
                            os.remove(zip_path)
                        
                        asyncio.run_coroutine_threadsafe(upload_zip(), loop)

                    else:
                        async def update_upload_status():
                             await bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=message_id_to_edit,
                                text=f"[{i+1}/{total_chapters}] 📤 در حال آپلود تصاویر برای: {chapter['name']}..."
                            )
                        
                        asyncio.run_coroutine_threadsafe(update_upload_status(), loop)

                        image_files = sorted([os.path.join(downloaded_folder, f) for f in os.listdir(downloaded_folder)])
                        for img_path in image_files:
                            async def upload_photo():
                                with open(img_path, 'rb') as photo:
                                    await bot.send_photo(chat_id=chat_id, photo=photo, caption=os.path.basename(img_path))
                            
                            asyncio.run_coroutine_threadsafe(upload_photo(), loop)
                    
                    shutil.rmtree(downloaded_folder)

            finally:
                if driver:
                    driver.quit()

        try:
            
            loop = asyncio.get_running_loop()
            await asyncio.to_thread(_download_all_chapters_sync, loop)

            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=message_id_to_edit, 
                text=f"✅ تمام عملیات برای '{manhwa_title}' با موفقیت به پایان رسید."
            )
        except Exception as e:
            logger.error(f"Celery Toonily.com Task Error: {e}", exc_info=True)
            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=message_id_to_edit, 
                text=f"❌ خطایی در پردازش دانلود رخ داد: {e}"
            )

    asyncio.run(_async_worker())


@cooldown_decorator()
async def handle_toonily_com_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip()
    user_id = update.effective_user.id
    is_allowed, message_text = await check_subscription(user_id, TOONILY_COM_DOMAIN)
    if not is_allowed:
        await update.message.reply_text(message_text)
        return ConversationHandler.END

    message = await update.message.reply_text(f"دانلودر: {TOONILY_COM_DOMAIN} | در حال اتصال و یافتن قسمت‌ها...")
    
    
    def _sync_find_chapters():
        driver = None
        try:
            driver = setup_driver()
            if not driver:
                return None, None
            return find_all_chapters_com(url, driver)
        finally:
            if driver:
                driver.quit()

    chapters, manhwa_title = await asyncio.to_thread(_sync_find_chapters)
        
    if not chapters:
        await message.edit_text("هیچ قسمتی یافت نشد یا در پردازش لینک خطایی رخ داد.")
        return ConversationHandler.END
    
    adapted_chapters = [{'name': c['title'], 'url': c['url']} for c in chapters]
    
    context.user_data['com_chapters'] = adapted_chapters
    context.user_data['com_title'] = manhwa_title
    context.user_data['com_selected_indices'] = []
    context.user_data['com_current_page'] = 0
    
    keyboard = create_chapter_keyboard(adapted_chapters, [], 0, "com")
    await message.edit_text(
        f"✅ {len(chapters)} قسمت برای '{manhwa_title}' یافت شد. لطفاً قسمت‌های مورد نظر را انتخاب کنید:", 
        reply_markup=keyboard
    )
    return COM_SELECTING_CHAPTERS

async def handle_chapter_selection_com(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    chapters = context.user_data.get('com_chapters', [])
    selected_indices = context.user_data.get('com_selected_indices', [])
    page = context.user_data.get('com_current_page', 0)
    
    if data.startswith("com_toggle_"):
        index = int(data.split('_')[-1])
        if index in selected_indices:
            selected_indices.remove(index)
        else:
            selected_indices.append(index)
    elif data.startswith("com_page_"):
        page = int(data.split('_')[-1])
    elif data == "com_select_all":
        selected_indices = list(range(len(chapters)))
    elif data == "com_deselect_all":
        selected_indices = []
    elif data == "com_start_download":
        if not selected_indices:
            await query.answer("لطفاً حداقل یک قسمت را انتخاب کنید.", show_alert=True)
            return COM_SELECTING_CHAPTERS
        keyboard = [
            [InlineKeyboardButton("بله، فایل ZIP بساز", callback_data="com_zip_yes")],
            [InlineKeyboardButton("نه، به صورت عکس بفرست", callback_data="com_zip_no")]
        ]
        await query.edit_message_text(
            "آیا می‌خواهید فایل‌های دانلود شده فشرده (ZIP) شوند؟", 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return COM_AWAIT_ZIP_OPTION
        
    context.user_data['com_selected_indices'] = selected_indices
    context.user_data['com_current_page'] = page
    keyboard = create_chapter_keyboard(chapters, selected_indices, page, "com")
    await query.edit_message_reply_markup(reply_markup=keyboard)
    return COM_SELECTING_CHAPTERS

async def process_toonily_com_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    create_zip = (query.data == 'com_zip_yes')
    chapters = context.user_data.get('com_chapters', [])
    manhwa_title = context.user_data.get('com_title', 'Unknown')
    selected_indices = context.user_data.get('com_selected_indices', [])

    if not all([chapters, manhwa_title, selected_indices is not None]):
        await query.edit_message_text("خطا: اطلاعات دانلود منقضی شده است. لطفاً دوباره تلاش کنید.")
        return ConversationHandler.END

    chapters_to_download = [chapters[i] for i in sorted(selected_indices)]

    
    process_toonily_com_task.delay(
        chat_id=query.message.chat.id,
        manhwa_title=manhwa_title,
        chapters_to_download=chapters_to_download,
        create_zip=create_zip
    )

    await query.edit_message_text(f"✅ درخواست شما برای دانلود {len(chapters_to_download)} قسمت به صف اضافه شد.")

    
    for key in list(context.user_data.keys()):
        if key.startswith('com_'):
            context.user_data.pop(key)
            
    return ConversationHandler.END


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data.startswith("yt_"):
        await yt_dlp_button_callback(update, context)



async def handle_yt_dlp_link(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """
    لینک ویدیو را مدیریت کرده و لیست کیفیت‌ها را برای کاربر نمایش می‌دهد.
    """
    message = await update.message.reply_text("دانلودر: yt-dlp | در حال پردازش لینک...")
    info = await asyncio.to_thread(get_full_video_info, url)
    if not info:
        await message.edit_text("خطا در استخراج اطلاعات."); return
        
    context.user_data['video_info'] = info
    formats = [f for f in info.get('formats', []) if f.get('vcodec') != 'none' and f.get('height')]
    if not formats:
        await message.edit_text("هیچ کیفیت ویدیویی قابل دانلودی یافت نشد."); return
    
    best_formats = {}
    for f in formats:
        h = f.get('height')
        current_tbr = f.get('tbr') or 0
        if h not in best_formats or current_tbr > (best_formats[h].get('tbr') or 0):
            best_formats[h] = f
            
    keyboard = [
        [
            InlineKeyboardButton(
                f"{h}p ({(f.get('filesize') or f.get('filesize_approx') or 0) / (1024*1024):.2f} MB)",
                callback_data=f"yt_{f['format_id']}"
            )
        ]
        for h, f in sorted(best_formats.items(), reverse=True)
    ]
    keyboard.append([InlineKeyboardButton("Best Quality (Auto)", callback_data='yt_best')])
    await message.edit_text('کیفیت مورد نظر را انتخاب کنید:', reply_markup=InlineKeyboardMarkup(keyboard))




def get_video_metadata(file_path: str) -> Tuple[int, int, int]:
    """
    (Synchronous Version)
    Extracts metadata (duration, width, height) from a video file using ffmpeg.
    This is a blocking function and should be run in a thread.
    """
    try:
        logger.info(f"Extracting metadata from: {file_path}")
        probe = ffmpeg.probe(file_path)
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        
        if not video_stream:
            logger.error("No video stream found in the file.")
            return 0, 0, 0
        
        duration = int(float(probe['format'].get('duration', 0)))
        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))
        
        logger.info(f"Metadata extracted: Duration={duration}s, Size={width}x{height}")
        return duration, width, height
        
    except (ffmpeg.Error, StopIteration, KeyError, ValueError) as e:
        logger.error(f"Error extracting metadata with ffmpeg: {e}", exc_info=True)
        return 0, 0, 0

async def upload_video_with_bot_api(
    bot: telegram.Bot,
    target_chat_id: int,
    file_path: str,
    thumb_path: str | None,
    caption: str,
    duration: int,
    width: int,
    height: int
) -> int | None:
    """
     ویدیو را با استفاده از کتابخانه python-telegram-bot و سرور محلی آپلود می‌کند.
    """
    logger.info(f"[BotAPI] در حال آماده‌سازی برای آپلود در چت {target_chat_id}: {file_path}")
    try:
        
        with open(file_path, "rb") as video_file:
            
            thumb_file_obj = open(thumb_path, "rb") if thumb_path and os.path.exists(thumb_path) else None
            try:
                message = await bot.send_video(
                    chat_id=target_chat_id,
                    video=video_file,
                    thumbnail=thumb_file_obj,
                    caption=caption,
                    duration=duration,
                    width=width,
                    height=height,
                    supports_streaming=True,
                    read_timeout=120,    
                    write_timeout=600    
                )
                logger.info(f"[BotAPI] فایل با موفقیت آپلود شد. آیدی پیام: {message.message_id}")
                return message.message_id
            finally:
                
                if thumb_file_obj:
                    thumb_file_obj.close()

    except TimedOut:
        logger.error("[BotAPI] خطا: زمان آپلود به پایان رسید.")
        return None
    except NetworkError as e:
        logger.error(f"[BotAPI] خطا در شبکه هنگام آپلود: {e}")
        return None
    except Exception as e:
        logger.error(f"[BotAPI] خطای پیش‌بینی نشده در هنگام آپلود: {e}", exc_info=True)
        return None

def apply_watermark_to_video(video_path: str, settings: dict) -> str | None:
    """
    (Synchronous Version)
    Applies a watermark to the video based on user settings and returns the path to the output file.
    Returns None on error. This is a blocking function and should be run in a thread.
    """
    if not settings.get("enabled") or not settings.get("text"):
        logger.info("Watermark is disabled or has no text. Skipping.")
        return video_path  

    
    if not os.path.isfile(FONT_FILE):
        logger.error(f"Font file '{FONT_FILE}' not found! Cannot apply watermark.")
        return video_path 

    output_path = f"{os.path.splitext(video_path)[0]}_watermarked.mp4"
    
    position_map = {
        "top_left": "x=10:y=10",
        "top_right": "x=w-text_w-10:y=10",
        "bottom_left": "x=10:y=h-text_h-10",
        "bottom_right": "x=w-text_w-10:y=h-text_h-10",
    }
    position = position_map.get(settings.get("position", "top_left"), "x=10:y=10")

    escaped_text = settings['text'].replace("'", "'\\''").replace(":", "\\:").replace("\\", "\\\\")
    
    
    escaped_font_path = FONT_FILE.replace('\\', '/').replace(':', '\\:')
    
    font_size = int(settings.get("size", 32))
    font_color = settings.get("color", "white")
    border_w = int(settings.get("stroke", 2))

    video_filter = (
        f"drawtext=fontfile='{escaped_font_path}':"
        f"text='{escaped_text}':"
        f"fontcolor={font_color}:fontsize={font_size}:"
        f"{position}:"
        f"borderw={border_w}:bordercolor=black@0.6"
    )

    command = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vf', video_filter,
        '-codec:a', 'copy',
        output_path
    ]

    logger.info("Running synchronous FFmpeg watermark command...")
    logger.info(shlex.join(command))

    try:
        
        result = subprocess.run(
            command,
            capture_output=True, 
            text=True,           
            check=False          
        )

        if result.returncode != 0:
            logger.error(f"Error in FFmpeg during watermarking: {result.stderr}")
            return None 
        
        logger.info("Watermark applied successfully.")
        
        
        os.remove(video_path)
        os.rename(output_path, video_path)
        
        return video_path 

    except Exception as e:
        logger.error(f"An unexpected error occurred while running ffmpeg for watermarking: {e}", exc_info=True)
        return None

async def watermark_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """پنل تنظیمات واترمارک را نمایش می‌دهد."""
    user_id = update.effective_user.id
    settings = get_user_watermark_settings(user_id)
    
    status_emoji = "✅ (فعال)" if settings["enabled"] else "❌ (غیرفعال)"
    position_text_map = {
        "top_left": " بالا چپ",
        "top_right": " بالا راست",
        "bottom_left": " پایین چپ",
        "bottom_right": " پایین راست",
    }
    pos_text = position_text_map.get(settings["position"])
    
    text = (
        "⚙️ **پنل تنظیمات واترمارک**\n\n"
        f"▪️ وضعیت: **{status_emoji}**\n"
        f"▪️ متن: `{settings['text']}`\n"
        f"▪️ موقعیت: **{pos_text}**\n"
        f"▪️ اندازه فونت: **{settings['size']}**\n"
        f"▪️ رنگ فونت: **{settings['color']}**\n"
        f"▪️ ضخامت حاشیه (Stroke): **{settings['stroke']}**\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"تغییر وضعیت {status_emoji}", callback_data="wm_toggle")],
        [InlineKeyboardButton("ویرایش متن واترمارک 📝", callback_data="wm_set_text")],
        [
            InlineKeyboardButton(" موقعیت", callback_data="wm_noop"),
            InlineKeyboardButton("🔼", callback_data="wm_pos_top_left"),
            InlineKeyboardButton("🔼", callback_data="wm_pos_top_right"),
        ],
        [
            InlineKeyboardButton(f"{pos_text}", callback_data="wm_noop"),
            InlineKeyboardButton("🔽", callback_data="wm_pos_bottom_left"),
            InlineKeyboardButton("🔽", callback_data="wm_pos_bottom_right"),
        ],
        [
             InlineKeyboardButton("➖", callback_data="wm_size_dec"),
             InlineKeyboardButton(f"اندازه: {settings['size']}", callback_data="wm_set_size"),
             InlineKeyboardButton("➕", callback_data="wm_size_inc"),
        ],
        [
             InlineKeyboardButton("➖", callback_data="wm_stroke_dec"),
             InlineKeyboardButton(f"حاشیه: {settings['stroke']}", callback_data="wm_set_stroke"),
             InlineKeyboardButton("➕", callback_data="wm_stroke_inc"),
        ],
        [
            InlineKeyboardButton("⚪️", callback_data="wm_color_white"),
            InlineKeyboardButton("⚫️", callback_data="wm_color_black"),
            InlineKeyboardButton("🟡", callback_data="wm_color_yellow"),
            InlineKeyboardButton("🔵", callback_data="wm_color_blue"),
        ],
        [InlineKeyboardButton("بستن پنل", callback_data="wm_close")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return WATERMARK_PANEL


async def watermark_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دکمه‌های پنل واترمارک را مدیریت می‌کند."""
    query = update.callback_query
    await query.answer()
    data = query.data.replace("wm_", "")
    user_id = query.from_user.id
    settings = get_user_watermark_settings(user_id)
    
    action_taken = True
    next_state = WATERMARK_PANEL

    if data == "toggle":
        settings["enabled"] = not settings["enabled"]
    elif data.startswith("pos_"):
        settings["position"] = data.replace("pos_", "")
    elif data.endswith("_inc") or data.endswith("_dec"):
        key, operation = data.rsplit('_', 1)
        current_value = settings.get(key, 0)
        increment = 5 if key == "size" else 1
        if operation == "inc":
            settings[key] = current_value + increment
        else:
            settings[key] = max(0, current_value - increment)
    elif data.startswith("color_"):
        settings["color"] = data.replace("color_", "")
    elif data == "set_text":
        await query.message.edit_text("لطفاً متن جدید واترمارک را وارد کنید:")
        return AWAIT_WATERMARK_TEXT
    elif data == "close":
        await query.message.delete()
        return ConversationHandler.END
    elif data == "noop":
        return WATERMARK_PANEL 
    else:
        action_taken = False

    if action_taken:
        update_user_watermark_settings(user_id, settings)
        
        status_emoji = "✅ (فعال)" if settings["enabled"] else "❌ (غیرفعال)"
        position_text_map = {"top_left": " بالا چپ", "top_right": " بالا راست", "bottom_left": " پایین چپ", "bottom_right": " پایین راست"}
        pos_text = position_text_map.get(settings["position"])
        text = (f"⚙️ **پنل تنظیمات واترمارک**\n\n"
                f"▪️ وضعیت: **{status_emoji}**\n▪️ متن: `{settings['text']}`\n"
                f"▪️ موقعیت: **{pos_text}**\n▪️ اندازه فونت: **{settings['size']}**\n"
                f"▪️ رنگ فونت: **{settings['color']}**\n▪️ ضخامت حاشیه (Stroke): **{settings['stroke']}**\n")
        keyboard = [[InlineKeyboardButton(f"تغییر وضعیت {status_emoji}", callback_data="wm_toggle")],
                    [InlineKeyboardButton("ویرایش متن واترمارک 📝", callback_data="wm_set_text")],
                    [InlineKeyboardButton(" موقعیت", callback_data="wm_noop"), InlineKeyboardButton("🔼", callback_data="wm_pos_top_left"), InlineKeyboardButton("🔼", callback_data="wm_pos_top_right")],
                    [InlineKeyboardButton(f"{pos_text}", callback_data="wm_noop"), InlineKeyboardButton("🔽", callback_data="wm_pos_bottom_left"), InlineKeyboardButton("🔽", callback_data="wm_pos_bottom_right")],
                    [InlineKeyboardButton("➖", callback_data="wm_size_dec"), InlineKeyboardButton(f"اندازه: {settings['size']}", callback_data="wm_set_size"), InlineKeyboardButton("➕", callback_data="wm_size_inc")],
                    [InlineKeyboardButton("➖", callback_data="wm_stroke_dec"), InlineKeyboardButton(f"حاشیه: {settings['stroke']}", callback_data="wm_set_stroke"), InlineKeyboardButton("➕", callback_data="wm_stroke_inc")],
                    [InlineKeyboardButton("⚪️", callback_data="wm_color_white"), InlineKeyboardButton("⚫️", callback_data="wm_color_black"), InlineKeyboardButton("🟡", callback_data="wm_color_yellow"), InlineKeyboardButton("🔵", callback_data="wm_color_blue")],
                    [InlineKeyboardButton("بستن پنل", callback_data="wm_close")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    return next_state

async def await_watermark_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """متن جدید واترمارک را از کاربر دریافت و ذخیره می‌کند."""
    user_id = update.effective_user.id
    new_text = update.message.text
    
    settings = get_user_watermark_settings(user_id)
    settings["text"] = new_text
    update_user_watermark_settings(user_id, settings)
    
    await update.message.delete() 
    
    await watermark_panel_command(update, context) 
    return WATERMARK_PANEL


async def yt_dlp_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_format = query.data.split("_", 1)[1]
    info = context.user_data.get('video_info')
    if not info:
        await query.edit_message_text(text="اطلاعات منقضی شده است. لطفاً لینک را دوباره ارسال کنید.")
        return
        
    url = info.get('webpage_url')
    user_id = query.from_user.id

    
    video_info_json = json.dumps(info)

   
    download_and_upload_video_task.delay(
        chat_id=query.message.chat.id,
        url=url,
        selected_format=selected_format,
        video_info_json=video_info_json, 
        user_id=user_id
    )
    
    await query.edit_message_text("✅ درخواست شما برای دانلود ویدیو به صف اضافه شد.")
    context.user_data.pop('video_info', None)


async def set_thumbnail_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("لطفاً یک عکس برای تنظیم به عنوان تامبنیل ارسال کنید یا /cancel را بزنید.")
    return AWAIT_THUMBNAIL

async def receive_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    set_user_thumbnail(update.effective_user.id, update.message.photo[-1].file_id)
    await update.message.reply_text("✅ تامبنیل با موفقیت تنظیم شد!")
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    if 'gdl_download_path' in context.user_data:
        download_path = context.user_data['gdl_download_path']
        if os.path.exists(download_path):
            shutil.rmtree(download_path)
        
    for key in list(context.user_data.keys()):
        if key.startswith(('com_', 'mn2_', 'mc_', 'md_', 'ct_', 'cm_', 'gdl_')):
            del context.user_data[key]
            
    await update.message.reply_text("عملیات لغو شد.")
    return ConversationHandler.END



async def check_subscription(user_id: int, domain: str) -> Tuple[bool, str]:
    """
    وضعیت کامل اشتراک کاربر را بررسی می‌کند.
    """
    user_data = get_user_data(user_id)
    if user_data.get('is_admin', False):
        return True, "Admin access granted."

    sub = user_data.get('subscription', {})
    
    
    if not sub.get('is_active', False):
        return False, "Your subscription is not active. Please subscribe to use the bot."

    
    expiry_date_str = sub.get('expiry_date')
    if expiry_date_str:
        try:
            if datetime.fromisoformat(expiry_date_str) < datetime.now():
                user_data['subscription']['is_active'] = False
                update_user_data(user_id, user_data)
                return False, "Your subscription has expired. Please renew it."
        except (ValueError, TypeError):
            user_data['subscription']['is_active'] = False
            update_user_data(user_id, user_data)
            return False, "Subscription data error. Please contact support."

    
    limit = sub.get('download_limit', -1)
    if limit != -1:
        stats = user_data.get('stats', {})
        downloads_today_data = stats.get('downloads_today', {})
        today_str = str(datetime.now().date())
        
        downloads_today_count = downloads_today_data.get('count', 0) if downloads_today_data.get('date') == today_str else 0
        if downloads_today_count >= limit:
            return False, f"You have reached your daily download limit of {limit} files."

    
    all_sites_flat = [site for category_sites in ALL_SUPPORTED_SITES.values() for site in category_sites]
    if domain in all_sites_flat:
        
        if not sub.get('allowed_sites', {}).get(domain, False):
            return False, f"Your subscription does not include access to {domain}."
    
    return True, "Access granted."

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """[نسخه اصلاح شده نهایی] نقطه ورود به پنل ادمین که هم با دستور و هم با دکمه کار می‌کند."""
    user_id = update.effective_user.id
    
    chat = update.effective_chat

    if not chat:
        
        return ConversationHandler.END

    if user_id not in ADMIN_IDS:
        await chat.send_message("شما اجازه دسترسی به این بخش را ندارید.")
        return ConversationHandler.END

    keyboard = [
        ["📊 آمار", "📢 همگانی"],
        ["⚙️ مدیریت اشتراک", "📝 متن ها"],
        ["❌ خروج از پنل"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    
    if update.callback_query:
        try:
            await update.callback_query.message.delete()
        except Exception:
            pass 

    
    await chat.send_message("به پنل ادمین خوش آمدید.", reply_markup=reply_markup)
    return ADMIN_PANEL

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """آمار کلی ربات را نمایش می‌دهد."""
    db = load_user_db()
    total_users = len(db)
    today_str = str(datetime.now().date())
    
    downloads_today = 0
    active_subs = 0
    expired_subs = 0
    site_usage = {}

    for user_id, data in db.items():
        if not isinstance(data, dict): continue
        
        if data.get('stats', {}).get('downloads_today', {}).get('date') == today_str:
            downloads_today += data['stats']['downloads_today'].get('count', 0)
        
        if data.get('subscription', {}).get('is_active'):
            expiry_date_str = data['subscription'].get('expiry_date')
            if expiry_date_str:
                try:
                    if datetime.fromisoformat(expiry_date_str) > datetime.now():
                        active_subs += 1
                    else:
                        expired_subs += 1
                except (ValueError, TypeError):
                    expired_subs += 1
            else:
                active_subs += 1
        
        for site, count in data.get('stats', {}).get('site_usage', {}).items():
            site_usage[site] = site_usage.get(site, 0) + count

    top_sites = sorted(site_usage.items(), key=lambda item: item[1], reverse=True)[:3]
    top_sites_text = "\n".join([f"• {site}" for site, count in top_sites]) if top_sites else "No data recorded"

    stats_text = (
        "📊 **Bot Statistics**\n\n"
        "👥 **Users**\n"
        f"• Total Users: {total_users}\n"
        f"• Downloads (Today): {downloads_today}\n\n"
        "🌐 **Most Popular Sites**\n"
        f"{top_sites_text}\n\n"
        "💳 **Subscriptions**\n"
        f"• Active Subscriptions: {active_subs}\n"
        f"• Expired Subscriptions: {expired_subs}\n\n"
        f"@{BOT_USERNAME}"
    )
    await update.message.reply_text(stats_text, parse_mode='Markdown')
    return ADMIN_PANEL

async def broadcast_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """گزینه‌های پیام همگانی را نمایش می‌دهد."""
    keyboard = [
        [InlineKeyboardButton("Send Text Message", callback_data="bc_text")],
        [InlineKeyboardButton("Forward Message", callback_data="bc_forward")],
        [InlineKeyboardButton("Back", callback_data="admin_back")]
    ]
    await update.message.reply_text("Please select the broadcast type:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_PANEL

async def await_broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """منتظر دریافت پیام متنی برای ارسال همگانی."""
    await update.callback_query.message.edit_text("Please enter the message to send to all users:")
    return AWAIT_BROADCAST_MESSAGE

async def send_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """پیام متنی دریافت شده را برای همه کاربران ارسال می‌کند."""
    message = await update.message.reply_text("Preparing to send...")
    db = load_user_db()
    sent_count = 0
    failed_count = 0
    for user_id in db.keys():
        try:
            await context.bot.copy_message(chat_id=user_id, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
            sent_count += 1
            await asyncio.sleep(0.1)
        except Exception:
            failed_count += 1
    
    await message.edit_text(f"✅ Broadcast sent successfully to {sent_count} users.\n❌ Failed to send to {failed_count} users.")
    return ADMIN_PANEL

async def await_broadcast_forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """منتظر فوروارد یک پیام برای ارسال همگانی."""
    await update.callback_query.message.edit_text("Please forward the message you want to broadcast to everyone:")
    return AWAIT_BROADCAST_FORWARD

async def forward_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """پیام فوروارد شده را برای همه کاربران فوروارد می‌کند."""
    message = await update.message.reply_text("Preparing to forward...")
    db = load_user_db()
    sent_count = 0
    failed_count = 0
    for user_id in db.keys():
        try:
            await context.bot.forward_message(chat_id=user_id, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
            sent_count += 1
            await asyncio.sleep(0.1)
        except Exception:
            failed_count += 1
            
    await message.edit_text(f"✅ Message forwarded successfully to {sent_count} users.\n❌ Failed to forward to {failed_count} users.")
    return ADMIN_PANEL

async def ask_for_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """از ادمین، آیدی عددی کاربر مورد نظر را می‌پرسد."""
    await update.message.reply_text("Please enter the User ID (UID) to manage their subscription:")
    return AWAIT_SUB_USER_ID



async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """خروج از پنل ادمین."""
    await update.message.reply_text("You have exited the Admin Panel.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def admin_sub_operation_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    عملیات فرعی در پنل ادمین را لغو کرده و به منوی اصلی بازمی‌گردد.
    """

    context.user_data.pop('target_user_id', None)
    
    await update.message.reply_text("عملیات لغو شد. به پنل اصلی ادمین بازگشتید.")

    return await admin_command(update, context)


def main() -> None:

    if not check_dependencies(): 
        sys.exit(1)
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    

    application = (
    Application.builder()
    .token(BOT_TOKEN)
    .base_url("http://91.107.146.233:8081/bot")
    .base_file_url("http://91.107.146.233:8081/file/bot") 
    .build()
    )
    

    all_gallery_dl_sites = GALLERY_DL_SITES + GALLERY_DL_ZIP_SITES
    gallery_dl_sites_pattern = '|'.join([re.escape(site) for site in all_gallery_dl_sites])

    thumb_conv_handler = ConversationHandler(

         entry_points=[CommandHandler('thumb', set_thumbnail_command)],
         states={
             AWAIT_THUMBNAIL: [MessageHandler(filters.PHOTO, receive_thumbnail)]
         },
         fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )

    toonily_com_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex(TOONILY_COM_DOMAIN), handle_toonily_com_link)],
        states={
            COM_SELECTING_CHAPTERS: [CallbackQueryHandler(handle_chapter_selection_com, pattern="^com_")],
            COM_AWAIT_ZIP_OPTION: [CallbackQueryHandler(process_toonily_com_download, pattern="^com_zip_")],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )

    toonily_me_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('SearchToonily', start_manhwa_me_search),
            MessageHandler(filters.TEXT & filters.Regex(TOONILY_ME_DOMAIN), handle_manhwa_me_link)
        ],
        states={
            ME_AWAIT_MANHWA_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_manhwa_me_search)],
            ME_SELECTING_MANHWA: [CallbackQueryHandler(select_manhwa_me_callback, pattern="^mn2_select_")],
            ME_SELECTING_CHAPTERS: [CallbackQueryHandler(chapter_selection_me_callback, pattern="^mn2_")],
            ME_AWAIT_ZIP_OPTION: [CallbackQueryHandler(process_manhwa_me_download, pattern="^mn2_zip_")],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )

    manhwaclan_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex(MANHWACLAN_DOMAIN), handle_manhwaclan_link)],
        states={
            MC_SELECTING_CHAPTERS: [CallbackQueryHandler(chapter_selection_mc_callback, pattern="^mc_")],
            MC_AWAIT_ZIP_OPTION: [CallbackQueryHandler(process_manhwaclan_download, pattern="^mc_zip_")],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )

    mangadistrict_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex(MANGA_DISTRICT_DOMAIN), handle_mangadistrict_link)],
        states={
            MD_SELECTING_CHAPTERS: [CallbackQueryHandler(chapter_selection_md_callback, pattern="^md_")],
            MD_AWAIT_ZIP_OPTION: [CallbackQueryHandler(process_mangadistrict_download, pattern="^md_zip_")],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )
    cosplaytele_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex(COSPLAYTELE_DOMAIN), handle_cosplaytele_link)],
        states={
            CT_AWAIT_USER_CHOICE: [CallbackQueryHandler(process_cosplaytele_download, pattern="^ct_choice_")],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )
    comick_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex(COMICK_DOMAIN), handle_comick_link)],
        states={
            CM_SELECTING_CHAPTERS: [CallbackQueryHandler(chapter_selection_cm_callback, pattern="^cm_")],
            CM_AWAIT_ZIP_OPTION: [CallbackQueryHandler(process_comick_download, pattern="^cm_zip_")],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )
    gallery_dl_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex(gallery_dl_sites_pattern), handle_gallery_dl_link)],
        states={
            GALLERY_DL_AWAIT_ZIP_OPTION: [CallbackQueryHandler(process_gallery_dl_upload, pattern="^gdl_zip_")],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )


    erome_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex(EROME_DOMAIN), handle_erome_link)],
        states={
            EROME_AWAIT_CHOICE: [CallbackQueryHandler(process_erome_download, pattern="^er_choice_")],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )


    watermark_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('water', watermark_panel_command)],
        states={
            WATERMARK_PANEL: [CallbackQueryHandler(watermark_panel_callback, pattern="^wm_")],
            AWAIT_WATERMARK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, await_watermark_text)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )

    video_edit_conv_handler = ConversationHandler(
         entry_points=[MessageHandler(filters.VIDEO, handle_user_video)],
         states={
             AWAIT_VIDEO_CHOICE: [CallbackQueryHandler(process_video_edit_choice, pattern="^vid_edit_")],
         },
         fallbacks=[CommandHandler('cancel', cancel_conversation)],
         conversation_timeout=300 
    )


    admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('admin', admin_command)],
        states={
            ADMIN_PANEL: [
                MessageHandler(filters.Regex('^📊 آمار$'), show_stats),
                MessageHandler(filters.Regex('^📢 همگانی$'), broadcast_options),
                MessageHandler(filters.Regex('^⚙️ مدیریت اشتراک$'), ask_for_user_id),
                MessageHandler(filters.Regex('^📝 متن ها$'), texts_panel_command),
                MessageHandler(filters.Regex('^راهنما$'), show_help_command), # <--- [اصلاح] اضافه شد
                CallbackQueryHandler(await_broadcast_message_handler, pattern='^bc_text$'),
                CallbackQueryHandler(await_broadcast_forward_handler, pattern='^bc_forward$'),
                CallbackQueryHandler(admin_command, pattern='^admin_back$'),
            ],
            AWAIT_BROADCAST_MESSAGE: [
                CommandHandler('cancel', admin_sub_operation_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, send_broadcast_message)
            ],
            AWAIT_BROADCAST_FORWARD: [
                CommandHandler('cancel', admin_sub_operation_cancel),
                MessageHandler(filters.FORWARDED, forward_broadcast_message)
            ],
            AWAIT_SUB_USER_ID: [
                CommandHandler('cancel', admin_sub_operation_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manage_subscription)
            ],
            MANAGE_USER_SUB: [
                CommandHandler('cancel', admin_sub_operation_cancel),
                MessageHandler(filters.Regex('^📊 آمار$'), show_stats),
                MessageHandler(filters.Regex('^📢 همگانی$'), broadcast_options),
                MessageHandler(filters.Regex('^⚙️ مدیریت اشتراک$'), ask_for_user_id),
                MessageHandler(filters.Regex('^📝 متن ها$'), texts_panel_command),
                MessageHandler(filters.Regex('^راهنما$'), show_help_command), # <--- [اصلاح] اضافه شد
                CallbackQueryHandler(manage_subscription_callback, pattern='^sub_')
            ],
            TEXTS_PANEL: [
                CallbackQueryHandler(texts_panel_callback, pattern='^texts_')
            ],
            AWAIT_HELP_TEXT: [
                CommandHandler('cancel', admin_sub_operation_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, await_help_text_handler)
            ]
        },
        fallbacks=[MessageHandler(filters.Regex('^❌ خروج از پنل$'), admin_cancel), CommandHandler('cancel', admin_cancel)],
    )
    

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(thumb_conv_handler)
    application.add_handler(toonily_com_conv_handler)
    application.add_handler(toonily_me_conv_handler)
    application.add_handler(manhwaclan_conv_handler)
    application.add_handler(mangadistrict_conv_handler)
    application.add_handler(cosplaytele_conv_handler)
    application.add_handler(comick_conv_handler)
    application.add_handler(gallery_dl_conv_handler)
    application.add_handler(erome_conv_handler)
    application.add_handler(watermark_conv_handler)
    application.add_handler(video_edit_conv_handler)
    application.add_handler(admin_conv_handler)
    
    general_link_filter = (
        filters.TEXT & 
        filters.Entity("url") &
        ~filters.COMMAND & 
        ~filters.Regex(TOONILY_COM_DOMAIN) & 
        ~filters.Regex(TOONILY_ME_DOMAIN) &
        ~filters.Regex(MANHWACLAN_DOMAIN) &
        ~filters.Regex(MANGA_DISTRICT_DOMAIN) &
        ~filters.Regex(COSPLAYTELE_DOMAIN) &
        ~filters.Regex(COMICK_DOMAIN) &
        ~filters.Regex(gallery_dl_sites_pattern) &
        ~filters.Regex(PORNHUB_DOMAIN) &
        ~filters.Regex(EROME_DOMAIN) &
        ~filters.Regex(EPORNER_DOMAIN) &
        ~filters.Regex(XVIDEOS_DOMAIN)
    )
    application.add_handler(MessageHandler(general_link_filter, handle_link))
    video_sites_pattern = f"({PORNHUB_DOMAIN}|{EPORNER_DOMAIN}|{XVIDEOS_DOMAIN})"
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(video_sites_pattern), handle_pornhub_link)) 
    
    application.add_handler(CallbackQueryHandler(button_callback))

    logger.info("ربات در حال اجراست... (برای خروج Ctrl+C را بزنید)")
    application.run_polling()

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("ربات خاموش شد.")

