"""Discovery service — run_discovery: load sources, scan, dedupe, batch create, return created IDs for scrape."""
import asyncio
import json
from uuid import UUID

from src.models.config import load_settings
from src.services.supabase.discovery_sources_dao import list_enabled_sources, update_first_run_at
from src.services.supabase.resources_dao import get_existing_urls
from src.services.resources_service import batch_create
from src.utils.logging import get_logger

from .rss_scanner import scan_rss
from .sitemap_scanner import scan_sitemap
from .youtube_scanner import scan_youtube_channel

logger = get_logger(__name__)

SOURCE_TYPES = frozenset({"sitemap", "rss", "youtube_channel"})


def _get_config(source: dict, key: str, default=None):
    """Get value from source config (JSONB). Handles config as dict or JSON string."""
    config = source.get("config") or {}
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (json.JSONDecodeError, TypeError):
            return default
    if isinstance(config, dict):
        return config.get(key, default)
    return default


def _initial_or_ongoing(source: dict, initial_key: str, ongoing_key: str, settings_key: str):
    """For first run use initial_* (config or settings default); else use ongoing config."""
    is_first = source.get("first_run_at") is None
    if is_first:
        val = _get_config(source, initial_key)
        if val is not None:
            return val
        return getattr(load_settings(), settings_key)
    return _get_config(source, ongoing_key)


async def _urls_for_source(source: dict) -> list[str]:
    """Run the appropriate scanner for one source. Returns list of candidate URLs. Raises on invalid config."""
    source_id = str(source["id"])
    source_type = (source.get("source_type") or "").strip().lower()
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"Unknown source_type: {source_type}")

    settings = load_settings()

    if source_type == "sitemap":
        url = _get_config(source, "url")
        if not url:
            raise ValueError("sitemap config missing 'url'")
        days_back = _initial_or_ongoing(source, "initial_days_back", "days_back", "discovery_initial_days_back")
        max_urls = None
        if source.get("first_run_at") is None:
            max_urls = _get_config(source, "initial_max_urls")
            if max_urls is None:
                max_urls = settings.discovery_initial_max_urls
        return await scan_sitemap(
            url,
            days_back=days_back,
            require_https=_get_config(source, "require_https", True),
            required_path_patterns=_get_config(source, "required_path_patterns"),
            excluded_path_patterns=_get_config(source, "excluded_path_patterns"),
            max_path_depth=_get_config(source, "max_path_depth"),
            max_urls=max_urls,
        )

    if source_type == "rss":
        feed_url = _get_config(source, "feed_url")
        if not feed_url:
            raise ValueError("rss config missing 'feed_url'")
        days_back = _initial_or_ongoing(source, "initial_days_back", "days_back", "discovery_initial_days_back")
        return await scan_rss(
            feed_url,
            days_back=days_back,
            min_relevance_score=_get_config(source, "min_relevance_score"),
            require_https=_get_config(source, "require_https", True),
        )

    if source_type == "youtube_channel":
        channel_id = _get_config(source, "channel_id")
        if not channel_id or not str(channel_id).strip():
            raise ValueError("youtube_channel config missing 'channel_id'")
        max_videos = _initial_or_ongoing(source, "initial_max_videos", "max_videos", "discovery_initial_max_videos")
        # Sync API — run in thread to avoid blocking
        return await asyncio.to_thread(
            scan_youtube_channel,
            str(channel_id).strip(),
            max_videos=max_videos,
        )

    return []


async def run_discovery(dry_run: bool = False) -> list[UUID]:
    """
    Load enabled discovery sources, run sitemap/RSS/YouTube scanners per source,
    deduplicate against existing URLs, create net-new resources with discovery_source_id,
    return list of created resource IDs (for spawning scrape). On dry_run=True, do not
    create resources or return IDs; log summary of what would be submitted.
    Per-source failures are logged and do not abort the run.
    """
    sources = await list_enabled_sources()
    if not sources:
        logger.info("run_discovery: no enabled sources")
        return [] if not dry_run else []

    # Collect (source_id, urls) per source
    by_source: list[tuple[str, list[str]]] = []
    for source in sources:
        source_id = str(source["id"])
        name = source.get("name") or source_id
        try:
            urls = await _urls_for_source(source)
            by_source.append((source_id, urls))
            logger.info(
                "run_discovery: source %s (%s) yielded %d URLs",
                name,
                source.get("source_type"),
                len(urls),
            )
        except Exception as e:
            logger.exception(
                "run_discovery: source %s (%s) failed: %s",
                name,
                source.get("source_type"),
                e,
            )
            continue

    all_candidates = [u for _, urls in by_source for u in urls]
    existing = await get_existing_urls(all_candidates) if all_candidates else set()

    if dry_run:
        total_new = sum(len([u for u in urls if u not in existing]) for _, urls in by_source)
        logger.info(
            "DRY RUN: would submit %d net-new URLs (total candidates %d, existing %d). No resources created, no scrape spawned.",
            total_new,
            len(all_candidates),
            len(existing),
        )
        for source_id, urls in by_source:
            net_new = [u for u in urls if u not in existing]
            if net_new:
                logger.info("DRY RUN: source %s would submit %d URLs (sample: %s)", source_id, len(net_new), net_new[:3])
        return []

    created_ids: list[UUID] = []
    for source_id, urls in by_source:
        net_new = [u for u in urls if u not in existing]
        if not net_new:
            continue
        response = await batch_create(
            net_new,
            discovery_source_id=source_id,
        )
        for r in response.results:
            if r.status == "created" and r.resource_id is not None:
                created_ids.append(r.resource_id)
        # Add newly created URLs to existing so we don't double-count if same URL in another source
        for r in response.results:
            if r.status == "created":
                existing.add(r.url)

    # Mark each source that was run as having completed its first run (idempotent)
    for source_id, _ in by_source:
        await update_first_run_at(source_id)

    return created_ids
