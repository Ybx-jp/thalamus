"""The headless coding-agent CLIs Thalamus shells out to, in one place.

Every surface that runs a coding agent as a subprocess resolves its binary,
default model and flags from here rather than spelling `claude` inline. The
reason is the one this repo keeps relearning: a hardcoded vendor binary is
invisible until the machine that lacks it tries to use it, and then it fails as
"distillation stopped happening" rather than as an error anyone reads. A Cursor
session on a Cursor-only machine must not need Claude Code installed and
authenticated to become memory.

Deliberately a leaf module — it imports nothing from Thalamus, so
`harness/extraction.py`, which already depends on `eval/`, can use it without a
cycle.

**Capability is declared, not assumed.** Claude Code and Cursor are near-identical
for extraction — both take `-p`, `--model` and `--output-format json`, and both
return an envelope carrying `result`, `is_error` and `duration_ms` under those
exact names. Codex agrees on none of it: `-p` is `--profile` there, print mode is
the `exec` subcommand, and `--json` streams a line per event instead of one object
(measured 2026-08-17, codex-cli 0.147.0). Rather than let each caller rediscover
that, each entry states what it can and cannot do, and callers refuse loudly on
the gaps instead of substituting a binary and hoping. The alternative — swapping
one binary for another everywhere and seeing what breaks — produces surfaces that
run and report success while measuring nothing, which is the failure class this
project has already paid for twice.

**Three discriminators, because the three things vary independently.**
`transport` says how the model is reached, `invocation` says how a CLI is asked,
`envelope` says how its answer is read. Cursor is the proof the last two are
separate axes: it shares Claude Code's argv shape exactly and still differs in what
the envelope carries (tokens, no price). `ghoul` is the proof the first is a third:
it is reached over HTTP, so `invocation` and `envelope` describe nothing about it
and `binary` is empty. One field covering any two would have to be a harness name
in disguise, which is the fork this module exists to replace. No field holds a
callable: a row holding a function is no longer data that can be listed, diffed or
serialized (`contract/probes.py`), and the readers therefore live with
`ExtractionRun` in `harness/extraction.py`.

**Not every row is a session an operator can be pinned into.** Until `ghoul` there
was one kind of entry — a CLI a human runs interactively and that also distills
headlessly — and several surfaces read `HARNESSES` on that assumption:
`launcher.py` asserts a launch shape per harness, `install.py` wires hooks and an
MCP registration per harness, and `thalamus pin --harness` offers the list. A
model served over HTTP has no TUI, no hook events and no transcript on disk, so it
belongs to none of them. `launch_blockers` states that per row the way
`arm_blockers` already states eligibility for eval arms, and `LAUNCHABLE` is what
those surfaces read. `HARNESSES` stays the whole registry, because extraction and
ingestion — the surfaces that only ever needed a model — can use every row.
"""

from __future__ import annotations

import os
import shutil
import urllib.request
from dataclasses import dataclass, field
from pathlib import PurePath

CLAUDE_DEFAULT_MODEL = "sonnet"

# Composer 2.5, deliberately not the fast variant: distillation is a batch sweep
# where nothing waits on the result, so the quality/latency trade runs the other
# way from interactive use. `composer-2.5-fast` is the variant being declined, and
# it is a real identifier — the choice is between two things that both exist.
#
# Verified against a live `agent --list-models` (2026-08-10, CLI 2026.08.04).
# A wrong string fails at invocation rather than silently selecting another model,
# and `MODEL_HINT` turns that failure into one command's worth of fixing.
CURSOR_DEFAULT_MODEL = "composer-2.5"

# Codex's mid-catalog frontier slug, on the same trade Cursor's pick was made on:
# distillation is a batch sweep where nothing waits on the result, so quality beats
# latency and cost beats the top tier. `gpt-5.6-sol` is the catalog default (priority
# 1) and is the one being declined; both are real identifiers.
#
# Verified against a live `codex debug models` (2026-08-17, codex-cli 0.147.0), which
# renders the raw catalog as JSON and — unlike Cursor's — answers without auth.
CODEX_DEFAULT_MODEL = "gpt-5.6-terra"

