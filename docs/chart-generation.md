# TSXV50 Report Chart Generation

How a commodity price chart gets from Yahoo Finance into a rendered PDF figure: the MCP pull, the Supabase draft row that carries it, and the Python that draws it.

Scope is `categories[].chart` only. Figure 1 (the master list table) is plain HTML, not a chart.

## The path end to end

```
Yahoo Finance
  │  yfinance.download(period="2y", interval="1wk")
  ▼
CMR-Finance-MCP  ·  get_stock_history            src/deployment/modal_mcp_finance.py:261
  │  agent trims to 52 weekly closes, builds the chart object
  ▼
CMR-Finance-MCP  ·  add_category                 src/deployment/modal_mcp_finance.py:474
  │  jsonb merge into one category key
  ▼
Supabase Postgres  ·  tsxv50_report_drafts.categories (jsonb)
  │  read back by render_report
  ▼
CMR-Finance-MCP  ·  _assemble_report_json        src/deployment/modal_mcp_finance.py:351
  │  cross-app Modal call with the assembled report_json
  ▼
CMR-PDF  ·  generate_pdf                         src/deployment/modal_pdf.py:45
  │  pydantic validate → matplotlib SVG → Jinja2 → WeasyPrint
  ▼
Supabase Storage  ·  bucket tsxv50-reports       src/services/pdf/storage.py:10
  │
  ▼
signed URL (30 days), also written to the draft row's pdf_url
```

Two Modal apps, one Supabase project. The MCP app never imports matplotlib or WeasyPrint; the PDF app never talks to Yahoo.

## Stage 1: pulling the series

`get_stock_history(symbols, period, interval)` wraps a single batched `yfinance.download`:

```python
raw = yf.download(
    symbols, period=period, interval=interval,
    auto_adjust=True, progress=False, group_by="ticker",
)
```

Details that matter:

- **`group_by="ticker"`** keys the column MultiIndex by symbol. The yfinance default keys by price field, which made `raw[symbol]` a `KeyError`. This was the batching bug fixed in `59d827f`.
- **`auto_adjust=True`** returns adjusted closes, so splits and dividends are already folded in.
- **Per symbol failures are isolated**: a symbol that raises lands as `result[symbol] = {"error": ...}` rather than failing the whole call. A caller must check for that key before reading records.
- Dates are stringified to `%Y-%m-%d` server side, so the response is JSON safe.
- Response records may carry plain keys (`Date`, `Close`) or symbol suffixed keys (`Date,`, `Close,GC=F`) depending on the deployed pandas/yfinance pairing. Chart building code should handle both.

The `chart-patterns` skill mandates `period="2y", interval="1wk"`, roughly 104 weekly bars. Two years is pulled but only twelve months are charted; the extra year exists so pattern analysis has context before the charted window opens. Never request two years of daily bars: about 20x the payload for no analytical gain.

## Stage 2: building the chart payload

The category to symbol map lives in the agent skill, not in this repo (`projects/tsxv-report-agent/skills/chart-patterns/SKILL.md`):

| Category | Symbol | Series label |
|---|---|---|
| Gold | `GC=F` | Gold (COMEX front month, US$/oz) |
| Silver | `SI=F` | Silver (COMEX front month, US$/oz) |
| Copper & Base Metals | `HG=F` | Copper (COMEX front month, US$/lb) |
| Uranium | `U-UN.TO` | Sprott Physical Uranium Trust (TSX, C$) |
| Lithium | `LIT` | Global X Lithium & Battery Tech ETF (US$) |
| Royalty & Streaming | `GC=F` | Gold, the price environment those companies monetize |
| Critical Minerals & Other | none | No chart, too heterogeneous |
| Unclassified | none | No chart |

Royalty & Streaming deliberately reuses the gold series, so a report with both categories renders the same chart twice under different figure numbers. That is intended, not a bug.

The payload shape:

```jsonc
{
  "title": "Gold — 12-Month Price",
  "type": "line",
  "y_label": "US$/oz",
  "series": [
    { "name": "Gold (COMEX front month)",
      "points": [ { "t": "2025-08-04", "v": 3439.10 }, ... ] }
  ]
}
```

Rules the schema does not enforce but the contract does:

- Weekly closes only, `t` ascending, about 52 points.
- **Trim to the report's own `meta.data_as_of`.** A pull made after the period closed returns bars past the report date; leaving them in puts price action in the chart that the prose never saw. Take the last 52 points at or before `data_as_of`.
- Series data comes only from a `get_stock_history` call made in that turn. If a symbol's pull failed, omit the chart rather than invent points.

## Stage 3: persistence in Supabase

Table `public.tsxv50_report_drafts`, one row per `(period_label, draft_slug)` (`migrations/009_tsxv50_report_drafts.sql`). The chart lives inside the `categories` jsonb column at `categories -> <name> -> content -> chart`.

Connection is asyncpg over the Supabase transaction pooler, service role, RLS enabled with no anon or authenticated policies. The DAO bypasses RLS by design, matching every other table in the project.

