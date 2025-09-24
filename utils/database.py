import logging
from datetime import datetime

from sqlalchemy import select
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
            selectinload(models.User.thumbnail)
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
            # The new 'allow_thumbnail' and 'allow_watermark' fields will use their default values (True) from the model.
        )
        session.add(user)

        # Create default watermark settings for the new user
        watermark = models.WatermarkSetting(user=user, text=f"@{settings.bot_token.split(':')[0]}")
        session.add(watermark)

        await session.commit()
        
        # Re-fetch the user to ensure relationships are loaded correctly
        result = await session.execute(stmt)
        user = result.scalar_one()

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
async def set_user_thumbnail(session: AsyncSession, user_id: int, file_id: str):
    user = await get_or_create_user(session, user_id)
    if user.thumbnail:
        user.thumbnail.file_id = file_id
    else:
        new_thumbnail = models.Thumbnail(user_id=user_id, file_id=file_id)
        session.add(new_thumbnail)
    await session.commit()

async def get_user_thumbnail(session: AsyncSession, user_id: int) -> str | None:
    stmt = select(models.Thumbnail.file_id).where(models.Thumbnail.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# --- Watermark ---
async def get_user_watermark_settings(session: AsyncSession, user_id: int) -> models.WatermarkSetting:
    user = await get_or_create_user(session, user_id)
    # Ensure a watermark settings object exists if one wasn't created with the user
    if user.watermark is None:
        watermark = models.WatermarkSetting(user_id=user_id, text=f"@{settings.bot_token.split(':')[0]}")
        session.add(watermark)
        await session.commit()
        await session.refresh(user, ['watermark']) # Refresh the user to load the new relationship
    return user.watermark

async def update_user_watermark_settings(session: AsyncSession, user_id: int, new_settings: dict):
    # This function is now simpler as get_user_watermark_settings ensures the object exists
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

    # Create a copy to modify, then assign back
    new_site_usage = user.stats_site_usage.copy()
    new_site_usage[domain] = new_site_usage.get(domain, 0) + 1
    user.stats_site_usage = new_site_usage
    
    flag_modified(user, "stats_site_usage")

    await session.commit()

