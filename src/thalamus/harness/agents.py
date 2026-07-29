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

from dataclasses import dataclass, field

CLAUDE_DEFAULT_MODEL = "sonnet"

# Composer 2.5, deliberately not the fast variant: distillation is a batch sweep
# where nothing waits on the result, so the quality/latency trade runs the other
# way from interactive use.
#
# ⚠️ Unverified. Cursor documents `--model <model>` and `--list-models` but
# publishes no identifier strings, Composer 2.5 has no public API model id (it is
# Cursor-platform-only), and no live Cursor has been observed from here. A wrong
# string fails at invocation rather than silently selecting another model, and
# `MODEL_HINT` turns that failure into one command's worth of fixing.
CURSOR_DEFAULT_MODEL = "composer-2.5"

MODEL_HINT = "run `agent --list-models` for the accepted identifiers"


@dataclass(frozen=True)
class AgentCLI:
    """One headless coding-agent CLI, and what Thalamus may ask of it."""

    harness: str
    binary: str
    default_model: str
    # Claude Code's JSON envelope prices the call (`total_cost_usd`); Cursor's
    # carries no cost or token fields at all. Kept as a capability rather than
    # defaulted to 0.0, because a zero meaning "not reported" is indistinguishable
    # from one meaning "free" and would under-report the spend `eval cost` totals.
    reports_cost: bool
    # Why this CLI cannot yet drive an eval arm. Empty means it can. Arms need far
    # more than a binary — see `eval/arms.py` — and a half-ported arm produces
    # records that look like measurements and are not.
    arm_blockers: tuple[str, ...] = field(default_factory=tuple)
    # Extra hint appended to invocation failures, where the vendor gives us a way
    # to discover the right value.
    model_hint: str = ""

    def argv(self, model: str) -> list[str]:
        """The print-mode invocation both CLIs share."""
        return [self.binary, "-p", "--model", model, "--output-format", "json"]

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
        arm_blockers=(
            "credential staging copies ~/.claude.json and "
            "~/.claude/.credentials.json into the arm HOME",
            "--max-turns, --permission-mode and --dangerously-skip-permissions "
            "are Claude Code flags with no confirmed Cursor equivalent",
            "the run envelope is read for num_turns and total_cost_usd, neither "
            "of which Cursor reports",
            "transcript capture, escape detection and session-fault "
            "classification all read Claude Code JSONL and its error strings",
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
