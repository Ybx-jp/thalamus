"""Where this install is: its own files, the checkout it runs from if any, and how
to run it.

Three facts, one place. The package's own files (hook scripts, skills, static
assets) sit next to this module wherever it was installed. A source checkout is
present only when the package was loaded from one (`uv sync` installs it editable,
so this module is `<checkout>/src/thalamus/contract/paths.py`); an installed wheel
has none, and everything that asks for one says what it does instead. The command
that runs this install follows from which of the two it is.

No config, no manifest, nothing above it in the import graph: it sits in the
vocabulary layer because the modules that need it sit in several, and a home inside
any one of them would make the others read across a boundary.

The hook scripts answer the same question in bash (`resolve-scope.sh`'s
`thalamus_checkout` and `thalamus_cli`), from the same test: a checkout is a
directory holding `pyproject.toml` with this package under its `src/`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: The installed package itself: `thalamus/`. Hook scripts, skills and static assets
#: are resolved under it, so they are found wherever the package was installed.
PACKAGE_DIR = Path(__file__).resolve().parents[1]


#: The graph server's compose file, shipped in the package beside the files it mounts.
#: `thalamus graph` runs Docker Compose against it; a clone's root compose file
#: includes it.
GRAPH_COMPOSE = PACKAGE_DIR / "graph" / "docker-compose.yml"


def _checkout() -> Path | None:
    root = PACKAGE_DIR.parents[1]
    if PACKAGE_DIR.parent.name == "src" and (root / "pyproject.toml").is_file():
        return root
    return None


#: The source checkout this package was loaded from, or None for an installed wheel.
CHECKOUT: Path | None = _checkout()

#: Where `thalamus init --check` says this install lives, and what an MCP
#: registration must name to be this install's: the checkout, or the interpreter the
#: wheel was installed under.
INSTALL_IDENTITY = str(CHECKOUT) if CHECKOUT else sys.executable

def config_root() -> Path:
    """The tier-0 configuration directory: THALAMUS_CONFIG_DIR, else the checkout's
    `config/`, else `~/.thalamus/config` for an installed wheel.

    A checkout's own `config/` is its development config; an installed wheel has none
    and reads the user's. Read at call time, so it follows the environment and HOME.
    Here rather than in `contract/manifest.py` because `role-guard.sh` resolves it on
    every edit through `contract/ownership.py`, which must not pay manifest's import.
    """
    override = os.environ.get("THALAMUS_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if CHECKOUT is not None:
        return CHECKOUT / "config"
    return Path.home() / ".thalamus" / "config"


def default_project_dir() -> Path:
    """Where a pinned session or the console opens when no directory is named: the
    checkout when running from one, else the directory the command was run in."""
    return CHECKOUT if CHECKOUT is not None else Path.cwd()


def cli_argv(*args: str) -> list[str]:
    """The command that runs this install's `thalamus` CLI with `args`.

    A checkout runs through `uv run --project`, which keeps its environment in step
    with its lockfile. An installed wheel runs under the interpreter it was installed
    into, by absolute path, because a harness's PATH is not the shell's.
    """
    if CHECKOUT is not None:
        return ["uv", "run", "--project", str(CHECKOUT), "thalamus", *args]
    return [sys.executable, "-m", "thalamus", *args]


def mcp_argv() -> list[str]:
    """The command that serves this install's MCP server."""
    if CHECKOUT is not None:
        return ["uv", "run", "--project", str(CHECKOUT), "thalamus-mcp"]
    return [sys.executable, "-m", "thalamus.harness.mcp_server"]
