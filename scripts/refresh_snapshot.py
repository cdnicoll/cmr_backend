#!/usr/bin/env python3
"""Validate and insert a TSXV50 watchlist snapshot.

Every symbol is checked against Yahoo Finance before anything is written, so
dead tickers (delistings, TSX uplistings, renames) are caught at refresh time
instead of surfacing as blank companies in a generated report.

Usage:
    python scripts/refresh_snapshot.py entries.json           # dry run: validate only
    python scripts/refresh_snapshot.py entries.json --apply   # validate, then insert

entries.json is a JSON array of {"symbol", "name", "category"} objects, the
same shape as the POST /api/v1/tsxv50/snapshot body. Requires dev deps
(yfinance): `uv sync --dev`.

Checks per symbol:
- Symbol resolves on Yahoo (has a name and a price). If a .V symbol is dead,
  the .TO variant is tried and a swap is suggested (uplisting case).
- Yahoo's company name is reported when it differs from the entry name
  (rename case, warning only).
- Exactly 50 unique symbols, none Unclassified.
"""
import argparse
import asyncio
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import yfinance as yf

from src.api.schemas.tsxv50 import SnapshotRequest


def _lookup(symbol: str) -> dict:
    """Return {names, price} for a symbol, or empty values if it doesn't resolve."""
    try:
        info = yf.Ticker(symbol).info
        return {
            "names": [n for n in (info.get("shortName"), info.get("longName")) if n],
            "price": info.get("regularMarketPrice") or info.get("currentPrice"),
        }
    except Exception:
        return {"names": [], "price": None}


def _norm(name: str) -> str:
    return "".join(ch for ch in name.casefold() if ch.isalnum())


def _names_match(entry_name: str, yahoo_names: list[str]) -> bool:
    # Yahoo shortName is uppercase, unpunctuated, and truncated (~31 chars),
    # so compare normalized prefixes against both short and long names.
    a = _norm(entry_name)
    return any(a.startswith(_norm(y)) or _norm(y).startswith(a) for y in yahoo_names)


def validate(entries: list[dict]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors block the insert; warnings don't."""
    errors: list[str] = []
    warnings: list[str] = []

    symbols = [e["symbol"] for e in entries]
    if len(entries) != 50:
        errors.append(f"expected 50 entries, got {len(entries)}")
    if len(set(symbols)) != len(symbols):
        dupes = sorted({s for s in symbols if symbols.count(s) > 1})
        errors.append(f"duplicate symbols: {', '.join(dupes)}")
    for e in entries:
        if e["category"] == "Unclassified":
            errors.append(f"{e['symbol']}: category is Unclassified — classify before refresh")

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = dict(zip(symbols, pool.map(_lookup, symbols)))

    for e in entries:
        symbol, live = e["symbol"], results[e["symbol"]]
        if live["price"] is None:
            if symbol.endswith(".V"):
                to_variant = symbol[:-2] + ".TO"
                alt = _lookup(to_variant)
                if alt["price"] is not None:
                    errors.append(
                        f"{symbol}: no data on Yahoo, but {to_variant} resolves "
                        f"({alt['names'][0] if alt['names'] else '?'}) — likely uplisted to the TSX; use {to_variant}"
                    )
                    continue
            errors.append(f"{symbol}: no data on Yahoo (delisted or bad symbol?)")
        elif live["names"] and not _names_match(e["name"], live["names"]):
            warnings.append(
                f"{symbol}: entry name '{e['name']}' vs Yahoo '{live['names'][0]}' — possible rename"
            )

    return errors, warnings


async def _insert(entries: list[dict]) -> None:
    from src.services.supabase.tsxv50_dao import get_latest_snapshot, insert_snapshot_entries

    before = await get_latest_snapshot()
    if before:
        print(f"previous snapshot: id={before['id']} created_at={before['created_at']}")
    row = await insert_snapshot_entries(entries)
    print(f"inserted snapshot: id={row['id']} created_at={row['created_at']} entries={len(row['entries'])}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entries_file", help="JSON array of {symbol, name, category}")
    parser.add_argument("--apply", action="store_true", help="insert after validation (default: dry run)")
    args = parser.parse_args()

    with open(args.entries_file) as f:
        entries = json.load(f)

    # Reuse the API schema so script and endpoint enforce identical shape rules.
    SnapshotRequest(entries=entries)

    errors, warnings = validate(entries)
    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        print(f"\n{len(errors)} error(s) — nothing written.")
        return 1

    print(f"all {len(entries)} symbols resolve on Yahoo Finance.")
    if not args.apply:
        print("dry run complete — rerun with --apply to insert.")
        return 0

    asyncio.run(_insert(entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
