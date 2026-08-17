"""Rendering an experiment into something a stranger can read and re-run.

A `lab/` entry is a notebook: it records what happened, for us. An **experiment**
is a publication: it states what was pre-registered, what was measured, what the
null was, and how to regenerate every number in it. The two are different genres
and this module serves only the second.

Three conventions are load-bearing, and each is here because the literature audit
found the corpus violating it:

- **The null rides in the results table, never in the discussion.** "Used 63%
  (permuted 59%, κ 0.10)" is a result; "used 63%" is a number that reads as five
  times more signal than it has.
- **The reproducibility checklist is rendered, not implied.** Pineau et al. (JMLR
  22(164), 2021) — a checklist in prose lets a reader see what is present and never
  what is missing. Rendering absence as a visible state is the same discipline
  docs/03 applies to provenance gaps.
- **The absent artifact is explained.** The graph is one operator's session history
  and is never shipped. An unexplained missing dataset reads as concealment; a
  named threat model reads as a boundary.

Figures are hand-emitted SVG rather than matplotlib rasters. Not asceticism: the
marks carry CSS custom properties, so one chart is correct in both light and dark
without a second render, and the page stays a single self-contained file that
survives being mailed to someone.
"""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# Series colours are referenced through the CSS variables in templates/theme.css so
# a chart re-themes with the page; these names are the contract.
SERIES = [f"var(--series-{i})" for i in range(1, 7)]


@dataclass
class Registration:
    """What was committed to before the data was seen."""

    question: str
    hypothesis: str
    endpoint: str
    falsifier: str
    stopping_rule: str
    registered_at: str = ""
    registered_ref: str = ""


@dataclass
class Provenance:
    """Everything needed to regenerate the page from scratch."""

    snapshot: str
    snapshot_sha256: str
    snapshot_vertices: int
    snapshot_edges: int
    seed: int
    git_ref: str
    command: str
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )


@dataclass
class ChecklistItem:
    requirement: str
    state: str  # "yes" | "no" | "n/a"
    detail: str = ""


# The subset of the ML Reproducibility Checklist that a Thalamus experiment can
# meaningfully answer. Items that do not apply are answered "n/a" *with a reason*,
# never dropped — a checklist you can silently shorten is not a checklist.
DEFAULT_CHECKLIST = [
    "A clear description of the estimand and the estimator used for it",
    "The population the result generalises to, stated as a limit",
    "The null or baseline every reported rate is compared against",
    "An interval on every point estimate, with the resampling unit named",
    "The number of runs, and the seed",
    "The data the analysis read, pinned by name and hash",
    "A command that regenerates every number and figure in this page",
    "Instrument validation: agreement with a reference judgement",
    "Cost reported alongside utility",
    "What was withheld, and why",
]


@dataclass
class Stat:
    """A headline number. `null` and `interval` are optional but rarely absent."""

    label: str
    value: str
    interval: str = ""
    null: str = ""
    note: str = ""


@dataclass
class Section:
    title: str
    body: str  # HTML
    anchor: str = ""


@dataclass
class Experiment:
    slug: str
    title: str
    standfirst: str
    registration: Registration
    provenance: Provenance
    stats: list[Stat]
    sections: list[Section]
    checklist: list[ChecklistItem]
    verdict: str = ""
    verdict_kind: str = "measured"  # measured | null | withdrawn


