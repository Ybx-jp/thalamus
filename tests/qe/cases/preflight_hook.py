"""The session preflight hook, driven the way Claude Code drives it.

`src/thalamus/harness/hooks/claude-code/preflight.sh` decides at the first tool call
whether a run may continue. The suite in `tests/test_preflight.py` holds each check
against a passing and a failing fixture and runs the hook end to end for the ordinary
autonomous and attended paths. These cases hold the three claims that only hold if no
input the hook can be given undoes them:

1. **An autonomous run is stopped unless the preflight is shown to pass.** Rows: a state
   file that is empty, truncated, `{}`, `[]` or `passed:false` all deny; a junk or
   mixed-case `THALAMUS_SESSION_TYPE` resolves the way the shell resolver documents
   (junk under an `sdk*` entrypoint is autonomous); a subagent call carries the
   session's id and reads the session's result. The unreadable-payload row is its own
   case, because it is the one that falls open (#403).
2. **An attended session is never stopped.** Whatever state the box and the state
   directory are in, the hook exits 0 and prints neither `continue:false` nor a deny.
3. **The session-start/first-tool-call dedupe never hides a finding that session start
   did not tell.** A finding is suppressed only when the same `(check, detail)` pair
   was told; a check that passed at start, or failed with another detail, is told. A
   start record that cannot be read must not suppress anything (#404).

The hook is run with a throwaway `HOME` and a `uv` stub that runs this interpreter's
`thalamus`, which is what `tests/test_preflight.py` does for the same reason: the hook
resolves its CLI from the checkout it sits in.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_ROOT = Path(__file__).resolve().parents[3]
_HOOK = _ROOT / "src/thalamus/harness/hooks/claude-code/preflight.sh"
_SITE = "src/thalamus/harness/hooks/claude-code/preflight.sh"

_PAYLOAD = {"session_id": "qe-pf", "transcript_path": "/nonexistent/t.jsonl", "cwd": "/tmp",
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "ls"}}

_AUTONOMOUS = {"THALAMUS_SESSION_TYPE": "autonomous"}
_ATTENDED = {"THALAMUS_SESSION_TYPE": "attended"}


class _Run:
    def __init__(self, proc: subprocess.CompletedProcess, home: Path):
        self.code = proc.returncode
        self.out = proc.stdout.strip()
        self.err = proc.stderr.strip()
        self.home = home

    @property
    def parsed(self) -> dict | None:
        try:
            value = json.loads(self.out) if self.out else {}
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    @property
    def stopped(self) -> bool:
        data = self.parsed or {}
        decision = (data.get("hookSpecificOutput") or {}).get("permissionDecision")
        return self.code == 2 or data.get("continue") is False or decision == "deny"

    def describe(self) -> str:
        return f"exit={self.code} stdout={self.out[:90]!r}"


def _hook(payload: dict | None, env: dict, *, raw: str | None = None,
          seed: Callable[[Path], None] | None = None, uv: str | None = None,
          path_dirs: list[str] | None = None, keep_home: bool = True) -> _Run:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        bin_dir = root / "bin"
        bin_dir.mkdir()
        if uv != "absent":
            stub = bin_dir / "uv"
            body = uv or f'exec "{sys.executable}" -m thalamus "$@"'
            stub.write_text(f"#!/bin/bash\nshift 3\nshift\n{body}\n")
            stub.chmod(0o755)
        config = root / "config"
        (config / "experts").mkdir(parents=True)
        (config / "ownership.json").write_text("{}")
        if seed:
            seed(home)
        stdin = raw if raw is not None else json.dumps(payload)
        path = ":".join([str(bin_dir), *(path_dirs if path_dirs is not None else ["/usr/bin", "/bin"])])
        environ = {"PATH": path, "THALAMUS_CONFIG_DIR": str(config),
                   "THALAMUS_SETTING_SOURCES": "project",
                   "PYTHONPATH": str(_ROOT / "src"), **env}
        if keep_home:
            environ["HOME"] = str(home)
        proc = subprocess.run([str(_HOOK)], input=stdin, capture_output=True, text=True,
                              timeout=180, env=environ)
        return _Run(proc, home)


def _state(content: str, name: str = "qe-pf.json") -> Callable[[Path], None]:
    def seed(home: Path) -> None:
        directory = home / ".thalamus" / "preflight"
        directory.mkdir(parents=True)
        (directory / name).write_text(content)
    return seed


_FAILED = json.dumps({"passed": False, "checks": [
    {"name": "write path", "ok": False, "detail": "no pin-ledger row"}]})


# ------------------------------------------------------------------------------------
# 1. Autonomous: every state the hook can be left in still stops the run.
# ------------------------------------------------------------------------------------

def run_autonomous_stops() -> Finding | None:
    rows: list[tuple[str, _Run]] = []
    control = _hook(_PAYLOAD, _AUTONOMOUS, seed=_state(_FAILED))
    if not control.stopped:
        return Finding(FailureClass.COLLAPSED_SENTINEL,
                       "control failed: an autonomous session with a recorded failed state "
                       "was not stopped, so no row below can show an escape",
                       control.describe(), _SITE)
    for label, content in (("empty state file", ""), ("truncated state file", '{"passed": '),
                           ("state file {}", "{}"), ("state file []", "[]"),
                           ("passed missing", '{"checks": []}')):
        rows.append((label, _hook(_PAYLOAD, _AUTONOMOUS, seed=_state(content))))
    rows.append(("junk type under sdk entrypoint",
                 _hook(_PAYLOAD, {"THALAMUS_SESSION_TYPE": "junk",
                                  "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}, seed=_state(_FAILED))))
    rows.append(("type declared with case and padding",
                 _hook(_PAYLOAD, {"THALAMUS_SESSION_TYPE": " AUTONOMOUS "},
                       seed=_state(_FAILED))))
    rows.append(("subagent call on the session's id",
                 _hook({**_PAYLOAD, "agent_type": "thalamus-qe", "agent_id": "sub-1"},
                       _AUTONOMOUS, seed=_state(_FAILED))))
    escaped = [f"{label}: {r.describe()}" for label, r in rows if not r.stopped]
    if escaped:
        return Finding(FailureClass.FAILED_OPEN,
                       "an autonomous run was allowed past a recorded failure",
                       "; ".join(escaped), _SITE)
    return None


# ------------------------------------------------------------------------------------
# 1b. Autonomous: a payload the hook cannot read.
# ------------------------------------------------------------------------------------

def run_unreadable_payload() -> Finding | None:
    control = _hook(_PAYLOAD, _AUTONOMOUS)
    if not control.stopped:
        return Finding(FailureClass.COLLAPSED_SENTINEL,
                       "control failed: an autonomous session with a readable payload and "
                       "an unarmed pin was not stopped",
                       control.describe(), _SITE)
    drifted = {k: v for k, v in _PAYLOAD.items() if k != "session_id"}
    rows = {
        "stdin is not JSON": _hook(None, _AUTONOMOUS, raw="not json"),
        "stdin is empty": _hook(None, _AUTONOMOUS, raw=""),
        "no session_id key": _hook({**drifted, "sessionId": "qe-pf"}, _AUTONOMOUS),
        "jq not on PATH": _hook(_PAYLOAD, _AUTONOMOUS, path_dirs=[]),
        "HOME unset": _hook(_PAYLOAD, _AUTONOMOUS, keep_home=False),
    }
    open_rows = [f"{label}: {r.describe()}" for label, r in rows.items() if not r.stopped]
    if open_rows:
        return Finding(FailureClass.FAILED_OPEN,
                       "preflight.sh lets an autonomous call proceed when it cannot read "
                       "its own input; the control with a readable payload is stopped",
                       "; ".join(open_rows), _SITE + " (session_id read, `exit 0`)")
    return None


# ------------------------------------------------------------------------------------
# 2. Attended: never stopped.
# ------------------------------------------------------------------------------------

def run_attended_never_stopped() -> Finding | None:
    # The controls: the same hostile box stops an autonomous session, so a pass below
    # is the attended branch declining to stop, not the box being benign.
    control = _hook(_PAYLOAD, _AUTONOMOUS, seed=_state(_FAILED))
    if not control.stopped:
        return Finding(FailureClass.COLLAPSED_SENTINEL,
                       "control failed: the autonomous control was not stopped",
                       control.describe(), _SITE)
    crash = 'echo "boom" >&2; exit 3'
    rows = {
        "recorded failed state": _hook(_PAYLOAD, _ATTENDED, seed=_state(_FAILED)),
        "truncated state": _hook(_PAYLOAD, _ATTENDED, seed=_state('{"passed": ')),
        "empty state": _hook(_PAYLOAD, _ATTENDED, seed=_state("")),
        "unarmed pin, no state (first call)": _hook(_PAYLOAD, _ATTENDED),
        "no readable transcript": _hook({**_PAYLOAD, "transcript_path": ""}, _ATTENDED),
        "CLI crashes": _hook(_PAYLOAD, _ATTENDED, uv=crash),
        "CLI prints nothing": _hook(_PAYLOAD, _ATTENDED, uv="exit 0"),
        "uv absent": _hook(_PAYLOAD, _ATTENDED, uv="absent"),
        "payload is not JSON": _hook(None, _ATTENDED, raw="not json"),
        "junk type, interactive entrypoint": _hook(
            _PAYLOAD, {"THALAMUS_SESSION_TYPE": "junk", "CLAUDE_CODE_ENTRYPOINT": "cli"},
            seed=_state(_FAILED)),
    }
    stopped = [f"{label}: {r.describe()}" for label, r in rows.items()
               if r.stopped or r.code != 0]
    if stopped:
        return Finding(FailureClass.INVARIANT_FALSIFIED,
                       "an attended session was stopped or the hook exited non-zero",
                       "; ".join(stopped), _SITE)
    return None


# ------------------------------------------------------------------------------------
# 3. Dedupe soundness.
# ------------------------------------------------------------------------------------

def run_dedupe_is_sound() -> Finding | None:
    from thalamus.harness import preflight  # noqa: PLC0415

    def report(session_type: str, *checks) -> preflight.Report:
        return preflight.Report("qe-pf", "qe", session_type,
                                [preflight.Check(*c) for c in checks])

    def told_names(out: dict) -> str:
        return (out.get("hookSpecificOutput") or {}).get("additionalContext", "")

    attended = report("attended", ("alpha", False, "d1"), ("beta", True, ""),
                      ("gamma", False, "d3"))
    cases: list[tuple[str, dict, Callable[[dict], bool]]] = [
        ("control: nothing told, every failure is told",
         preflight.hook_output(attended, set()),
         lambda o: "alpha: d1" in told_names(o) and "gamma: d3" in told_names(o)),
        ("a failure told at start is not repeated, an untold one is",
         preflight.hook_output(attended, {("alpha", "d1")}),
         lambda o: "alpha" not in told_names(o) and "gamma: d3" in told_names(o)),
        ("same check, new detail is told",
         preflight.hook_output(attended, {("alpha", "older"), ("gamma", "d3")}),
         lambda o: "alpha: d1" in told_names(o) and "gamma" not in told_names(o)),
        ("a check that passed at start and fails now is told",
         preflight.hook_output(report("attended", ("alpha", False, "d1")), {("beta", "x")}),
         lambda o: "alpha: d1" in told_names(o)),
        ("everything already told prints nothing",
         preflight.hook_output(attended, {("alpha", "d1"), ("gamma", "d3")}), lambda o: o == {}),
        ("an autonomous abort is never hidden by a told set",
         preflight.hook_output(report("autonomous", ("alpha", False, "d1")),
                               {("alpha", "d1")}),
         lambda o: (o.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"),
        ("an undecided check (ok=None) in an autonomous report still aborts when told",
         preflight.hook_output(report("autonomous", ("alpha", None, "unknown")),
                               {("alpha", "unknown")}),
         lambda o: o.get("continue") is False),
    ]
    broken = [label for label, out, ok in cases if not ok(out)]
    if broken:
        return Finding(FailureClass.INVARIANT_FALSIFIED,
                       "the dedupe hid or repeated a finding it should not have",
                       "; ".join(broken), "src/thalamus/harness/preflight.py::hook_output")
    return None


def run_start_record_shape() -> Finding | None:
    """A start record that parses but is shaped wrongly must not silence the first call."""
    records = {
        "checks is an int": '{"checks": 5}',
        "checks is a string": '{"checks": "none"}',
        "record is a list": "[]",
        "record is a string": '"x"',
        "truncated JSON": '{"checks": [',
        "entries are not objects": '{"checks": [1, "a", null]}',
    }
    control = _hook(_PAYLOAD, _ATTENDED, seed=_state("{}", "qe-pf.start.json"))
    if "PREFLIGHT" not in json.dumps(control.parsed or {}):
        return Finding(FailureClass.COLLAPSED_SENTINEL,
                       "control failed: an attended first call with an empty start record "
                       "and an unarmed pin told nothing",
                       control.describe(), _SITE)
    silent = []
    for label, content in records.items():
        r = _hook(_PAYLOAD, _ATTENDED, seed=_state(content, "qe-pf.start.json"))
        if "PREFLIGHT" not in json.dumps(r.parsed or {}):
            tail = r.err.splitlines()[-1] if r.err else ""
            log = ""
            logfile = r.home / ".thalamus/logs/preflight.log"
            if logfile.exists():
                log = logfile.read_text().strip().splitlines()[-1][:100]
            silent.append(f"{label}: {r.describe()} {tail} {log}".strip())
    if silent:
        return Finding(FailureClass.INVARIANT_FALSIFIED,
                       "a malformed session-start record leaves the first tool call silent "
                       "although the check found failures (the control with `{}` tells them)",
                       "; ".join(silent), "src/thalamus/harness/preflight.py::told_at_start")
    return None


_NEEDS = (Substrate.HERMETIC, Substrate.NEEDS_JQ)

CASES = (
    Case(name="preflight-autonomous-recorded-failure-always-stops", tier=Tier.FAST,
         substrate=_NEEDS, classes=(FailureClass.FAILED_OPEN, FailureClass.COLLAPSED_SENTINEL),
         summary="an autonomous run is stopped from any recorded state, session-type spelling "
                 "or subagent call",
         run=run_autonomous_stops),
    Case(name="preflight-autonomous-unreadable-payload-fails-closed", tier=Tier.FAST,
         substrate=_NEEDS, classes=(FailureClass.FAILED_OPEN, FailureClass.COLLAPSED_SENTINEL),
         summary="an autonomous run whose hook payload cannot be read is stopped, not allowed",
         run=run_unreadable_payload, issue=403),
    Case(name="preflight-attended-session-is-never-stopped", tier=Tier.FAST,
         substrate=_NEEDS,
         classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
         summary="an attended session proceeds whatever state the box and state directory are in",
         run=run_attended_never_stopped),
    Case(name="preflight-dedupe-never-hides-an-untold-finding", tier=Tier.FAST,
         substrate=(Substrate.HERMETIC,), classes=(FailureClass.INVARIANT_FALSIFIED,),
         summary="the first tool call suppresses only findings session start told, and never an abort",
         run=run_dedupe_is_sound),
    Case(name="preflight-start-record-shape-does-not-hide-findings", tier=Tier.FAST,
         substrate=_NEEDS,
         classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
         summary="a malformed session-start record leaves the first tool call telling every finding",
         run=run_start_record_shape, issue=404, fixed=True),
)

CASE = CASES[0]  # the first, for a loader that reads one
