import logging
from datetime import datetime

from sqlalchemy import func, select
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
            selectinload(models.User.watermarks),
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
            sub_encode_limit=-1,
            stats_site_usage={},
        )
        session.add(user)

        watermark = models.WatermarkSetting(
            user=user,
            text=f"@{settings.bot_token.split(':')[0]}",
            display_name="پیش‌فرض",
        )
        session.add(watermark)

        await session.commit()

        result = await session.execute(stmt)
        user = result.scalar_one()

    updated = False

    if username and user.username != username:
        user.username = username
        updated = True

    if getattr(user, "sub_encode_limit", None) is None:
        user.sub_encode_limit = -1
        updated = True

    if updated:
        await session.commit()

    return user

async def get_user_daily_task_count(
    session: AsyncSession,
    user_id: int,
    task_type: str | None = None,
) -> int:
    """Returns the number of tasks the user has started today."""
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    stmt = (
        select(func.count(models.TaskUsage.id))
        .where(
            models.TaskUsage.user_id == user_id,
            models.TaskUsage.created_at >= today_start,
        )
    )
    if task_type:
        stmt = stmt.where(models.TaskUsage.task_type == task_type)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() or 0


async def can_user_start_task(
    session: AsyncSession,
    user_id: int,
    task_type: str = "download",
    tasks_needed: int = 1,
) -> tuple[bool, int, int]:
    """
    Checks whether the user still has daily task quota remaining.

    Returns a tuple of (allowed, limit, used_today).
    """
    user = await get_or_create_user(session, user_id)
    limit_attr = "sub_encode_limit" if task_type == "encode" else "sub_download_limit"
    user_limit_value = getattr(user, limit_attr, 0)
    tasks_today = await get_user_daily_task_count(session, user_id, task_type)

    if user_limit_value == -1:
        return True, -1, tasks_today

    limit = user_limit_value or 0

    return tasks_today + tasks_needed <= limit, limit, tasks_today


async def record_task_usage(
    session: AsyncSession,
    user_id: int,
    task_type: str,
    commit: bool = True,
) -> models.TaskUsage:
    """Records a generic task usage entry for daily limit tracking."""
    usage = models.TaskUsage(
        user_id=user_id,
        task_type=task_type,
        created_at=datetime.utcnow(),
    )
    session.add(usage)

    if commit:
        await session.commit()
        await session.refresh(usage)

    return usage


def format_task_limit_message(task_type: str, limit: int, used_today: int) -> str:
    """Returns a localized message explaining the daily task limit."""
    task_label = {
        "encode": "انکد",
        "download": "دانلود",
    }.get(task_type, task_type)

    return (
        f"سقف استفاده روزانه شما برای {task_label} به پایان رسیده است.\n"
        f"حداکثر تسک {task_label} در روز: {limit}\n"
        f"تسک‌های {task_label} انجام‌شده امروز: {used_today}\n"
        "لطفاً فردا دوباره تلاش کنید."
    )

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


