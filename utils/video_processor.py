import ffmpeg
import io
import os
import logging
import shlex
import subprocess
from typing import Tuple
from pathlib import Path

from PIL import Image, ImageOps

from utils.models import WatermarkSetting # Import the model

# --- Constants ---
FONT_FILE = str(Path(__file__).parent.parent / "Aviny.ttf")
THUMBNAIL_MAX_DIMENSION = 320
THUMBNAIL_MAX_FILE_SIZE = 200 * 1024  # 200 KB as required by Telegram
logger = logging.getLogger(__name__)


def get_video_metadata(file_path: str) -> Tuple[int, int, int]:
    """
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


def apply_watermark_to_video(
    input_path: str,
    output_path: str,
    settings: WatermarkSetting
) -> bool:
    """
    Applies a watermark to a video using ffmpeg-python.
    This is a blocking function and should be run in a thread.
    """
    if not settings.enabled or not settings.text:
        logger.info("Watermark is disabled or has no text. Skipping.")
        return False

    if not os.path.isfile(FONT_FILE):
        logger.error(f"Font file '{FONT_FILE}' not found! Cannot apply watermark.")
        return False

    position_map = {
        "top_left": "x=10:y=10",
        "top_right": "x=w-text_w-10:y=10",
        "bottom_left": "x=10:y=h-text_h-10",
        "bottom_right": "x=w-text_w-10:y=h-text_h-10",
    }
    position = position_map.get(settings.position, "top_left")

    try:
        logger.info(f"Applying watermark to {input_path}...")
        (
            ffmpeg
            .input(input_path)
            .output(
                output_path,
                vf=f"drawtext=fontfile='{FONT_FILE}':text='{settings.text}':fontcolor={settings.color}:fontsize={settings.size}:{position}:borderw={settings.stroke}:bordercolor=black@0.6",
                **{'c:v': 'libx264', 'preset': 'fast', 'crf': 25, 'c:a': 'copy'}
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.info(f"Watermark applied successfully to {output_path}")
        return True
    except ffmpeg.Error as e:
        logger.error(f"Error applying watermark: {e.stderr.decode()}", exc_info=True)
        return False


def generate_thumbnail_from_video(video_path: str, output_path: str) -> bool:
    """
    Generates a thumbnail from the video file using ffmpeg.
    """
    try:
        (
            ffmpeg
            .input(video_path, ss=1)
            .output(output_path, vframes=1)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.info(f"Thumbnail created successfully at {output_path}")
        return True
    except ffmpeg.Error as e:
        logger.error(f"Error generating thumbnail: {e.stderr.decode()}")
        return False


def prepare_thumbnail_image(image_path: str | Path) -> bool:
    """Ensure a thumbnail image complies with Telegram's requirements.

    Telegram only accepts JPEG thumbnails that are at most 320x320 pixels and
    smaller than 200 KB. This helper converts the downloaded image to JPEG,
    keeps the aspect ratio, resizes it to fit within the allowed dimensions,
    and progressively lowers the quality until the size requirement is met.

    Args:
        image_path: The path to the downloaded image file.

    Returns:
        bool: ``True`` if the image is within the allowed limits after
        processing, ``False`` otherwise.
    """

    path = Path(image_path)
    if not path.exists():
        logger.warning(f"Thumbnail path does not exist: {path}")
        return False

    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB":
                img = img.convert("RGB")

            img.thumbnail((THUMBNAIL_MAX_DIMENSION, THUMBNAIL_MAX_DIMENSION), Image.LANCZOS)

            buffer = io.BytesIO()
            quality = 90
            min_quality = 25
            success = False

            while quality >= min_quality:
                buffer.seek(0)
                buffer.truncate(0)
                img.save(buffer, format="JPEG", optimize=True, quality=quality)
                if buffer.tell() <= THUMBNAIL_MAX_FILE_SIZE:
                    success = True
                    break
                quality -= 5

            if not success:
                buffer.seek(0)
                buffer.truncate(0)
                img.save(buffer, format="JPEG", optimize=True, quality=min_quality)

        path.write_bytes(buffer.getvalue())
        final_size = path.stat().st_size

        if final_size > THUMBNAIL_MAX_FILE_SIZE:
            logger.warning(
                "Thumbnail at %s still exceeds %d bytes after compression (current size: %d bytes)",
                path,
                THUMBNAIL_MAX_FILE_SIZE,
                final_size,
            )
            return False

        logger.info("Thumbnail at %s prepared successfully (%d bytes).", path, final_size)
        return True

    except Exception as error:  # pylint: disable=broad-except
        logger.error("Failed to prepare thumbnail %s: %s", path, error, exc_info=True)
        return False

def repair_video(initial_path: str, repaired_path: str) -> bool:
    """
    Repairs a video file by copying streams with ffmpeg. Useful for fixing downloads.
    """
    logger.info("[ffmpeg] Repairing and copying video streams...")
    try:
        ffmpeg.input(initial_path).output(repaired_path, c='copy', loglevel='error').run(overwrite_output=True)
        return True
    except ffmpeg.Error as e:
        error_message = e.stderr.decode() if e.stderr else "No stderr output"
        logger.error(f"[ffmpeg] Error during stream copy: {error_message}")
        return False

def transcode_video(input_path: str, output_path: str, height: int) -> bool:
    """
    Transcodes a video to a specific height, preserving aspect ratio.
    """
    logger.info(f"[ffmpeg] Transcoding video to {height}p...")
    try:
        (
            ffmpeg
            .input(input_path)
            .output(output_path, vf=f'scale=-2:{height}', preset='fast', crf=24)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.info(f"Video successfully transcoded to {output_path}")
        return True
    except ffmpeg.Error as e:
        logger.error(f"Error during transcoding: {e.stderr.decode()}", exc_info=True)
        return False