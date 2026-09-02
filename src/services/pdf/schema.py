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


def check_master_list_integrity(entries: list[MasterListEntry]) -> list[str]:
    """Mechanical checks on master_list alone: duplicate tickers, non-contiguous
    ranks, and market cap not sorted descending. Shared by set_master_list (Phase 1,
    checked at write time, before Checkpoint 1 ever presents the list) and Report's
    full-payload validator (Phase 3's finalize_report) so both stages enforce the
    same rule instead of Checkpoint 1 resting on the agent's own prose self-check
    (2026-07-28 Billy report: duplicate VIPR.V and an inverted market-cap sort both
    survived to Checkpoint 1 because nothing actually checked master_list before it
    was presented as verified)."""
    issues: list[str] = []

    ticker_counts: dict[str, int] = {}
    for entry in entries:
        ticker_counts[entry.ticker] = ticker_counts.get(entry.ticker, 0) + 1
    duplicates = sorted(ticker for ticker, count in ticker_counts.items() if count > 1)
    if duplicates:
        issues.append(f"duplicate ticker(s) in master_list: {duplicates}")

    ranks = sorted(entry.rank for entry in entries)
    if ranks != list(range(1, len(ranks) + 1)):
        issues.append(f"master_list ranks must be contiguous starting at 1; got {ranks}")

    by_rank = sorted(entries, key=lambda e: e.rank)
    for prev, curr in zip(by_rank, by_rank[1:]):
        if curr.market_cap_cad_mn > prev.market_cap_cad_mn:
            issues.append(
                "master_list not sorted by market_cap_cad_mn descending: rank "
                f"{curr.rank} ({curr.ticker}, {curr.market_cap_cad_mn}) exceeds rank "
                f"{prev.rank} ({prev.ticker}, {prev.market_cap_cad_mn})"
            )

    return issues


RESEARCH_RESULTS = ("developments", "quiet", "unavailable")


def _research_companies(research: dict) -> list[dict]:
    """Pull the per-company entries out of a research object.

    Accepts either `{"companies": [...]}` or `{"companies": {"NAU.V": {...}}}`,
    because the research object is agent-authored jsonb and the 2026-08-25 run
    found three researchers producing three shapes for the same idea. The
    container is tolerated; what each entry must carry is not.
    """
    companies = research.get("companies")
    if isinstance(companies, dict):
        out = []
        for key, entry in companies.items():
            if isinstance(entry, dict):
                out.append({**entry, "ticker": entry.get("ticker") or key})
        return out
    if isinstance(companies, list):
        return [entry for entry in companies if isinstance(entry, dict)]
    return []


def check_research_verification(category: str, research: dict) -> tuple[list[str], dict]:
    """Mechanical check that a category's research records what was actually checked.

    Returns (issues, summary). `summary` counts what the research claims:
    {total, checked, developments, quiet, unavailable}.

    Why this exists (2026-09-02, Billy's August-update run): the period pass came
    back with essentially no August releases, an audit found two material releases
    it had missed, and when asked to independently verify all 50 companies the
    agent reported 50/50 complete. Most of those had been carried forward from the
    original research rather than checked. Challenged, it said 10 verified and 40
    not. Asked to finish, it reported 50/50 again while its own reasoning said it
    could not reach the sources. Nothing in the system could contradict any of it,
    because "verified" was a sentence in a chat message rather than a record.

    This does not make the agent truthful — a boolean can always be asserted. What
    it does is make the count mechanical: verification becomes N per-company
    records rather than one free-text claim, a company said to have developments
    must carry a dated source to back it, and the tool response rather than the
    agent's narration is what the operator sees. Same move as
    check_master_list_integrity: the gate is at the write boundary, so an
    unverifiable claim never becomes stored state.
    """
    issues: list[str] = []
    entries = _research_companies(research)
    summary = {"total": 0, "checked": 0, "developments": 0, "quiet": 0, "unavailable": 0}

    if not entries:
        issues.append(
            f"{category}: research carries no company entries — expected "
            '`companies` as a list of objects or an object keyed by ticker'
        )
        return issues, summary

    summary["total"] = len(entries)
    for index, entry in enumerate(entries):
        ticker = entry.get("ticker")
        label = ticker or f"companies[{index}]"
        if not ticker:
            issues.append(
                f"{category}: {label} has no `ticker` (the key is `ticker`, not "
                "`symbol` or `company` — pinned 2026-08-25 after three researchers "
                "used three different names)"
            )

        verification = entry.get("verification")
        if not isinstance(verification, dict):
            issues.append(
                f"{category}: {label} has no `verification` object — every company "
                "needs {checked, result, sources} recording what the period pass "
                "actually did"
            )
            continue

        result = verification.get("result")
        if result not in RESEARCH_RESULTS:
            issues.append(
                f"{category}: {label} verification.result is {result!r}, expected "
                f"one of {list(RESEARCH_RESULTS)}"
            )
            continue
        summary[result] += 1

        checked = verification.get("checked")
        if checked is True:
            summary["checked"] += 1
        elif result != "unavailable":
            issues.append(
                f"{category}: {label} has result {result!r} but checked is "
                f"{checked!r} — a company can only be reported quiet or advancing "
                "if its period pass actually ran"
            )

        sources = verification.get("sources") or []
        if result == "developments":
            dated = [
                s
                for s in sources
                if isinstance(s, dict) and s.get("url") and s.get("date")
            ]
            if not dated:
                issues.append(
                    f"{category}: {label} reports developments with no dated source "
                    "— every claimed development needs at least one {url, date}, or "
                    "the finding is an assertion rather than a citation"
                )

    return issues, summary


