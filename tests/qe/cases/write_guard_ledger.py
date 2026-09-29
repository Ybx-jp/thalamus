"""A guard that blocks a call must leave a row in the guard ledger saying so.

`write-guard.sh` blocks the two self-memory-write verbs from inside a session and appends
a `guard: write-guard` row (with a `verb` naming the blocked command) to
`$HOME/.thalamus/guards/<YYYY-MM>.jsonl`, the ledger the other guards write and the eval
loop reads. The codex and cursor adapters run the same script.

The property, each part asserted on a real invocation with HOME a temporary directory so
no probe row reaches the operator's instrument:

- both blocked verbs exit 2 and land exactly one valid one-line-JSON row whose `guard`,
  `verdict`, `verb` and `scope` are right, from the claude-code, codex and cursor
  payload shapes;
- a payload with no session_id/cwd, and one whose fields carry quotes, newlines and
  backslashes, still yields one parseable row;
- the row's `scope` follows `agent_type` (`thalamus-qe` gives `qe`; a subagent type with
  no manifest keeps the launcher's pin);
- a command the guard does not block writes no row;
- a guards directory that cannot be written (read-only, or a file in its place) never
  changes the block: exit 2, reason on stderr.

**Controls.** The guard must actually block each probe - a guard that no longer matches
would write no row for an honest reason. And `role-guard.sh`, blocking a write under
`tests/qe/` from scope `main` in the same HOME, must write its row there - otherwise the
ledger path itself moved and every guard would read absent.

**Shown capable of going red.** Against the parent of the fix (`write-guard.sh` calling a
`log_event` it never defines) the case fails on its first probe with 0 rows. Deleting the
`log_event block` call from the current script drives it red the same way.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]
_HOOKS = _REPO / "src/thalamus/harness/hooks"
_SITE = "src/thalamus/harness/hooks/claude-code/write-guard.sh"
# Assembled so this file's own text never matches the guard's verb pattern.
_WRITE = "thalamus " + "wri" + "te f.json"
_EXTRACT = "thalamus extract --session x --force --" + "wri" + "te"


def _invoke(script: str, payload: dict | str, home: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = home
    env["THALAMUS_SCOPE"] = "main"
    for var in ("CLAUDE_CODE_AGENT", "THALAMUS_ROOM", "THALAMUS_SANDBOX"):
        env.pop(var, None)
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(["bash", str(_HOOKS / script)], input=stdin,
                          capture_output=True, text=True, env=env, timeout=60,
                          check=False)


def _rows(home: str) -> tuple[list[dict], int]:
    """Parsed rows, and the count of non-empty lines that were not valid JSON."""
    rows, bad = [], 0
    for path in (Path(home) / ".thalamus" / "guards").glob("*.jsonl"):
        if not path.is_file():
            continue
        for line in path.read_text().split("\n"):
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                bad += 1
    return rows, bad


def _bash(command: str, **extra) -> dict:
    return {"tool_name": "Bash", "session_id": "qe-probe", "cwd": "/tmp",
            "tool_input": {"command": command}, **extra}


def _expect_row(label: str, script: str, payload: dict | str, *, verb: str,
                scope: str = "main") -> Finding | None:
    """One blocked call in a fresh HOME: blocked, one valid row, right guard/verb/scope."""
    with tempfile.TemporaryDirectory(prefix="qe-guardlog-") as home:
        result = _invoke(script, payload, home)
        # cursor's adapter answers a block as exit 0 with a `deny` JSON on stdout.
        blocked = result.returncode == 2 or (
            script.startswith("cursor/") and '"deny"' in result.stdout)
        if not blocked:
            return Finding(FailureClass.COLLAPSED_SENTINEL,
                         f"{label}: the guard did not block, so the ledger check has "
                         "nothing to observe",
                         witness=f"exit {result.returncode}: {result.stderr[-300:]}",
                         site=_SITE)
        rows, bad = _rows(home)
        if len(rows) != 1 or bad:
            return Finding(FailureClass.INVARIANT_FALSIFIED,
                         f"{label}: a write-guard block must land exactly one valid "
                         "row in the guard ledger",
                         witness=f"exit {result.returncode}, {len(rows)} rows, {bad} unparseable",
                         site=_SITE)
        row = rows[0]
        if (row.get("guard"), row.get("verdict"), row.get("verb"),
                row.get("scope")) != ("write-guard", "block", verb, scope):
            return Finding(FailureClass.INVARIANT_FALSIFIED,
                         f"{label}: the row misnames the block",
                         witness=f"row {row}; wanted guard=write-guard verdict=block "
                                 f"verb={verb!r} scope={scope!r}",
                         site=_SITE)
    return None


def run() -> Finding | None:
    with tempfile.TemporaryDirectory(prefix="qe-guardlog-") as home:
        control = _invoke("claude-code/role-guard.sh", {
            "tool_name": "Write", "session_id": "qe-probe", "cwd": str(_REPO),
            "tool_input": {"file_path": str(_REPO / "tests/qe/cases/probe.py"),
                           "content": "probe"}}, home)
        if control.returncode != 2 or not any(
                r.get("verdict", "").startswith("block") for r in _rows(home)[0]):
            return Finding(FailureClass.COLLAPSED_SENTINEL,
                         "role-guard's control block did not land a ledger row in the "
                         "probe HOME, so an absent write-guard row would prove nothing",
                         witness=f"role-guard exit {control.returncode}; "
                                 f"rows {_rows(home)[0]}",
                         site=_SITE)

    cc = "claude-code/write-guard.sh"
    quirky = {"tool_name": "Bash", "session_id": 's"q\\', "cwd": "/a\nb\t",
              "tool_input": {"command": _WRITE + ' "a\nb" \'x\' \\ \u2028'}}
    for label, script, payload, verb, scope in (
        ("write", cc, _bash(_WRITE), "thalamus write", "main"),
        ("extract --write", cc, _bash(_EXTRACT), "thalamus extract --write", "main"),
        ("codex adapter", "codex/write-guard.sh", _bash(_WRITE),
         "thalamus write", "main"),
        ("cursor adapter", "cursor/write-guard.sh",
         {"command": _WRITE, "conversation_id": "c", "workspace_roots": ["/w"]},
         "thalamus write", "main"),
        ("no session_id or cwd", cc, {"tool_input": {"command": _WRITE}},
         "thalamus write", "main"),
        ("quotes, newlines, backslashes", cc, quirky, "thalamus write", "main"),
        ("pinned qe subagent", cc, _bash(_WRITE, agent_type="thalamus-qe"),
         "thalamus write", "qe"),
        ("subagent with no manifest", cc, _bash(_WRITE, agent_type="Explore"),
         "thalamus write", "main"),
    ):
        finding = _expect_row(label, script, payload, verb=verb, scope=scope)
        if finding:
            return finding

    with tempfile.TemporaryDirectory(prefix="qe-guardlog-") as home:
        for command in ("ls -la", "thalamus recall x",
                        "git commit -m 'note: " + _WRITE + "'"):
            _invoke(cc, _bash(command), home)
        if _rows(home)[0]:
            return Finding(FailureClass.INVARIANT_FALSIFIED,
                         "a command write-guard does not block wrote a ledger row",
                         witness=f"rows {_rows(home)[0]}",
                         site=_SITE)

    def _readonly(home: str) -> None:
        guards = Path(home) / ".thalamus" / "guards"
        guards.mkdir(parents=True)
        guards.chmod(0o500)

    def _file_in_place(home: str) -> None:
        (Path(home) / ".thalamus").mkdir()
        (Path(home) / ".thalamus" / "guards").write_text("x")

    for label, setup in (("read-only guards dir", _readonly),
                         ("file where the guards dir goes", _file_in_place)):
        for command in (_WRITE, _EXTRACT):
            with tempfile.TemporaryDirectory(prefix="qe-guardlog-") as home:
                setup(home)
                result = _invoke(cc, _bash(command), home)
                guards = Path(home, ".thalamus", "guards")
                if guards.is_dir():
                    guards.chmod(0o700)
                if result.returncode != 2 or "Blocked" not in result.stderr:
                    return Finding(FailureClass.INVARIANT_FALSIFIED,
                                 f"{label}: a ledger write that fails must not change "
                                 "the block",
                                 witness=f"exit {result.returncode}: "
                                         f"{result.stderr[-200:]}",
                                 site=_SITE)
    return None


CASE = Case(
    name="write-guard-block-lands-a-ledger-row",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a write-guard block must append a row to the guard ledger like every guard",
    run=run,
    issue=295,
    fixed=True,
)
