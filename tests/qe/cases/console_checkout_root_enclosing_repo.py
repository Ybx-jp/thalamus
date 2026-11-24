"""The console must not take an enclosing git repository for its own checkout.

Issue #378. `thalamus_console.server.checkout_root()` asks git for the toplevel of the
directory holding its own `__file__` and treats any answer as the checkout it was
installed from. A wheel installed into a virtualenv that sits inside someone else's
repository (a project with `.venv` in its `.gitignore`) is answered with that
repository: `git -C .venv/lib/python3.12/site-packages/thalamus_console rev-parse
--show-toplevel` prints the project and exits 0. `deploy`, `build_info` and the
background fetch loop then act on the project as if it were the thalamus checkout.

Driven directly rather than through the install matrix: the property is a pure function
of where the module file sits relative to a git toplevel, and a child interpreter
importing a copy of the shipped package from a scratch tree reaches it without a wheel
build. The copy is what `__file__` resolves to, so the real checkout is never asked.

**Two arms, one oracle.**

1. *The defect arm.* The package is copied into
   `<scratch repo>/.venv/lib/python3.12/site-packages/thalamus_console` with `.venv`
   gitignored. `checkout_root()` must be None. The case also reads the git answer
   itself, so a box where git stops naming the enclosing repository reports that
   instead of a pass the code did not earn.
2. *The control.* The same copy placed at
   `<scratch repo>/packages/thalamus-console/src/thalamus_console` - where the module
   lives in a real checkout - must still resolve to the scratch repository. A fix that
   returned None unconditionally would pass arm 1 and break every development install.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "packages/thalamus-console/src/thalamus_console/server.py:checkout_root"
_PKG = Path(__file__).resolve().parents[3] / "packages/thalamus-console/src/thalamus_console"
_PROBE = (
    "import thalamus_console.server as s;"
    "r = s.checkout_root();"
    "print('FILE=' + s.__file__);"
    "print('ROOT=' + ('None' if r is None else str(r)))"
)


def _env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          timeout=30, env=_env())


def _root_from(copy_parent: Path) -> tuple[str, str]:
    """(module file the child imported, checkout_root() it reported)."""
    env = _env()
    env["PYTHONPATH"] = str(copy_parent)
    r = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True,
                       timeout=60, env=env, cwd=copy_parent)
    out = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    if "ROOT" not in out:
        return "", f"probe died: {r.stderr.strip()[-300:]}"
    return out["FILE"], out["ROOT"]


def run() -> Finding | None:
    if shutil.which("git") is None or not _PKG.is_dir():
        return None
    with tempfile.TemporaryDirectory(prefix="qe-378-") as tmp:
        repo = Path(tmp).resolve() / "project"
        repo.mkdir()
        (repo / ".gitignore").write_text(".venv\n")
        if _git("init", "-q", cwd=repo).returncode != 0:
            return None
        site = repo / ".venv/lib/python3.12/site-packages"
        site.mkdir(parents=True)
        ignore = shutil.ignore_patterns("__pycache__")
        shutil.copytree(_PKG, site / "thalamus_console", ignore=ignore)

        # Control: in the real layout the scratch repo IS the checkout.
        dev = repo / "packages/thalamus-console/src"
        dev.mkdir(parents=True)
        shutil.copytree(_PKG, dev / "thalamus_console", ignore=ignore)
        file_c, root_c = _root_from(dev)
        if root_c != str(repo) or not file_c.startswith(str(dev)):
            return Finding(
                FailureClass.COLLAPSED_SENTINEL,
                summary="control failed: a console living at its own path in a git "
                        "repository no longer resolves that repository as its checkout, "
                        "so the venv arm below proves nothing",
                witness=f"file={file_c!r} checkout_root={root_c!r} want {str(repo)!r}",
                site=_SITE,
            )

        asked = _git("-C", str(site / "thalamus_console"), "rev-parse",
                     "--show-toplevel", cwd=repo)
        if asked.stdout.strip() != str(repo):
            return Finding(
                FailureClass.COLLAPSED_SENTINEL,
                summary="premise failed: git no longer names the enclosing repository "
                        "for a gitignored venv path",
                witness=f"git said {asked.stdout.strip()!r} rc={asked.returncode}",
                site=_SITE,
            )

        file_v, root_v = _root_from(site)
        if not file_v.startswith(str(site)):
            return Finding(
                FailureClass.COLLAPSED_SENTINEL,
                summary="the probe imported the wrong copy of thalamus_console",
                witness=f"imported {file_v!r}, wanted a path under {str(site)!r}",
                site=_SITE,
            )
        if root_v != "None":
            return Finding(
                FailureClass.BOUNDARY_LEAK,
                summary="checkout_root() names a repository that merely encloses the "
                        "venv the console is installed in; deploy, build_info and the "
                        "fetch loop would act on it as the thalamus checkout",
                witness=f"module at {file_v} -> checkout_root()={root_v!r}, want None",
                site=_SITE,
            )
    return None


CASE = Case(
    name="console-checkout-root-requires-its-own-source",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="a console installed into a venv inside another git repository must report "
            "no checkout, not that repository",
    run=run,
    issue=378,
    fixed=True,
)
