"""RSS scanner: fetch feed via httpx, parse with feedparser, apply config filters."""
from datetime import datetime, timezone, timedelta

import feedparser
import httpx


def _parse_entry_date(entry: dict) -> datetime | None:
    """Get published or updated date from feed entry."""
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed and len(parsed) >= 6:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    return None


async def scan_rss(
    feed_url: str,
    *,
    days_back: int | None = None,
    min_relevance_score: float | None = None,
    require_https: bool = True,
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    """
    Fetch RSS/Atom feed, parse with feedparser, filter by date and options.
    Returns list of candidate URLs (entry links).
    """
    if require_https and not feed_url.startswith("https://"):
        return []

    cutoff = None
    if days_back is not None and days_back > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    try:
        resp = await client.get(feed_url)
        resp.raise_for_status()
        text = resp.text
    except Exception:
        return []
    finally:
        if own_client:
            await client.aclose()

    feed = feedparser.parse(text)
    urls: list[str] = []

    for entry in feed.entries:
        link = entry.get("link")
        if not link or not isinstance(link, str):
            continue
        link = link.strip()
        if require_https and not link.startswith("https://"):
            continue
        if cutoff is not None:
            pub = _parse_entry_date(entry)
            if pub is not None and pub < cutoff:
                continue
        if min_relevance_score is not None:
            # feedparser doesn't provide relevance; skip filter if not interpretable
            pass
        urls.append(link)

    return urls
