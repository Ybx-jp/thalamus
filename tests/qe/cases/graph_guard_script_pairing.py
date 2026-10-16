"""graph-guard.sh must tie the marker-bearing file to the interpreter that runs it.

Issue #344. The claude-code `graph-guard.sh` asks two questions independently: does any
`.py` token in the command name a file holding a graph-connection marker, and is an
interpreter or network client invoked anywhere in the command. It never asks whether
that interpreter is running that file. Two defects follow, and both are asserted here:

  - false positive: a command that only *reads* the marker-bearing file (grep, then
    head) and also runs an unrelated `curl` is blocked.
  - false negative: the script-file branch only reads tokens that match `*.py`, so a
    script name with a separator attached (`<script>;` or `<script>&&`) never opens the
    file and a marker-bearing script runs unblocked.

**Driven directly**, as `graph_guard_scope_boundary.py` does: the real hook, synthetic
PreToolUse payloads, `$HOME` redirected to a temp dir so the guard ledger is never
touched, the pin named through `THALAMUS_SCOPE`. Fixtures are created in a temp dir and
passed as the payload `cwd`, so the case does not depend on repo source: `marked.py`
holds a connection marker, `clean.py` holds none.

Each probe varies one condition of the next, and the controls are asserted so a red
verdict is attributable:

  T1  read marked.py + curl                        expected pass
  C1  read marked.py + ls                          expected pass (no interpreter)
  C2  read clean.py + curl                         expected pass (no marker)
  C4  python3 marked.py                            expected block (the rule works)
  N1  python3 marked.py; ls                        expected block
  N2  python3 marked.py&& ls                       expected block
  M1  C4 under `main`                              expected pass (scope boundary)

A control that does not hold is COLLAPSED_SENTINEL: the red would then say nothing about
the pairing. Known-red while T1, N1 and N2 return the wrong verdict.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_HOOK = (Path(__file__).resolve().parents[3]
         / "src/thalamus/harness/hooks/claude-code/graph-guard.sh")
_SITE = "src/thalamus/harness/hooks/claude-code/graph-guard.sh"
_BLOCK = 2

#: A real roster scope, so the boundary applies; `main` passes everything.
_EXPERT = "architect"

BLOCK, PASS = "block", "pass"

#: Assembled so this module's own text carries no marker.
_MARKER_LINE = "from thalamus." + "substrate.writer import connect\nconnect()\n"


def _invoke(command: str, scope: str, home: str, cwd: str) -> str:
    env = dict(os.environ)
    env["HOME"] = home
    env["THALAMUS_SCOPE"] = scope
    for key in ("CLAUDE_CODE_AGENT", "THALAMUS_ROOM", "THALAMUS_SANDBOX"):
        env.pop(key, None)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                          "cwd": cwd, "session_id": "qe-344-probe"})
    proc = subprocess.run(["bash", str(_HOOK)], input=payload, capture_output=True,
                          text=True, env=env, timeout=30, check=False)
    if proc.returncode == _BLOCK:
        return BLOCK
    return PASS if proc.returncode == 0 else f"exit {proc.returncode}"


def run() -> Finding | None:
    if not _HOOK.is_file():
        return Finding(failure_class=FailureClass.COLLAPSED_SENTINEL,
                       summary="graph-guard.sh is not on disk, so nothing was driven",
                       witness=f"missing: {_HOOK}", site=_SITE)

    url = "https://example.invalid/x"
    # (label, command, scope, expected, is_control)
    probes = [
        ("C1 read marked.py + ls", "grep -n roots marked.py | head -3; ls",
         _EXPERT, PASS, True),
        ("C2 read clean.py + curl", f"grep -n roots clean.py | head -3; curl -s {url}",
         _EXPERT, PASS, True),
        ("C4 python3 marked.py", "python3 marked.py", _EXPERT, BLOCK, True),
        ("M1 main: python3 marked.py", "python3 marked.py", "main", PASS, True),
        ("T1 read marked.py + curl",
         f"grep -n roots marked.py | head -3; curl -s {url}", _EXPERT, PASS, False),
        ("N1 python3 marked.py; ls", "python3 marked.py; ls", _EXPERT, BLOCK, False),
        ("N2 python3 marked.py&& ls", "python3 marked.py&& ls", _EXPERT, BLOCK, False),
    ]

    broken_controls: list[str] = []
    wrong: list[str] = []
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as cwd:
        (Path(cwd) / "marked.py").write_text(_MARKER_LINE)
        (Path(cwd) / "clean.py").write_text("print('no graph here')\n")
        for label, command, scope, expected, is_control in probes:
            got = _invoke(command, scope, home, cwd)
            if got != expected:
                row = f"{label}: got {got}, expected {expected}"
                (broken_controls if is_control else wrong).append(row)

    if broken_controls:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="a control for the graph-guard pairing probes did not hold, so the "
                    "T1/N1/N2 verdicts cannot be attributed to the pairing",
            witness="; ".join(broken_controls), site=_SITE)
    if wrong:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary="graph-guard.sh checks 'a .py token names a marker-bearing file' and "
                    "'an interpreter or network client is invoked' independently: a read "
                    "of such a file beside an unrelated curl is blocked, and a script "
                    "name with an attached separator is never read",
            witness="; ".join(wrong), site=_SITE)
    return None


CASE = Case(
    name="graph-guard-script-pairing",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="graph-guard.sh must block a marker-bearing script only when an interpreter "
            "runs it: reading one beside a curl passes, a separator-attached name is read",
    run=run,
    issue=344,
    fixed=False,
)