# ---------------------------------------------------------------------------
# Figures — hand-emitted SVG, themed by CSS custom properties
# ---------------------------------------------------------------------------


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def rate_vs_null(
    rows: list[tuple[str, float, float, tuple[float, float], tuple[float, float]]],
    *,
    title: str,
    width: int = 720,
    row_height: int = 46,
) -> str:
    """Paired bars: the measured rate against its permuted null, per judge.

    rows: (label, rate, null, rate_ci, null_ci) with everything in 0..1.

    The null is drawn as a marked span rather than a second bar of equal weight,
    because it is not a competing series — it is the floor the bar is read against,
    and a reader who takes the two as rival measurements has read the chart wrong.
    """
    left, right, top = 132, 96, 46
    plot = width - left - right
    height = top + row_height * len(rows) + 34
    parts = [
        f'<figure class="fig"><svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{_esc(title)}" class="chart">',
        f'<text x="0" y="18" class="fig-title">{_esc(title)}</text>',
    ]

    for index in range(0, 11, 2):
        x = left + plot * index / 10
        parts.append(f'<line x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{height - 30}" '
                     f'class="grid"/>')
        parts.append(f'<text x="{x:.1f}" y="{height - 12}" class="tick" text-anchor="middle">'
                     f'{index * 10}%</text>')

    for row_index, (label, rate, null, rate_ci, null_ci) in enumerate(rows):
        y = top + row_index * row_height
        bar_h = 16
        parts.append(
            f'<text x="{left - 12}" y="{y + bar_h - 2}" class="row-label" '
            f'text-anchor="end">{_esc(label)}</text>'
        )
        # The null band first, so the bar reads against it.
        n_lo, n_hi = left + plot * null_ci[0], left + plot * null_ci[1]
        parts.append(
            f'<rect x="{n_lo:.1f}" y="{y - 3}" width="{max(2.0, n_hi - n_lo):.1f}" '
            f'height="{bar_h + 6}" class="null-band"/>'
        )
        parts.append(
            f'<line x1="{left + plot * null:.1f}" y1="{y - 5}" '
            f'x2="{left + plot * null:.1f}" y2="{y + bar_h + 5}" class="null-line"/>'
        )
        parts.append(
            f'<rect x="{left}" y="{y}" width="{max(2.0, plot * rate):.1f}" height="{bar_h}" '
            f'rx="4" class="bar" style="fill:{SERIES[row_index % len(SERIES)]}"/>'
        )
        lo, hi = left + plot * rate_ci[0], left + plot * rate_ci[1]
        parts.append(
            f'<line x1="{lo:.1f}" y1="{y + bar_h / 2}" x2="{hi:.1f}" y2="{y + bar_h / 2}" '
            f'class="ci"/>'
            f'<line x1="{lo:.1f}" y1="{y + 2}" x2="{lo:.1f}" y2="{y + bar_h - 2}" class="ci"/>'
            f'<line x1="{hi:.1f}" y1="{y + 2}" x2="{hi:.1f}" y2="{y + bar_h - 2}" class="ci"/>'
        )
        parts.append(
            f'<text x="{width - right + 10}" y="{y + bar_h - 2}" class="value">'
            f'{rate * 100:.1f}%</text>'
        )

    parts.append(
        f'<g transform="translate({left},{height - 30})">'
        f'<rect x="0" y="-9" width="18" height="9" class="null-band"/>'
        f'<text x="24" y="-1" class="legend">permuted null, 95% band</text>'
        f'<line x1="176" y1="-11" x2="176" y2="0" class="ci"/>'
        f'<text x="184" y="-1" class="legend">95% CI, session-clustered</text></g>'
    )
    parts.append("</svg></figure>")
    return "\n".join(parts)


def kappa_strip(rows: list[tuple[str, float]], *, title: str, width: int = 720) -> str:
    """κ per judge on a common axis — the share of headroom actually captured."""
    left, right, top = 132, 60, 44
    plot = width - left - right
    height = top + 30 * len(rows) + 30
    top_value = max(0.35, max((abs(v) for _, v in rows), default=0.1) * 1.25)
    parts = [
        f'<figure class="fig"><svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{_esc(title)}" class="chart">',
        f'<text x="0" y="18" class="fig-title">{_esc(title)}</text>',
    ]
    for step in range(0, 6):
        value = top_value * step / 5
        x = left + plot * step / 5
        parts.append(f'<line x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{height - 26}" class="grid"/>')
        parts.append(f'<text x="{x:.1f}" y="{height - 8}" class="tick" text-anchor="middle">'
                     f'{value:.2f}</text>')
    for index, (label, value) in enumerate(rows):
        y = top + index * 30
        parts.append(f'<text x="{left - 12}" y="{y + 11}" class="row-label" text-anchor="end">'
                     f'{_esc(label)}</text>')
        x = left + plot * max(0.0, value) / top_value
        parts.append(f'<line x1="{left}" y1="{y + 6}" x2="{x:.1f}" y2="{y + 6}" class="lollipop"/>')
        parts.append(f'<circle cx="{x:.1f}" cy="{y + 6}" r="5" class="dot" '
                     f'style="fill:{SERIES[index % len(SERIES)]}"/>')
        parts.append(f'<text x="{x + 12:.1f}" y="{y + 10}" class="value">{value:.3f}</text>')
    parts.append("</svg></figure>")
    return "\n".join(parts)


def table(headers: list[str], rows: list[list[str]], *, caption: str = "") -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell if '<' in str(cell) else _esc(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    cap = f"<caption>{_esc(caption)}</caption>" if caption else ""
    return f'<div class="table-wrap"><table>{cap}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def callout(kind: str, title: str, body: str) -> str:
    """kind: finding | caveat | withdrawal | method"""
    return (
        f'<aside class="callout callout-{_esc(kind)}">'
        f'<p class="callout-title">{_esc(title)}</p>{body}</aside>'
    )


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------


def render(experiment: Experiment) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["pct"] = lambda v: f"{v * 100:.1f}%"
    template = env.get_template("experiment.html.j2")
    theme = (TEMPLATE_DIR / "theme.css").read_text()
    layout = (TEMPLATE_DIR / "experiment.css").read_text()
    return template.render(x=experiment, css=theme + "\n" + layout)


def write(experiment: Experiment, directory: Path, results: dict) -> tuple[Path, Path]:
    """Write results.json and index.html side by side. Both are the deliverable."""
    directory.mkdir(parents=True, exist_ok=True)
    results_path = directory / "results.json"
    results_path.write_text(
        json.dumps(
            {
                "experiment": experiment.slug,
                "title": experiment.title,
                "provenance": asdict(experiment.provenance),
                "registration": asdict(experiment.registration),
                "results": results,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    page_path = directory / "index.html"
    page_path.write_text(render(experiment))
    return results_path, page_path
