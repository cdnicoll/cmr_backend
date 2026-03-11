"""YouTube channel scanner: YouTube Data API v3, channel uploads, form video URLs."""
import os
from typing import Any

# google-api-python-client
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def _get_youtube_client():
    """Build YouTube API client. Requires YOUTUBE_API_KEY in environment."""
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is required for YouTube discovery")
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def _channel_uploads_playlist_id(youtube: Any, channel_id: str) -> str | None:
    """Resolve channel ID to uploads playlist ID."""
    try:
        resp = youtube.channels().list(
            part="contentDetails",
            id=channel_id,
            fields="items(contentDetails/relatedPlaylists/uploads)",
        ).execute()
        items = resp.get("items") or []
        if not items:
            return None
        uploads = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        return uploads
    except (HttpError, KeyError, IndexError):
        return None


def scan_youtube_channel(
    channel_id: str,
    *,
    max_videos: int | None = None,
) -> list[str]:
    """
    Fetch recent video IDs for a YouTube channel via Data API v3, return watch URLs.
    Requires YOUTUBE_API_KEY in environment (or Modal secret).
    """
    youtube = _get_youtube_client()
    playlist_id = _channel_uploads_playlist_id(youtube, channel_id)
    if not playlist_id:
        return []

    limit = max_videos or 50
    urls: list[str] = []
    next_page_token = None

    while len(urls) < limit:
        try:
            resp = youtube.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=min(50, limit - len(urls)),
                pageToken=next_page_token or None,
            ).execute()
        except HttpError:
            break

        for item in (resp.get("items") or []):
            vid = item.get("contentDetails", {}).get("videoId")
            if vid:
                urls.append(f"https://www.youtube.com/watch?v={vid}")
        next_page_token = resp.get("nextPageToken")
        if not next_page_token:
            break

    return urls[:limit]
