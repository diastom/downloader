import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from utils import video_processor

logger = logging.getLogger(__name__)

# TODO: This function is the aiogram replacement for the original upload_video_with_bot_api.
# It's designed to be used within the new aiogram-based application.

async def upload_video(
    bot: Bot,
    target_chat_id: int,
    file_path: str,
    thumb_path: str | None,
    caption: str,
    duration: int,
    width: int,
    height: int,
    supports_streaming: bool = True
) -> int | None:
    """
    Uploads a video to Telegram using the aiogram Bot instance.

    :param bot: The aiogram Bot instance.
    :param target_chat_id: The chat ID to upload the video to.
    :param file_path: The local path to the video file.
    :param thumb_path: The local path to the thumbnail image.
    :param caption: The caption for the video.
    :param duration: The duration of the video in seconds.
    :param width: The width of the video in pixels.
    :param height: The height of the video in pixels.
    :param supports_streaming: Whether the video supports streaming.
    :return: The message ID of the uploaded video, or None on failure.
    """
    logger.info(f"[BotAPI] Preparing to upload video to chat {target_chat_id}: {file_path}")
    try:
        video_file = FSInputFile(file_path)
        thumb_file = None

        if thumb_path and os.path.exists(thumb_path):
            prepared = await asyncio.to_thread(
                video_processor.prepare_thumbnail_image,
                Path(thumb_path),
            )
            if prepared:
                thumb_file = FSInputFile(thumb_path)
            else:
                logger.warning("Thumbnail %s could not be prepared within Telegram limits.", thumb_path)

        message = await bot.send_video(
            chat_id=target_chat_id,
            video=video_file,
            thumbnail=thumb_file,
            caption=caption,
            duration=duration,
            width=width,
            height=height,
            supports_streaming=supports_streaming
        )
        logger.info(f"[BotAPI] File uploaded successfully. Message ID: {message.message_id}")
        return message.message_id

    except Exception as e:
        # Catching a broad exception class as aiogram can raise various network/API errors
        logger.error(f"[BotAPI] An unexpected error occurred during upload: {e}", exc_info=True)
        return None