async def set_user_thumbnail(
    session: AsyncSession,
    user_id: int,
    file_id: str,
    display_name: str | None = None,
) -> models.Thumbnail:
    """Adds a new thumbnail for the user with an optional display name."""
    user = await get_or_create_user(session, user_id)
    existing = list(user.thumbnails)
    if len(existing) >= 50:
        raise ValueError("Maximum number of thumbnails reached")

    new_thumbnail = models.Thumbnail(user_id=user_id, file_id=file_id, display_name=display_name)
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
async def get_user_watermarks(session: AsyncSession, user_id: int) -> list[models.WatermarkSetting]:
    """Returns all watermark profiles for the user, creating a default one if missing."""
    await get_or_create_user(session, user_id)
    stmt = (
        select(models.WatermarkSetting)
        .where(models.WatermarkSetting.user_id == user_id)
        .order_by(models.WatermarkSetting.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_user_watermark_by_id(
    session: AsyncSession,
    user_id: int,
    watermark_id: int,
) -> models.WatermarkSetting | None:
    stmt = (
        select(models.WatermarkSetting)
        .where(
            models.WatermarkSetting.user_id == user_id,
            models.WatermarkSetting.id == watermark_id,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_user_watermark(
    session: AsyncSession,
    user_id: int,
    text: str,
    display_name: str | None = None,
) -> models.WatermarkSetting:
    watermarks = await get_user_watermarks(session, user_id)
    if len(watermarks) >= 50:
        raise ValueError("Maximum number of watermarks reached")

    watermark = models.WatermarkSetting(
        user_id=user_id,
        text=text or f"@{settings.bot_token.split(':')[0]}",
        display_name=display_name,
    )
    session.add(watermark)
    await session.commit()
    await session.refresh(watermark)
    return watermark


async def update_user_watermark(
    session: AsyncSession,
    user_id: int,
    watermark_id: int,
    updates: dict,
) -> models.WatermarkSetting | None:
    watermark = await get_user_watermark_by_id(session, user_id, watermark_id)
    if not watermark:
        return None

    for key, value in updates.items():
        if hasattr(watermark, key):
            setattr(watermark, key, value)

    await session.commit()
    await session.refresh(watermark)
    return watermark


async def delete_user_watermark(session: AsyncSession, user_id: int, watermark_id: int) -> bool:
    watermark = await get_user_watermark_by_id(session, user_id, watermark_id)
    if not watermark:
        return False

    await session.delete(watermark)
    await session.commit()
    return True


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

def _update_user_site_usage(user: models.User, domain: str) -> None:
    if user.stats_site_usage is None:
        user.stats_site_usage = {}

    new_site_usage = user.stats_site_usage.copy()
    new_site_usage[domain] = new_site_usage.get(domain, 0) + 1
    user.stats_site_usage = new_site_usage
    flag_modified(user, "stats_site_usage")


async def record_download_event(
    session: AsyncSession,
    user_id: int,
    domain: str,
    bytes_downloaded: int,
) -> models.DownloadRecord:
    """Logs a completed download event for analytics purposes."""
    user = await get_or_create_user(session, user_id)
    _update_user_site_usage(user, domain)

    record = models.DownloadRecord(
        user_id=user_id,
        domain=domain,
        bytes_downloaded=max(0, bytes_downloaded),
        created_at=datetime.utcnow(),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def get_bot_statistics(session: AsyncSession) -> dict:
    """Aggregates bot-wide statistics for the admin dashboard."""
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)

    total_users = await session.scalar(select(func.count(models.User.id))) or 0
    users_today = (
        await session.scalar(
            select(func.count(models.User.id)).where(models.User.created_at >= today_start)
        )
        or 0
    )

    active_subs = (
        await session.scalar(
            select(func.count(models.User.id)).where(
                models.User.sub_is_active.is_(True),
                (models.User.sub_expiry_date.is_(None)) | (models.User.sub_expiry_date >= now),
            )
        )
        or 0
    )

    expired_subs = (
        await session.scalar(
            select(func.count(models.User.id)).where(
                models.User.sub_expiry_date.is_not(None),
                models.User.sub_expiry_date < now,
            )
        )
        or 0
    )

    total_downloads = (
        await session.scalar(select(func.count(models.DownloadRecord.id)))
    ) or 0
    downloads_today = (
        await session.scalar(
            select(func.count(models.DownloadRecord.id)).where(
                models.DownloadRecord.created_at >= today_start
            )
        )
    ) or 0

    total_bytes = (
        await session.scalar(
            select(func.coalesce(func.sum(models.DownloadRecord.bytes_downloaded), 0))
        )
    ) or 0
    today_bytes = (
        await session.scalar(
            select(func.coalesce(func.sum(models.DownloadRecord.bytes_downloaded), 0)).where(
                models.DownloadRecord.created_at >= today_start
            )
        )
    ) or 0

    top_sites_stmt = (
        select(
            models.DownloadRecord.domain,
            func.count(models.DownloadRecord.id).label("downloads"),
        )
        .group_by(models.DownloadRecord.domain)
        .order_by(func.count(models.DownloadRecord.id).desc())
        .limit(3)
    )
    top_sites_result = await session.execute(top_sites_stmt)
    top_sites = [row.domain for row in top_sites_result.all()]

    return {
        "total_users": total_users,
        "users_today": users_today,
        "active_subscriptions": active_subs,
        "expired_subscriptions": expired_subs,
        "total_downloads": total_downloads,
        "downloads_today": downloads_today,
        "total_bytes": total_bytes,
        "today_bytes": today_bytes,
        "top_sites": top_sites,
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