MODEL_HINT = "run `agent --list-models` for the accepted identifiers"
CODEX_MODEL_HINT = "run `codex debug models` for the accepted identifiers"

# The sandbox a headless Thalamus subprocess runs in, named in two ways because
# each one is visible to a different observer.
#
# A headless run is a full session to its own harness: it gets a session id, a
# transcript on disk, and — because the hook suite is installed at user scope — it
# fires SessionEnd, which distills it. The result is memory *about the act of making
# memory*: a Session whose summary paraphrases the session it was distilling, its own
# Claims and open Threads, and its own headless run behind it, one level deeper. A
# sandbox is not a session and must leave no memory.
#
# `SANDBOX_ENV` marks the subprocess so every hook the sandbox inherits can
# recognise itself and decline (hooks are children of the CLI, so the marker
# reaches them). `SANDBOX_TMP_PREFIX` names the throwaway cwd it runs in, which
# is what the transcript *reader* sees — a transcript already on disk carries no
# environment, so retroactive sweeps (`thalamus bootstrap`, an explicit
# `thalamus extract -- <dir>`) need the second name to refuse the same input.
#
# Both are belt and braces where a harness can simply be told not to write: codex
# takes `--ephemeral`, so its sandbox leaves no transcript for a reader to reach in
# the first place. Where a CLI offers that, the flag is declared in
# `headless_preconditions` and these two remain as the floor for the ones that do not.
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
    # `outputTokens`, `cacheReadTokens`, `cacheWriteTokens` — so the gap
    # is pricing, not instrumentation, and a future rate table could close it.
    # Kept as a capability rather than defaulted to 0.0, because a zero meaning
    # "not reported" is indistinguishable from one meaning "free" and would
    # under-report the spend `eval cost` totals.
    reports_cost: bool
    # Why this CLI cannot yet drive an eval arm. Empty means it can. Arms need far
    # more than a binary, and a half-ported arm produces records that look like
    # measurements and are not.
    arm_blockers: tuple[str, ...] = field(default_factory=tuple)
    # Extra hint appended to invocation failures, where the vendor gives us a way
    # to discover the right value. Attached to the *model* argument specifically —
    # a hint appended to every failure misattributes unrelated ones, which is how
    # a workspace-trust refusal came to advise running `agent --list-models`.
    model_hint: str = ""
    # Model identifiers this CLI accepts, for the surfaces that must offer a *closed*
    # list rather than a text box — the console's distillation panel is the one that
    # forced it. A model typed into a box is a value nothing can check, and it fails
    # at invocation inside a detached SessionEnd job, which is the one place a failure
    # reaches nobody. `default_model` is the entry a caller gets by choosing nothing
    # and is required to appear here.
    #
    # Not exhaustive and not meant to be: each list is the handful worth choosing
    # between for a batch extraction pass, taken from the vendor's own live catalog
    # (the `model_hint` command, or `--help` where there is no catalog). A slug absent
    # here is still reachable through `--model`, which is the escape hatch that keeps
    # this list a curation rather than a gate.
    models: tuple[str, ...] = ()
    # Flags this CLI needs before it will run non-interactively in a directory it
    # has never seen. Not a preference: Cursor refuses an untrusted workspace with
    # exit 1 and a human-readable prompt *instead of* the JSON envelope, so every
    # sandbox extraction fails before doing any work (measured live — the
    # extraction sandbox is a fresh mkdtemp every run and is therefore never
    # trusted). Claude Code has no equivalent precondition and declares none.
    #
    # This is the seam the shared `argv()` hid: the two CLIs agree on `-p`,
    # `--model` and `--output-format json`, and the near-identity made an
    # invocation shape look like a shared one. It is not — one side has a
    # precondition the other lacks, and a method returning a single argv had
    # nowhere to say so.
    headless_preconditions: tuple[str, ...] = field(default_factory=tuple)
    # How this CLI is asked to run one non-interactive turn.
    #
    #   "print" — a flag on the bare binary (`claude -p …`, `agent -p …`)
    #   "exec"  — a subcommand (`codex exec …`)
    #
    # Declared rather than derived from the binary name, because the difference is
    # not cosmetic: on codex `-p` is `--profile`, so the print-mode argv would parse,
    # run, and mean something else entirely. That is the failure this field exists
    # to make impossible to reach by accident.
    invocation: str = "print"
    # How this CLI's answer is read back.
    #
    #   "object"       — one JSON object on stdout: `result`, `is_error`, `duration_ms`
    #   "jsonl-events" — a line per event, terminated by a final `turn.completed`
    #
    # Separate from `invocation` because the two axes are independent, and Cursor is
    # the standing proof: identical argv shape to Claude Code, different envelope
    # contents. Collapsing them would key the reader to the caller's flags, which is
    # true today by coincidence and not by anything either vendor promised.
    envelope: str = "object"
    # How the model is reached at all.
    #
    #   "subprocess"  — spawn `binary` and hand it the prompt on stdin
    #   "http-openai" — POST to `endpoint` + /chat/completions, OpenAI wire format
    #
    # The axis `invocation` and `envelope` both presuppose: they describe a CLI's
    # argv and its stdout, and a row reached over HTTP has neither. Declared rather
    # than inferred from an empty `binary`, because "no binary" is the *consequence*
    # of the transport and reading it as the cause would make every future row that
    # happens to omit a field look like an HTTP one.
    transport: str = "subprocess"
    # Base URL for `transport="http-openai"`, without a trailing slash. Empty on
    # subprocess rows, where it would be a value nothing reads.
    endpoint: str = ""
    # The model's hard context ceiling in tokens, or 0 for "do not budget against
    # this row". Not a fact about the vendor's largest model — a fact about what
    # *this* row is configured to serve, which is the number a caller has to fit a
    # prompt into. It exists because the digest budget was a module constant sized
    # for a frontier window (240k chars ≈ 60k tokens): handing that to a 16k server
    # does not fail, it truncates, and a truncated transcript distills into memory
    # that is wrong rather than absent. `extraction.digest_budget` reads this.
    context_window: int = 0
    # Why this row cannot be an interactive session an operator is pinned into.
    # Empty means it can. Same shape and same discipline as `arm_blockers`: one
    # independently falsifiable claim per entry, retired by deletion when it stops
    # being true.
    launch_blockers: tuple[str, ...] = field(default_factory=tuple)

    @property
    def display(self) -> str:
        """What to call this row when addressing the operator.

        The binary, which is what an operator would type and what a PATH failure
        will name — except on a row that has no binary, where the harness name is
        the only handle there is. Prose that interpolated `binary` unconditionally
        rendered an empty pair of backticks on the HTTP row.
        """
        return self.binary or self.harness

    @property
    def runs_interactive(self) -> bool:
        return not self.launch_blockers

    def argv(self, model: str) -> list[str]:
        """The non-interactive invocation, plus whatever this CLI needs to run at all.

        `headless_preconditions` comes last on both dialects, and on codex it carries
        the real weight: outside a git repo `codex exec` refuses with
        "Not inside a trusted directory and --skip-git-repo-check was not specified"
        and exits 1 *before* any network call (measured 2026-08-17). The extraction
        sandbox is a fresh `mkdtemp`, so without the flag every extraction fails
        having done no work — the same wall Cursor's `--trust` answers.
        """
        if self.transport != "subprocess":
            raise NoArgv(
                f"`{self.harness}` is reached over {self.transport}, not spawned — "
                f"it has no argv. Callers that build a command line must check "
                f"`transport` first."
            )
        if self.invocation == "exec":
            return [
                self.binary, "exec", "--json", "--model", model,
                *self.headless_preconditions,
            ]
        return [
            self.binary, "-p", "--model", model, "--output-format", "json",
            *self.headless_preconditions,
        ]

    @property
    def runs_arms(self) -> bool:
        return not self.arm_blockers

    @property
    def available(self) -> bool:
        """Can this row actually be reached right now?

        Asked because selecting an absent extractor is not a failed setting — it is
        distillation that stops happening. `run_extraction` raises `ExtractionError`
        on `FileNotFoundError`, and the only caller is a detached SessionEnd job
        writing to a per-session log, so the loss surfaces as a widget row hours
        later and as nothing at all if the widget is not open. A surface that offers
        a harness therefore has to ask this first.

        On a subprocess row that is a PATH lookup. On an HTTP row it is a connect to
        `endpoint`, which is a stronger check than the PATH one and a slower one: an
        installed binary can still be unauthenticated, while a server that answers is
        serving. The timeout is short and the failure is "not available" rather than
        an exception, because every caller here is deciding whether to *offer* a
        row, not whether to run it.
        """
        if self.transport == "subprocess":
            return shutil.which(self.binary) is not None
        try:
            urllib.request.urlopen(f"{self.endpoint}/models", timeout=1.5).read(1)
        except OSError:
            return False
        return True


