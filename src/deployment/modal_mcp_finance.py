"""Modal MCP server for TSXV Venture 50 finance data."""
import calendar
from datetime import date

import modal

app = modal.App("CMR-Finance-MCP")


def _months_ago(day: date, months: int) -> date:
    """Calendar-month subtraction, clamping to the last day of the target month."""
    year, month = day.year, day.month - months
    while month <= 0:
        month += 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last_day))


def _pct_change_from_baseline(closes: list[tuple[date, float]], target: date) -> float | None:
    """Percent change from the closest close at or before `target` to the latest close.

    `closes` is (date, adjusted_close) sorted ascending. Returns None — never a guess —
    when history is empty or doesn't reach back to the target date (e.g. new listings).
    """
    if not closes:
        return None
    latest = closes[-1][1]
    baseline = None
    for day, value in reversed(closes):
        if day <= target:
            baseline = value
            break
    if baseline is None or baseline == 0:
        return None
    return round((latest - baseline) / baseline * 100, 1)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastmcp", "yfinance", "asyncpg", "pydantic")
    # Needed for the report-draft tools' `from src.services...` imports below —
    # schema.py/tsxv50_report_drafts_dao.py are pure Python (no templates/assets),
    # so unlike modal_pdf.py this doesn't also need add_local_dir for anything.
    .add_local_python_source("src")
)


