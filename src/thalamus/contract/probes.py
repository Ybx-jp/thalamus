"""Re-probing harness capability declarations against the CLIs that answer them.

Every claim this repo makes about a harness has, until now, been prose that nothing
could check. lab/054 is the bill: five declarations were wrong at once, one of them
("Cursor distillation works") wrong in a way that broke the feature on every machine
for its whole life, and the test suite was green throughout. The failure is not that
someone wrote the wrong thing down — that is ordinary. It is that **nothing ever
asked the CLI again.**

So this module is deliberately not a type system. A better-typed record of an
unchecked belief is the same belief. What it adds is the one question the layer has
never asked: *is this still true?*

## The sentinel probe

Asking a CLI whether it supports a flag looks like it needs a real invocation —
which costs auth, network, a model call, and on Cursor a workspace-trust grant that
the extraction sandbox can never satisfy (lab/054). It does not.

Both `claude` and `agent` are commander.js programs, and commander rejects an
unknown option during argument parsing — **before** auth, network, workspace trust
and any model call. So put the flag under test first and a guaranteed-unknown
sentinel second, and read which one commander names:

    agent --trust    --thalamus-probe-sentinel -p x  → "unknown option '--thalamus-probe-sentinel'"
    agent --max-turns 5 --thalamus-probe-sentinel -p x  → "unknown option '--max-turns'"

If the CLI names the sentinel, everything before it parsed, so the flag exists. If it
names the flag, it does not. The query is total, offline, unauthenticated, free, and
side-effect-free, at roughly 0.6 s per probe.

Two traps this shape avoids, both measured rather than reasoned about:

- **Do not probe with an action option.** `agent --max-turns 5 --version` exits 0 and
  prints the version: `--version` short-circuits option validation, so a probe built
  on it reports every absent flag as present. The sentinel must be the *only* thing
  that can fail.
- **Do not read `--help`.** `claude --help` does not mention `--max-turns`, while
  `eval/arms.py:707` passes it in production and the sentinel confirms the CLI
  accepts it. Help output omits working flags, and `agent create-chat` is a
  subcommand absent from `agent --help` too. Help text is unsound in both
  directions; the parser is the authority.

## Soundness, and the limit of a probe

A probe is **sound as a falsifier and unsound as a generalizer.** That `--trust`
parses says the flag exists; it does not say what it does, nor that anything holds
in a mode the probe never entered. This is not pedantry — it is the specific error
this session nearly shipped, when a `<timestamp>` observed in print mode was one
inference away from unwiring the clock tier for interactive sessions that had never
been looked at.

So a probe carries the `condition` it was taken under, a declaration carries the
`holds_under` it claims, and a claim wider than its evidence is **MALFORMED** — a
defect in the record, reported separately from DRIFT, which is a defect in the world.
The default condition is the narrowest one, because a wide default is exactly how one
print-mode observation becomes a general belief.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum

# Guaranteed-unknown to any CLI, and namespaced so a vendor cannot plausibly claim it
# later. If a CLI ever accepts this, every probe result becomes "flag exists" and the
# checker would report a clean sweep — so `probe_flag` verifies the sentinel is
# rejected on its own before trusting any answer.
SENTINEL = "--thalamus-probe-sentinel"

# Long enough for process start on a cold page cache, short enough that a hung CLI
# fails the run rather than the run waiting on it. Measured at ~0.6s per probe.
PROBE_TIMEOUT = 30


class Outcome(str, Enum):
    """What re-probing one declaration found."""

    CONFIRMED = "confirmed"       # the CLI still answers as declared
    DRIFT = "drift"               # the CLI answers differently — the world moved
    MALFORMED = "malformed"       # the record is internally wrong, independent of the CLI
    UNPROBEABLE = "unprobeable"   # no probe exists that is free of side effects
    UNAVAILABLE = "unavailable"   # the CLI is not on this box, so nothing was asked


class Condition(str, Enum):
    """The mode an observation was taken under.

    `PRINT` and `INTERACTIVE` are separate because Cursor was measured injecting its
    own `<timestamp>` under `-p` and has never been observed interactively. `PARSE`
    is weaker than both: it says the argument parser accepted a flag, which holds
    regardless of the mode the program would then have entered.
    """

    PARSE = "parse"
    PRINT = "mode:print"
    INTERACTIVE = "mode:interactive"


@dataclass(frozen=True)
class FlagProbe:
    """Does this CLI's argument parser accept this flag?

    A typed row, deliberately not a shell string. A table of commands that a checker
    executes is a laundering surface pointed at the operator's own box — the checker
    would run whatever the row said, and rows are exactly the thing under suspicion.
    It is also not a callable: `tests/test_graph_audit.py` is graph-free precisely
    because its predicates are pure over plain rows, and a row holding a function is
    no longer data that can be listed, diffed or serialized.
    """

    binary: str
    flag: str
    # Values the flag requires to parse. `--max-turns` needs one; `--trust` takes none.
    args: tuple[str, ...] = ()

    @property
    def condition(self) -> Condition:
        return Condition.PARSE

    def argv(self) -> list[str]:
        # The flag under test first, the sentinel second, so the sentinel is the only
        # thing that can fail once the flag has parsed. `-p x` gives commander a
        # complete-looking invocation without reaching execution — parsing fails first.
        return [self.binary, self.flag, *self.args, SENTINEL, "-p", "x"]


@dataclass(frozen=True)
class ProbeResult:
    probe: FlagProbe
    declared: bool
    observed: bool | None
    outcome: Outcome
    detail: str = ""


def _run(argv: list[str]) -> str:
    """Combined output of a probe invocation. Never raises on non-zero exit."""
    proc = subprocess.run(
        argv, capture_output=True, text=True, timeout=PROBE_TIMEOUT,
    )
    return f"{proc.stdout}\n{proc.stderr}"


def sentinel_is_rejected(binary: str) -> bool:
    """Is the sentinel still unknown to this CLI?

    The probe reads a *negative* — "the CLI did not complain about my flag" — so it
    is only meaningful while the sentinel itself reliably provokes a complaint. If a
    vendor ever accepted it, every flag would read as present and the checker would
    report a clean sweep of confirmations. Checked once per binary, not per row.
    """
    return f"unknown option '{SENTINEL}'" in _run([binary, SENTINEL, "-p", "x"])


def probe_flag(probe: FlagProbe, *, declared: bool) -> ProbeResult:
    """Ask the parser, and compare with what was declared."""
    if shutil.which(probe.binary) is None:
        return ProbeResult(probe, declared, None, Outcome.UNAVAILABLE,
                           f"`{probe.binary}` not on PATH")

    if not sentinel_is_rejected(probe.binary):
        # Refuse rather than report: a probe whose control has failed produces
        # confident answers that are all the same, which is worse than no answer.
        return ProbeResult(
            probe, declared, None, Outcome.MALFORMED,
            f"`{probe.binary}` no longer rejects the sentinel, so flag probes "
            f"cannot discriminate — every flag would read as present",
        )

    output = _run(probe.argv())
    named_sentinel = f"unknown option '{SENTINEL}'" in output
    named_flag = f"unknown option '{probe.flag}'" in output

    if named_sentinel:
        observed = True
    elif named_flag:
        observed = False
    else:
        # Neither named: the CLI did something other than reject an unknown option —
        # an action option short-circuited validation, or the output shape changed.
        # Not an answer, and must not be rounded into one.
        return ProbeResult(
            probe, declared, None, Outcome.UNPROBEABLE,
            f"neither `{probe.flag}` nor the sentinel was named: {output.strip()[:160]}",
        )

    if observed == declared:
        return ProbeResult(probe, declared, observed, Outcome.CONFIRMED)
    return ProbeResult(
        probe, declared, observed, Outcome.DRIFT,
        f"declared {'present' if declared else 'absent'}, "
        f"parser says {'present' if observed else 'absent'}",
    )


# The claims `agents.py` already makes that a parser can answer today. Nothing here
# is new belief — each row is an assertion the registry has been carrying in prose or
# in a tuple, now written where it can be re-asked.
#
# `--max-turns` is the row that matters most: it is the surviving half of the
# `arm_blockers` sentence whose other half was false for weeks, and its truth is the
# difference between "Cursor cannot drive an eval arm" and "Cursor can".
CAPABILITY_ROWS: tuple[tuple[FlagProbe, bool, str], ...] = (
    # (probe, declared_present, why this row exists)
    (FlagProbe("agent", "--trust"), True,
     "agents.cursor.headless_preconditions — without it every sandbox extraction "
     "exits 1 before doing any work (lab/054)"),
    (FlagProbe("agent", "--max-turns", ("5",)), False,
     "agents.cursor.arm_blockers — an arm cannot bound turns without it"),
    (FlagProbe("agent", "--output-format", ("json",)), True,
     "agents.AgentCLI.argv — extraction parses the JSON envelope"),
    (FlagProbe("agent", "--model", ("composer-2.5",)), True,
     "agents.cursor.default_model is passed through --model"),
    (FlagProbe("claude", "--output-format", ("json",)), True,
     "agents.AgentCLI.argv — the shared half of the two invocations"),
    (FlagProbe("claude", "--max-turns", ("5",)), True,
     "eval/arms.py:707 passes it in production, and `claude --help` does not "
     "mention it — so this row exists to outlive the help text"),
)


def check_capabilities() -> list[ProbeResult]:
    """Re-ask every probeable declaration. Opens no graph connection, by design."""
    return [probe_flag(probe, declared=declared) for probe, declared, _ in CAPABILITY_ROWS]
