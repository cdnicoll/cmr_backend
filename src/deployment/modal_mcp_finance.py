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
    .pip_install("fastmcp", "yfinance", "asyncpg")
)


@app.function(
    image=image,
    keep_warm=1,
    secrets=[modal.Secret.from_name("finance-mcp-credentials")],
)
@modal.asgi_app()
def serve():
    import asyncio
    import concurrent.futures
    import json
    import os

    import asyncpg
    import yfinance as yf
    from fastmcp import FastMCP
    from fastmcp.server.http import create_streamable_http_app
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

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
                info = yf.Ticker(symbol).info
                results.append({
                    "symbol": symbol,
                    "name": info.get("longName"),
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
    def get_stock_history(symbols: list[str], period: str = "1mo") -> dict:
        """Get OHLCV price history for one or more symbols via a single batched Yahoo Finance request.
        Valid periods: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, ytd, max.
        Returns a dict keyed by symbol, each containing a list of {Date, Open, High, Low, Close, Volume} records."""
        try:
            raw = yf.download(symbols, period=period, auto_adjust=True, progress=False)
            if len(symbols) == 1:
                df = raw.reset_index()
                df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
                return {symbols[0]: df.to_dict(orient="records")}
            result = {}
            for symbol in symbols:
                try:
                    df = raw[symbol].reset_index()
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
        Uses 10 concurrent threads to fetch all 51 symbols efficiently."""
        def fetch_summary(symbol: str) -> dict:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                summary = {
                    "symbol": symbol,
                    "name": info.get("longName"),
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

    token = os.environ["FINANCE_MCP_TOKEN"]
    return create_streamable_http_app(
        mcp,
        streamable_http_path="/mcp",
        stateless_http=True,
        middleware=[Middleware(BearerAuthMiddleware, token=token)],
    )