def check_synthesis_ready(categories: dict) -> tuple[list[str], dict]:
    """Refuse synthesis until every category's research is present and complete.

    The old rule was that synthesis "requires every category's research to exist".
    Existence is not verification: a research object asserting fifty unchecked
    companies satisfied it completely, which is how the 2026-09-02 run reached the
    edge of synthesising against research nobody had validated.

    Returns (issues, totals) so the refusal can state the real numbers rather than
    leaving the operator to take the agent's word for them.
    """
    issues: list[str] = []
    totals = {"total": 0, "checked": 0, "developments": 0, "quiet": 0, "unavailable": 0}

    researched = {
        name: block.get("research")
        for name, block in (categories or {}).items()
        if isinstance(block, dict) and block.get("research")
    }
    if not researched:
        return (
            ["no category research exists yet — synthesis runs after every category"],
            totals,
        )

    for name, research in sorted(researched.items()):
        cat_issues, summary = check_research_verification(name, research)
        issues.extend(cat_issues)
        for key in totals:
            totals[key] += summary[key]
        if summary["unavailable"]:
            issues.append(
                f"{name}: {summary['unavailable']} company(ies) marked unavailable "
                "— retrieval failed for them, so their status is unknown, not quiet"
            )

    unchecked = totals["total"] - totals["checked"]
    if unchecked:
        issues.append(
            f"{unchecked} of {totals['total']} companies have no completed period "
            "pass; synthesis needs all of them"
        )
    return issues, totals


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
        only reliable join key; Unclassified rows are exempt, being master-list-only
        by contract), no ticker may repeat anywhere in the payload, ranks must be
        contiguous starting at 1, and market_cap_cad_mn must be sorted descending
        (delegated to check_master_list_integrity, shared with set_master_list's
        write-time check). This is what closes the 2026-07-26 truncated-payload gap:
        a partial payload (missing categories, duplicate tail rows) must fail here
        instead of rendering a confident wrong PDF. Collects every violation before
        raising, so a bad payload is diagnosed in one round-trip instead of one error
        at a time."""
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

        master_tickers = {entry.ticker for entry in self.master_list}
        for entry in self.master_list:
            # Unclassified rows are master-list-only by contract: non-mining
            # constituents of the source list keep their rank but get no
            # category section (agents/main.md Phase 1, per Travis).
            if (
                entry.ticker not in category_ticker_counts
                and entry.category != "Unclassified"
            ):
                issues.append(
                    f"master_list rank {entry.rank} ({entry.ticker}) has no matching "
                    "company or limited_activity entry in categories"
                )

        orphaned_category_tickers = sorted(set(category_ticker_counts) - master_tickers)
        if orphaned_category_tickers:
            issues.append(
                "categories contain ticker(s) with no master_list entry: "
                f"{orphaned_category_tickers}"
            )

        issues.extend(check_master_list_integrity(self.master_list))

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
