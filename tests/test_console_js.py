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

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from thalamus.harness import dispatch

JS_DIR = Path(__file__).parent / "js"
SCRIPTS = sorted(JS_DIR.glob("*.test.mjs"))
NODE = shutil.which("node")


def test_js_suite_is_discovered():
    """A rename or a move must not silently empty this file."""
    assert SCRIPTS, f"no *.test.mjs found under {JS_DIR}"


def test_status_vocabulary_is_pinned():
    """The JS one-owner guard covers exactly the statuses Python defines.

    `tests/js/dialogue.test.mjs` forbids the client from branching on a harness
    session status, and it needs the vocabulary to do it. node cannot import Python,
    so `tests/js/statuses.mjs` hardcodes the list and this asserts the equality from
    the side that owns it. Without this, a status added to `dispatch.py` would widen
    the guard's blind spot silently: every JS check would still pass while no longer
    covering the new value. Adding one here means updating that file in the same
    change — which is the point.
    """
    source = (JS_DIR / "statuses.mjs").read_text()
    m = re.search(r"HARNESS_STATUSES\s*=\s*\[(.*?)\]", source, re.S)
    assert m, "HARNESS_STATUSES array not found in tests/js/statuses.mjs"
    js = tuple(re.findall(r"""["'`]([^"'`]+)["'`]""", m.group(1)))
    assert js == dispatch.DELIVERABLE_STATUSES + (dispatch.WAITING_STATUS,)


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
