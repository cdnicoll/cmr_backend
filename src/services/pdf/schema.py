"""Pydantic models for the TSXV50 report_json contract.

Mirrors _local/pdf-generation/2026-06-11-tsxv50-report-json-schema.md — any field
change here must update that doc (and vice versa).
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

Category = Literal[
    "Gold",
    "Copper & Base Metals",
    "Royalty & Streaming",
    "Silver",
    "Lithium",
    "Uranium",
    "Critical Minerals & Other",
    "Unclassified",
]

# Display order for the master list and category sections.
SECTOR_ORDER: list[str] = [
    "Gold",
    "Copper & Base Metals",
    "Royalty & Streaming",
    "Silver",
    "Lithium",
    "Uranium",
    "Critical Minerals & Other",
    "Unclassified",
]


class Meta(BaseModel):
    publication: str
    report_title: str
    edition_tagline: str
    period_label: str
    data_as_of: date
    currency: str = "CAD"
    cover_image: str | None = None


class Section(BaseModel):
    subhead: str
    body: str


class Introduction(BaseModel):
    sections: list[Section] = Field(min_length=1)


class MasterListEntry(BaseModel):
    rank: int = Field(ge=1)
    company: str
    ticker: str
    category: Category
    market_cap_cad_mn: float


class ChartPoint(BaseModel):
    t: date
    v: float


class ChartSeries(BaseModel):
    name: str
    points: list[ChartPoint] = Field(min_length=2)


class Chart(BaseModel):
    title: str
    type: Literal["line"]
    x_label: str = ""
    y_label: str = ""
    series: list[ChartSeries] = Field(min_length=1)


class CompanyTable(BaseModel):
    main_regions: str
    market_cap_cad_mn: float
    price_cad: float
    wk52_high_cad: float
    wk52_low_cad: float
    chg_3mo_pct: float | None = None
    chg_12mo_pct: float | None = None
    pb: float | None = None
    upside_to_target_pct: float | None = None


class Blurbs(BaseModel):
    company: str
    recent_operations: str
    finances: str
    outlook: str


class Company(BaseModel):
    name: str
    ticker: str
    table: CompanyTable
    subhead: str
    blurbs: Blurbs


class LimitedActivityEntry(BaseModel):
    """A quiet company covered by a one-line note instead of a full profile.
    It keeps its master_list row; only the profile is compressed."""

    name: str
    ticker: str
    note: str


class CategoryBlock(BaseModel):
    category: Category
    tagline: str
    intro: Introduction
    # Optional: the commodity-series source is an upstream gap; a category
    # without a chart renders without its figure rather than failing.
    chart: Chart | None = None
    companies: list[Company] = Field(default_factory=list)
    limited_activity: list[LimitedActivityEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_content(self) -> "CategoryBlock":
        if not self.companies and not self.limited_activity:
            raise ValueError(
                "category block must have at least one company or limited_activity entry"
            )
        return self


class GlossaryEntry(BaseModel):
    term: str
    definition: str


class Report(BaseModel):
    meta: Meta
    introduction: Introduction
    master_list: list[MasterListEntry] = Field(min_length=1)
    categories: list[CategoryBlock] = Field(min_length=1)
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    disclaimer: str

    @model_validator(mode="after")
    def master_list_matches_categories(self) -> "Report":
        """Cross-checks master_list against every category block's companies and
        limited_activity entries (issue #2): every master_list row must have exactly
        one matching entry across categories (by ticker — company/name fields differ
        between MasterListEntry and Company/LimitedActivityEntry, so ticker is the
        only reliable join key), no ticker may repeat anywhere in the payload, and
        ranks must be contiguous starting at 1. This is what closes the 2026-07-26
        truncated-payload gap: a partial payload (missing categories, duplicate
        tail rows) must fail here instead of rendering a confident wrong PDF.
        Collects every violation before raising, so a bad payload is diagnosed in
        one round-trip instead of one error at a time."""
        issues: list[str] = []

        category_ticker_counts: dict[str, int] = {}
        for block in self.categories:
            for entry in [*block.companies, *block.limited_activity]:
                category_ticker_counts[entry.ticker] = (
                    category_ticker_counts.get(entry.ticker, 0) + 1
                )

        duplicate_category_tickers = sorted(
            ticker for ticker, count in category_ticker_counts.items() if count > 1
        )
        if duplicate_category_tickers:
            issues.append(
                f"duplicate ticker(s) across categories: {duplicate_category_tickers}"
            )

        master_ticker_counts: dict[str, int] = {}
        ranks: list[int] = []
        for entry in self.master_list:
            master_ticker_counts[entry.ticker] = (
                master_ticker_counts.get(entry.ticker, 0) + 1
            )
            ranks.append(entry.rank)
            if entry.ticker not in category_ticker_counts:
                issues.append(
                    f"master_list rank {entry.rank} ({entry.ticker}) has no matching "
                    "company or limited_activity entry in categories"
                )

        duplicate_master_tickers = sorted(
            ticker for ticker, count in master_ticker_counts.items() if count > 1
        )
        if duplicate_master_tickers:
            issues.append(f"duplicate ticker(s) in master_list: {duplicate_master_tickers}")

        orphaned_category_tickers = sorted(
            set(category_ticker_counts) - set(master_ticker_counts)
        )
        if orphaned_category_tickers:
            issues.append(
                "categories contain ticker(s) with no master_list entry: "
                f"{orphaned_category_tickers}"
            )

        sorted_ranks = sorted(ranks)
        if sorted_ranks != list(range(1, len(sorted_ranks) + 1)):
            issues.append(
                f"master_list ranks must be contiguous starting at 1; got {sorted_ranks}"
            )

        if issues:
            raise ValueError("; ".join(issues))
        return self


class ReportValidationError(Exception):
    """report_json failed schema validation; carries structured issues for the agent."""

    def __init__(self, issues: list[dict]):
        self.issues = issues
        super().__init__(f"report_json failed validation ({len(issues)} issue(s))")

    def to_dict(self) -> dict:
        return {"error": {"type": "validation_error", "issues": self.issues}}


def validate_report(report_json: dict) -> Report:
    """Validate report_json against the contract; raise ReportValidationError on failure."""
    if not isinstance(report_json, dict):
        raise ReportValidationError(
            [{"path": "", "message": "report_json must be a JSON object"}]
        )
    try:
        return Report.model_validate(report_json)
    except ValidationError as e:
        issues = [
            {"path": ".".join(str(loc) for loc in err["loc"]), "message": err["msg"]}
            for err in e.errors()
        ]
        raise ReportValidationError(issues) from e
