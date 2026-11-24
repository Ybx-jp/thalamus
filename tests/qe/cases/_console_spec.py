"""Which console surfaces the design board specifies, and which of them `src/` serves.

The console's design lives in Penpot, file *Thalamus console — living design space*
(`f94d4a33-8a31-8063-8008-84d80d45e63d`), on three pages: the repos view (page 1,
frames 01–59 with the index at `00a` and the redlines at `08`), *Jobs — pipelines,
runs and git* (J1–J6, D1, handoff note N1) and *Board — widgets* (B1–B4, D2, the
chess App widget C1–C6, handoff notes N2 and N3). Cases written from it cite a frame
by its number, the way the board's own index does.

Most of that is unbuilt as this is written, and the cases against it are written
anyway: the oracle should exist before the code it judges, not be fitted to it
afterwards. Each such case declares a `Substrate.CONSOLE_UNBUILT_*` member, so it
SKIPS — naming the surface it waits for — until the probe below sees the surface in
the tree, and arms itself in the commit that lands it.

**The failure that design invites** is a skip that outlives its reason: the surface
lands under a name the probe does not look for, and its cases skip green forever.
`CASE` below is the guard. Each surface carries a second, looser probe — a hint that
something of it has been built — and a hint without an armed probe is red, naming the
surface. Probe and hint are deliberately different evidence (a served route versus a
word in the client), so renaming the route trips the guard rather than both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ._console_rig import CONSOLE_PKG, SERVER_PY, STATIC_DIR

PENPOT_FILE = "f94d4a33-8a31-8063-8008-84d80d45e63d"


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _served_static(name: str) -> bool:
    """A page is served when the file exists AND `STATIC` routes it."""
    return (STATIC_DIR / name).exists() and f'"/{name}"' in _read(SERVER_PY)


def _client_text() -> str:
    return "\n".join(_read(p) for p in sorted(STATIC_DIR.glob("*"))
                     if p.suffix in (".js", ".html"))


@dataclass(frozen=True)
class Surface:
    key: str
    board: str  # where on the board it is specified

    def served(self) -> bool:
        server = _read(SERVER_PY)
        if self.key == "jobs-api":
            return '"/api/jobs/"' in server
        if self.key == "jobs-page":
            return _served_static("jobs.html")
        if self.key == "board-page":
            return _served_static("board.html")
        if self.key == "repos":
            return (bool(re.search(r'"/api/(repos|checkouts?)\b', server))
                    or _served_static("repos.html"))
        raise KeyError(self.key)

    def hint(self) -> str:
        """Evidence that some of this surface exists, or "" for none."""
        if self.key == "jobs-api":
            if (CONSOLE_PKG / "jobs_source.py").exists():
                return "thalamus_console/jobs_source.py exists"
            if "--jobs-source" in _read(CONSOLE_PKG / "plugin.py"):
                return "plugin.py declares --jobs-source"
        if self.key == "jobs-page":
            if any("jobs" in p.name for p in STATIC_DIR.glob("*")):
                return "a static file is named for jobs"
        if self.key == "board-page":
            if any("board" in p.name for p in STATIC_DIR.glob("*")):
                return "a static file is named for the board"
        if self.key == "repos":
            text = _client_text()
            # Frame 01: the roster's entry control is the word REPOS, upper case.
            if re.search(r"\bREPOS\b", text):
                return "the client carries the REPOS entry control (frame 01)"
            server = _read(SERVER_PY)
            for route in ("/api/stage", "/api/commit", "/api/push", "/api/upstream"):
                if f'"{route}' in server:
                    return f"server.py routes {route}"
        return ""


SURFACES = {
    "jobs-api": Surface("jobs-api", "N1 — 'The console has no jobs API'; the proxy "
                                    "/api/jobs/ -> <source>/v1/console/"),
    "jobs-page": Surface("jobs-page", "Jobs page, J1–J6 and D1"),
    "board-page": Surface("board-page", "Board page, B1–B4, D2, C1–C6"),
    "repos": Surface("repos", "page 1, frames 01–59; redlines at 08"),
}


def surface_served(key: str) -> bool:
    return SURFACES[key].served()
