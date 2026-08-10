"""Bridge the console's JavaScript tests into `uv run pytest`.

The console ships a real client — a markdown renderer, a repaint guard, a poll
loop — and bugs there reach the phone exactly like bugs in the server do. They
were being caught by throwaway scripts, which is to say caught once. These run
with the rest of the suite instead.

node is optional: it is not a dependency of the package, and a checkout without
it skips these rather than failing. CI that wants the coverage installs node;
everyone else loses nothing they had before.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS_DIR = Path(__file__).parent / "js"
SCRIPTS = sorted(JS_DIR.glob("*.test.mjs"))
NODE = shutil.which("node")


def test_js_suite_is_discovered():
    """A rename or a move must not silently empty this file."""
    assert SCRIPTS, f"no *.test.mjs found under {JS_DIR}"


@pytest.mark.skipif(NODE is None, reason="node not installed; console JS tests skipped")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.stem)
def test_console_js(script: Path):
    proc = subprocess.run(
        [NODE, str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=script.parent,
    )
    if proc.returncode != 0:
        pytest.fail(f"{script.name} failed\n\n{proc.stdout}\n{proc.stderr}")
