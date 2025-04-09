from twelvelabs import models
from typing import List, Union, Optional
import os
import subprocess
import threading
import tempfile
import logging


def download_clips(search_data: models.SearchResult, num_clips: int) -> List[str]:
    """
    Download video clips from search results using ffmpeg.

    Args:
        search_data: SearchResult object from the twelvelabs API
        num_clips: Maximum number of clips to download

    Returns:
        List of paths to downloaded video clips
    """
    # Extract SearchData objects from the search results
    clips_data = []

    # Handle both SearchData and GroupByVideoSearchData in the results
    for item in search_data.data:
        if isinstance(item, models.SearchData):
            clips_data.append(item)
        elif isinstance(item, models.GroupByVideoSearchData) and item.clips:
            clips_data.extend(item.clips)

    # Limit to the requested number of clips
    clips_data = clips_data[:num_clips]

    if not clips_data:
        print("No clips found in search results")
        return []

    # Create output directory
    output_dir = os.path.join(tempfile.gettempdir(), "twelvelabs_clips")
    os.makedirs(output_dir, exist_ok=True)

    downloaded_clips = []

    # Download each clip
    for i, clip in enumerate(clips_data):
        # Get video info using the index_id and video_id
        index_id = search_data.pool.index_id
        video_id = clip.video_id

        # Get video URL (this would typically come from an API call)
        video_url = get_video_url(index_id, video_id)
        if not video_url:
            print(f"[ERROR] Could not get URL for video ID: {video_id}")
            continue

        # Create output filename
        filename = f"clip_{i + 1}_{clip.video_id}_{clip.start:.2f}_{clip.end:.2f}.mp4"
        output_path = os.path.join(output_dir, filename)

        # Download the clip
        success = download_clip(video_url, clip.start, clip.end, output_path)
        if success:
            downloaded_clips.append(output_path)

    print(f"Downloaded {len(downloaded_clips)} of {len(clips_data)} clips")
    return downloaded_clips


def get_video_url(index_id: str, video_id: str) -> Optional[str]:
    """
    Get the video URL for a given index_id and video_id.
    This is a placeholder - in a real implementation, you would
    fetch this from the TwelveLabs API.

    Args:
        index_id: The index ID from the search results
        video_id: The video ID from the search data

    Returns:
        URL of the video or None if not found
    """
    # This is where you would make an API call to get the video URL
    # For example, using the client to get video details
    # For now, we'll return a placeholder value
    print(f"Getting video URL for index_id={index_id}, video_id={video_id}")

    # Replace this with actual API call to get the video URL
    return f"https://example.com/videos/{video_id}.mp4"  # Placeholder


def download_clip(
    video_url: str, start_time: float, end_time: float, output_path: str
) -> bool:
    """
    Download a specific portion of a video using ffmpeg.

    Args:
        video_url: URL of the source video
        start_time: Start timestamp in seconds
        end_time: End timestamp in seconds
        output_path: Path to save the downloaded clip

    Returns:
        True if download was successful, False otherwise
    """
    # Skip if file already exists
    if os.path.exists(output_path):
        print(f"[INFO] Clip already exists: {os.path.basename(output_path)}")
        return True

    try:
        print(f"[INFO] Downloading clip: {os.path.basename(output_path)}")

        # Calculate duration and optimize seeking strategy
        duration = end_time - start_time

        # For more accurate seeking:
        # 1. First seek (before input) to ~5 seconds before desired start (fast but less accurate)
        # 2. Then use a second seek (after input) for precise position (slower but accurate)
        offset = 5
        input_seek = max(0, start_time - offset)
        accurate_seek = start_time - input_seek

        # Build ffmpeg command
        cmd = [
            "ffmpeg",
            "-ss",
            str(input_seek),  # Initial seek (faster)
            "-i",
            video_url,  # Input file
            "-ss",
            str(accurate_seek),  # Fine-tune seek (accurate)
            "-t",
            str(duration),  # Duration
            "-c:v",
            "libx264",  # Video codec
            "-b:v",
            "2M",  # Video bitrate
            "-maxrate",
            "2M",  # Max bitrate
            "-bufsize",
            "4M",  # Buffer size
            "-r",
            "30",  # Frame rate
            "-pix_fmt",
            "yuv420p",  # Pixel format for compatibility
            "-c:a",
            "aac",  # Audio codec
            "-b:a",
            "192k",  # Audio bitrate
            "-ar",
            "44100",  # Audio sample rate
            "-preset",
            "medium",  # Encoding speed/quality tradeoff
            "-crf",
            "23",  # Quality level
            "-movflags",
            "+faststart",  # Optimize for web playback
            "-y",  # Overwrite output
            output_path,
        ]

        # Execute ffmpeg process
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
        )

        # Function to handle process output
        def log_output(stream, prefix):
            for line in stream:
                if "error" in line.lower() or "warning" in line.lower():
                    print(f"[{prefix}] {line.strip()}")

        # Start threads to handle stdout and stderr
        stdout_thread = threading.Thread(
            target=log_output, args=(process.stdout, "FFMPEG"), daemon=True
        )
        stderr_thread = threading.Thread(
            target=log_output, args=(process.stderr, "FFMPEG"), daemon=True
        )

        stdout_thread.start()
        stderr_thread.start()

        # Wait for process to complete
        exit_code = process.wait()

        if exit_code == 0:
            print(f"[SUCCESS] Downloaded clip: {os.path.basename(output_path)}")
            return True
        else:
            print(
                f"[ERROR] Failed to download clip: {os.path.basename(output_path)} (exit code: {exit_code})"
            )
            return False

    except Exception as e:
        print(f"[ERROR] Exception during download: {str(e)}")
        return False