# A local OpenAI-compatible server — llama.cpp, vLLM, ollama, LM Studio. Unlike the
# three vendor rows below, what this one points at is a property of the box rather
# than of a product, so it reads three values from the environment and defaults them
# to the ollama convention (port 11434, loopback only) that is the common case.
#
# `THALAMUS_LOCAL_WINDOW` has to match what the server is actually serving. It sizes
# the digest, and a value larger than the truth does not error — the server truncates
# and distils a partial transcript into memory that reads as complete. The transport's
# own overflow guard is the backstop, not the primary control: it can only refuse a
# prompt after the budget has already been spent building it.
LOCAL_ENDPOINT = os.environ.get("THALAMUS_LOCAL_ENDPOINT") or "http://127.0.0.1:11434/v1"
LOCAL_DEFAULT_MODEL = os.environ.get("THALAMUS_LOCAL_MODEL") or "qwen2.5-coder:14b"
LOCAL_WINDOW = int(os.environ.get("THALAMUS_LOCAL_WINDOW") or 16384)


AGENT_CLIS: dict[str, AgentCLI] = {
    "claude": AgentCLI(
        harness="claude",
        binary="claude",
        default_model=CLAUDE_DEFAULT_MODEL,
        reports_cost=True,
        # Aliases rather than dated ids, and exactly the three `claude --help` names
        # under `--model` (read 2026-08-23). An alias tracks the latest model behind
        # it, which is what a batch pass wants; a pinned `claude-fable-5` would have
        # to be re-verified on every vendor release and there is no catalog command
        # to re-verify it against — hence no `model_hint` on this entry.
        models=("sonnet", "opus", "fable"),
    ),
    "cursor": AgentCLI(
        harness="cursor",
        binary="agent",
        default_model=CURSOR_DEFAULT_MODEL,
        reports_cost=False,
        model_hint=MODEL_HINT,
        # The two Composer rungs and nothing else. The catalog `--list-models` prints
        # is ~40 entries wide and most of it is other vendors' models resold through
        # Cursor — offering those here would let the panel route a distillation to
        # Anthropic *through* Cursor, which is the opposite of what picking a
        # non-Claude extractor is for. Verified live 2026-08-23.
        models=("composer-2.5", "composer-2.5-fast"),
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
            "from its own config root, which XDG_CONFIG_HOME moves",
            "--max-turns has no Cursor equivalent, so an arm cannot bound turns",
            "the run envelope is read for num_turns, which Cursor does not report",
            "escape detection and session-fault classification read Claude Code's "
            "error strings, which Cursor's envelope does not carry",
        ),
    ),
    "codex": AgentCLI(
        harness="codex",
        binary="codex",
        default_model=CODEX_DEFAULT_MODEL,
        # `turn.completed` carries a `usage` block — input_tokens, cached_input_tokens,
        # cache_write_input_tokens, output_tokens, reasoning_output_tokens — and no
        # dollar figure anywhere. Same gap as Cursor's and for the same reason: pricing,
        # not instrumentation.
        reports_cost=False,
        model_hint=CODEX_MODEL_HINT,
        # The listed catalog's top three plus the cheap rung, by the vendor's own
        # `priority` (2, 1, 3, 23). Verified live 2026-08-23, codex-cli 0.147.0.
        # `codex-auto-review` is in the catalog and omitted: it ships
        # `visibility: "hide"`, so it is not a model the vendor offers for selection.
        models=("gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.4-mini"),
        invocation="exec",
        envelope="jsonl-events",
        # `--skip-git-repo-check` answers the trust refusal and nothing else — the
        # narrow flag, the way `--trust` was chosen over `--force` on Cursor.
        # `--ephemeral` ("run without persisting session files to disk") closes the
        # self-distillation loop at its source rather than downstream of it: with no
        # rollout on disk there is no session for a later sweep to find, so the
        # `is_sandbox_cwd` reader-side refusal has nothing left to catch. `SANDBOX_ENV`
        # still rides the environment, because hooks fire either way and they are what
        # the marker is for.
        headless_preconditions=("--skip-git-repo-check", "--ephemeral"),
        arm_blockers=(
            "credential staging copies ~/.claude.json and "
            "~/.claude/.credentials.json into the arm HOME; codex authenticates from "
            "$CODEX_HOME/auth.json, which CODEX_HOME moves",
            "`codex exec` has no turn-limit flag, so an arm cannot bound turns",
            "the run envelope is read for num_turns, which codex does not report",
            "escape detection and session-fault classification read Claude Code's "
            "error strings, which codex's event stream does not carry",
        ),
    ),
    "local": AgentCLI(
        harness="local",
        # No binary, and the empty string is the honest value rather than a
        # placeholder: this row is not spawned. `display` is what prose reads.
        binary="",
        default_model=LOCAL_DEFAULT_MODEL,
        # No price to report, and no token accounting worth trusting either: the
        # OpenAI `usage` block a local server returns counts a cached prefill as
        # zero prompt tokens, so a repeated context prices at nothing. The transport
        # counts the prompt itself and reports that instead.
        reports_cost=False,
        transport="http-openai",
        endpoint=LOCAL_ENDPOINT,
        context_window=LOCAL_WINDOW,
        # Open by construction — a local server serves whatever has been pulled onto
        # the box, and there is no catalog command that is the same on llama.cpp,
        # vLLM and ollama. The closed-list surfaces get the configured default and
        # `--model` remains the escape hatch it already is everywhere else.
        models=(LOCAL_DEFAULT_MODEL,),
        model_hint="the server's own model list, e.g. `ollama list`",
        launch_blockers=(
            "there is no interactive TUI to attach to a tmux pane, so a pin would "
            "route to a window with nothing in it",
            "no SessionStart/SessionEnd events fire, so a pinned session would "
            "never arm the hooks that record the pin or distil the result",
            "no transcript is written to disk, so transcripts.discover() has "
            "nothing to hand a later extraction pass",
        ),
        arm_blockers=(
            "credential staging copies ~/.claude.json and "
            "~/.claude/.credentials.json into the arm HOME; a local server "
            "authenticates nothing and reads none of it",
            "there is no agentic loop here at all — one prompt in, one completion "
            "out — so an arm has no turns to bound and none to count",
            "the run envelope is read for num_turns, which a chat completion "
            "does not carry",
            "escape detection and session-fault classification read Claude Code's "
            "error strings, which an OpenAI-shaped response does not carry",
        ),
    ),
}


class UnknownHarness(ValueError):
    pass


class NoArgv(ValueError):
    """A command line was asked of a row that is not spawned as one."""


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

# The rows that are a session an operator can be pinned into. Read by every surface
# that wires or launches one — `launcher.LAUNCH_SHAPES`, `install.HARNESSES`, the
# `--harness` choices on `pin` and `spawn`. Extraction and ingestion read `HARNESSES`
# instead, because a model is all they ever needed.
LAUNCHABLE = tuple(h for h in HARNESSES if AGENT_CLIS[h].runs_interactive)
