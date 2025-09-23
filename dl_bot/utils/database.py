import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models
from ..config import settings
from .helpers import ALL_SUPPORTED_SITES

logger = logging.getLogger(__name__)

# --- User ---
async def get_or_create_user(session: AsyncSession, user_id: int, username: str | None = None) -> models.User:
    """
    Retrieves a user from the database or creates a new one if they don't exist.
    """
    # Try to get the user
    stmt = select(models.User).where(models.User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        logger.info(f"Creating new user profile for user_id: {user_id}")
        # Create default settings for a new user
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

        # Also create their default watermark settings
        watermark = models.WatermarkSetting(user=user, text=f"@{settings.bot_token.split(':')[0]}")
        session.add(watermark)

        await session.commit()
        await session.refresh(user)

    # Update username if it has changed
    if username and user.username != username:
        user.username = username
        await session.commit()

    return user

async def get_all_users(session: AsyncSession) -> list[models.User]:
    """Retrieves all users from the database."""
    stmt = select(models.User)
    result = await session.execute(stmt)
    return result.scalars().all()


# --- Thumbnail ---
async def set_user_thumbnail(session: AsyncSession, user_id: int, file_id: str):
    user = await get_or_create_user(session, user_id)
    if user.thumbnail:
        user.thumbnail.file_id = file_id
    else:
        user.thumbnail = models.Thumbnail(file_id=file_id)
    await session.commit()

async def get_user_thumbnail(session: AsyncSession, user_id: int) -> str | None:
    stmt = select(models.Thumbnail.file_id).where(models.Thumbnail.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# --- Watermark ---
async def get_user_watermark_settings(session: AsyncSession, user_id: int) -> models.WatermarkSetting:
    user = await get_or_create_user(session, user_id)
    # The relationship ensures the watermark settings are loaded with the user
    # and created if they don't exist via get_or_create_user
    return user.watermark

async def update_user_watermark_settings(session: AsyncSession, user_id: int, new_settings: dict):
    stmt = select(models.WatermarkSetting).where(models.WatermarkSetting.user_id == user_id)
    result = await session.execute(stmt)
    watermark = result.scalar_one()

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

    # Update site usage stats
    new_site_usage = user.stats_site_usage.copy() if user.stats_site_usage else {}
    new_site_usage[domain] = new_site_usage.get(domain, 0) + 1
    user.stats_site_usage = new_site_usage # Must re-assign for SQLAlchemy to detect the change

    # This function now only handles the site usage. Daily download count can be handled
    # by a separate system or a more complex query if needed.
    # For simplicity, we'll omit the daily counter from the DB model for now.

    await session.commit()
