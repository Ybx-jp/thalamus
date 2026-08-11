"""A PreToolUse guard that cannot parse its input must not permit the call.

Every guard shares one prologue: `set -euo pipefail`, then `input=$(cat)`, then `jq`.
Under `set -e` a `jq` failure aborts the script before any guard logic runs, and the
abort code is not the blocking code (2), so the tool call proceeds. From outside, a
guard that examined the input and approved it and a guard that died before looking are
the same event.

The positive control is the whole case, and it took four attempts to build correctly —
three earlier ones "demonstrated" the fail-open using input the guard would never have
blocked anyway:

- `g.V().drop()` is ALLOWED, correctly: `.drop()` IS a terminal step, and this guard's
  subject is unterminated laziness, not destruction.
- a bare `g.V().hasLabel("Claim")` is allowed too, because `gremlin-guard.sh:46`
  requires a gremlin-python MARKER before it engages at all.
- malformed shell quoting produced `jq` exit 5 from the harness's own broken JSON,
  which reads exactly like the defect under test.

So the blocking input must satisfy three conjunctive conditions — marker, source step,
no terminal step — and the control asserts it really does block before any conclusion is
drawn from it not blocking.

That narrowness is itself worth recording. It is deliberate (guard v4 over-blocked and
the session routed around it, lab/008), but it means effective coverage is far narrower
than "guards Gremlin queries": anything without those markers is never examined.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_HOOKS = Path(__file__).resolve().parents[3] / "src/thalamus/harness/hooks/claude-code"
_GUARDS = ("gremlin-guard.sh", "role-guard.sh", "room-guard.sh")
_BLOCK = 2

# Marker + source step + no terminal step: the conjunction gremlin-guard.sh actually
# requires. Verified to return exit 2 with jq present.
_BLOCKING_COMMAND = (
    'python3 -c "from gremlin_python.process.anonymous_traversal import traversal; '
    'g.V().hasLabel(\\"Claim\\")"'
)


def _payload(command: str) -> str:
    return json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "session_id": "qe-probe",
        "cwd": "/tmp",
    })


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


def _invoke(script: str, stdin: str, *, strip_jq: bool = False, home: str) -> int:
    """Run one guard and return its exit code.

    HOME is redirected because these scripts append to `$HOME/.thalamus/guards/<YYYY-MM>.jsonl`,
    which `thalamus eval gremlin` reads as fluency data. Probing without redirection would
    write probe rows into the live instrument and quietly corrupt a real measurement —
    the suite would become a source of the defect class it hunts.
    """
    env = dict(os.environ)
    env["HOME"] = home
    env.pop("THALAMUS_SANDBOX", None)  # sandbox makes every hook exit 0; that mutes the probe
    if strip_jq:
        shadow = tempfile.mkdtemp(prefix="qe-nojq-")
        env["PATH"] = _shadow_jq(shadow) + os.pathsep + env.get("PATH", "")
    proc = subprocess.run(
        ["bash", str(_HOOKS / script)],
        input=stdin, capture_output=True, text=True, env=env, timeout=30, check=False,
    )
    return proc.returncode


def run() -> Finding | None:
    if not _HOOKS.is_dir():
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="hook directory not found, so 'no fail-open' would be indistinguishable "
                    "from 'nothing was probed'",
            witness=str(_HOOKS),
            site="tests/qe/cases/guard_failopen.py",
        )

    with tempfile.TemporaryDirectory() as home:
        blocking = _payload(_BLOCKING_COMMAND)

        # CONTROL: with jq present, this input must actually block.
        control = _invoke("gremlin-guard.sh", blocking, home=home)
        if control != _BLOCK:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    "positive control failed: the reference input did not block even with "
                    "jq present, so any 'fail-open' below would be unfalsifiable — the "
                    "guard's trigger conditions have changed"
                ),
                witness=f"gremlin-guard.sh returned {control}, expected {_BLOCK}",
                site="src/thalamus/harness/hooks/claude-code/gremlin-guard.sh:46",
            )

        leaks: list[str] = []

        # The same input that just blocked, with jq removed from PATH.
        rc = _invoke("gremlin-guard.sh", blocking, strip_jq=True, home=home)
        if rc != _BLOCK:
            leaks.append(f"gremlin-guard.sh no-jq rc={rc} on input that blocks with jq")

        # Malformed and empty stdin, across every guard. These cannot use the blocking
        # input by construction, so they assert the weaker but still required property:
        # an unparseable input must not yield a permit that is indistinguishable from an
        # examined approval.
        for script in _GUARDS:
            for label, stdin in (("malformed", '{"tool_name": "Bash", broken'), ("empty", "")):
                rc = _invoke(script, stdin, home=home)
                if rc != _BLOCK:
                    leaks.append(f"{script} {label}-stdin rc={rc}")

    if not leaks:
        return None

    return Finding(
        failure_class=FailureClass.FAILED_OPEN,
        summary=(
            "PreToolUse guards permit the tool call when they cannot parse their input; "
            "jq's failure aborts the script under `set -e` before any guard logic runs, "
            "and the abort code is not the blocking code (2)"
        ),
        witness=" | ".join(leaks),
        site="src/thalamus/harness/hooks/claude-code/*.sh (shared jq prologue)",
    )


CASE = Case(
    name="guards-fail-closed-on-unparseable-input",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.FAILED_OPEN, FailureClass.COLLAPSED_SENTINEL),
    summary="a guard that cannot parse its input must not permit the call",
    run=run,
)
