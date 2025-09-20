import json
from datetime import datetime
from ..config import settings

# --- Database File Paths ---
USER_DB_FILE = "dl_bot/data/BotData.json"
THUMBNAIL_DB = "dl_bot/data/Thumb.json"
WATERMARK_DB = "dl_bot/data/WatermarkSettings.json"
TEXTS_DB_FILE = "dl_bot/data/texts.json"
VIDEO_CACHE_DB = "dl_bot/data/VideoCache.json"

# A simple dictionary to hold all supported sites for initializing user profiles
# This should ideally be in a more central config, but keeping it here for now.
ALL_SUPPORTED_SITES = {
    "Manhwa/Webtoon": ["toonily.com", "toonily.me", "manhwaclan.com", "mangadistrict.com", "comick.io"],
    "Gallery/Hentai": ["rule34.xyz", "coomer.st", "aryion.com", "kemono.cr", "tapas.io", "tsumino.com", "danbooru.donmai.us", "e621.net", "mangadex.org", "e-hentai.org"],
    "Album": ["erome.com"],
    "Cosplay": ["cosplaytele.com"],
    "Video": ["pornhub.com", "eporner.com"]
}

# --- Generic DB Functions ---
def _load_json(filepath: str, default=None):
    """Loads a JSON file and returns its content, or a default value on error."""
    if default is None:
        default = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def _save_json(filepath: str, data: dict):
    """Saves a dictionary to a JSON file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- Thumbnail DB ---
def get_user_thumbnail(user_id: int) -> str | None:
    db = _load_json(THUMBNAIL_DB)
    return db.get(str(user_id))

def set_user_thumbnail(user_id: int, file_id: str):
    db = _load_json(THUMBNAIL_DB)
    db[str(user_id)] = file_id
    _save_json(THUMBNAIL_DB, db)

def delete_user_thumbnail(user_id: int) -> bool:
    db = _load_json(THUMBNAIL_DB)
    if str(user_id) in db:
        del db[str(user_id)]
        _save_json(THUMBNAIL_DB, db)
        return True
    return False

# --- User Data DB (BotData.json) ---
def get_user_data(user_id: int) -> dict:
    """Retrieves user data, creating a default profile if one doesn't exist."""
    db = _load_json(USER_DB_FILE)
    user_id_str = str(user_id)

    if user_id_str not in db:
        db[user_id_str] = {
            "username": "",
            "is_admin": user_id in settings.admin_ids,
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
        _save_json(USER_DB_FILE, db)

    return db[user_id_str]

def update_user_data(user_id: int, data: dict):
    """Updates the data for a specific user."""
    db = _load_json(USER_DB_FILE)
    db[str(user_id)] = data
    _save_json(USER_DB_FILE, db)

def get_all_users() -> dict:
    """Loads the entire user database."""
    return _load_json(USER_DB_FILE)

def log_download_activity(user_id: int, site_domain: str):
    """Logs a user's download activity for statistics."""
    user_data = get_user_data(user_id)
    today_str = str(datetime.now().date())

    # Reset daily download count if the date has changed
    if user_data['stats']['downloads_today'].get('date') != today_str:
        user_data['stats']['downloads_today'] = {"date": today_str, "count": 0}

    user_data['stats']['downloads_today']['count'] += 1
    user_data['stats']['site_usage'][site_domain] = user_data['stats']['site_usage'].get(site_domain, 0) + 1

    update_user_data(user_id, user_data)

# --- Texts DB ---
def get_texts() -> dict:
    """Loads the editable texts database."""
    return _load_json(TEXTS_DB_FILE, default={"help_text": "Default help text. Admin can change this."})

def save_texts(data: dict):
    """Saves the editable texts database."""
    _save_json(TEXTS_DB_FILE, data)

# --- Video Cache DB ---
def add_to_video_cache(url: str, format_id: str, message_id: int):
    """Adds a video with a specific format to the cache."""
    cache = _load_json(VIDEO_CACHE_DB)
    if url not in cache:
        cache[url] = {}
    cache[url][format_id] = message_id
    _save_json(VIDEO_CACHE_DB, cache)

def get_from_video_cache(url: str, format_id: str) -> int | None:
    """Looks up a video with a specific format in the cache."""
    cache = _load_json(VIDEO_CACHE_DB)
    return cache.get(url, {}).get(format_id)

# --- Watermark DB ---
def get_user_watermark_settings(user_id: int) -> dict:
    """Retrieves watermark settings for a user, returning defaults if not set."""
    db = _load_json(WATERMARK_DB)
    user_id_str = str(user_id)

    defaults = {
        "enabled": False,
        "text": f"@{settings.bot_token.split(':')[0]}", # A safe way to get bot username-like ID
        "position": "top_left",
        "size": 32,
        "color": "white",
        "stroke": 2,
    }

    if user_id_str in db:
        user_settings = db[user_id_str]
        # Ensure all keys from defaults exist
        for key, value in defaults.items():
            user_settings.setdefault(key, value)
        return user_settings
    else:
        return defaults

def update_user_watermark_settings(user_id: int, new_settings: dict):
    """Updates watermark settings for a user."""
    db = _load_json(WATERMARK_DB)
    db[str(user_id)] = new_settings
    _save_json(WATERMARK_DB, db)
