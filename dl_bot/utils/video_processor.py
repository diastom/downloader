import ffmpeg
import os
import logging
import shlex
import subprocess
from typing import Tuple
from pathlib import Path

# --- Constants ---
# Define path relative to this file's location to make it more robust
FONT_FILE = str(Path(__file__).parent.parent / "Aviny.ttf")
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


def apply_watermark_to_video(video_path: str, settings: dict) -> str | None:
    """
    Applies a watermark to the video based on user settings and returns the path to the output file.
    Returns the original path if watermarking is disabled or fails.
    This is a blocking function and should be run in a thread.
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

    # Escape text for ffmpeg filter
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

    logger.info("Running FFmpeg watermark command: %s", shlex.join(command))

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error(f"Error in FFmpeg during watermarking: {result.stderr}")
            return video_path # Return original path on failure

        logger.info("Watermark applied successfully.")

        # Replace original file with watermarked one
        os.remove(video_path)
        os.rename(output_path, video_path)

        return video_path

    except Exception as e:
        logger.error(f"An unexpected error occurred while running ffmpeg for watermarking: {e}", exc_info=True)
        return video_path


def generate_thumbnail_from_video(video_path: str, output_path: str) -> bool:
    """
    Generates a thumbnail from the video file using ffmpeg.
    """
    try:
        (
            ffmpeg
            .input(video_path, ss=1) # Capture frame at 1 second
            .output(output_path, vframes=1)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.info(f"Thumbnail created successfully at {output_path}")
        return True
    except ffmpeg.Error as e:
        logger.error(f"Error generating thumbnail: {e.stderr.decode()}")
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
        logger.error(f"[ffmpeg] Error during stream copy: {e.stderr.decode()}")
        return False
