"""Re-probing harness capability declarations against the CLIs that answer them.

Every claim this repo makes about a harness has, until now, been prose that nothing
could check. The bill came due: five declarations were wrong at once, one of them
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
the extraction sandbox can never satisfy. It does not.

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
in a mode the probe never entered. This is not pedantry: a `<timestamp>` observed in
print mode is one inference away from unwiring the clock tier for interactive sessions
nobody has looked at.

So a flag probe establishes the narrowest condition there is — `Condition.PARSE`, that
the argument parser accepted the flag — and never a mode it did not enter, because a
wider reading is exactly how one print-mode observation becomes a general belief. A
declaration does not state a condition it claims to hold under, so the checker cannot
compare the two and a claim wider than its evidence is not detectable here.
**MALFORMED** reports the defects in the record it can see — an unresolvable derivation,
or a sentinel the CLI accepted — and stays separate from DRIFT, a defect in the world.
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

    def argv(self) -> list[str]:
        # The flag under test first, the sentinel second, so the sentinel is the only
        # thing that can fail once the flag has parsed. `-p x` gives commander a
        # complete-looking invocation without reaching execution — parsing fails first.
        return [self.binary, self.flag, *self.args, SENTINEL, "-p", "x"]


@dataclass(frozen=True)
class DerivedProbe:
    """Recompute a claim the repo makes about *itself* from the data it is about.

    The second failure mode is not a vendor changing something — it is a
    claim about our own tables going stale while the tables move underneath it.
    `install.py` asserted a hook-parity count that was wrong for three scripts, and
    no test could notice, because a prose count is compared to nothing.

    A CLI probe cannot reach this: the subject is the repo, not the harness. But it
    is the *same* failure — a declaration nothing re-asks — so it belongs to the same
    checker rather than to a separate one that would be run at a different time.

    The derivation is named, not held: a row carrying a function is no longer data
    that can be listed, diffed or serialized, and this table's whole value is that it
    can be read. `DERIVATIONS` resolves the name, and an unresolvable name is
    MALFORMED rather than skipped — a row pointing at a derivation that no longer
    exists is exactly the drift being hunted.
    """

    derivation: str
    # The hand-authored expectation. Compared field by field, so a partial record
    # checks the fields it names and stays silent about the rest.
    declared: dict


@dataclass(frozen=True)
class ProbeResult:
    probe: FlagProbe | DerivedProbe
    declared: bool | dict
    observed: bool | dict | None
    outcome: Outcome
    detail: str = ""

    @property
    def label(self) -> str:
        if isinstance(self.probe, DerivedProbe):
            return f"derived {self.probe.derivation}"
        return f"{self.probe.binary} {self.probe.flag}"


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
     "exits 1 before doing any work"),
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


def _derive_hook_parity() -> dict:
    # Imported here rather than at module scope: `contract/` does not depend on
    # `harness/`, and a derivation is not a reason to invert that.
    from thalamus.harness.install import derive_hook_parity

    return derive_hook_parity()


def _refute_hook_parity_claims() -> dict:
    # Same local import, same reason.
    from thalamus.harness.install import DECLARED_HOOK_PARITY, refute_parity_claims

    return {"refuted": refute_parity_claims(DECLARED_HOOK_PARITY)}


# Name -> the function that recomputes it. Adding a derivation here is what makes a
# self-claim checkable; a claim with no entry is prose again.
#
# Two entries for one record, because its six fields split on whether the tables can
# produce them. `hook_parity` recomputes the four that are set arithmetic over the
# wirings. `hook_parity_claims` cannot recompute `renames` and `native` — the tables
# carry nothing that says one script plays another's role — so it tries to refute them
# instead, and declares that nothing does. Refutation is a weaker instrument than
# recomputation and is the one available; the alternative was leaving two fields
# compared to nothing, which is the state the record was built to end.
DERIVATIONS = {
    "hook_parity": _derive_hook_parity,
    "hook_parity_claims": _refute_hook_parity_claims,
}


def probe_derived(probe: DerivedProbe) -> ProbeResult:
    """Recompute, and compare field by field with what was declared."""
    compute = DERIVATIONS.get(probe.derivation)
    if compute is None:
        return ProbeResult(
            probe, probe.declared, None, Outcome.MALFORMED,
            f"no derivation named `{probe.derivation}`",
        )

    observed = compute()
    # Only the declared fields are compared. A record that names three of five fields
    # is checked on three and makes no claim about the other two, which keeps a
    # partial declaration honest instead of forcing it to invent the rest.
    disagreements = [
        f"{field}: declared {value!r}, computed {observed.get(field)!r}"
        for field, value in probe.declared.items()
        if observed.get(field) != value
    ]
    if disagreements:
        return ProbeResult(probe, probe.declared, observed, Outcome.DRIFT,
                           "; ".join(disagreements))
    return ProbeResult(probe, probe.declared, observed, Outcome.CONFIRMED)


def _declared_parity_row() -> tuple[DerivedProbe, str]:
    from thalamus.harness.install import DECLARED_HOOK_PARITY

    return (
        DerivedProbe(
            derivation="hook_parity",
            declared={
                "scripts": DECLARED_HOOK_PARITY.scripts,
                "shared": DECLARED_HOOK_PARITY.shared,
                "missing": DECLARED_HOOK_PARITY.missing,
                "extra": DECLARED_HOOK_PARITY.extra,
            },
        ),
        "install.DECLARED_HOOK_PARITY — the count that was wrong for three scripts while "
        "the suite stayed green",
    )


def _parity_claims_row() -> tuple[DerivedProbe, str]:
    """The two fields the wirings cannot produce, declared as unrefuted.

    `()` is a real claim, not a tautology: it asserts every hand-written rename and
    native entry is still consistent with the tables that moved underneath it and with
    the scripts on disk. When it breaks, the computed side names which one and how.
    """
    return (
        DerivedProbe(derivation="hook_parity_claims", declared={"refuted": ()}),
        "install.DECLARED_HOOK_PARITY.renames/.native — the two fields the wiring "
        "tables cannot re-derive, checked by refutation instead",
    )


def check_capabilities() -> list[ProbeResult]:
    """Re-ask every checkable declaration. Opens no graph connection, by design."""
    results = [probe_flag(probe, declared=declared) for probe, declared, _ in CAPABILITY_ROWS]
    for row in (_declared_parity_row(), _parity_claims_row()):
        probe, _ = row
        results.append(probe_derived(probe))
    return results
