"""Crawl4AI client wrapper for website content extraction."""
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig


async def fetch_website_content(url: str, proxy_url: str | None = None) -> tuple[str, str]:
    """
    Fetch website content via Crawl4AI.
    Returns (markdown_content, title).
    Raises on fetch/crawl errors.
    """
    browser_config = BrowserConfig(headless=True, proxy=proxy_url)
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=run_config)

    # result.markdown is MarkdownGenerationResult with raw_markdown
    markdown = result.markdown
    if hasattr(markdown, "raw_markdown"):
        markdown = markdown.raw_markdown or ""
    elif isinstance(markdown, str):
        pass
    else:
        markdown = str(markdown) if markdown else ""

    # Title from metadata (CrawlResult.metadata)
    title = ""
    if hasattr(result, "metadata") and result.metadata:
        meta = result.metadata
        title = meta.get("title", "") if isinstance(meta, dict) else getattr(meta, "title", "") or ""

    return (markdown, title)
