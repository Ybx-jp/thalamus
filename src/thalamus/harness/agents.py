"""The headless coding-agent CLIs Thalamus shells out to, in one place.

Every surface that runs a coding agent as a subprocess resolves its binary,
default model and flags from here rather than spelling `claude` inline. The
reason is the one this repo keeps relearning: a hardcoded vendor binary is
invisible until the machine that lacks it tries to use it, and then it fails as
"distillation stopped happening" rather than as an error anyone reads. A Cursor
session on a Cursor-only machine must not need Claude Code installed and
authenticated to become memory (docs/07).

Deliberately a leaf module — it imports nothing from Thalamus, so both
`harness/extraction.py` (which already depends on `eval/`) and `eval/arms.py`
can use it without a cycle.

**Capability is declared, not assumed.** The two CLIs are near-identical for
extraction — both take `-p`, `--model` and `--output-format json`, and both
return an envelope carrying `result`, `is_error` and `duration_ms` under those
exact names — and quite different everywhere else. Rather than let each caller
rediscover that, each entry states what it can and cannot do, and callers refuse
loudly on the gaps instead of substituting a binary and hoping. The alternative
— swapping `claude` for `agent` everywhere and seeing what breaks — produces
surfaces that run and report success while measuring nothing, which is the
failure class lab/016 and lab/022 are both about.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import PurePath

CLAUDE_DEFAULT_MODEL = "sonnet"

# Composer 2.5, deliberately not the fast variant: distillation is a batch sweep
# where nothing waits on the result, so the quality/latency trade runs the other
# way from interactive use. `composer-2.5-fast` is the variant being declined, and
# it is a real identifier — the choice is between two things that both exist.
#
# Verified against a live `agent --list-models` (2026-08-10, CLI 2026.08.04, lab/054).
# A wrong string fails at invocation rather than silently selecting another model,
# and `MODEL_HINT` turns that failure into one command's worth of fixing.
CURSOR_DEFAULT_MODEL = "composer-2.5"

MODEL_HINT = "run `agent --list-models` for the accepted identifiers"

# The sandbox a headless Thalamus subprocess runs in, named in two ways because
# each one is visible to a different observer.
#
# A headless `claude -p` / `agent -p` is a full session to its own harness: it
# gets a session id, a transcript on disk, and — because the hook suite is
# installed at user scope — it fires SessionEnd, which distills it. The result is
# memory *about the act of making memory*: a Session whose summary paraphrases
# the session it was distilling, its own Claims and open Threads, and its own
# headless run behind it, one level deeper. A sandbox is not a session and must
# leave no memory.
#
# `SANDBOX_ENV` marks the subprocess so every hook the sandbox inherits can
# recognise itself and decline (hooks are children of the CLI, so the marker
# reaches them). `SANDBOX_TMP_PREFIX` names the throwaway cwd it runs in, which
# is what the transcript *reader* sees — a transcript already on disk carries no
# environment, so retroactive sweeps (`thalamus bootstrap`, an explicit
# `thalamus extract -- <dir>`) need the second name to refuse the same input.
SANDBOX_ENV = "THALAMUS_SANDBOX"
SANDBOX_TMP_PREFIX = "thalamus-extract-"


def sandbox_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """`base` (default: the current environment) plus the sandbox marker."""
    return {**(os.environ if base is None else base), SANDBOX_ENV: "1"}


def is_sandbox_cwd(cwd: str) -> bool:
    """Was this working directory an extraction sandbox?

    Matches on the directory *name*, not on `/tmp`: TMPDIR moves the sandbox and
    a path-prefix test would silently stop recognising it there.
    """
    return any(part.startswith(SANDBOX_TMP_PREFIX) for part in PurePath(cwd).parts)


@dataclass(frozen=True)
class AgentCLI:
    """One headless coding-agent CLI, and what Thalamus may ask of it."""

    harness: str
    binary: str
    default_model: str
    # Claude Code's JSON envelope prices the call (`total_cost_usd`); Cursor's
    # carries no dollar figure. It does carry a `usage` block — `inputTokens`,
    # `outputTokens`, `cacheReadTokens`, `cacheWriteTokens` (lab/054) — so the gap
    # is pricing, not instrumentation, and a future rate table could close it.
    # Kept as a capability rather than defaulted to 0.0, because a zero meaning
    # "not reported" is indistinguishable from one meaning "free" and would
    # under-report the spend `eval cost` totals.
    reports_cost: bool
    # Why this CLI cannot yet drive an eval arm. Empty means it can. Arms need far
    # more than a binary — see `eval/arms.py` — and a half-ported arm produces
    # records that look like measurements and are not.
    arm_blockers: tuple[str, ...] = field(default_factory=tuple)
    # Extra hint appended to invocation failures, where the vendor gives us a way
    # to discover the right value. Attached to the *model* argument specifically —
    # a hint appended to every failure misattributes unrelated ones, which is how
    # a workspace-trust refusal came to advise running `agent --list-models`.
    model_hint: str = ""
    # Flags this CLI needs before it will run non-interactively in a directory it
    # has never seen. Not a preference: Cursor refuses an untrusted workspace with
    # exit 1 and a human-readable prompt *instead of* the JSON envelope, so every
    # sandbox extraction fails before doing any work (measured live, lab/054 — the
    # extraction sandbox is a fresh mkdtemp every run and is therefore never
    # trusted). Claude Code has no equivalent precondition and declares none.
    #
    # This is the seam the shared `argv()` hid: the two CLIs agree on `-p`,
    # `--model` and `--output-format json`, and the near-identity made an
    # invocation shape look like a shared one. It is not — one side has a
    # precondition the other lacks, and a method returning a single argv had
    # nowhere to say so.
    headless_preconditions: tuple[str, ...] = field(default_factory=tuple)

    def argv(self, model: str) -> list[str]:
        """The print-mode invocation, plus whatever this CLI needs to run at all."""
        return [
            self.binary, "-p", "--model", model, "--output-format", "json",
            *self.headless_preconditions,
        ]

    @property
    def runs_arms(self) -> bool:
        return not self.arm_blockers


AGENT_CLIS: dict[str, AgentCLI] = {
    "claude": AgentCLI(
        harness="claude",
        binary="claude",
        default_model=CLAUDE_DEFAULT_MODEL,
        reports_cost=True,
    ),
    "cursor": AgentCLI(
        harness="cursor",
        binary="agent",
        default_model=CURSOR_DEFAULT_MODEL,
        reports_cost=False,
        model_hint=MODEL_HINT,
        # `--trust` and not `--force`: the refusal is about the *workspace*, and
        # the narrower flag is the one that answers it. `--force`/`--yolo` would
        # also clear it, by additionally allowing every tool call — authority the
        # extraction pass has no use for, since it reads a transcript handed to it
        # on stdin and calls nothing.
        headless_preconditions=("--trust",),
        # One claim per row, each independently falsifiable. A row bundling a true
        # and a false claim cannot be checked or retired: the permission-flag half
        # of the former second row was false from the day Cursor shipped `--force`,
        # and it survived because retiring it would have meant retiring `--max-turns`
        # with it. Rows retired on live evidence are deleted, not annotated.
        arm_blockers=(
            "credential staging copies ~/.claude.json and "
            "~/.claude/.credentials.json into the arm HOME; Cursor authenticates "
            "from its own config root, which XDG_CONFIG_HOME moves (lab/054)",
            "--max-turns has no Cursor equivalent, so an arm cannot bound turns",
            "the run envelope is read for num_turns, which Cursor does not report",
            "escape detection and session-fault classification read Claude Code's "
            "error strings, which Cursor's envelope does not carry",
        ),
    ),
}


class UnknownHarness(ValueError):
    pass


def cli_for(harness: str) -> AgentCLI:
    try:
        return AGENT_CLIS[harness]
    except KeyError:
        raise UnknownHarness(
            f"no agent CLI for harness `{harness}`; "
            f"known: {', '.join(sorted(AGENT_CLIS))}"
        ) from None


def default_model(harness: str) -> str:
    return cli_for(harness).default_model


HARNESSES = tuple(sorted(AGENT_CLIS))
