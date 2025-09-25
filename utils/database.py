import logging
from datetime import datetime

from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession

from utils import models
from config import settings
from utils.helpers import ALL_SUPPORTED_SITES

logger = logging.getLogger(__name__)

# --- User ---
async def get_or_create_user(session: AsyncSession, user_id: int, username: str | None = None) -> models.User:
    """
    Retrieves a user from the database or creates a new one if they don't exist.
    Correctly handles the new User model without 'sub_details'.
    """
    stmt = (
        select(models.User)
        .where(models.User.id == user_id)
        .options(
            selectinload(models.User.watermark),
            selectinload(models.User.thumbnails)
        )
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        logger.info(f"Creating new user profile for user_id: {user_id}")
        default_allowed_sites = {site: False for category in ALL_SUPPORTED_SITES.values() for site in category}

        user = models.User(
            id=user_id,
            username=username,
            is_admin=user_id in settings.admin_ids,
            sub_is_active=False,
            sub_download_limit=-1,
            sub_allowed_sites=default_allowed_sites,
            stats_site_usage={},
        )
        session.add(user)

        watermark = models.WatermarkSetting(user=user, text=f"@{settings.bot_token.split(':')[0]}")
        session.add(watermark)

        await touch_user_activity(session, user_id)
        await session.commit()

        result = await session.execute(stmt)
        user = result.scalar_one()
        return user

    updated = False
    if username and user.username != username:
        user.username = username
        updated = True

    if await touch_user_activity(session, user_id):
        updated = True

    if updated:
        await session.commit()

    return user

async def get_all_users(session: AsyncSession) -> list[models.User]:
    """Retrieves all users from the database."""
    stmt = select(models.User)
    result = await session.execute(stmt)
    return result.scalars().all()

async def has_feature_access(session: AsyncSession, user_id: int, feature: str) -> bool:
    """
    Checks if a user has access to a specific feature ('thumbnail' or 'watermark').
    """
    user = await get_or_create_user(session, user_id)
    if user.is_admin:
        return True

    if feature == 'thumbnail':
        return user.allow_thumbnail
    elif feature == 'watermark':
        return user.allow_watermark

    return False

# --- Thumbnail ---
async def get_user_thumbnails(session: AsyncSession, user_id: int) -> list[models.Thumbnail]:
    stmt = (
        select(models.Thumbnail)
        .where(models.Thumbnail.user_id == user_id)
        .order_by(models.Thumbnail.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def set_user_thumbnail(session: AsyncSession, user_id: int, file_id: str) -> models.Thumbnail:
    """Adds a new thumbnail for the user. Keeps compatibility with previous name."""
    user = await get_or_create_user(session, user_id)
    existing = list(user.thumbnails)
    if len(existing) >= 10:
        raise ValueError("Maximum number of thumbnails reached")

    new_thumbnail = models.Thumbnail(user_id=user_id, file_id=file_id)
    session.add(new_thumbnail)
    await session.commit()
    await session.refresh(new_thumbnail)
    return new_thumbnail


async def delete_user_thumbnail(session: AsyncSession, user_id: int, thumbnail_id: int) -> bool:
    stmt = (
        select(models.Thumbnail)
        .where(
            models.Thumbnail.user_id == user_id,
            models.Thumbnail.id == thumbnail_id,
        )
    )
    result = await session.execute(stmt)
    thumbnail = result.scalar_one_or_none()
    if not thumbnail:
        return False

    await session.delete(thumbnail)
    await session.commit()
    return True


async def get_user_thumbnail(session: AsyncSession, user_id: int) -> str | None:
    thumbnails = await get_user_thumbnails(session, user_id)
    if not thumbnails:
        return None
    return thumbnails[0].file_id


async def get_user_thumbnail_by_id(session: AsyncSession, user_id: int, thumbnail_id: int) -> models.Thumbnail | None:
    stmt = (
        select(models.Thumbnail)
        .where(
            models.Thumbnail.user_id == user_id,
            models.Thumbnail.id == thumbnail_id,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# --- Watermark ---
async def get_user_watermark_settings(session: AsyncSession, user_id: int) -> models.WatermarkSetting:
    user = await get_or_create_user(session, user_id)
    if user.watermark is None:
        watermark = models.WatermarkSetting(user_id=user_id, text=f"@{settings.bot_token.split(':')[0]}")
        session.add(watermark)
        await session.commit()
        await session.refresh(user, ['watermark'])
    return user.watermark

async def update_user_watermark_settings(session: AsyncSession, user_id: int, new_settings: dict):
    watermark = await get_user_watermark_settings(session, user_id)
    for key, value in new_settings.items():
        if hasattr(watermark, key):
            setattr(watermark, key, value)
    await session.commit()


# --- Bot Texts ---
async def get_text(session: AsyncSession, key: str, default: str = "") -> str:
    stmt = select(models.BotText.value).where(models.BotText.key == key)
    result = await session.execute(stmt)
    value = result.scalar_one_or_none()
    return value or default

async def set_text(session: AsyncSession, key: str, value: str):
    stmt = select(models.BotText).where(models.BotText.key == key)
    result = await session.execute(stmt)
    bot_text = result.scalar_one_or_none()
    if bot_text:
        bot_text.value = value
    else:
        bot_text = models.BotText(key=key, value=value)
        session.add(bot_text)
    await session.commit()

# --- Stats ---
async def log_download_activity(session: AsyncSession, user_id: int, domain: str):
    user = await get_or_create_user(session, user_id)

    if user.stats_site_usage is None:
        user.stats_site_usage = {}

    new_site_usage = user.stats_site_usage.copy()
    new_site_usage[domain] = new_site_usage.get(domain, 0) + 1
    user.stats_site_usage = new_site_usage

    flag_modified(user, "stats_site_usage")
    await touch_user_activity(session, user_id)
    await session.commit()


async def touch_user_activity(session: AsyncSession, user_id: int) -> bool:
    """Creates or updates the activity record for a user."""
    now = datetime.utcnow()
    stmt = select(models.UserActivity).where(models.UserActivity.user_id == user_id)
    result = await session.execute(stmt)
    activity = result.scalar_one_or_none()

    if activity is None:
        session.add(models.UserActivity(user_id=user_id, first_seen=now, last_seen=now))
        return True

    activity.last_seen = now
    return True


async def record_download_event(
    session: AsyncSession,
    user_id: int,
    domain: str,
    size_bytes: int,
    task_type: str = "download",
):
    """Persists a download or encode event with its size for analytics."""
    await get_or_create_user(session, user_id)

    log_entry = models.DownloadLog(
        user_id=user_id,
        domain=domain,
        task_type=task_type,
        size_bytes=max(0, int(size_bytes)),
    )
    session.add(log_entry)
    await touch_user_activity(session, user_id)
    await session.commit()


async def get_bot_stats(session: AsyncSession) -> dict:
    """Aggregates key metrics for the admin statistics panel."""
    now = datetime.utcnow()
    start_of_day = datetime(now.year, now.month, now.day)

    total_users = await session.scalar(select(func.count()).select_from(models.User)) or 0
    users_today = await session.scalar(
        select(func.count()).select_from(models.UserActivity).where(models.UserActivity.first_seen >= start_of_day)
    ) or 0

    active_subscriptions = await session.scalar(
        select(func.count()).select_from(models.User).where(models.User.sub_is_active.is_(True))
    ) or 0
    expired_subscriptions = await session.scalar(
        select(func.count())
        .select_from(models.User)
        .where(
            models.User.sub_is_active.is_(False),
            models.User.sub_expiry_date.isnot(None),
            models.User.sub_expiry_date < now,
        )
    ) or 0

    total_downloads = await session.scalar(select(func.count()).select_from(models.DownloadLog)) or 0
    downloads_today = await session.scalar(
        select(func.count())
        .select_from(models.DownloadLog)
        .where(models.DownloadLog.created_at >= start_of_day)
    ) or 0

    total_size_bytes = await session.scalar(
        select(func.coalesce(func.sum(models.DownloadLog.size_bytes), 0))
    ) or 0
    size_today_bytes = await session.scalar(
        select(func.coalesce(func.sum(models.DownloadLog.size_bytes), 0))
        .where(models.DownloadLog.created_at >= start_of_day)
    ) or 0

    popular_sites_stmt = (
        select(models.DownloadLog.domain, func.count().label("count"))
        .where(models.DownloadLog.task_type == "download")
        .group_by(models.DownloadLog.domain)
        .order_by(desc("count"))
        .limit(5)
    )
    popular_sites_result = await session.execute(popular_sites_stmt)
    popular_sites = [row[0] for row in popular_sites_result if row[0]]

    return {
        "total_users": int(total_users),
        "users_today": int(users_today),
        "active_subscriptions": int(active_subscriptions),
        "expired_subscriptions": int(expired_subscriptions),
        "total_downloads": int(total_downloads),
        "downloads_today": int(downloads_today),
        "total_size_bytes": int(total_size_bytes),
        "size_today_bytes": int(size_today_bytes),
        "popular_sites": popular_sites,
    }

# --- Public Archive ---
async def get_public_archive_item(session: AsyncSession, url_hash: str) -> models.PublicArchive | None:
    """
    Retrieves a public archive item by its URL hash.
    """
    stmt = select(models.PublicArchive).where(models.PublicArchive.url_hash == url_hash)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def add_public_archive_item(session: AsyncSession, url: str, message_id: int, channel_id: int):
    """
    Adds a new item to the public archive.
    """
    url_hash = models.PublicArchive.create_hash(url)
    new_item = models.PublicArchive(
        url_hash=url_hash,
        message_id=message_id,
        channel_id=channel_id
    )
    session.add(new_item)
    await session.commit()