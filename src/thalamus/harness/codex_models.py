"""codex's live model catalog — the models it offers now, rather than on the day a list
here was written.

The catalog is the vendor's, and it moves on two clocks: a codex release ships a bundled
copy, and between releases codex re-fetches it and rewrites `$CODEX_HOME/models_cache.json`
stamped with the `client_version` that fetched it. Measured on codex-cli 0.154.0
(2026-09-24): `codex debug models` refreshed that file's `fetched_at` and printed the
same models it holds, while `codex debug models --bundled` left the file untouched and
printed the binary's own copy, which already disagreed with the live one on priorities
and on which models exist.

So the read is: the cache file when it was written by the installed version, else one
`codex debug models`, which also refreshes the file for the next read. That covers a
codex update — the installed version stops matching the cache's — and a catalog change
between updates, which codex's own runs keep writing into the file. Everything here
returns nothing rather than raising when codex is absent or answers badly, and callers
keep their pinned lists for that case.

The catalog has no notion of a model's tier, so which class a slug serves stays a table
in `pin.py`. What the catalog does carry is the vendor's own retirement record — an
`upgrade` naming the model to move to — which `current` follows.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime

from thalamus.harness.codex_transcripts import codex_home

CACHE_FILE = "models_cache.json"


@dataclass(frozen=True)
class CatalogModel:
    slug: str
    priority: int
    # `visibility: "list"` — offered for selection. The rest ship `"hide"`.
    listed: bool
    # The model the vendor says to move to, and when this one stops working.
    upgrade: str = ""
    retires_at: datetime | None = None


def _parse(models: list) -> tuple[CatalogModel, ...]:
    out = []
    for entry in models:
        upgrade = entry.get("upgrade") or {}
        retires = upgrade.get("retirement_at")
        out.append(CatalogModel(
            slug=entry["slug"],
            priority=int(entry.get("priority", 0)),
            listed=entry.get("visibility") == "list",
            upgrade=upgrade.get("model", ""),
            retires_at=datetime.fromisoformat(retires.replace("Z", "+00:00")) if retires else None,
        ))
    return tuple(sorted(out, key=lambda m: m.priority))


def _installed_version(binary: str) -> str | None:
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    parts = out.split()
    return parts[-1] if parts else None


# Keyed on the binary's and the cache file's mtimes, so a long-lived reader (the
# console) re-reads exactly when codex was replaced or re-fetched its catalog, and
# otherwise pays one stat per call rather than a subprocess.
_memo: dict[tuple, tuple[CatalogModel, ...] | None] = {}


def catalog() -> tuple[CatalogModel, ...] | None:
    """The live catalog, highest priority first. None when it cannot be read."""
    binary = shutil.which("codex")
    if binary is None:
        return None
    cache = codex_home() / CACHE_FILE
    key = (binary, _mtime(binary), _mtime(cache))
    if key in _memo:
        return _memo[key]
    _memo.clear()
    _memo[key] = result = _read(binary, cache)
    return result


def _mtime(path) -> float:
    try:
        return os.stat(path).st_mtime
    except FileNotFoundError:
        return 0.0


def _read(binary: str, cache) -> tuple[CatalogModel, ...] | None:
    version = _installed_version(binary)
    if version is None:
        return None
    try:
        held = json.loads(cache.read_text())
        if held.get("client_version") == version:
            return _parse(held["models"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        out = subprocess.run([binary, "debug", "models"], capture_output=True, text=True,
                             timeout=60)
        return _parse(json.loads(out.stdout)["models"])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None


def offered(models: tuple[CatalogModel, ...], now: datetime | None = None) -> tuple[str, ...]:
    """The slugs worth offering for selection: listed, and not already retired."""
    now = now or datetime.now(UTC)
    return tuple(
        m.slug for m in models
        if m.listed and (m.retires_at is None or m.retires_at > now)
    )


def current(slug: str, models: tuple[CatalogModel, ...] | None) -> str:
    """`slug`, or the model the vendor's upgrade chain says replaces it.

    A slug the catalog does not carry comes back unchanged: it may be one the account
    can still reach, and substituting a guess would change the model silently.
    """
    by_slug = {m.slug: m for m in models or ()}
    seen = {slug}
    while slug in by_slug and by_slug[slug].upgrade and by_slug[slug].upgrade not in seen:
        slug = by_slug[slug].upgrade
        seen.add(slug)
    return slug


def live_offered() -> tuple[str, ...]:
    """What the catalog offers now, or () when it cannot be read."""
    models = catalog()
    return offered(models) if models else ()
