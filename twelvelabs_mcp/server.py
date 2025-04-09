from typing import Optional
from mcp.server.fastmcp import FastMCP
from twelvelabs import TwelveLabs, models
import os
from dotenv import load_dotenv
import subprocess
import uuid
from pathlib import Path


# init
load_dotenv()
mcp = FastMCP("twelvelabs")
api_key = os.environ.get("TWELVELABS_API_KEY")
print(f"api_key: {api_key}")
if not api_key:
    raise ValueError("TWELVELABS_API_KEY is required")
client = TwelveLabs(api_key=api_key, version="v1.3")
# check that we have configured a client
if not client:
    raise ValueError("TwelveLabs client not configured")


@mcp.resource("config://app")
def get_config() -> dict:
    """Return configuration data for the TwelveLabs MCP application"""
    return {
        "name": "TwelveLabs MCP",
        "version": "1.0.0",
        "api_version": "v1.3",
        "description": "TwelveLabs Multimodal Content Processing API integration",
        "defaults": {
            "group_by": "clip",
            "query_media_type": "image",
            "page_limit": 20,
            "options": ["visual", "conversation", "text_in_video"],
        },
    }


@mcp.tool(
    description="""Retrieve a specific video from a TwelveLabs index
        Args:
            index_id: The unique identifier of the index containing the video
            id: The unique identifier of the video to retrieve
        Returns:
            A dictionary containing the video details including metadata, status, and URLs
        """
)
async def retrieve_video(index_id: str, id: str) -> dict:
    try:
        video_info: models.Video = client.index.video.retrieve(index_id, id)
        return video_info.model_dump()
    except Exception as e:
        print(f"Error in retrieve_video: {e}")
        import traceback

        traceback.print_exc()


@mcp.tool(
    description="""Search for content within an index using text or media queries
    Args:
        index_id: The unique identifier of the index to search
        options: Required list of search options (e.g. ["visual", "audio"])
        query_text: The text query to search for (required for text queries)
        query_media_url: URL of the media file to search with (for media queries)
        query_media_type: Type of media to search with (defaults to "image")
        adjust_confidence_level: Value between 0-1 to adjust confidence thresholds
        group_by: Group results by "video" or "clip" (defaults to "clip")
        threshold: Filter by confidence level ("high", "medium", "low", "none")
        sort_option: How to sort results ("score" or "clip_count")
        operator: Logical operator for multiple search options ("and" or "or")
        page_limit: Number of results per page (max 50)
        filter: JSON string to filter results
    """
)
async def search(
    index_id: str,
    options: list[str] = ["visual", "audio"],
    query_text: Optional[str] = None,
    query_media_url: Optional[str] = None,
    query_media_type: Optional[str] = "image",
    adjust_confidence_level: Optional[float] = 0.5,
    group_by: Optional[str] = "clip",
    threshold: Optional[str] = "low",
    sort_option: Optional[str] = "score",
    operator: Optional[str] = "or",
    page_limit: Optional[int] = 10,
    filter: Optional[str] = None,
    num_clips: Optional[int] = 5,
) -> dict:
    try:
        params = {"index_id": index_id}

        # Add required query parameters
        if query_text:
            params["query_text"] = query_text
        if query_media_url:
            params["query_media_url"] = query_media_url
            params["query_media_type"] = query_media_type
        if options:
            params["options"] = options

        # Add optional parameters if provided
        if adjust_confidence_level is not None:
            params["adjust_confidence_level"] = adjust_confidence_level
        if group_by:
            params["group_by"] = group_by
        if threshold:
            params["threshold"] = threshold
        if sort_option:
            params["sort_option"] = sort_option
        if operator:
            params["operator"] = operator
        if page_limit:
            params["page_limit"] = page_limit
        if filter:
            params["filter"] = filter

        results: models.SearchResult = client.search.query(**params)

        return results.model_dump()
    except Exception as e:
        print(f"Error in search: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@mcp.tool(
    description="""Download clips from a TwelveLabs search result, using the mcp_tool @retrieve_video and @search results
    """
)
async def download_clips(num_clips: int, search_result: dict, video_info: dict) -> dict:
    # Get host directory from environment variables
    host_dir = os.environ.get("TWELVELABS_MCP_BASE_PATH")
    if not host_dir:
        raise ValueError("TWELVELABS_MCP_BASE_PATH environment variable is required")

    # Properly handle tilde expansion to get absolute path
    host_dir = os.path.abspath(os.path.expanduser(host_dir))
    host_dir = Path(host_dir)
    print(f"Using output directory: {host_dir}")
    host_dir.mkdir(exist_ok=True, parents=True)

    # Get m3u8 URL from video_info
    if not video_info.get("hls") or not video_info["hls"].get("video_url"):
        return {"status": "error", "message": "No HLS video URL found in video_info"}

    m3u8_url = video_info["hls"]["video_url"]

    # Process search results
    clips_data = search_result.get("data", [])
    downloaded_clips = []

    # Handle different result structures (clip or video grouping)
    processed_clips = []

    # Check if results are grouped by video
    if clips_data and isinstance(clips_data[0], dict) and "clips" in clips_data[0]:
        # Handle GroupByVideoSearchData format
        for group in clips_data:
            if group.get("clips"):
                processed_clips.extend(group["clips"][:num_clips])
                if len(processed_clips) >= num_clips:
                    break
    else:
        # Handle regular SearchData format
        processed_clips = clips_data[:num_clips]

    processed_clips = processed_clips[
        :num_clips
    ]  # Ensure we only take requested number

    # Download each clip
    for i, clip in enumerate(processed_clips):
        start_time = clip.get("start")
        end_time = clip.get("end")

        if start_time is None or end_time is None:
            continue

        # Generate unique filename
        clip_id = str(uuid.uuid4())[:8]
        output_path = host_dir / f"clip_{clip_id}_{i}.mp4"

        try:
            # Use ffmpeg to download and trim the clip
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(start_time),
                "-to",
                str(end_time),
                "-i",
                m3u8_url,
                "-c",
                "copy",
                str(output_path),
            ]

            subprocess.run(cmd, check=True, capture_output=True)

            downloaded_clips.append(
                {
                    "index": i,
                    "start": start_time,
                    "end": end_time,
                    "path": str(output_path),
                    "clip_data": clip,
                }
            )

        except subprocess.CalledProcessError as e:
            print(f"Error downloading clip {i}: {e}")
            print(f"STDERR: {e.stderr.decode() if e.stderr else 'None'}")

    return {
        "status": "success",
        "clips_requested": num_clips,
        "clips_downloaded": len(downloaded_clips),
        "clips": downloaded_clips,
    }


if __name__ == "__main__":
    # Start the server
    print("Starting TwelveLabs MCP server...")
    mcp.run()
