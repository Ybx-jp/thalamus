"""Pulse web app — serves the dashboard and its two JSON feeds.

Designed to sit behind `tailscale serve --set-path /pulse` (the prefix is
stripped before the request arrives, measured against the /console service), so
every route is root-relative and the frontend fetches relative URLs.

Two cadences, matching what the data can honestly say:
- /api/live — ledger files only, cheap, polled every few seconds;
- /api/report — graph + transcript scan, TTL-cached, rebuilt at most once a
  minute. Graph unreachable degrades to tap-only with `graph_ok: false`, and
  the report's `health` block names it as a failed check the page prints.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from thalamus.pulse import metrics

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).with_name("static")
REPORT_TTL_SECONDS = 60
_REVALIDATE = {"Cache-Control": "no-cache"}


class _ReportCache:
    """Stale-while-revalidate: requests get the last build instantly; one
    background rebuild runs at a time once the TTL lapses."""

    def __init__(self, build, ttl: float = REPORT_TTL_SECONDS):
        self._build = build
        self._ttl = ttl
        self._lock = threading.Lock()
        self._payload: dict | None = None
        self._built_at = 0.0
        self._building = False

    def get(self) -> dict:
        with self._lock:
            fresh = self._payload is not None and (time.time() - self._built_at) < self._ttl
            if fresh or self._building:
                return self._payload or {"building": True}
            self._building = True
        if self._payload is None:
            # First request: build inline so the page never sees an empty report.
            return self._rebuild()
        threading.Thread(target=self._rebuild, daemon=True).start()
        return self._payload

    def _rebuild(self) -> dict:
        try:
            payload = self._build()
        except Exception:  # noqa: BLE001 — the dashboard must outlive a bad build
            logger.exception("Report build failed")
            payload = self._payload or {"graph_ok": False, "error": "report build failed"}
        with self._lock:
            self._payload = payload
            self._built_at = time.time()
            self._building = False
        return payload


def create_pulse_app(
    url: str | None = None,
    project_dir: Path | None = None,
    traces_base: Path | None = None,
    guards_base: Path | None = None,
    conditioning_base: Path | None = None,
    pins_file: Path | None = None,
    profiles_base: Path | None = None,
    projects_base: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Thalamus Pulse", docs_url=None, redoc_url=None)
    # Recorded once, here: the app is created at process start, and this is the
    # commit whose Python the process goes on running whatever the checkout does.
    build = metrics.record_build()

    def build_report() -> dict:
        g = _try_connect(url)
        try:
            return metrics.report_snapshot(
                g,
                project_dir=project_dir,
                traces_base=traces_base,
                guards_base=guards_base,
                conditioning_base=conditioning_base,
                pins_file=pins_file,
                profiles_base=profiles_base,
                projects_base=projects_base,
                build=build,
            )
        finally:
            if g is not None:
                _try_close(g)

    cache = _ReportCache(build_report)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/live")
    def live() -> JSONResponse:
        return JSONResponse(
            metrics.live_snapshot(traces_base=traces_base, pins_file=pins_file)
        )

    @app.get("/api/report")
    def report() -> JSONResponse:
        return JSONResponse(cache.get())

    # The page is one file on purpose. Static files are read per request while the
    # Python is loaded once, so after a pull the page is new and the server is not;
    # a page split across files the old server does not know how to serve would load
    # blank, where one file loads and says the server is stale. `no-cache` makes the
    # browser revalidate every load rather than guess at freshness.
    @app.get("/")
    @app.get("/index.html")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers=_REVALIDATE)

    # PWA install surface and the Plex faces. No service worker by design: Chrome
    # installs from manifest alone, and the plane's stale-shell incident is a whole
    # bug class this dashboard opts out of. Relative URLs throughout — the page
    # lives behind `tailscale serve --set-path /pulse`, which strips the prefix;
    # only the manifest names /pulse/ absolutely (id/scope/start_url). The fonts are
    # pulse's own copies of the console's subsets, so neither surface's static dir
    # reaches into the other's; a missing face falls back to the system stack.
    _assets = {
        "manifest.webmanifest": "application/manifest+json",
        "icon-192.png": "image/png",
        "icon-512.png": "image/png",
        "icon.svg": "image/svg+xml",
        "plex-mono-400.woff2": "font/woff2",
        "plex-mono-600.woff2": "font/woff2",
        "plex-sans-400.woff2": "font/woff2",
        "plex-sans-600.woff2": "font/woff2",
        "PLEX-OFL.txt": "text/plain; charset=utf-8",
    }

    @app.get("/{asset}")
    def static_asset(asset: str) -> FileResponse:
        media_type = _assets.get(asset)
        if media_type is None:
            raise HTTPException(status_code=404)
        return FileResponse(STATIC_DIR / asset, media_type=media_type)

    return app


def _try_connect(url: str | None):
    from thalamus.substrate.writer import DEFAULT_URL, connect

    try:
        return connect(url or DEFAULT_URL)
    except Exception:  # noqa: BLE001 — graph down is a rendered state, not a crash
        logger.warning("Graph unreachable; serving tap-only report")
        return None


def _try_close(g) -> None:
    from thalamus.substrate.writer import close_connection

    try:
        close_connection(g)
    except Exception:  # noqa: BLE001
        pass
