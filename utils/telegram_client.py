import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import CreateChannelRequest, EditAdminRequest
from telethon.tl.types import ChatAdminRights, PeerChannel
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from utils import database

logger = logging.getLogger(__name__)


async def get_or_create_personal_archive(session: AsyncSession, user_id: int, bot_username: str) -> int | None:
    """
    Checks for a user's personal archive channel. If it doesn't exist,
    it creates a new private channel using the configured session string.
    """
    user = await database.get_or_create_user(session, user_id)
    if user.personal_archive_id:
        logger.info(f"[Archive] Personal channel for user {user_id} already exists: {user.personal_archive_id}")
        return user.personal_archive_id

    logger.info(f"[Archive] Creating personal archive channel for user {user_id}...")

    # --- CHANGE ---
    # Simplified to always use the session string from settings.
    client = TelegramClient(StringSession(settings.session_string), settings.api_id, settings.api_hash)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("[Telethon] CRITICAL: The session string is invalid or has expired. Please generate a new one.")
            return None

        result = await client(CreateChannelRequest(
            title=f"Archive for {user_id}",
            about=f"Personal media archive for @{bot_username}",
            megagroup=False
        ))

        new_channel_id = result.chats[0].id
        full_channel_id = int(f"-100{new_channel_id}")

        channel_entity = await client.get_entity(PeerChannel(new_channel_id))
        bot_entity = await client.get_entity(bot_username)

        admin_rights = ChatAdminRights(
            post_messages=True, edit_messages=True, delete_messages=True,
            invite_users=True, change_info=True, pin_messages=True,
            add_admins=False, ban_users=True, manage_call=True, anonymous=False, other=True
        )
        await client(EditAdminRequest(channel=channel_entity, user_id=bot_entity, admin_rights=admin_rights, rank='bot'))

        user.personal_archive_id = full_channel_id
        await session.commit()

        logger.info(f"[Archive] Successfully created channel {full_channel_id} for user {user_id}.")
        return full_channel_id

    except FloodWaitError as e:
        logger.error(f"[Archive] Flood wait error: Waiting for {e.seconds} seconds.")
        await asyncio.sleep(e.seconds)
        return None
    except Exception as e:
        logger.error(f"[Archive] Error creating personal channel for user {user_id}: {e}", exc_info=True)
        return None
    finally:
        if client.is_connected():
            await client.disconnect()
