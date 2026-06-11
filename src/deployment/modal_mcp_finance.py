"""Modal MCP server for TSXV Venture 50 finance data."""
import modal

app = modal.App("CMR-Finance-MCP")

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
        conn = await asyncpg.connect(os.environ["TRANSACTION_POOLER_URL"])
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
        Valid categories: Gold, Copper & Base Metals, Royalty & Streaming, Silver, Lithium, Uranium, Unclassified.
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
        """Screen all TSX Venture 50 symbols in parallel and return key fundamentals (price, market cap, sector, P/E).
        Uses 10 concurrent threads to fetch all 51 symbols efficiently."""
        def fetch_summary(symbol: str) -> dict:
            try:
                info = yf.Ticker(symbol).info
                return {
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
                }
            except Exception as e:
                return {"symbol": symbol, "error": str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            return list(executor.map(fetch_summary, TSXV50))

    token = os.environ["FINANCE_MCP_TOKEN"]
    return create_streamable_http_app(
        mcp,
        streamable_http_path="/mcp",
        stateless_http=True,
        middleware=[Middleware(BearerAuthMiddleware, token=token)],
    )
