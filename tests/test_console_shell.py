"""
The console's shell: what `serve()` boots, and what the shipped client asks for.

Interfaces: thalamus.console.server.serve and its STATIC table, against the files
under thalamus/console/static/.
Infrastructure: a real socket on a real port and a real `git ls-files`; no tmux, no
graph, no browser.
Scope: the two failures that never reach a handler test. The first is `serve()`
itself — every other test in this suite constructs `ThreadingHTTPServer` and
`Handler` by hand, so a console that cannot boot, or whose index page 404s, passes
the suite. The second is the gap between what the client references and what the
repository ships: the service worker's `install` fails *as a whole* if any precached
entry 404s, so one untracked asset disables the PWA on a clean clone, offline shell
and web fonts together, with nothing red anywhere.
"""

import json
import re
import socket
import subprocess
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from thalamus.console import server
from thalamus.console.server import STATIC, STATIC_DIR, Config

REPO_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _tracked() -> set[Path]:
    """Paths under `static/` that git actually has, as absolute paths.

    `git ls-files` rather than a directory walk: the whole question is whether a
    file present on the operator's disk would also be present on a clean clone,
    and a walk answers that with the operator's disk.
    """
    listed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", str(STATIC_DIR)],
        capture_output=True, text=True, timeout=30, check=True,
    ).stdout.split()
    return {(REPO_ROOT / line).resolve() for line in listed}


# ---- what the shipped client asks for ----


def _shell_entries() -> list[str]:
    """The service worker's precache list, read out of the shipped sw.js."""
    source = (STATIC_DIR / "sw.js").read_text()
    body = re.search(r"const SHELL = \[(.*?)\];", source, re.S)
    assert body, "sw.js no longer declares `const SHELL = [...]` — the guard reads it by name"
    return [m.group(1) for m in re.finditer(r'"([^"]+)"', body.group(1))]


def _referenced() -> dict[str, str]:
    """Every asset URL the shipped shell references, mapped to what references it.

    Three surfaces, because a file can be dropped from any one of them and the
    others keep working: the service worker precache, the manifest's icons, and
    the stylesheet's `@font-face` sources.
    """
    refs = {entry: "sw.js SHELL" for entry in _shell_entries()}
    manifest = json.loads((STATIC_DIR / "manifest.webmanifest").read_text())
    for icon in manifest["icons"]:
        refs.setdefault(icon["src"], "manifest.webmanifest icons")
    for url in re.findall(r'url\("([^"]+)"\)', (STATIC_DIR / "style.css").read_text()):
        refs.setdefault(url, "style.css @font-face")
    return refs


def test_every_asset_the_shell_references_is_tracked_in_git():
    """On disk is not the property. In git is.

    A `.gitignore` line or a forgotten `git add` leaves the asset working on the
    machine that authored it and absent from every clone — which is exactly how
    four `plex-*.woff2` files and the OFL licence shipped broken once already. The
    cost is not one missing font: `addAll` rejects if any entry 404s, so `install`
    fails, and the service worker never registers at all.
    """
    tracked = _tracked()
    missing = {url: by for url, by in _referenced().items()
               if not url.endswith("/") and (STATIC_DIR / url).resolve() not in tracked}

    assert not missing, f"referenced by the shipped shell but not tracked in git: {missing}"


def test_every_asset_the_shell_references_is_served():
    """The other half of the precache contract: tracked *and* on the allowlist.

    `Handler` serves the `STATIC` table and nothing else, so a file that is in the
    repository and not in that table 404s at request time and fails `install` in
    exactly the same way as one that was never committed.
    """
    unserved = {url: by for url, by in _referenced().items()
                if url not in ("./",) and f"/{url}" not in STATIC}

    assert not unserved, f"referenced by the shipped shell but not in STATIC: {unserved}"


def test_the_static_table_names_files_that_exist():
    """The table is hand-written; a rename on disk does not update it."""
    absent = {route: name for route, (name, _) in STATIC.items()
              if not (STATIC_DIR / name).is_file()}

    assert not absent, f"routed by STATIC with no file behind them: {absent}"


# ---- what `serve()` boots ----


@pytest.fixture
def booted(tmp_path):
    """A console brought up through `serve()` — the real entry point, once.

    Constructing `ThreadingHTTPServer` and `Handler` directly, as the handler tests
    do, skips everything `serve()` does with them: attaching the config the handlers
    read, the fetch thread, the bind. `thalamus console` is the command this release
    is named for and its only covered case was the one where it refuses to start.

    `fetch_interval_s=0` keeps the background fetch thread out of the test; the port
    is picked and released rather than passed as 0, because `serve()` takes a port
    and never reports back which one it got.
    """
    port = _free_port()
    project = tmp_path / "code" / "alpha"
    project.mkdir(parents=True)
    (project / ".git").mkdir()
    cfg = Config(project_root=project, fetch_interval_s=0)

    booted_server: list = []
    real = server.ThreadingHTTPServer

    class Recording(real):  # type: ignore[misc, valid-type]
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            booted_server.append(self)

    server.ThreadingHTTPServer = Recording
    thread = threading.Thread(target=server.serve,
                              kwargs={"cfg": cfg, "host": "127.0.0.1", "port": port},
                              daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not booted_server:
            time.sleep(0.02)
        assert booted_server, "serve() did not bind within 10s"
        yield port
    finally:
        server.ThreadingHTTPServer = real
        if booted_server:
            booted_server[0].shutdown()
        thread.join(timeout=10)


def _fetch(port: int, path: str) -> tuple[int, str, bytes]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path)
    response = conn.getresponse()
    body = response.read()
    ctype = response.getheader("Content-Type") or ""
    conn.close()
    return response.status, ctype, body


def test_serve_answers_on_the_port_it_was_given(booted):
    """The bind is the whole claim: a console that cannot boot cannot be reached."""
    status, ctype, body = _fetch(booted, "/")

    assert status == 200
    assert ctype.startswith("text/html")
    assert b"<html" in body.lower()


@pytest.mark.parametrize("route", sorted(STATIC))
def test_every_static_route_is_served_over_http(booted, route):
    """Read through the socket, not off the disk.

    A route can be in the table, backed by a real file, and still not reach a
    client — a content type the handler cannot resolve, a read mode that mangles a
    woff2, a path escape check that rejects its own entry. The fonts matter most:
    they are the entries most recently found missing, and the ones the precache
    fails on.
    """
    expected_type = STATIC[route][1]

    status, ctype, body = _fetch(booted, route)

    assert status == 200, f"{route} returned {status}"
    assert ctype == expected_type
    assert body, f"{route} served an empty body"


def test_an_unrouted_path_is_a_404_and_not_a_traceback(booted):
    """The other half: `STATIC` is an allowlist, and it holds under a real request."""
    status, _, _ = _fetch(booted, "/../server.py")

    assert status == 404
