"""YouTube transcript extraction via youtube-transcript-api."""
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL. Returns None if invalid."""
    parsed = urlparse(url)
    netloc = (parsed.netloc or "").lower().replace("www.", "")
    path = (parsed.path or "").strip("/")

    if "youtu.be" in netloc:
        return path.split("/")[0] if path else None
    if "youtube.com" in netloc:
        if "/shorts/" in parsed.path:
            return path.split("/")[-1] if path else None
        if "v" in parse_qs(parsed.query or ""):
            return parse_qs(parsed.query)["v"][0]
    return None


def fetch_youtube_transcript(url: str) -> tuple[str, str]:
    """
    Fetch YouTube transcript for the given video URL.
    Returns (markdown_content, title).
    Title is placeholder (YouTube transcript API doesn't provide it); use url for display.
    Raises on fetch errors (e.g. captions disabled, video not found).
    """
    video_id = _extract_video_id(url)
    if not video_id:
        raise ValueError(f"Could not extract video ID from URL: {url}")

    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id)

    # Concatenate snippet text into markdown
    parts = [snippet.text for snippet in transcript]
    markdown = "\n\n".join(parts) if parts else ""

    # Title: transcript API doesn't provide it; use placeholder; caller may enrich
    title = f"YouTube video {video_id}"

    return (markdown, title)
