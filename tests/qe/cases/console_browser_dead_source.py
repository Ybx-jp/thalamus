"""A dead jobs source reads as a dead source, not as an empty list.

The jobs source note on the design board: *"a dead source reads as a dead source and not
as an empty list"*; and the config's own contract: *"Empty — the default — means no jobs,
board or app-widget screens; nothing is invented."* (`jobs_source.py`: 502 for a source
that does not answer, 404 for none configured.) The failure is quiet and total: a
console whose source is down shows "no jobs", which an operator reads as "nothing is
scheduled", so a stopped pipeline looks like a quiet week.

For each surface (the jobs page J1, the board page) the case starts three real consoles
and reads the rendered text of the screen's `#main`:

- **A**: a source answering a valid, *empty* collection. This is the control that the
  empty state has words of its own ("The jobs source lists no jobs." / "Nothing pinned
  yet"); without it, a difference between A and B could be two broken screens.
- **B**: a source on a closed port. Must say the source is unreachable ("unreachable")
  and must not show A's empty-state words.
- **C**: no source configured. Must say there is no source ("no jobs source" /
  "not configured") and must not show A's empty-state words or invent a single row.

and then A, B, C must be pairwise different. A screen that paints nothing for any of
them (the text is empty after the wait) is a collapsed sentinel: it cannot be compared.

**Driven red** by mutating a copy of `jobs.js` so `route()` swallows its error and
paints the empty list: B and C then read exactly like A and the case names the equal
strings. Arms with `CONSOLE_UNBUILT_JOBS_PAGE` (J1) / `CONSOLE_UNBUILT_BOARD_PAGE`.
"""

from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_browser import browser, collapsed, finding, source_responder
from ._console_rig import console_rig, dead_port, jobs_source

_NO_SOURCE = re.compile(r"no jobs source|not configured|no source", re.I)


def _main_text(rig_base: str, page_path: str, page) -> str:
    page.goto(rig_base + page_path)
    deadline = time.monotonic() + 8
    text = ""
    while time.monotonic() < deadline:
        text = page.inner_text("#main").strip()
        if text and "loading" not in text.lower():
            break
        time.sleep(0.15)
    time.sleep(0.3)
    return page.inner_text("#main").strip()


def _surface(page_path: str, empty_words: str, empty_world: dict, board: dict | None,
             rows_selector: str) -> Finding | None:
    with tempfile.TemporaryDirectory(prefix="qe-dead-source-") as td:
        tokfile = Path(td) / "token"
        tokfile.write_text("qe-token\n")
        seen: dict[str, tuple[str, int]] = {}

        def read(label: str, extra: tuple[str, ...]) -> None:
            with console_rig(extra_args=extra) as rig:
                with browser(rig.base) as (page, _w):
                    text = _main_text(rig.base, page_path, page)
                    seen[label] = (text, page.locator(rows_selector).count())

        with jobs_source(responder=source_responder(empty_world, board=board)) as src:
            read("A empty source", ("--jobs-source", src.url,
                                    "--jobs-token-file", str(src.token_file)))
        read("B dead source", ("--jobs-source", f"http://127.0.0.1:{dead_port()}",
                               "--jobs-token-file", str(tokfile)))
        read("C no source", ())

    for label, (text, _n) in seen.items():
        if not text:
            return collapsed(f"{page_path} painted nothing for '{label}', so it cannot be "
                             "compared with the other states", f"texts={seen}")
    a, b, c = (seen[k][0] for k in ("A empty source", "B dead source", "C no source"))
    if empty_words.lower() not in a.lower():
        return collapsed(f"the empty-source control on {page_path} does not say "
                         f"{empty_words!r}, so the empty state has no words to be "
                         "confused with", f"A text={a!r}")
    bad = []
    if not re.search(r"unreachable", b, re.I):
        bad.append(f"dead source does not say it is unreachable: {b!r}")
    if empty_words.lower() in b.lower():
        bad.append(f"dead source shows the empty-list words: {b!r}")
    if not _NO_SOURCE.search(c):
        bad.append(f"no-source console does not say there is no source: {c!r}")
    if empty_words.lower() in c.lower() or seen["C no source"][1]:
        bad.append(f"no-source console shows empty-list words or {seen['C no source'][1]} "
                   f"rows: {c!r}")
    if len({a, b, c}) < 3:
        bad.append(f"two states render identically: A={a!r} B={b!r} C={c!r}")
    if bad:
        return finding(
            FailureClass.COLLAPSED_SENTINEL,
            f"{page_path} renders a dead or absent jobs source like (or unlike what it "
            "should against) an empty list",
            "; ".join(bad),
            site="packages/thalamus-console/src/thalamus_console/static/"
                 + page_path.lstrip("/").replace(".html", ".js"))
    return None


def run_jobs() -> Finding | None:
    return _surface("/jobs.html", "lists no jobs", {"jobs": {"groups": [], "summary": ""}},
                    None, ".j-row")


def run_board() -> Finding | None:
    return _surface("/board.html", "Nothing pinned", {}, {"widgets": [], "evals": {}},
                    ".b-card")


CASE = Case(
    name="browser-jobs-page-dead-source-is-not-an-empty-list",
    tier=Tier.BROWSER,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_PLAYWRIGHT,
               Substrate.CONSOLE_UNBUILT_JOBS_API, Substrate.CONSOLE_UNBUILT_JOBS_PAGE),
    classes=(FailureClass.COLLAPSED_SENTINEL,),
    summary="J1 against a dead port says the source is unreachable, with no source says "
            "so, and neither reads like a source that answered with no jobs",
    run=run_jobs,
)

CASE_BOARD = Case(
    name="browser-board-page-dead-source-is-not-an-empty-board",
    tier=Tier.BROWSER,
    substrate=(Substrate.NEEDS_TMUX, Substrate.NEEDS_PLAYWRIGHT,
               Substrate.CONSOLE_UNBUILT_JOBS_API, Substrate.CONSOLE_UNBUILT_BOARD_PAGE),
    classes=(FailureClass.COLLAPSED_SENTINEL,),
    summary="the board against a dead port says the source is unreachable, with no "
            "source says so, and neither reads like an empty board",
    run=run_board,
)

CASES = (CASE, CASE_BOARD)
