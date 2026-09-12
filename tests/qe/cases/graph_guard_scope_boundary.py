"""An expert pin's shell must not reach the graph the MCP tools confine it away from.

Issue #204: `substrate.writer.connect()` applies no scope filter, and `Bash` is not in
`ROSTER_CAPABILITY_DEFAULT.deny_tools`, so before `graph-guard.sh` existed a pin holding
a shell read every vertex and edge in the graph — `main`'s episodic memory and every
other expert's included — regardless of what `memory_query` and `reader.recall` confine
it away from on the MCP surface. `graph-guard.sh` is the fix, wired on all three
harnesses (claude-code directly, codex by delegation, cursor by adapter): outside
`main`, a Bash command carrying a graph-connection marker — on the command line
itself, or inside a `.py` file the command names and the guard reads one level deep —
is refused unless it falls into one of the four misses the guard's own header accepts
on purpose.

Landed in the same change this case does, so this is the regression guard rather than
triaged red — `fixed=True` — and the case is the reproduction issue #204 says is owed.

**Three things this case discriminates**, per the task that filed it, and the second
and third exist because the first alone proves nothing:

  (a) an expert pin's inline `connect()` is refused (`branch: direct` — the marker is
      on the command line)
  (b) the identical command under `main` is not — without this, "everything is
      refused" and "the boundary holds" are the same observation
  (c) an ordinary unmarked command under an expert pin is untouched: `ALLOW`, and
      absent from the ledger entirely, because the marker gate exits before the
      logger is even defined — "the ledger records this boundary's decisions, not
      every Bash call" is the guard's own claim about itself, asserted here rather
      than taken on faith

**A fourth and fifth thing, beyond what the task asked for.**

The guard reads one level into a `.py` file a command names (never its imports), which
closes the two-step bypass this case originally demonstrated live: a heredoc that
writes a file containing the marker, followed by a separate `python <that file>`. The
heredoc still passes (`branch: textedit` — the marker is on that command's own line,
so it was never a miss), but the run that follows is now refused on a new branch,
`branch: script` — asserted below as a REFUSE, not a miss, because the guard's header
says explicitly that this sequence "is not this case" (i.e. not one of the accepted
misses) any more.

What the header accepts now, and what is asserted here as `ALLOW` and labelled a
miss — not left unasserted, so a change to any of the four, in either direction, is
otherwise invisible until someone reads the header and the code side by side:

  1. a house entrypoint (`thalamus`/`pytest`, struck from the command before the
     interpreter check runs)
  2. `docker exec` — the graph without the client, no marker anywhere to see
  3. a script that reaches the graph only through a house module it imports rather
     than naming the client itself — the guard reads the named file, not what it
     imports
  4. a `.py` file that does not exist yet when the guard runs (written by the same
     command that runs it — but not the sequence in the paragraph above, where the
     write and the run are two separate Bash calls with the write going first — or
     fetched mid-pipeline)

Driven directly against the shipped scripts with synthetic PreToolUse/beforeShellExecution
payloads: hermetic, and `$HOME` is redirected per run so the real guard ledger under
`~/.thalamus/guards/` is never touched. Misses 3 and 4 need a real file at a real path
relative to the payload's `cwd`, because that is what the guard itself resolves against,
so this case builds small fixture directories on disk (under a temp dir, cleaned up with
it) rather than asserting against a path it merely names. No live graph anywhere — the
guard decides on command text and, at most, one file's text, and never opens a
connection, which is the property under test.

**Shown capable of going red**, against copies of the hook tree with the real files
untouched — verified by hand against a mutated copy before trusting a red run against
either:

  - Deleting the `if [ "$scope" = "main" ]; then log_event pass main; exit 0; fi` block
    from `claude-code/graph-guard.sh` and rerunning control (b) (`main` running the
    documented `connect()` idiom) turns its verdict from `ALLOW` to `DENY` — this case
    reports `BOUNDARY_LEAK`.
  - Widening the marker gate so an unmarked command no longer exits before the logger is
    defined leaves `ls -la /tmp` at `ALLOW` but adds a ledger row for it — this case
    reports `INVARIANT_FALSIFIED`.
  - Removing the house-entrypoint strike (or the one-level `.py`-file read, or the
    two-step refusal) so a named miss flips to `DENY`, or so the two-step sequence's
    second call flips from `DENY` back to `ALLOW`, is reported as `DOC_CODE_DRIFT` in
    either direction: the header and the code disagreeing is the finding, regardless of
    which one someone intended to be true.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_HOOKS_ROOT = Path(__file__).resolve().parents[3] / "src/thalamus/harness/hooks"
_SCRIPT = "graph-guard.sh"
_HARNESSES = ("claude-code", "codex", "cursor")

#: claude-code's and codex's blocking exit code.
_BLOCK = 2

DENY = "DENY"
ALLOW = "ALLOW"

#: Standing in for any non-main scope: the env-fallback half of `thalamus_resolve_scope`
#: does not check the name against a manifest, so any non-"main" string draws the
#: boundary this guard exists to draw. `architect` is used because it is a real roster
#: scope (`config/experts/architect.yaml`) rather than a name invented for this probe.
_EXPERT_SCOPE = "architect"

#: The documented `connect()` idiom — issue #204's own reproduction — with a marker and
#: an interpreter invocation, so a refusal here says something about a real session.
_CONNECT = (
    'python -c "from thalamus.substrate.writer import connect; '
    "g = connect(); print(g.V().count().next())\""
)

#: No marker anywhere, no `.py` argument to open: this guard's stated business is
#: neither.
_PERMITTED_COMMAND = "ls -la /tmp"

#: A marker, spelled so `grep -qE` finds it whether it sits on a command line or
#: inside a file the guard opens to check.
_MARKER_LINE = "from thalamus.substrate.writer import connect\n"


def _payload(harness: str, command: str, cwd: str) -> str:
    if harness == "cursor":
        return json.dumps({"command": command, "cwd": cwd,
                           "conversation_id": "qe-204-probe", "workspace_roots": [cwd]})
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                       "session_id": "qe-204-probe", "cwd": cwd})


def _verdict(harness: str, proc: subprocess.CompletedProcess) -> tuple[str, str]:
    """Claude Code and codex verdict on the exit code; Cursor's is a JSON object on
    stdout with the exit code carrying nothing (mirrors `guard_failopen.py`'s readers).
    """
    if harness != "cursor":
        if proc.returncode == _BLOCK:
            return DENY, "exit 2"
        return ALLOW, f"exit {proc.returncode}"
    raw = proc.stdout.strip()
    try:
        obj = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return ALLOW, f"stdout not JSON: {raw[:120]!r}"
    permission = obj.get("permission") if isinstance(obj, dict) else None
    if permission == "deny":
        return DENY, "permission=deny"
    return ALLOW, f"permission={permission!r}"


def _invoke(harness: str, command: str, scope: str, home: str, cwd: str) -> tuple[str, str]:
    """Run one harness's `graph-guard.sh` against a synthetic payload.

    `$HOME` is the caller's temp dir, never the real one — the guard appends to
    `$HOME/.thalamus/guards/<YYYY-MM>.jsonl`, and this suite must not write probe rows
    into the ledger `thalamus eval gremlin` reads as fluency data. `cwd` is what the
    guard resolves a `.py` argument against, so fixture-file probes must pass the
    directory the fixture actually lives in. `THALAMUS_SCOPE` is the only channel this
    probe uses to name the pin: no `agent_type` field is set, so `thalamus_resolve_scope`'s
    payload and `CLAUDE_CODE_AGENT` channels both fall through to it, and Cursor — which
    has no other channel at all — resolves the same scope by the same variable.
    """
    script = _HOOKS_ROOT / harness / _SCRIPT
    env = dict(os.environ)
    env["HOME"] = home
    env["THALAMUS_SCOPE"] = scope
    for key in ("CLAUDE_CODE_AGENT", "THALAMUS_ROOM", "THALAMUS_SANDBOX"):
        env.pop(key, None)
    proc = subprocess.run(
        ["bash", str(script)], input=_payload(harness, command, cwd),
        capture_output=True, text=True, env=env, timeout=30, check=False,
    )
    return _verdict(harness, proc)


def _command_hash(command: str) -> str:
    """Mirrors the guard's own `sha256sum | cut -c1-16` join key."""
    return hashlib.sha256(command.encode()).hexdigest()[:16]


def _ledger_hashes(home: str) -> set[str]:
    guard_dir = Path(home) / ".thalamus" / "guards"
    if not guard_dir.is_dir():
        return set()
    hashes: set[str] = set()
    for path in guard_dir.glob("*.jsonl"):
        for line in path.read_text().splitlines():
            if line.strip():
                hashes.add(json.loads(line).get("command_hash", ""))
    return hashes


def _named_misses(tmp_root: Path) -> list[tuple[str, str, str]]:
    """The header's four accepted misses, as (label, command, cwd).

    Two need a real fixture on disk at the path the guard will resolve `cwd` against;
    two need only an absent one. Built once per run and reused across harnesses, since
    none of this depends on which harness is being probed.
    """
    misses: list[tuple[str, str, str]] = [
        ("house entrypoint: thalamus/pytest struck before the interpreter check runs",
         "thalamus eval sync --graph thalamus.substrate", "/tmp"),
        ("docker exec: the graph without the client, no marker to see",
         "docker exec gremlin-server bin/gremlin.sh", "/tmp"),
    ]

    # Miss 3: a script that imports a house module rather than naming the client
    # itself. `runner.py` — the file the command names — carries no marker at all;
    # `wrapper.py` does, and the guard never opens it because it is read one level
    # deep only, off the command line, not off `runner.py`'s own imports.
    imports_dir = tmp_root / "imports-house-module"
    imports_dir.mkdir()
    (imports_dir / "wrapper.py").write_text(
        _MARKER_LINE + "\n\ndef go():\n    return connect()\n"
    )
    (imports_dir / "runner.py").write_text("import wrapper\nwrapper.go()\n")
    misses.append((
        "script imports a house module rather than naming the client itself "
        "(one level deep only)",
        "python runner.py", str(imports_dir),
    ))

    # Miss 4: a `.py` file that does not exist yet when the guard runs. An empty cwd
    # with nothing named `generated/query.py` under it is the whole fixture.
    missing_dir = tmp_root / "missing-py-file"
    missing_dir.mkdir()
    misses.append((
        "a .py file that does not exist when the guard runs",
        "python generated/query.py", str(missing_dir),
    ))

    return misses


def run() -> Finding | None:
    missing = [h for h in _HARNESSES if not (_HOOKS_ROOT / h / _SCRIPT).is_file()]
    if missing:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "graph-guard.sh is not on disk for every harness this case means to "
                "cover, so a green run here would say nothing about the harness it "
                "never reached"
            ),
            witness=f"missing: {missing}",
            site="src/thalamus/harness/hooks/*/graph-guard.sh",
        )

    boundary_failures: list[str] = []
    invariant_failures: list[str] = []
    drift_failures: list[str] = []

    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as tmp_root:
        named_misses = _named_misses(Path(tmp_root))

        for harness in _HARNESSES:
            # (a) the reproduction: an expert pin's inline connect() is refused.
            verdict, detail = _invoke(harness, _CONNECT, _EXPERT_SCOPE, home, "/tmp")
            if verdict != DENY:
                boundary_failures.append(
                    f"{harness}: an expert pin's inline connect() was not refused "
                    f"({verdict}: {detail})"
                )

            # (b) the discrimination control: the identical command under `main`.
            verdict, detail = _invoke(harness, _CONNECT, "main", home, "/tmp")
            if verdict != ALLOW:
                boundary_failures.append(
                    f"{harness}: `main` was refused the same command an expert pin "
                    f"is refused ({verdict}: {detail})"
                )

            # (c) an unmarked command under an expert pin is untouched: ALLOW, and no
            # ledger row names it — the marker gate exits before log_event is defined,
            # so a row here means the gate ran on a command with no marker in it.
            verdict, detail = _invoke(harness, _PERMITTED_COMMAND, _EXPERT_SCOPE, home, "/tmp")
            if verdict != ALLOW:
                invariant_failures.append(
                    f"{harness}: an unmarked command was not left alone "
                    f"({verdict}: {detail})"
                )
            elif _command_hash(_PERMITTED_COMMAND) in _ledger_hashes(home):
                invariant_failures.append(
                    f"{harness}: an unmarked command was logged to the ledger, which "
                    f"is documented to record this boundary's decisions and not every "
                    f"Bash call"
                )

            # The header's four named misses: asserted ALLOW and labelled as misses,
            # so a change to any of them — either direction — is drift against the
            # header rather than an unnoticed pass or an unexplained new red.
            for label, command, cwd in named_misses:
                verdict, detail = _invoke(harness, command, _EXPERT_SCOPE, home, cwd)
                if verdict != ALLOW:
                    drift_failures.append(
                        f"{harness}/{label}: documented as an accepted miss, but this "
                        f"run refused it ({verdict}: {detail})"
                    )

            # The two-step sequence this case originally demonstrated as a live
            # bypass: a heredoc that writes a marked file (still ALLOW — the marker
            # sits on that command's own line, so it was never a miss) followed by a
            # separate call that runs the file it wrote. The guard cannot see step
            # one's side effect on its own — a PreToolUse hook is asked before the
            # tool runs, not after — so this materializes the file itself, standing in
            # for step one's real Bash execution, and checks step two only. The
            # header is explicit that this sequence is not an accepted miss any more,
            # so a flip to ALLOW here is doc-code drift, not a new finding.
            seq_dir = Path(tmp_root) / f"seq-{harness}"
            seq_dir.mkdir()
            seq_file = seq_dir / "seq.py"
            heredoc = f"cat > {seq_file} <<'EOF'\n{_MARKER_LINE}EOF"
            verdict, detail = _invoke(harness, heredoc, _EXPERT_SCOPE, home, str(seq_dir))
            if verdict != ALLOW:
                drift_failures.append(
                    f"{harness}/heredoc step of the two-step sequence: documented as "
                    f"ALLOW (`branch: textedit`, the marker is on that command's own "
                    f"line), but this run refused it ({verdict}: {detail})"
                )
            seq_file.write_text(_MARKER_LINE)
            verdict, detail = _invoke(
                harness, f"python {seq_file}", _EXPERT_SCOPE, home, str(seq_dir)
            )
            if verdict != DENY:
                drift_failures.append(
                    f"{harness}/run step of the two-step sequence: the guard's header "
                    f"says a written-then-run file is refused (`branch: script`), but "
                    f"this run allowed it ({verdict}: {detail}) — the two-step bypass "
                    f"this case was written to demonstrate is open again"
                )

    if boundary_failures:
        return Finding(
            failure_class=FailureClass.BOUNDARY_LEAK,
            summary=(
                "graph-guard.sh's scope boundary does not hold as documented: an "
                "expert pin's direct graph connection must be refused and `main`'s "
                "must not be, and at least one harness got one of the two wrong"
            ),
            witness="; ".join(boundary_failures),
            site="src/thalamus/harness/hooks/*/graph-guard.sh",
        )

    if invariant_failures:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "graph-guard.sh's marker gate is documented to leave unmarked Bash "
                "calls both unblocked and unlogged; at least one harness violated "
                "the logging half, the ledger half, or both"
            ),
            witness="; ".join(invariant_failures),
            site="src/thalamus/harness/hooks/claude-code/graph-guard.sh",
        )

    if drift_failures:
        return Finding(
            failure_class=FailureClass.DOC_CODE_DRIFT,
            summary=(
                "graph-guard.sh's header names four misses it accepts on purpose and "
                "explicitly disclaims a fifth (the write-then-run sequence); at least "
                "one of those five claims no longer matches what the guard does"
            ),
            witness="; ".join(drift_failures),
            site="src/thalamus/harness/hooks/claude-code/graph-guard.sh",
        )

    return None


CASE = Case(
    name="graph-guard-scope-boundary",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.INVARIANT_FALSIFIED,
             FailureClass.DOC_CODE_DRIFT, FailureClass.COLLAPSED_SENTINEL),
    summary=(
        "issue #204's reproduction: an expert pin's inline connect() is refused "
        "across every harness, main's is not, an unmarked command is left alone, and "
        "the write-then-run two-step this case once demonstrated as a live bypass is "
        "refused on its second step"
    ),
    run=run,
    issue=204,
    fixed=True,
)
