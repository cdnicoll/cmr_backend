"""Sitemap scanner: fetch sitemap URL, parse urlset/sitemapindex, apply config filters."""
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Sitemap namespace; ElementTree uses full names in tag
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
NS_MAP = {"sm": SITEMAP_NS}


def _tag(name: str) -> str:
    return f"{{{SITEMAP_NS}}}{name}"


def _parse_lastmod(el: ET.Element | None) -> datetime | None:
    if el is None or el.text is None:
        return None
    text = el.text.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text.replace("Z", "+00:00"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _path_depth(path: str) -> int:
    p = path.rstrip("/") or "/"
    return len([x for x in p.split("/") if x])


def _matches_patterns(path: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return True
    for pat in patterns:
        if re.search(pat, path):
            return True
    return False


def _excluded_by_patterns(path: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return False
    for pat in patterns:
        if re.search(pat, path):
            return True
    return False


async def scan_sitemap(
    url: str,
    *,
    days_back: int | None = None,
    require_https: bool = True,
    required_path_patterns: list[str] | None = None,
    excluded_path_patterns: list[str] | None = None,
    max_path_depth: int | None = None,
    max_urls: int | None = None,
    max_index_depth: int = 2,
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    """
    Fetch sitemap at url, parse urlset and sitemapindex (with capped recursion).
    Returns list of candidate URLs after filters. When max_urls is set, returns
    the most recent N by lastmod (nulls last).
    """
    cutoff = None
    if days_back is not None and days_back > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    try:
        # (url, lastmod) for sort-and-cap when max_urls is set
        url_pairs: list[tuple[str, datetime | None]] = []
        index_queue: list[tuple[str, int]] = [(url, 0)]  # (url, depth)

        while index_queue:
            current_url, depth = index_queue.pop(0)
            try:
                resp = await client.get(current_url)
                resp.raise_for_status()
                text = resp.text
            except Exception as e:
                logger.warning(
                    "sitemap fetch failed: url=%s depth=%s error=%s",
                    current_url,
                    depth,
                    e,
                )
                continue

            try:
                root = ET.fromstring(text)
            except ET.ParseError as e:
                logger.warning(
                    "sitemap parse failed: url=%s error=%s",
                    current_url,
                    e,
                )
                continue

            # urlset: <url><loc>...</loc>[<lastmod>...</lastmod>]</url>
            for url_el in root.findall(f".//{_tag('url')}"):
                loc_el = url_el.find(_tag("loc"))
                if loc_el is None or loc_el.text is None:
                    continue
                loc = loc_el.text.strip()
                if not loc:
                    continue
                if require_https and not loc.startswith("https://"):
                    continue
                parsed = urlparse(loc)
                path = parsed.path or "/"
                if required_path_patterns and not _matches_patterns(path, required_path_patterns):
                    continue
                if excluded_path_patterns and _excluded_by_patterns(path, excluded_path_patterns):
                    continue
                if max_path_depth is not None and _path_depth(path) > max_path_depth:
                    continue
                lastmod = _parse_lastmod(url_el.find(_tag("lastmod")))
                if cutoff is not None and lastmod is not None and lastmod < cutoff:
                    continue
                url_pairs.append((loc, lastmod))

            # sitemapindex: follow <sitemap><loc> if within depth
            if depth < max_index_depth:
                for sitemap_el in root.findall(f".//{_tag('sitemap')}"):
                    loc_el = sitemap_el.find(_tag("loc"))
                    if loc_el is None or loc_el.text is None:
                        continue
                    sub_url = loc_el.text.strip()
                    if sub_url:
                        index_queue.append((sub_url, depth + 1))

        if max_urls is not None and max_urls > 0:
            # Sort by lastmod descending, nulls last; take first max_urls
            _min = datetime.min.replace(tzinfo=timezone.utc)
            url_pairs.sort(
                key=lambda p: (p[1] is None, -(p[1] or _min).timestamp() if p[1] else 0),
                reverse=False,
            )
            url_pairs = url_pairs[:max_urls]
        result = [u for u, _ in url_pairs]
        if not result:
            logger.info(
                "sitemap yielded 0 URLs: url=%s days_back=%s (check warnings for fetch/parse failures, or relax days_back)",
                url,
                days_back,
            )
        return result
    finally:
        if own_client:
            await client.aclose()
