"""A guard that blocks a call must leave a row in the guard ledger saying so.

`write-guard.sh` blocks `thalamus write` and `thalamus extract … --write` from inside a
session, and it calls `log_event block "$verb"` to record that it did. `log_event` is
defined in `role-guard.sh` and `graph-guard.sh`, each for itself — not in
`resolve-scope.sh`, the one file `write-guard.sh` sources. So the call is to a function
that does not exist, its `2>/dev/null || true` swallows the `command not found`, and
every block this guard has ever made is absent from `~/.thalamus/guards/`, the ledger
the other guards write and the eval loop reads.

The block itself still happens (exit 2, the reason on stderr), which is what makes the
gap quiet: nothing a session sees is wrong, and a reader of the ledger concludes the
guard never fired.

The property: a `write-guard.sh` block appends a row naming the guard to
`$HOME/.thalamus/guards/<YYYY-MM>.jsonl`. HOME is a temporary directory, so no probe row
reaches the operator's instrument.

**Controls.** The guard must actually block the probe (exit 2) — a guard that no longer
matches the command would write no row for an honest reason. And `role-guard.sh`,
blocking a write under `tests/qe/` from scope `main` in the same HOME, must write its
row there — otherwise the ledger path itself moved and every guard would read absent.

**Shown capable of going red.** Red on the tree as it stands. Define `log_event` in
`write-guard.sh` (or move one definition into `resolve-scope.sh`) and it goes green.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]
_HOOKS = _REPO / "src/thalamus/harness/hooks/claude-code"


def _invoke(script: str, payload: dict, home: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = home
    env["THALAMUS_SCOPE"] = "main"
    for var in ("CLAUDE_CODE_AGENT", "THALAMUS_ROOM", "THALAMUS_SANDBOX"):
        env.pop(var, None)
    return subprocess.run(["bash", str(_HOOKS / script)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=60,
                          check=False)


def _rows(home: str) -> list[dict]:
    rows = []
    for path in (Path(home) / ".thalamus" / "guards").glob("*.jsonl"):
        for line in path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def run() -> Finding | None:
    with tempfile.TemporaryDirectory(prefix="qe-guardlog-") as home:
        control = _invoke("role-guard.sh", {
            "tool_name": "Write", "session_id": "qe-probe", "cwd": str(_REPO),
            "tool_input": {"file_path": str(_REPO / "tests/qe/cases/probe.py"),
                           "content": "probe"}}, home)
        if control.returncode != 2 or not any(
                r.get("verdict", "").startswith("block") for r in _rows(home)):
            return Finding(
                FailureClass.COLLAPSED_SENTINEL,
                "role-guard's control block did not land a ledger row in the probe HOME, "
                "so an absent write-guard row would prove nothing",
                witness=f"role-guard exit {control.returncode}; rows {_rows(home)}",
                site="tests/qe/cases/write_guard_ledger.py")
        before = len(_rows(home))
        blocked = _invoke("write-guard.sh", {
            "tool_name": "Bash", "session_id": "qe-probe", "cwd": "/tmp",
            "tool_input": {"command": "thalamus extract --session x --write"}}, home)
        if blocked.returncode != 2:
            return Finding(
                FailureClass.COLLAPSED_SENTINEL,
                "write-guard did not block `thalamus extract --write`, so the ledger "
                "check has nothing to observe",
                witness=f"exit {blocked.returncode}: {blocked.stderr[-300:]}",
                site="src/thalamus/harness/hooks/claude-code/write-guard.sh")
        new = _rows(home)[before:]
        if new:
            return None
    return Finding(
        FailureClass.INVARIANT_FALSIFIED,
        "write-guard blocks `thalamus extract --write` and records nothing in the guard "
        "ledger: the `log_event` it calls is defined in no file it sources",
        witness="exit 2, 0 new rows (role-guard's control row landed in the same HOME)",
        site="src/thalamus/harness/hooks/claude-code/write-guard.sh (log_event)")


CASE = Case(
    name="write-guard-block-lands-a-ledger-row",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a write-guard block must append a row to the guard ledger like every guard",
    run=run,
    issue=295,
)
