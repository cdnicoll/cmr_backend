"""Matplotlib chart rendering for the TSXV50 report — SVG strings for HTML inlining."""
import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from src.services.pdf.schema import Chart  # noqa: E402

BRAND_RED = "#CF1F2E"
INK = "#1A1A1A"
MUTED = "#6B6B6B"
GRID = "#DDDDDD"

SERIES_COLORS = [BRAND_RED, MUTED, INK, "#B08D2E"]

# One shared style block so every figure in the document matches.
RC_PARAMS = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 9,
    "text.color": INK,
    "axes.edgecolor": "#999999",
    "axes.labelcolor": MUTED,
    "axes.linewidth": 0.6,
    "axes.grid": True,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "grid.color": GRID,
    "grid.linewidth": 0.5,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.frameon": False,
    "legend.fontsize": 8,
    # Outline text as paths so the PDF doesn't depend on font availability.
    "svg.fonttype": "path",
}


def render_chart_svg(chart: Chart) -> str:
    """Render a line chart to an SVG string (no XML prolog, ready to inline in HTML)."""
    with plt.rc_context(RC_PARAMS):
        fig, ax = plt.subplots(figsize=(7.0, 2.9))
        for i, series in enumerate(chart.series):
            xs = [p.t for p in series.points]
            ys = [p.v for p in series.points]
            ax.plot(
                xs,
                ys,
                color=SERIES_COLORS[i % len(SERIES_COLORS)],
                linewidth=1.6,
                label=series.name,
            )
        if chart.x_label and chart.x_label.lower() != "date":
            ax.set_xlabel(chart.x_label)
        if chart.y_label:
            ax.set_ylabel(chart.y_label)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
        if len(chart.series) > 1:
            ax.legend(loc="upper left")
        fig.tight_layout()

        buf = io.StringIO()
        fig.savefig(buf, format="svg", bbox_inches="tight")
        plt.close(fig)

    svg = buf.getvalue()
    return svg[svg.index("<svg") :]
