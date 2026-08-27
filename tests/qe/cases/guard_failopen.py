"""A PreToolUse guard that cannot read its input must not permit the call.

Every guard shares one prologue: `set -euo pipefail`, then a read of stdin, then `jq`.
Three inputs defeat that prologue — jq missing (exit 127), jq refusing malformed JSON
(exit 5), and an empty payload — and under `set -e` any of them aborts the script
before a single guard rule runs. The abort code is not the blocking code, so the tool
call proceeds. From outside, a guard that examined the input and approved it and a
guard that died before looking are the same event.

A fourth input defeats it without breaking anything: **valid JSON in a shape the guard
does not expect.** That is not hypothetical here. Cursor's `beforeShellExecution`
payload schema is Cursor's, versioned on their release cadence, and the shims are
tracked against a dated build (`cursor/2026.08.11-e8db854`). A field that moves takes
the write boundary, the gremlin terminal-step rule and the room-command rule out
together, silently, with exit 0 and nothing in any log. So the drifted-key row feeds
each guard's own refusable command under a key one step away from the real one, and
requires the same refusal.

## The verdict is not the exit code

Refusal is `exit 2` on claude-code and codex, and a `{"permission": "deny"}` object on
**stdout** on Cursor, where the process exits 0 either way. A case that read only
`proc.returncode` — this one did — scored every Cursor guard as passing no matter what
it printed, which is why widening the table without changing the reader was worse than
not widening it. `_HARNESSES` pairs each hook directory with the reader for its own
protocol, and a Cursor guard that prints no permission object at all is read as
NO_VERDICT rather than as a refusal: what Cursor does with a hook that emits nothing is
not established anywhere in this repo, so it cannot be counted as a block.

## Coverage is enumerated, not listed

`_GUARDS` is checked against `*-guard.sh` on disk in every harness directory. A guard
that is added, renamed or moved fails this case rather than quietly leaving the table
one row shorter — which is the shape the previous version failed in: it named three
scripts under one harness and read as full coverage of twelve.

## The positive controls, and why they took four attempts

Every row has one, per harness, and the case asserts them all before drawing any
conclusion from a refusal. Building the gremlin control took four attempts — three
earlier ones "demonstrated" the fail-open using input the guard would never have
blocked anyway:

- `g.V().drop()` is ALLOWED, correctly: `.drop()` IS a terminal step, and that guard's
  subject is unterminated laziness, not destruction.
- a bare `g.V().hasLabel("Claim")` is allowed too, because `gremlin-guard.sh` requires
  a gremlin-python MARKER before it engages at all.
- malformed shell quoting produced `jq` exit 5 from the harness's own broken JSON,
  which reads exactly like the defect under test.

So the blocking input must satisfy three conjunctive conditions — marker, source step,
no terminal step. That narrowness is worth recording: it is deliberate (guard v4
over-blocked and the session routed around it, lab/008), but effective coverage is far
narrower than "guards Gremlin queries".

Each row also carries a **permitted** input asserted to be ALLOWED, and that is the
control on the controls. Without it a guard that denied unconditionally would satisfy
every refusal assertion in this file and look like the strongest guard in the tree.

## Two guards are legitimately narrower

`role-guard.sh` matches Edit/Write/Skill/apply_patch and `room-guard.sh` matches
SendMessage. On those an absent command is a call with nothing to say, not a payload
the guard could not read, so they carry no drifted-key row — asserting one would demand
a refusal the boundary does not owe. They still owe a refusal on malformed, empty and
no-jq input, which is where their rows are.

`room-command-guard.sh` has no boundary at all outside a room and is a documented
no-op there, so its rows run with THALAMUS_ROOM set. One asymmetry survives that and is
not asserted here: the Cursor adapter reads the command before asking the room
question, so it refuses an unreadable payload outside a room where claude-code and
codex stay a no-op.

## Shown capable of going red

The table is 69 cells over 12 guard scripts, and all 69 are green on this tree — so it
was driven red four ways instead, each against a copy of the hook tree with
`_HOOKS_ROOT` pointed at it. Repeat any of them the same way; none of them needs the
real hooks touched. Measured 2026-08-26:

1. `claude-code/resolve-scope.sh`, `thalamus_refuse_unreadable` body replaced with
   `exit 0` — 31 rows leak, every claude-code and codex row. The Cursor rows survive,
   because their refusal is minted in the Cursor mirror of that function.
2. `cursor/resolve-scope.sh`, the same function printing `{"permission": "allow"}`
   instead of the deny object — the 12 Cursor rows leak and nothing else does.
3. `thalamus_read_guard_command` (claude-code) reverted to `[ -n "$command" ] || exit
   0` — exactly 4 rows leak: the drifted-key cells of gremlin-guard and
   room-command-guard on claude-code and codex. Malformed, empty and no-jq stay green,
   which is the discrimination the drifted-key row exists for. `write-guard.sh` also
   stays green there and legitimately so: it does not use that helper's value, it falls
   back to searching the RAW payload, and the drifted key leaves the command text in
   the haystack.
4. The Cursor twin of (3) — the 3 Cursor drifted-key cells leak as NO_VERDICT rather
   than ALLOW, because that mutant ends the adapter before it prints anything. An
   exit-code reader cannot tell that from the deny path, which also exits 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_HOOKS_ROOT = Path(__file__).resolve().parents[3] / "src/thalamus/harness/hooks"

#: Claude Code's and codex's blocking exit code. Anything else lets the call through.
_BLOCK = 2

DENY = "DENY"
ALLOW = "ALLOW"
#: Cursor only: the process ended without printing a permission object. Not a refusal —
#: what Cursor does with one is not established — but distinct from an explicit allow,
#: because the two want different fixes.
NO_VERDICT = "NO_VERDICT"

#: A room name that is a plain word, because `room-command-guard.sh` interpolates it
#: into a grep -E pattern and `room-guard.sh` into another.
_ROOM = "qeprobe"

#: A path no scope but `qe` may write, per contract/ownership.PATH_OWNERSHIP. Absolute,
#: because that table fnmatches the absolute POSIX path — and containing the literal
#: `/tests/qe/` so the guard's degraded raw-payload branch matches it too. Either way
#: the verdict is a block, which is what makes this control independent of whether the
#: box can import `thalamus.contract.ownership` at all.
_OWNED_PATH = "/qe-probe/tests/qe/cases/probe.py"

#: Marker + source step + no terminal step: the conjunction gremlin-guard.sh requires.
_LAZY_TRAVERSAL = (
    'python3 -c "from gremlin_python.process.anonymous_traversal import traversal; '
    'g.V().hasLabel(\\"Claim\\")"'
)

#: A command every shell guard is documented to leave alone. The negative control.
_PERMITTED_COMMAND = "ls -la /tmp"


# ------------------------------------------------------------------------------------
# Payloads. Shape is per harness, not per guard: Cursor's shell hook receives
# `{command, cwd, workspace_roots, conversation_id}` and its adapters reshape that onto
# the Claude Code payload, which codex sends verbatim.
# ------------------------------------------------------------------------------------

def _shell_payload(harness: str, command: str, *, drift: bool = False) -> str:
    key = "shell_command" if drift else "command"
    if harness == "cursor":
        return json.dumps({key: command, "cwd": "/tmp",
                           "conversation_id": "qe-probe", "workspace_roots": ["/tmp"]})
    return json.dumps({"tool_name": "Bash", "tool_input": {key: command},
                       "session_id": "qe-probe", "cwd": "/tmp"})


def _role_payload(harness: str, target: str) -> str:
    """An edit of one file. codex's editing tool is `apply_patch` and names its targets
    in the patch envelope's own header lines, so its adapter is exercised rather than
    bypassed by handing it a `Write` it would only forward."""
    if harness == "codex":
        patch = (f"*** Begin Patch\n*** Update File: {target}\n@@\n hello\n+probe\n"
                 "*** End Patch")
        return json.dumps({"tool_name": "apply_patch", "tool_input": {"command": patch},
                           "session_id": "qe-probe", "cwd": "/tmp"})
    return json.dumps({"tool_name": "Write",
                       "tool_input": {"file_path": target, "content": "probe"},
                       "session_id": "qe-probe", "cwd": "/tmp"})


def _room_payload(harness: str, to: str) -> str:
    return json.dumps({"tool_name": "SendMessage", "tool_input": {"to": to},
                       "session_id": "qe-probe", "cwd": "/tmp"})


# ------------------------------------------------------------------------------------
# Verdict readers, one per harness protocol.
# ------------------------------------------------------------------------------------

def _verdict_from_exit(proc: subprocess.CompletedProcess) -> tuple[str, str]:
    """Claude Code and codex: exit 2 blocks, and every other code lets the call run.

    A guard that died at its first `jq` exits 5, which is reported as ALLOW with the
    code attached — because that is what it does to the tool call, and the code is the
    part of the witness that says why.
    """
    if proc.returncode == _BLOCK:
        return DENY, "exit 2"
    return ALLOW, f"exit {proc.returncode}"


def _verdict_from_permission(proc: subprocess.CompletedProcess) -> tuple[str, str]:
    """Cursor: the verdict is a JSON object on stdout, and the exit code says nothing.

    `ask` is not a refusal here. It is a different outcome the protocol allows and no
    guard in this tree emits, so reporting it as ALLOW with the value attached names
    the drift rather than absorbing it into either bucket.
    """
    raw = proc.stdout.strip()
    if not raw:
        return NO_VERDICT, f"nothing on stdout (exit {proc.returncode})"
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return NO_VERDICT, f"stdout is not JSON: {raw[:120]!r}"
    if not isinstance(obj, dict):
        return NO_VERDICT, f"stdout JSON is {type(obj).__name__}, not an object"
    permission = obj.get("permission")
    if permission == "deny":
        return DENY, "permission=deny"
    return ALLOW, f"permission={permission!r}"


_HARNESSES: dict[str, Callable[[subprocess.CompletedProcess], tuple[str, str]]] = {
    "claude-code": _verdict_from_exit,
    "cursor": _verdict_from_permission,
    "codex": _verdict_from_exit,
}


# ------------------------------------------------------------------------------------
# The table.
# ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Guard:
    script: str
    #: Which hook directories ship this script. Verified against disk, not trusted.
    harnesses: tuple[str, ...]
    #: Builds a payload for one harness: (harness, subject). Shell builders take a
    #: `drift` keyword and are the only ones asked for it — the narrower matchers owe
    #: no refusal on a missing command, so they are never handed one.
    payload: Callable[..., str]
    #: The subject the guard is documented to refuse, and one it must leave alone.
    refusable: str
    permitted: str
    #: True where the hook's matcher is `Bash`, so the command IS the event and an
    #: absent one is an unreadable payload rather than a call with nothing in it.
    bash_matched: bool = True
    env: dict[str, str] = field(default_factory=dict)


_GUARDS: tuple[_Guard, ...] = (
    _Guard("write-guard.sh", ("claude-code", "cursor", "codex"), _shell_payload,
           refusable="thalamus write /tmp/qe-probe-subgraph.json",
           permitted=_PERMITTED_COMMAND),
    _Guard("gremlin-guard.sh", ("claude-code", "cursor", "codex"), _shell_payload,
           refusable=_LAZY_TRAVERSAL, permitted=_PERMITTED_COMMAND),
    _Guard("room-command-guard.sh", ("claude-code", "cursor", "codex"), _shell_payload,
           refusable='tmux send-keys -t other-session "hello" Enter',
           permitted=_PERMITTED_COMMAND,
           env={"THALAMUS_ROOM": _ROOM}),
    # Narrower matchers: no drifted-key row. See the module docstring.
    _Guard("role-guard.sh", ("claude-code", "codex"), _role_payload,
           refusable=_OWNED_PATH, permitted="/tmp/qe-probe-role.txt",
           bash_matched=False),
    _Guard("room-guard.sh", ("claude-code",), _room_payload,
           refusable="outsider", permitted="main",
           bash_matched=False, env={"THALAMUS_ROOM": _ROOM}),
)

#: Truncated JSON: `jq` exits 5 and, unguarded, `set -e` kills the script there.
_MALFORMED_STDIN = '{"tool_name": "Bash", broken'


def _shadow_jq(directory: str) -> str:
    """A PATH entry that makes `jq` fail with 127 while leaving everything else alone.

    The obvious move — `PATH=/nonexistent` — is wrong, and wrong in a way that reads as
    a finding: it removes `bash`, `cat`, `printf` and `grep` too, so the script dies for
    a reason that has nothing to do with the defect under test. The first version of this
    case did exactly that and the runner flagged it MALFORMED, which is the correct
    handling of a broken check and the reason MALFORMED is not a failure bucket.

    127 is chosen because it is what a shell returns for a command it cannot find, so
    the guard sees precisely what it would see on a box without jq.
    """
    stub = Path(directory) / "jq"
    stub.write_text("#!/bin/sh\nexit 127\n", encoding="utf-8")
    stub.chmod(0o755)
    return directory


def _invoke(harness: str, guard: _Guard, stdin: str, *,
            strip_jq: bool = False, home: str) -> tuple[str, str]:
    """Run one guard and read its verdict in its own harness's protocol.

    HOME is redirected because these scripts append to
    `$HOME/.thalamus/guards/<YYYY-MM>.jsonl`, which `thalamus eval gremlin` reads as
    fluency data. Probing without redirection would write probe rows into the live
    instrument and quietly corrupt a real measurement — the suite would become a source
    of the defect class it hunts.

    THALAMUS_SCOPE is pinned to `main` and CLAUDE_CODE_AGENT scrubbed so the scope the
    guards resolve is a property of this call and not of the session running it. Under
    the operator's own pin `role-guard.sh` would resolve `qe`, which owns `_OWNED_PATH`,
    and its positive control would silently stop being one.
    """
    env = dict(os.environ)
    env["HOME"] = home
    env["THALAMUS_SCOPE"] = "main"
    env.pop("CLAUDE_CODE_AGENT", None)
    env.pop("THALAMUS_ROOM", None)
    env.pop("THALAMUS_SANDBOX", None)  # sandbox makes every hook exit 0; that mutes the probe
    env.update(guard.env)
    if strip_jq:
        env["PATH"] = _shadow_jq(tempfile.mkdtemp(prefix="qe-nojq-")) + os.pathsep \
            + env.get("PATH", "")
    proc = subprocess.run(
        ["bash", str(_HOOKS_ROOT / harness / guard.script)],
        input=stdin, capture_output=True, text=True, env=env, timeout=60, check=False,
    )
    return _HARNESSES[harness](proc)


def _coverage_gap() -> str:
    """Every `*-guard.sh` on disk against every one this table names, both directions."""
    declared = {(h, g.script) for g in _GUARDS for h in g.harnesses}
    found: set[tuple[str, str]] = set()
    for harness in _HARNESSES:
        directory = _HOOKS_ROOT / harness
        if not directory.is_dir():
            return f"{directory} is not a directory, so its guards were never probed"
        found |= {(harness, p.name) for p in directory.glob("*-guard.sh")}
    untested = sorted(f"{h}/{s}" for h, s in found - declared)
    missing = sorted(f"{h}/{s}" for h, s in declared - found)
    parts = []
    if untested:
        parts.append(f"on disk and untested: {', '.join(untested)}")
    if missing:
        parts.append(f"named here and not on disk: {', '.join(missing)}")
    return "; ".join(parts)


def run() -> Finding | None:
    gap = _coverage_gap()
    if gap:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=("the guard table and the guard scripts on disk disagree, so this "
                     "case's coverage is not what it claims and a green run says "
                     "nothing about the scripts it never reached"),
            witness=gap,
            site="src/thalamus/harness/hooks/*/",
        )

    with tempfile.TemporaryDirectory() as home:
        # ---- Controls, both directions, before anything else is read ---------------
        broken_controls: list[str] = []
        for guard in _GUARDS:
            for harness in guard.harnesses:
                cell = f"{harness}/{guard.script}"
                verdict, detail = _invoke(
                    harness, guard, guard.payload(harness, guard.refusable), home=home)
                if verdict != DENY:
                    broken_controls.append(
                        f"{cell} did not refuse the input it is documented to refuse "
                        f"({verdict}: {detail})")
                verdict, detail = _invoke(
                    harness, guard, guard.payload(harness, guard.permitted), home=home)
                if verdict == DENY:
                    broken_controls.append(
                        f"{cell} refused a permitted call ({detail}), so its refusals "
                        "below are not evidence of anything")

        if broken_controls:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=("the positive controls failed: a guard that does not refuse "
                         "its own documented input, or refuses everything, makes every "
                         "refusal below unfalsifiable — the trigger conditions have "
                         "changed"),
                witness=" | ".join(broken_controls),
                site="src/thalamus/harness/hooks/*/",
            )

        # ---- The unreadable inputs -------------------------------------------------
        leaks: list[str] = []
        for guard in _GUARDS:
            for harness in guard.harnesses:
                cell = f"{harness}/{guard.script}"
                probes: list[tuple[str, str, bool]] = [
                    # Same refusable subject as the control, one key off. Valid JSON,
                    # and the guard cannot see the command in it.
                    ("drifted-key",
                     guard.payload(harness, guard.refusable, drift=True), False),
                    ("malformed-stdin", _MALFORMED_STDIN, False),
                    ("empty-stdin", "", False),
                    # jq gone from PATH, on the input that blocks when it is present.
                    ("no-jq", guard.payload(harness, guard.refusable), True),
                ] if guard.bash_matched else [
                    ("malformed-stdin", _MALFORMED_STDIN, False),
                    ("empty-stdin", "", False),
                    ("no-jq", guard.payload(harness, guard.refusable), True),
                ]
                for label, stdin, strip_jq in probes:
                    verdict, detail = _invoke(
                        harness, guard, stdin, strip_jq=strip_jq, home=home)
                    if verdict != DENY:
                        leaks.append(f"{cell} {label} -> {verdict} ({detail})")

    if not leaks:
        return None

    return Finding(
        failure_class=FailureClass.FAILED_OPEN,
        summary=(
            "PreToolUse guards permit the tool call on input they cannot read. The "
            "shared prologue aborts under `set -e` before any guard rule runs and the "
            "abort code is not the blocking code; a payload whose command field has "
            "moved is read as a call with nothing in it"
        ),
        witness=" | ".join(leaks),
        site="src/thalamus/harness/hooks/*/resolve-scope.sh "
             "(thalamus_read_guard_input, thalamus_read_guard_command)",
    )


CASE = Case(
    name="guards-fail-closed-on-unparseable-input",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.FAILED_OPEN, FailureClass.COLLAPSED_SENTINEL),
    summary="a guard that cannot read its input must not permit the call, on any harness",
    run=run,
)
