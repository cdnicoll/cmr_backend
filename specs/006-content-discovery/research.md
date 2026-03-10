# Phase 0: Research — Content Discovery

Decisions and rationale for sitemap, RSS, YouTube, filtering, and discovery run integration.

---

## 1. Sitemap parsing

**Decision**: Parse sitemap XML with Python stdlib `xml.etree.ElementTree` (and `httpx` for fetching). Support both plain sitemaps (`<urlset>`) and sitemap index files (`<sitemapindex>`) by following index entries recursively when needed.

**Rationale**: No extra dependency; legacy domain findings do not require a specific library. Sitemap format is simple; recursion depth can be capped (e.g. 2 levels) to avoid runaway index chains.

**Alternatives considered**: `ultrarapidjson` or third-party sitemap packages — rejected to keep dependencies minimal and behavior explicit.

---

## 2. RSS parsing

**Decision**: Use `feedparser` for RSS/Atom feed parsing.

**Rationale**: Matches legacy (`08-content-discovery.md`: "Uses feedparser"); well-maintained, handles RSS and Atom and common quirks; already used in similar codebases.

**Alternatives considered**: Stdlib-only parsing — possible but brittle for real-world feeds; custom XML parsing — more work for no clear benefit.

---

## 3. YouTube channel video listing

**Decision**: Use YouTube Data API v3 (e.g. `search.list` with `channelId` or `playlistItems.list` for the channel’s “uploads” playlist) to get recent video IDs, then form video URLs. Require an API key in env/Modal secret (e.g. `YOUTUBE_API_KEY`); document quota and optional caching if needed.

**Rationale**: Official, supported way to get channel videos; no scraping of YouTube pages. Quota is manageable for daily discovery of a modest number of channels.

**Alternatives considered**: Scraping channel page — fragile and against ToS; RSS feed of channel uploads — YouTube provides this per-channel; could be added later as an alternative if quota becomes an issue.

---

## 4. URL filtering defaults

**Decision**: Use configurable defaults aligned with legacy where specified: e.g. `days_back` default 7–14 days; `batch_size` for submit default 50; `require_https` default true; path rules (required_path_patterns, excluded_path_patterns, max_path_depth) optional per source. Store these as columns or JSONB on `discovery_sources` so operators can override per source.

**Rationale**: Legacy `08-content-discovery.md` mentions `days_back_filter`, `min_relevance_score`, `required_path_patterns`, `excluded_path_patterns`, `max_path_depth`, `require_https`. Preserving these and giving sensible defaults keeps behavior predictable.

**Alternatives considered**: Global-only config — rejected so that per-source tuning is possible without new code.

---

## 5. Discovery run: resource creation and scrape trigger

**Decision**: From the discovery Modal worker, call the existing resources batch-create path and scrape spawner **in-process** (same codebase): load discovery sources from Supabase, run scanners, deduplicate against existing URLs (DAO or batch_create semantics), call `batch_create(urls)` (or equivalent service method), then for each created resource ID call `scrape_resource.spawn(resource_id)`. Use Supabase service-role client and existing Modal secrets inside the worker; no HTTP call to the app’s own API unless we explicitly choose that for consistency with external callers.

**Rationale**: Build plan says "submits new URLs to POST /api/v1/resources" and "batch spawns scrape jobs"; doing this inside the worker avoids an extra network hop and reuses the same auth (service role). If we later want cron to call the API over HTTP, we can add a thin endpoint that delegates to the same discovery service.

**Alternatives considered**: HTTP POST to `POST /api/v1/resources` from the worker with service JWT — valid but adds latency and another failure mode; keeping internal call keeps Phase 5 simpler.

---

## 6. Dry-run and reporting

**Decision**: Discovery run accepts a `dry_run: bool` (e.g. function argument or env). When true: run all scanners and filters, deduplicate, but do not call batch_create and do not spawn scrape; log or return a summary (counts per source, sample URLs that would be submitted) so operators can validate config.

**Rationale**: Spec FR-010 and user story 3 require dry-run with reporting of what would be submitted; no new technology choice, just a flag and conditional execution.

---

## 7. Per-source failure handling

**Decision**: For each enabled source, run the scanner in a try/except (or equivalent). On failure (timeout, 5xx, parse error): log the error and source id/type, append to a run-level list of source errors, continue to the next source. At end of run, if any source failed, log or emit the list so operators can act. Do not abort the whole run for one bad source.

**Rationale**: Spec FR-011 and edge cases require continuing with other sources and reporting failures; no new research, just implementation discipline.
