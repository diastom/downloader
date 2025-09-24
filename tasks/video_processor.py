import logging
import os
import ffmpeg

logger = logging.getLogger(__name__)

def repair_video(initial_path: str, repaired_path: str) -> bool:
    """Repairs the video file by copying streams to a new container."""
    logger.info("Starting video stream copy/repair...")
    try:
        (
            ffmpeg.input(initial_path)
            .output(repaired_path, c='copy', loglevel='error')
            .run(overwrite_output=True)
        )
        return True
    except ffmpeg.Error as e:
        logger.error(f"FFmpeg error during stream copy: {e.stderr.decode()}")
        return False

def get_video_metadata(file_path: str) -> tuple[int, int, int]:
    """Extracts duration, width, and height from a video file."""
    try:
        logger.info(f"Extracting metadata from: {file_path}")
        probe = ffmpeg.probe(file_path)
        video_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
        if not video_stream:
            raise ValueError("No video stream found")
            
        duration = int(float(probe['format'].get('duration', 0)))
        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))
        logger.info(f"Metadata extracted: {duration}s, {width}x{height}")
        return duration, width, height
    except (ffmpeg.Error, StopIteration, KeyError, ValueError) as e:
        logger.error(f"Error extracting metadata: {e}")
        return 0, 0, 0

def generate_thumbnail_from_video(video_path: str, output_path: str) -> bool:
    """
    Generates a thumbnail from the middle of the video.
    """
    logger.info(f"Attempting to generate thumbnail for {video_path}")
    try:
        duration, _, _ = get_video_metadata(video_path)
        if duration == 0:
            logger.warning("Video duration is 0, cannot generate thumbnail.")
            return False
            
        # Seek to the middle of the video
        seek_time = duration // 2
        
        (
            ffmpeg
            .input(video_path, ss=seek_time)
            .output(output_path, vframes=1)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.info(f"Thumbnail successfully generated at {output_path}")
        return True
    except ffmpeg.Error as e:
        logger.error(f"FFmpeg error during thumbnail generation: {e.stderr.decode()}")
        return False
