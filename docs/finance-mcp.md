# CMR Finance MCP Server

A Modal-hosted MCP server that exposes TSX Venture Exchange stock data to Claude and other MCP clients. Uses Yahoo Finance as the data source and ships with the 2026 TSX Venture 50 watch list pre-loaded.

## Overview

- **App name**: `CMR-Finance-MCP`
- **Modal workspace**: `canadain-mining-report` / environment: `main`
- **MCP server name** (in `.mcp.json`): `cmr-stock-ticker`
- **Transport**: Streamable HTTP (`POST /mcp`)
- **Auth**: Bearer token (`FINANCE_MCP_TOKEN`)

## Tools

### `get_tsxv50_watchlist()`
Returns the full list of ticker symbols from the bundled `top50config.json`.

```
→ list[str]  e.g. ["SCZ.V", "UCU.V", ...]
```

### `get_stock_info(symbols)`
Full Yahoo Finance fundamentals for one or more symbols — P/E ratio, market cap, sector, business description, 52-week range, dividend yield, and more.

```
symbols: list[str]
→ list[dict]  one entry per symbol; failed lookups include {"symbol": "X.V", "error": "..."}
```

### `get_stock_price(symbols)`
Current quote snapshot — price, previous close, day high/low, volume, and 52-week range.

```
symbols: list[str]
→ list[dict]
```

### `get_stock_history(symbols, period)`
OHLCV price history via a single batched Yahoo Finance request. Returns a dict keyed by symbol.

```
symbols: list[str]
period:  str  — one of: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, ytd, max  (default: "1mo")
→ dict[str, list[dict]]  each record has: Date, Open, High, Low, Close, Volume
```

### `screen_tsxv50()`
Convenience tool — fetches all 51 TSXV 50 symbols in parallel (10 threads) and returns key fundamentals for each. Equivalent to calling `get_stock_info` on the full watch list in one shot, plus 3-month and 12-month percent price changes computed from adjusted closes (the baseline is the closest trading day at or before the target date; `null` when history doesn't cover the window, e.g. new listings or delisted symbols).

```
→ list[dict]  fields: symbol, name, currency, current_price, market_cap, sector, industry, pe_ratio, fifty_two_week_high, fifty_two_week_low, chg_3mo_pct, chg_12mo_pct
```

### `generate_tsxv50_pdf(report_json)`
Renders the quarterly TSXV50 report PDF. Thin pass-through to the `CMR-PDF` Modal app
(WeasyPrint + matplotlib, deployed from `src/deployment/modal_pdf.py`); the heavy render runs
there, and the finished PDF is uploaded to the `tsxv50-reports` Supabase Storage bucket.
The payload must follow the report_json schema contract
(`_local/pdf-generation/2026-06-11-tsxv50-report-json-schema.md`); invalid payloads return a
structured error instead of a half-rendered report.

```
report_json: dict — full report contract: meta, introduction, master_list, categories, glossary, disclaimer
→ dict  {pdf_url, filename, bytes, page_count}
        or {"error": {"type": "validation_error", "issues": [{path, message}]}}
```

## Setup

### 1. Generate a bearer token

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Add the output to `.env`:

```
FINANCE_MCP_TOKEN=<generated-token>
```

### 2. Deploy

Ensure the `canadain-mining-report` Modal profile is active:

```bash
modal profile list        # confirm • is on canadain-mining-report
modal profile activate canadain-mining-report  # if not active
```

Deploy via the project deploy script (deploys all three Modal apps):

```bash
uv run deploy_dev
```

Or deploy only the finance MCP:

```bash
modal deploy -e main src/deployment/modal_mcp_finance.py
```

### 3. Update `.mcp.json`

After deploying, Modal prints the endpoint URL. Update `.mcp.json`:

```json
"cmr-stock-ticker": {
  "type": "http",
  "url": "https://canadain-mining-report--cmr-finance-mcp-serve.modal.run/mcp",
  "headers": {
    "Authorization": "Bearer <your-FINANCE_MCP_TOKEN>"
  }
}
```

## Updating the TSXV 50 Watch List

The watch list is stored in [`top50config.json`](../top50config.json) at the repo root. It is bundled into the Modal container image at deploy time (`/app/top50config.json`).

To update:
1. Edit `top50config.json` — symbols use the `.V` suffix for Yahoo Finance (e.g. `"SCZ.V"`)
2. Redeploy: `modal deploy -e main src/deployment/modal_mcp_finance.py`

The list currently reflects the **2026 TSX Venture 50** ranking (published February 2026, based on 2025 performance). The ranking is updated annually — check [tsx.com/venture50](https://tsx.com/venture50) for the latest.

## Architecture

```
Claude / MCP client
       │
       │ POST /mcp  (Authorization: Bearer <token>)
       ▼
Modal endpoint  (keep_warm=1, stateless_http=True)
       │
       ├─ BearerAuthMiddleware  →  401 if token invalid
       │
       ├─ FastMCP server
       │       ├─ get_tsxv50_watchlist()   reads /app/top50config.json
       │       ├─ get_stock_info()         yf.Ticker(symbol).info  (per symbol)
       │       ├─ get_stock_price()        yf.Ticker(symbol).info  (per symbol)
       │       ├─ get_stock_history()      yf.download()           (batched)
       │       └─ screen_tsxv50()          ThreadPoolExecutor(10)  (parallel)
       │
       └─ Yahoo Finance (unofficial API, no key required)
```

`keep_warm=1` keeps one container alive to avoid cold-start latency on interactive calls. `stateless_http=True` means each POST is handled independently — no session state — which is required for Modal's request routing model.

## Files

| File | Purpose |
|---|---|
| `src/deployment/modal_mcp_finance.py` | Modal app definition and all MCP tools |
| `top50config.json` | TSXV 50 ticker symbols (update quarterly) |
| `.mcp.json` | MCP client config (not committed — in `.gitignore`) |
| `.env` | `FINANCE_MCP_TOKEN`, `MODAL_WORKSPACE`, `MODAL_PROJECT` |