### The concurrent write merge

Category writes never read-modify-write from Python. `_merge_category_field` (`src/services/supabase/tsxv50_report_drafts_dao.py:431`) does it in one atomic statement:

```sql
UPDATE public.tsxv50_report_drafts
SET categories = jsonb_set(
        categories,
        ARRAY[$3],
        COALESCE(categories -> $3, '{}'::jsonb) || $4::jsonb,
        true
    ),
    updated_at = now()
WHERE period_label = $1 AND draft_slug = $2
```

Each UPDATE is atomic per row and evaluates `categories` on the right hand side from the pre-update value, so parallel category-drafter subagents writing different category keys never clobber each other.

### Write time category validation

`jsonb_set` will happily create a key for any string, so a misspelled or HTML escaped category name silently creates a phantom category. On 2026-08-25 a caller passed the ampersand escaped and the draft held both `Copper & Base Metals` and `Copper &amp; Base Metals`, each with the same two companies. Nothing surfaced until `finalize_report` reported duplicate tickers, a symptom a long way from the cause.

`_validate_category` (`:412`) now rejects any name outside the eight-member `Category` literal before the row is touched.

### Side effects of a category write

`upsert_category_content` also sets `finalize_result = NULL, status = 'in_progress'` in the same statement. A stale "finalized" verdict must never survive an edit, because `render_report` refuses to run on anything but a finalized draft.

## Stage 4: assembly

`_assemble_report_json` (`src/deployment/modal_mcp_finance.py:351`) flattens the draft row into the renderer contract:

```python
for category_name, entry in categories_map.items():
    content = (entry or {}).get("content")
    if content:
        categories.append({"category": category_name, **content})
```

**Nothing here rebuilds a chart.** The stored content is splatted verbatim. Category order in the PDF is the insertion order of the `categories` jsonb object, not `SECTOR_ORDER`; only the master list uses `SECTOR_ORDER`.

`glossary` and `disclaimer` are not stored on the draft. They are static boilerplate passed as arguments to `render_report` at render time.

> **This is the single most common way charts go missing.** `chart` is `Chart | None` in the schema, so a category that omits it validates cleanly and renders prose describing a figure that is not on the page. Every Q2 2026 and August 2026 render between 2026-07-26 and 2026-08-25 shipped with only Figure 1 for exactly this reason: the drafter contract wrongly stated the render phase would rebuild the chart from tool data. Fixed in `be54f94` on the agent side. If a category intro describes price action and no chart sits beside it, this has recurred.

## Stage 5: rendering

Runs in the `CMR-PDF` Modal app, `region="ca"` for Canadian data residency. The image apt-installs `libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz0b`, `libharfbuzz-subset0` and `fonts-liberation`, which are WeasyPrint's native dependencies.

### Validation

`validate_report` (`src/services/pdf/schema.py:253`) runs pydantic v2 over the payload and converts `ValidationError` into a flat `[{path, message}]` list. Chart constraints:

| Model | Constraint |
|---|---|
| `Chart.type` | `Literal["line"]`, the only supported type |
| `Chart.series` | `min_length=1` |
| `ChartSeries.points` | `min_length=2`, a one-point line is rejected |
| `ChartPoint.t` | coerced to `datetime.date` |
| `ChartPoint.v` | `float` |

### Drawing

`render_chart_svg` (`src/services/pdf/charts.py:45`) returns an SVG string, one figure per chart, at `figsize=(7.0, 2.9)` inches.

matplotlib is forced onto the `Agg` backend at import time, before `pyplot` is imported, so it never tries to open a display in the container.

Style is applied through a single shared `RC_PARAMS` dict inside a `plt.rc_context`, so every figure in the document matches and no global state leaks between renders. Series colours cycle `[brand red, muted grey, ink, gold]`; `BRAND_RED = "#A43331"` must stay in sync with `--brand-red` in `templates/report.css`.

Three pieces of non-obvious logic:

1. **`"svg.fonttype": "path"`** outlines all chart text as vector paths. The PDF then carries no font dependency for chart labels, so axis text renders identically whether or not the container has the font installed.

2. **Y axis decimals follow the axis span**, not the value magnitude:

   ```python
   span = ax.get_ylim()[1] - ax.get_ylim()[0]
   decimals = 2 if span < 5 else 1 if span < 50 else 0
   ```

   Copper trades around US$4.50/lb with a span under 5, so it needs two decimals or every tick label rounds to the same integer. Gold at US$4,000/oz needs none.

3. **The x axis formats as `%b %y`** and the `x_label` is suppressed when it is just "Date", since the tick labels already say so. A legend is drawn only when a chart has more than one series, which no current chart does.

The SVG is returned sliced from its first `<svg` tag, dropping matplotlib's XML prolog so it can be inlined directly into HTML.

### Figure numbering and template

`render_html` (`src/services/pdf/renderer.py:85`) pre-renders every chart to SVG and computes figure numbers in one pass:

