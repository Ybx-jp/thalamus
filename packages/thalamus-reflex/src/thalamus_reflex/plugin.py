"""The surfaces this plugin adds to core: the `reflex` command its hooks run, `eval
reflex` and `eval vocabulary`, and the two Claude Code hook scripts.

Registered through core's hooks (`thalamus.plugins`). `register_commands` runs on every
`thalamus` invocation, so this module builds parsers and nothing else, and the handlers
in `commands.py` import the reflex only when one of these commands runs.
"""

from __future__ import annotations

from pathlib import Path

from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.plugins import Hook, hookimpl
from thalamus.substrate.writer import DEFAULT_URL
from thalamus_reflex import commands

CLAUDE_HOOKS = Path(__file__).resolve().parent / "hooks" / "claude-code"


@hookimpl
def register_hooks() -> list[Hook]:
    """Claude Code only.

    Not on Cursor: `reflex.sh` injects from `PostToolUse`, and Cursor's
    `afterShellExecution` cannot inject — the same gap that makes `conditioning.sh`
    deliver one tool call late through the spool. A reflex delivered a call late is the
    deferred channel arm the design measures separately, not the immediate one this
    script is, so it waits for that arm rather than shipping as it.

    Not on codex: the failure test reads Claude Code's
    `tool_response.stdout`/`.stderr`/`.interrupted`, or a failure's
    `error`/`is_interrupt`, and codex's shell result has been measured only on the input
    side — it arrives as one string, which the `gremlin-tap.sh` adapter reshapes onto
    the stdout leg — so a reflex there would build its trigger against a payload half
    nobody has read. Whether codex can carry one is open, not decided.

    `reflex-pointer-tap.sh` goes wherever `reflex.sh` goes: it records the agent opening
    a reflex pointer file, and without the reflex there is none.
    """
    return [
        Hook("claude", "PostToolUse", "Bash", CLAUDE_HOOKS / "reflex.sh"),
        Hook("claude", "PostToolUseFailure", "Bash", CLAUDE_HOOKS / "reflex.sh"),
        Hook("claude", "PostToolUse", None, CLAUDE_HOOKS / "reflex-pointer-tap.sh"),
        Hook("claude", "PostToolUseFailure", None, CLAUDE_HOOKS / "reflex-pointer-tap.sh"),
    ]


@hookimpl
def register_commands(subparsers, groups) -> None:
    # The PostToolUse memory reflex's worker (reflex.py).
    reflex_parser = subparsers.add_parser(
        "reflex",
        help="Serve memory against a failed Bash result; the reflex.sh hook's worker. "
        "Prints the digest to inject, or nothing.",
    )
    reflex_parser.add_argument(
        "--session-id", default="",
        help="The session that ran the command (required except with --work/--sweep)",
    )
    reflex_parser.add_argument(
        "--response-file", type=Path, default=None,
        help="File holding the command's stdout then stderr, as the model saw them "
        "(required to fire or shadow)",
    )
    reflex_parser.add_argument(
        "--transcript", default="",
        help="The session's transcript path, from the hook payload; an agentic job "
        "builds its excerpt from it",
    )
    reflex_parser.add_argument(
        "--tool-use-id", default="",
        help="The id of the call that fired, from the hook payload; an agentic job "
        "keeps that call's result in its excerpt and measures delivery depth from it",
    )
    reflex_parser.add_argument(
        "--work", action="store_true",
        help="Run the agentic plan's queued jobs and exit when none remain — the "
        "detached worker the trigger starts (harness/reflex_worker.py)",
    )
    reflex_parser.add_argument(
        "--job-tools", type=Path, default=None, metavar="DIR",
        help="Serve one claude-channel job's vocabulary over MCP stdio, relaying each "
        "call to the worker through DIR's socket — what the job's `claude -p` starts "
        "(harness/reflex_channel.py)",
    )
    reflex_parser.add_argument(
        "--deliver", action="store_true",
        help="Print the digests ready for this session and agent, oldest first, and "
        "record their delivery — the carrier's delivery half",
    )
    reflex_parser.add_argument(
        "--reflex-dir", type=Path, default=None,
        help="Reflex ledger and queue dir for --work, --deliver and --sweep "
        "(default: ~/.thalamus/reflex)",
    )
    reflex_parser.add_argument(
        "--sweep", action="store_true",
        help="Record and clear queue state no worker or carrier will reach: jobs of a "
        "dead worker, results and jobs of ended sessions",
    )
    reflex_parser.add_argument(
        "--scope", default=MAIN_SCOPE,
        help="Scope to retrieve in — the pin, resolved by the hook (default: main)",
    )
    reflex_parser.add_argument(
        "--agent-id", default="",
        help="The subagent that ran the command, empty for the session itself; part "
        "of the dedup key because subagents share their parent's session id",
    )
    reflex_parser.add_argument("--agent-type", default="", help="The subagent's type, recorded in the trace")
    reflex_parser.add_argument("--cwd", default="", help="Working directory, recorded in the trace")
    reflex_parser.add_argument(
        "--tool-name", default="Bash", help="The tool whose result fired the reflex (default: Bash)"
    )
    reflex_parser.add_argument(
        "--event", default="",
        help="The hook event that ran the reflex — PostToolUse (exit 0) or "
        "PostToolUseFailure (non-zero exit) — recorded in the ledger and the trace",
    )
    reflex_parser.add_argument(
        "--shadow", action="store_true",
        help="The output did not read as a failure: record what it would have anchored "
        "on under ~/.thalamus/reflex/shadow/, with no graph read and no output",
    )
    reflex_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    reflex_parser.set_defaults(plugin_run=commands.reflex)

    eval_sub = groups["eval"]
    eval_reflex_parser = eval_sub.add_parser(
        "reflex",
        help="The memory reflex read by arm: qualifying failures, what was served, "
        "and the lexical and citation used-verdicts on what landed",
    )
    eval_reflex_parser.add_argument(
        "--reflex", type=Path, default=None,
        help="Reflex ledger dir (default: ~/.thalamus/reflex)",
    )
    eval_reflex_parser.add_argument(
        "--traces", type=Path, default=None, help="Trace tap dir (default: ~/.thalamus/traces)"
    )
    eval_reflex_parser.add_argument(
        "--url", default=DEFAULT_URL,
        help="Gremlin endpoint for the verdict half; the ledger half renders without it",
    )

    eval_vocabulary_parser = eval_sub.add_parser(
        "vocabulary",
        help="Replay real reflex anchor sets through every retrieval-vocabulary tool "
        "and report what each returns: rows, characters and time per call, and per "
        "anchor set the totals a job cap has to sit under",
    )
    eval_vocabulary_parser.add_argument(
        "--reflex", type=Path, default=None,
        help="Reflex ledger dir the anchor sets come from (default: ~/.thalamus/reflex)",
    )
    eval_vocabulary_parser.add_argument(
        "--limit", type=int, default=40, help="Most recent distinct anchor sets to replay"
    )
    eval_vocabulary_parser.add_argument(
        "--scope", default=MAIN_SCOPE, help="Scope to retrieve in (default: main)"
    )
    eval_vocabulary_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_reflex_parser.set_defaults(plugin_run=commands.eval_reflex)
    eval_vocabulary_parser.set_defaults(plugin_run=commands.eval_vocabulary)
