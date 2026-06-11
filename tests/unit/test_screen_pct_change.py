"""Unit tests for the screen_tsxv50 percent-change helpers."""
from datetime import date, timedelta

from src.deployment.modal_mcp_finance import _months_ago, _pct_change_from_baseline


def _daily_closes(start: date, values: list[float]) -> list[tuple[date, float]]:
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


def test_months_ago_simple():
    assert _months_ago(date(2026, 6, 11), 3) == date(2026, 3, 11)
    assert _months_ago(date(2026, 6, 11), 12) == date(2025, 6, 11)


def test_months_ago_year_rollover_and_day_clamp():
    assert _months_ago(date(2026, 2, 11), 3) == date(2025, 11, 11)
    # May 31 minus 3 months clamps to Feb 28 (no Feb 31)
    assert _months_ago(date(2026, 5, 31), 3) == date(2026, 2, 28)


def test_pct_change_normal_case():
    # Baseline 100.0 ten days ago, latest 112.5 -> +12.5%
    closes = _daily_closes(date(2026, 6, 1), [100.0] + [105.0] * 9 + [112.5])
    assert _pct_change_from_baseline(closes, date(2026, 6, 1)) == 12.5


def test_pct_change_uses_closest_day_at_or_before_target():
    # Target falls on a weekend gap: June 5 missing, June 4 is the baseline
    closes = [
        (date(2026, 6, 1), 90.0),
        (date(2026, 6, 4), 100.0),
        (date(2026, 6, 8), 110.0),
    ]
    assert _pct_change_from_baseline(closes, date(2026, 6, 5)) == 10.0


def test_pct_change_negative():
    closes = _daily_closes(date(2026, 6, 1), [100.0, 95.0, 91.8])
    assert _pct_change_from_baseline(closes, date(2026, 6, 1)) == -8.2


def test_pct_change_missing_baseline_returns_null():
    # History starts after the target date (new listing) -> None, not 0
    closes = _daily_closes(date(2026, 6, 1), [10.0, 11.0, 12.0])
    assert _pct_change_from_baseline(closes, date(2026, 5, 1)) is None


def test_pct_change_short_history_returns_null():
    closes = [(date(2026, 6, 10), 10.0)]
    assert _pct_change_from_baseline(closes, date(2026, 3, 10)) is None


def test_pct_change_empty_history_returns_null():
    assert _pct_change_from_baseline([], date(2026, 3, 10)) is None


def test_pct_change_zero_baseline_returns_null():
    closes = _daily_closes(date(2026, 6, 1), [0.0, 5.0])
    assert _pct_change_from_baseline(closes, date(2026, 6, 1)) is None
