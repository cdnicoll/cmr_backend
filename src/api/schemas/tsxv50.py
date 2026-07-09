"""TSXV50 snapshot API schemas."""
from typing import Literal

from pydantic import BaseModel, field_validator


class SnapshotEntry(BaseModel):
    """A single TSXV50 watchlist entry: symbol, display name, and sector category."""

    symbol: str
    name: str
    category: Literal[
        "Gold",
        "Copper & Base Metals",
        "Royalty & Streaming",
        "Silver",
        "Lithium",
        "Uranium",
        "Critical Minerals & Other",
        "Unclassified",
    ]

    @field_validator("symbol")
    @classmethod
    def symbol_has_v_suffix(cls, v: str) -> str:
        if not v.endswith(".V"):
            raise ValueError("symbol must end with '.V'")
        return v

    @field_validator("name")
    @classmethod
    def name_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("name must not be empty")
        return v


class SnapshotRequest(BaseModel):
    """Request body for POST /api/v1/tsxv50/snapshot."""

    entries: list[SnapshotEntry]

    @field_validator("entries")
    @classmethod
    def entries_non_empty(cls, v: list[SnapshotEntry]) -> list[SnapshotEntry]:
        if not v:
            raise ValueError("entries must not be empty")
        return v
