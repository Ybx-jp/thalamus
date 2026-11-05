"""`render_rows` must render a map row whose keys are not strings.

Corpus record: issue #384. `json.dumps(default=str)` converts values it cannot
serialise but not dict keys, so a `group()` keyed by a list — which the driver
returns as a dict with tuple keys — raised TypeError out of `memory_query` instead
of rendering. `_json_keys` now stringifies every key JSON cannot hold, recursively.

Controls: a row with plain string keys must render with its keys intact (a fix that
stringified or dropped everything would pass the tuple-key assertion), and a tuple
key nested inside a list inside a map must render too.
"""

from __future__ import annotations

from thalamus.substrate.query import render_rows

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "src/thalamus/substrate/query.py::render_rows"


def run() -> Finding | None:
    problems: list[str] = []

    for label, rows, wanted in (
        ("tuple key", [{("a",): 1}], "('a',)"),
        ("nested tuple key", [{"k": [{("x", "y"): 2}]}], "('x', 'y')"),
        ("int key", [{1: "one"}], "one"),
        ("control: string keys", [{"plain": 3}], '"plain": 3'),
    ):
        try:
            out = render_rows(rows)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{label}: raised {type(exc).__name__}: {exc}")
            continue
        if wanted not in out or "1 row(s)" not in out:
            problems.append(f"{label}: rendered {out!r}, missing {wanted!r}")

    if not problems:
        return None
    return Finding(
        failure_class=FailureClass.COLLAPSED_SENTINEL,
        summary="render_rows raises on a map row with a non-string key instead of "
                "rendering it, so a valid group() traversal returns an exception",
        witness="; ".join(problems),
        site=_SITE,
    )


CASE = Case(
    name="query-render-rows-nonstring-keys",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.COLLAPSED_SENTINEL,),
    summary="render_rows renders a row whose map keys are tuples or ints rather "
            "than raising TypeError",
    run=run,
    issue=384,
    fixed=True,
)