```python
chart_svgs = [render_chart_svg(cat.chart) if cat.chart else None for cat in report.categories]
```

Figure 1 is always the master list table, so category charts start at 2 and increment only for categories that actually have a chart. Categories without one get `None` and consume no number.

The template inlines the SVG through the `safe` filter, since it is generated markup rather than user text:

```jinja
{% if cat.chart %}
<div class="figure">
  <h4 class="figure-label">Figure {{ figure_numbers[loop.index0] }}: {{ cat.chart.title }}</h4>
  {{ chart_svgs[loop.index0] | safe }}
</div>
{% endif %}
```

`.figure` carries `page-break-inside: avoid` and `.figure-label` carries `page-break-after: avoid`, so WeasyPrint never splits a chart across pages or strands its caption. A chart that will not fit in the remaining space moves whole to the next page, so added charts cost more page growth than their own height. Adding five charts to the Q2 2026 report took it from 19 pages to 22.

WeasyPrint renders with `base_url` set to the template directory so relative asset paths (`assets/cmr-icon.svg`, `assets/cover-default.jpg`) resolve.

## Stage 6: storage

`upload_pdf` (`src/services/pdf/storage.py:10`) uploads to the private `tsxv50-reports` bucket and returns a signed URL valid for 30 days, which covers the edition send window.

**The upload uses `upsert: "true"`.** The filename is derived from the period alone:

```python
filename = f"tsxv50-{period_slug(report.meta.period_label)}.pdf"   # "Q2 2026" → tsxv50-q2-2026.pdf
```

So re-rendering a period overwrites the previously published PDF at the same path. There is no versioning. To produce a variant without destroying the published edition, render locally rather than through `generate_tsxv50_pdf` or `render_report`.

## Libraries

| Library | Where | Purpose |
|---|---|---|
| `yfinance` | Finance MCP | Yahoo Finance price history and fundamentals |
| `pandas` | Finance MCP | MultiIndex frame handling in the batched download |
| `asyncpg` | Finance MCP | Direct Postgres access to the draft store via the transaction pooler |
| `fastmcp` | Finance MCP | MCP server, Streamable HTTP transport |
| `pydantic` v2 | both | `report_json` schema contract and validation |
| `matplotlib` | PDF app | Chart drawing, `Agg` backend, SVG output |
| `jinja2` | PDF app | HTML templating with autoescape |
| `weasyprint` | PDF app | HTML and CSS to PDF |
| `supabase` | PDF app | Storage upload and signed URL |

`src/services/pdf/__init__.py` resolves `render_html`, `render_pdf` and `RenderedReport` lazily through a module `__getattr__`. The Finance MCP image installs neither matplotlib nor WeasyPrint but still calls `validate_report`, so `from src.services.pdf import validate_report` has to succeed without the renderer dependencies present.

## Rendering locally

The PDF path needs WeasyPrint's native libraries, which are not Python packages:

```bash
brew install pango
```

Then point the dynamic linker at Homebrew's lib directory, since `ctypes.util.find_library` does not consult it on macOS:

```bash
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -c "
import json, sys; sys.path.insert(0, '.')
from src.services.pdf.renderer import render_pdf
r = render_pdf(json.load(open('report_json.json')))
open('out.pdf', 'wb').write(r.pdf_bytes)
print(r.page_count, r.filename)
"
```

`render_pdf` returns the bytes and never uploads. `render_html` needs matplotlib but not WeasyPrint, which makes it the fast way to check that charts are present:

```python
html = render_html(validate_report(payload))
html.count("<svg")          # one per chart
```

## Failure modes

| Symptom | Cause |
|---|---|
| Prose describes price action, no figure on the page | `chart` absent from the stored category content. Nothing downstream rebuilds it. |
| Only Figure 1 in the whole PDF | No category stored a chart. Check `categories -> <name> -> content -> chart` in the draft row. |
| Chart present but contradicts the prose | Prose written without the chart visible. The series is right and the sentence is wrong. |
| Y axis ticks all identical | Span based decimal logic hitting a low priced series. Check the `decimals` ladder in `charts.py`. |
| `KeyError` on `raw[symbol]` | `group_by="ticker"` missing from the `yf.download` call. |
| Duplicate tickers reported at finalize | Phantom category from an escaped or misspelled name, now blocked by `_validate_category`. |
| Chart split across a page break | `page-break-inside: avoid` lost from `.figure` in `report.css`. |
| `OSError: cannot load library 'libpango-1.0-0'` | Local render without pango installed. See above. |
| Published PDF replaced unexpectedly | `upsert: "true"` on a period keyed filename. Any re-render of a period overwrites it. |

## Related

- `docs/finance-mcp.md`, the MCP server and its full tool list
- `docs/runbook.md`, deploy procedure and the post-deploy tool verification rule
- `projects/tsxv-report-agent/skills/chart-patterns/SKILL.md`, the symbol map, pattern catalog and writing rules
- `projects/tsxv-report-agent/agents/category-drafter.md`, the contract requiring `chart` when the intro describes one