@app.function(
    image=image,
    keep_warm=1,
    secrets=[
        modal.Secret.from_name("finance-mcp-credentials"),
        # The report-draft tools' DAO uses load_settings() (src/models/config.py),
        # which requires the full Settings model, not just TRANSACTION_POOLER_URL.
        # Matches modal_pdf.py's secrets exactly — same live Supabase project.
        modal.Secret.from_name("supabase-credentials-develop"),
        modal.Secret.from_name("app-config-develop"),
    ],
)
@modal.asgi_app()
def serve():
    import asyncio
    import concurrent.futures
    import json
    import os
    import time
    from datetime import datetime, timezone

    import asyncpg
    import pandas as pd
    import yfinance as yf
    from fastmcp import FastMCP
    from fastmcp.server.http import create_streamable_http_app
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    from pydantic import ValidationError

    from src.services.pdf.schema import (
        MasterListEntry,
        ReportValidationError,
        check_master_list_integrity,
        validate_report,
    )
    from src.services.supabase import tsxv50_report_drafts_dao as drafts

    def _decode_jsonb(value):
        return json.loads(value) if isinstance(value, str) else value

    async def _load_tsxv50() -> tuple[list[str], list[dict]]:
        conn = await asyncpg.connect(
            os.environ["TRANSACTION_POOLER_URL"], statement_cache_size=0
        )
        row = await conn.fetchrow(
            "SELECT symbols, entries FROM public.tsxv50_snapshots ORDER BY created_at DESC LIMIT 1"
        )
        await conn.close()
        if not row:
            raise RuntimeError("tsxv50_snapshots table is empty")
        symbols = _decode_jsonb(row["symbols"])
        entries = _decode_jsonb(row["entries"])
        if entries is not None:
            return [entry["symbol"] for entry in entries], entries
        return symbols, []

    TSXV50, TSXV50_ENTRIES = asyncio.run(_load_tsxv50())
    # Fallback for Yahoo responses with real price/cap data but a missing
    # longName (e.g. VROY.V) -- the watchlist's own name is a reliable
    # substitute so a company is never silently dropped over a name lookup
    # gap alone (2026-07-28: this nearly re-dropped Vizsla Royalties).
    TSXV50_NAMES = {entry["symbol"]: entry["name"] for entry in TSXV50_ENTRIES if entry.get("name")}

    class BearerAuthMiddleware(BaseHTTPMiddleware):
        def __init__(self, app, token: str):
            super().__init__(app)
            self._token = token

        async def dispatch(self, request, call_next):
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {self._token}":
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            return await call_next(request)

    mcp = FastMCP("CMR Finance")

    @mcp.tool()
    def get_tsxv50_watchlist() -> list[str]:
        """Returns the 2026 TSX Venture 50 watchlist symbols (TSXV tickers with .V suffix for Yahoo Finance)."""
        return TSXV50

    @mcp.tool()
    def get_tsxv50_by_category(category: str) -> list[dict]:
        """Return TSXV50 watchlist entries (symbol, name, category) matching the given category.
        Valid categories: Gold, Copper & Base Metals, Royalty & Streaming, Silver, Lithium, Uranium, Critical Minerals & Other, Unclassified.
        Returns an empty list if the loaded snapshot predates categorization (legacy snapshot)."""
        return [entry for entry in TSXV50_ENTRIES if entry.get("category") == category]

    def _ticker_info_with_retry(symbol: str, attempts: int = 3) -> dict:
        """Fetch yf.Ticker(symbol).info, retrying transient failures.

        Yahoo intermittently returns an info payload with null price fields
        (no exception raised) — one such blip put a null price_cad into a
        render payload and blocked a PDF. Same class of blip can leave
        longName null while price/market cap come through fine (2026-07-28:
        VROY.V) — retry on exceptions AND on any of these missing essential
        fields; return whatever the last attempt produced so truly dead
        symbols still come back (empty) rather than erroring the batch.
        """
        last_exc: Exception | None = None
        info: dict = {}
        for attempt in range(attempts):
            if attempt:
                time.sleep(2**attempt)  # 2s, 4s
            try:
                info = yf.Ticker(symbol).info
                last_exc = None
            except Exception as e:
                last_exc = e
                continue
            if (
                info.get("currentPrice") is not None
                and info.get("marketCap") is not None
                and info.get("longName") is not None
            ):
                return info
        if last_exc is not None:
            raise last_exc
        return info

    @mcp.tool()
    def get_stock_info(symbols: list[str]) -> list[dict]:
        """Get fundamental data (P/E, market cap, sector, description, 52-week range, etc.) for one or more symbols."""
        results = []
        for symbol in symbols:
            try:
                info = yf.Ticker(symbol).info
                results.append({"symbol": symbol, **info})
            except Exception as e:
                results.append({"symbol": symbol, "error": str(e)})
        return results

    @mcp.tool()
    def get_stock_price(symbols: list[str]) -> list[dict]:
        """Get current price, previous close, day high/low, volume, and 52-week range for one or more symbols."""
        results = []
        for symbol in symbols:
            try:
                info = _ticker_info_with_retry(symbol)
                results.append({
                    "symbol": symbol,
                    "name": info.get("longName") or TSXV50_NAMES.get(symbol),
                    "currency": info.get("currency"),
                    "current_price": info.get("currentPrice"),
                    "previous_close": info.get("previousClose"),
                    "day_high": info.get("dayHigh"),
                    "day_low": info.get("dayLow"),
                    "volume": info.get("volume"),
                    "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                    "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                })
            except Exception as e:
                results.append({"symbol": symbol, "error": str(e)})
        return results

    @mcp.tool()
    def get_stock_history(symbols: list[str], period: str = "1mo", interval: str = "1d") -> dict:
        """Get OHLCV price history for one or more symbols via a single batched Yahoo Finance request.
        Valid periods: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, ytd, max.
        Valid intervals: 1d, 1wk, 1mo — use 1wk/1mo for long periods to keep responses small.
        Returns a dict keyed by symbol, each containing a list of {Date, Open, High, Low, Close, Volume} records."""
        try:
            # group_by="ticker" keys the column MultiIndex by symbol; the default
            # ("column") keys by price field, which made raw[symbol] a KeyError.
            raw = yf.download(
                symbols,
                period=period,
                interval=interval,
                auto_adjust=True,
                progress=False,
                group_by="ticker",
            )
            result = {}
            for symbol in symbols:
                try:
                    df = raw[symbol] if isinstance(raw.columns, pd.MultiIndex) else raw
                    df = df.dropna(how="all").reset_index()
                    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
                    result[symbol] = df.to_dict(orient="records")
                except Exception as e:
                    result[symbol] = {"error": str(e)}
            return result
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    def screen_tsxv50() -> list[dict]:
        """Screen all TSX Venture 50 symbols in parallel and return key fundamentals
        (price, market cap, sector, P/E) plus chg_3mo_pct and chg_12mo_pct — percent price
        change over ~3 and ~12 calendar months, computed from adjusted closes and rounded
        to 1 decimal (null when history doesn't cover the window, e.g. new listings).
        Uses 10 concurrent threads to fetch all 50 watchlist symbols efficiently."""
        def fetch_summary(symbol: str) -> dict:
            try:
                ticker = yf.Ticker(symbol)
                info = _ticker_info_with_retry(symbol)
                summary = {
                    "symbol": symbol,
                    "name": info.get("longName") or TSXV50_NAMES.get(symbol),
                    "currency": info.get("currency"),
                    "current_price": info.get("currentPrice"),
                    "market_cap": info.get("marketCap"),
                    "sector": info.get("sector"),
                    "industry": info.get("industry"),
                    "pe_ratio": info.get("trailingPE"),
                    "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                    "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                    "chg_3mo_pct": None,
                    "chg_12mo_pct": None,
                }
                try:
                    # 2y so a trading day exists at or before the 12-month baseline
                    # ("1y" starts exactly at the target date). auto_adjust makes Close
                    # the adjusted close, so both endpoints are split/dividend-adjusted.
                    hist = ticker.history(period="2y", auto_adjust=True)
                    closes = [
                        (ts.date(), float(v)) for ts, v in hist["Close"].dropna().items()
                    ]
                    today = date.today()
                    summary["chg_3mo_pct"] = _pct_change_from_baseline(
                        closes, _months_ago(today, 3)
                    )
                    summary["chg_12mo_pct"] = _pct_change_from_baseline(
                        closes, _months_ago(today, 12)
                    )
                except Exception:
                    pass  # history failure leaves the change fields null
                return summary
            except Exception as e:
                return {"symbol": symbol, "error": str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            return list(executor.map(fetch_summary, TSXV50))

    @mcp.tool()
    def generate_tsxv50_pdf(report_json: dict) -> dict:
        """Render the quarterly TSXV50 report PDF from a complete report_json payload.
        Pure renderer (no data fetching): the payload must follow the report_json schema
        contract — meta, introduction, master_list, categories (with company tables, blurbs,
        and chart series), glossary, disclaimer.
        Returns {pdf_url, filename, bytes, page_count} on success, or
        {"error": {"type": "validation_error", "issues": [{path, message}]}} when the
        payload fails the schema."""
        pdf_fn = modal.Function.from_name("CMR-PDF", "generate_pdf")
        return pdf_fn.remote(report_json)

    def _assemble_report_json(
        draft: dict, glossary: list[dict] | None = None, disclaimer: str | None = None
    ) -> dict:
        """Build a report_json dict from a draft row's stored fields. glossary/disclaimer
        are renderer-supplied at render time (Phase D static boilerplate); finalize_report
        uses placeholders since it only needs to check master_list/categories/meta/
        introduction completeness, not the standing renderer-owned text."""
        categories_map = draft.get("categories") or {}
        categories = []
        for category_name, entry in categories_map.items():
            content = (entry or {}).get("content")
            if content:
                categories.append({"category": category_name, **content})
        return {
            "meta": draft.get("meta"),
            "introduction": draft.get("introduction"),
            "master_list": draft.get("master_list"),
            "categories": categories,
            "glossary": glossary if glossary is not None else [],
            "disclaimer": disclaimer if disclaimer is not None else "[disclaimer pending render]",
        }

    @mcp.tool()
    async def start_report(period_label: str, meta: dict, draft_slug: str = "primary") -> dict:
        """Start or resume a report draft. period_label is the normalized slug (e.g.
        "2026-Q2"), distinct from meta.period_label (the display string, e.g. "Q2 2026
        (April 1 - June 30, 2026)"). draft_slug defaults to "primary" — the common
        single-draft-per-period case; pass a different slug (e.g. "editorial-a") only
        when deliberately trying multiple versions of the same period.
        Calling this again with the same (period_label, draft_slug) resumes the existing
        draft instead of creating a new one — this is the fresh-chat resume path; always
        call this first on any turn, never assume prior state from conversation memory.
        Returns the full draft row: {period_label, draft_slug, status, meta, master_list,
        introduction, categories, synthesis, finalize_result, conversation_ids, pdf_url,
        created_at, updated_at}."""
        await drafts.get_or_create_draft(period_label, draft_slug)
        return await drafts.set_meta(period_label, draft_slug, meta)

    @mcp.tool()
    async def set_meta(period_label: str, meta: dict, draft_slug: str = "primary") -> dict:
        """Update the draft's meta block: {publication, report_title, edition_tagline,
        period_label (display string), data_as_of, currency, cover_image}. start_report
        sets an initial version (usually with a placeholder edition_tagline, since the
        real theme-based tagline isn't known until synthesis is done); call this again
        later (finalizer) with the complete object once the real tagline is decided.
        Full overwrite, not a merge — pass every field, not just the one that changed.
        Returns the updated draft row."""
        return await drafts.set_meta(period_label, draft_slug, meta)

    @mcp.tool()
    async def set_master_list(
        period_label: str, master_list: list[dict], draft_slug: str = "primary"
    ) -> dict:
        """Write Phase A's ranked master list (orchestrator only). Each entry:
        {rank, company, ticker, category, market_cap_cad_mn}, ranks contiguous from 1.
        Validates the list before writing: duplicate tickers, non-contiguous ranks, and
        market cap not sorted descending all fail here with {"error": {"type":
        "validation_error", "issues": [...]}} and nothing is persisted — a bad list can
        never reach Checkpoint 1 as an already-"verified" pass. (Added after the
        2026-07-28 report: this check didn't exist before, so a duplicate ticker and an
        inverted market-cap sort both survived undetected to the operator, because the
        only real check on master_list ran inside finalize_report, in Phase 3, long after
        Checkpoint 1 had already presented the list as PASS.) On failure, recompute the
        sort/dedup and retry — do not patch a single inversion found by hand.
        On success, also clears finalize_result and resets status to in_progress, the
        same cascade-invalidation add_category already does — a master_list edit after
        finalization can orphan category tickers, so a stale "finalized"/"rendered"
        verdict must never survive it. Call finalize_report again before any render.
        Returns the updated draft row on success."""
        try:
            entries = [MasterListEntry.model_validate(entry) for entry in master_list]
        except ValidationError as e:
            issues = [
                {"path": ".".join(str(loc) for loc in err["loc"]), "message": err["msg"]}
                for err in e.errors()
            ]
            return {"error": {"type": "validation_error", "issues": issues}}
        integrity_issues = check_master_list_integrity(entries)
        if integrity_issues:
            return {
                "error": {
                    "type": "validation_error",
                    "issues": [
                        {"path": "master_list", "message": issue} for issue in integrity_issues
                    ],
                }
            }
        return await drafts.set_master_list(period_label, draft_slug, master_list)

    @mcp.tool()
    async def set_introduction(
        period_label: str, introduction: dict, draft_slug: str = "primary"
    ) -> dict:
        """Write the whole-report introduction (finalizer, once synthesis is done):
        {sections: [{subhead, body}, ...]}. This is the executive-summary-level content
        that needs full-draft visibility, not per-category drafting. Returns the updated
        draft row."""
        return await drafts.set_introduction(period_label, draft_slug, introduction)

    @mcp.tool()
    async def set_category_research(
        period_label: str, category: str, research: dict, draft_slug: str = "primary"
    ) -> dict:
        """Write one category's Phase A.5 research (category-researcher). Idempotent per
        category name — re-running overwrites only that category's research, leaving every
        other category's research and any already-drafted content untouched. Call this
        once per category; the synthesist requires every category's research to exist
        before it can run. Returns the updated draft row."""
        return await drafts.upsert_category_research(period_label, draft_slug, category, research)

    @mcp.tool()
    async def set_synthesis(period_label: str, synthesis: dict, draft_slug: str = "primary") -> dict:
        """Write the synthesist's cross-company trend-detection/sector-comparison output.
        Runs once, only after every category's research exists — internal editorial
        machinery, never printed in the rendered report. Returns the updated draft row."""
        return await drafts.set_synthesis(period_label, draft_slug, synthesis)

    @mcp.tool()
    async def add_category(
        period_label: str,
        category: str,
        content: dict,
        sources: list[dict] | None = None,
        draft_slug: str = "primary",
    ) -> dict:
        """Write one category's drafted content (category-drafter). content must match the
        report_json category shape: {tagline, intro, chart, companies, limited_activity}.
        Idempotent per category name — editing an already-drafted category is the normal
        path, not an exception. Clears any existing finalize_result and resets status to
        in_progress: a stale "locked" verdict must never survive an edit. Returns the
        updated draft row."""
        return await drafts.upsert_category_content(period_label, draft_slug, category, content, sources)

    @mcp.tool()
    async def finalize_report(period_label: str, draft_slug: str = "primary") -> dict:
        """Run the completeness/duplicate check (issue #2) against the current draft: every
        master_list company must appear in exactly one category block, no duplicate tickers
        anywhere, ranks contiguous from 1, plus every category's own schema constraints.
        Re-runnable — safe to call again after editing a category; a passing result marks
        the draft 'finalized', anything else leaves it 'in_progress' so render_report keeps
        refusing to run. Requires meta, master_list, and introduction to already be set.
        Returns {"status": "pass", "checked_at": ISO timestamp} or {"status": "fail",
        "issues": [{path, message}], "checked_at": ISO timestamp}, or {"error": {...}} if
        the draft doesn't exist yet or is missing a prerequisite field."""
        draft = await drafts.get_draft(period_label, draft_slug)
        if draft is None:
            return {
                "error": {
                    "type": "not_found",
                    "message": f"no draft for period_label={period_label!r} draft_slug={draft_slug!r}; call start_report first",
                }
            }
        missing = [f for f in ("meta", "master_list", "introduction") if not draft.get(f)]
        if missing:
            return {
                "error": {
                    "type": "incomplete_draft",
                    "message": f"missing required field(s) before finalize_report can run: {missing}",
                }
            }
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            validate_report(_assemble_report_json(draft))
            result = {"status": "pass", "checked_at": checked_at}
        except ReportValidationError as e:
            result = {"status": "fail", "issues": e.issues, "checked_at": checked_at}
        await drafts.set_finalize_result(period_label, draft_slug, result)
        return result

    @mcp.tool()
    async def render_report(
        period_label: str,
        glossary: list[dict],
        disclaimer: str,
        draft_slug: str = "primary",
    ) -> dict:
        """Render the PDF from a finalized draft. Refuses to run unless the draft's status
        is "finalized" — call finalize_report first; any edit to a category resets status
        back to in_progress, so a stale "locked" verdict can never reach this tool.
        glossary/disclaimer are supplied here (Phase D static boilerplate), not stored on
        the draft. Returns {pdf_url, filename, bytes, page_count} on success (also recorded
        on the draft row), or {"error": {...}} if the draft isn't finalized or the fully
        assembled payload still fails validation."""
        draft = await drafts.get_draft(period_label, draft_slug)
        if draft is None:
            return {
                "error": {
                    "type": "not_found",
                    "message": f"no draft for period_label={period_label!r} draft_slug={draft_slug!r}",
                }
            }
        if draft["status"] != "finalized":
            return {
                "error": {
                    "type": "not_finalized",
                    "message": f"draft status is {draft['status']!r}, not 'finalized' — call finalize_report first",
                }
            }
        report_json = _assemble_report_json(draft, glossary=glossary, disclaimer=disclaimer)
        try:
            validate_report(report_json)
        except ReportValidationError as e:
            return e.to_dict()
        pdf_fn = modal.Function.from_name("CMR-PDF", "generate_pdf")
        result = pdf_fn.remote(report_json)
        if "pdf_url" in result:
            await drafts.set_pdf_url(period_label, draft_slug, result["pdf_url"])
        return result

    @mcp.tool()
    async def get_draft(period_label: str, draft_slug: str = "primary") -> dict:
        """Read the current state of one draft. Every pipeline role calls this first
        on every turn — never trust conversation memory for state; a same-day gap and
        a three-day gap must look identical. Returns the full row: {period_label,
        draft_slug, status, meta, master_list, introduction, categories, synthesis,
        finalize_result, conversation_ids, pdf_url, created_at, updated_at}, or
        {"error": {"type": "not_found", ...}} if no draft exists yet for this
        (period_label, draft_slug) — call start_report first in that case."""
        draft = await drafts.get_draft(period_label, draft_slug)
        if draft is None:
            return {
                "error": {
                    "type": "not_found",
                    "message": f"no draft for period_label={period_label!r} draft_slug={draft_slug!r}; call start_report first",
                }
            }
        return draft

    @mcp.tool()
    async def list_drafts(period_label: str) -> list[dict]:
        """List every draft version for a period (discoverability across draft_slug
        versions), newest-updated first. Never used to auto-resolve which draft to act
        on — that choice is always an explicit draft_slug parameter to the other tools;
        surface this list to the operator when it's ambiguous which draft they mean."""
        return await drafts.list_drafts(period_label)

    token = os.environ["FINANCE_MCP_TOKEN"]
    return create_streamable_http_app(
        mcp,
        streamable_http_path="/mcp",
        stateless_http=True,
        middleware=[Middleware(BearerAuthMiddleware, token=token)],
    )
