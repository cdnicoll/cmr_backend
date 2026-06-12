"""Pydantic models for the TSXV50 report_json contract.

Mirrors _local/pdf-generation/2026-06-11-tsxv50-report-json-schema.md — any field
change here must update that doc (and vice versa).
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

Category = Literal[
    "Gold",
    "Copper & Base Metals",
    "Royalty & Streaming",
    "Silver",
    "Lithium",
    "Uranium",
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


class CategoryBlock(BaseModel):
    category: Category
    tagline: str
    intro: Introduction
    # Optional: the commodity-series source is an upstream gap; a category
    # without a chart renders without its figure rather than failing.
    chart: Chart | None = None
    companies: list[Company] = Field(min_length=1)


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
