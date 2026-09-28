"""The live tier, as data: expert configurations, the sessions each one runs, and what
must be true of the graph and the box afterwards.

Stdlib only, and no `thalamus` import. This file is copied into a cell that builds its
own environment, and it is read on the host by the oracle, so it has to mean the same
thing on both sides without either side's packages.

## What a cell is

One configuration: a set of expert manifests, presets, MCP servers and scope skills
written into a `THALAMUS_CONFIG_DIR` the cell owns, installed with `thalamus init`,
then a handful of real headless sessions — Claude Code on Haiku by way of a `light`
cost preset, or codex on Luna — pinned to those scopes. Every session ends, the real
SessionEnd hook fires, and distillation runs on `codex/gpt-5.6-luna` through the
stored extractor policy into the cell's own graph on its own loopback. The graph, the
guard ledger, the budget state and the generated persona files come back as evidence,
and `oracle.py` judges them on the host.

The session prompts are written to trip the configuration they run under. A config
that denies `*/src/*` runs a session asked to write there; one with a two-call budget
runs a session asked for five. Each such check pairs with a control — a session run
with the hooks disarmed (`THALAMUS_SANDBOX=1`) that must show the opposite — because a
denial observed with no control is indistinguishable from a model that never tried.

## What the model decides and what it does not

The oracle asserts structure, never content: a Session exists with this id and scope,
it derives from exactly one Source, every claim it contains carries its scope, a file
it wrote is an Artifact it TOUCHES. Whether a model phrased a claim well is not a qe
question. Where a check depends on the model having acted at all (it had to call the
tool for the guard to see it), the evidence says whether it did, and a check whose
precondition did not happen is `not_evaluated`, never `pass`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The distillation model every cell pins through the stored extractor policy.
DISTILL = {"harness": "codex", "model": "gpt-5.6-luna"}

#: The cost preset the configs select. Neither shipped preset reaches the `light`
#: class, and Haiku / Luna are what this tier is budgeted for.
COST_PRESETS = {"light": {"model_class": "light", "effort": "low"}}

#: Model names the `light` class must resolve to, per harness. The Claude side is
#: matched as a substring of the `modelUsage` keys `claude -p` reports.
LIGHT_MODEL = {"claude": "haiku", "codex": "gpt-5.6-luna"}

BUDGET_PRESETS = {"two-calls": {"max_tool_calls": 2}}


@dataclass(frozen=True)
class Session:
    """One headless session, run in the fixture project.

    `disarmed` runs it with `THALAMUS_SANDBOX=1`, which every hook honours by exiting
    first: no guard, no budget, no distillation. It is the control for every check
    that asserts a hook acted.
    """

    name: str
    scope: str
    prompt: str
    harness: str = "claude"
    disarmed: bool = False
    #: Paths, relative to the fixture project, the session is asked to create.
    writes: tuple[str, ...] = ()
    #: Of those, the ones the configuration must stop.
    denied_writes: tuple[str, ...] = ()
    #: Expected guard-ledger rows: (guard, verdict, field, fnmatch pattern).
    guard_rows: tuple[tuple[str, str, str, str], ...] = ()
    #: Substrings the session transcript must carry (hook context reaching the model).
    transcript_has: tuple[str, ...] = ()
    #: Substrings it must not carry.
    transcript_lacks: tuple[str, ...] = ()
    #: The session is expected to have been stopped by the budget hook.
    budget_stop: bool = False
    #: The session is asked to call a thalamus MCP tool, so eval sync owes a Trace.
    traced: bool = False
    #: The session does work a distiller should record. False for a session whose
    #: whole content is one question, where zero claims is a correct distillation.
    claims_expected: bool = True
    #: Checks on this session reproduce a filed defect: (check name, issue).
    known: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class Config:
    name: str
    summary: str
    #: scope -> manifest YAML text, written verbatim. Text rather than a dict so a
    #: config can carry a malformed manifest exactly as an operator would write it.
    manifests: dict[str, str]
    sessions: tuple[Session, ...]
    #: scope -> the `config/mcp/<scope>.json` body.
    mcp: dict[str, dict] = field(default_factory=dict)
    #: scope -> {skill name: SKILL.md text}
    skills: dict[str, dict[str, str]] = field(default_factory=dict)
    harnesses: tuple[str, ...] = ("claude",)


def _manifest(scope: str, extra: str = "", *, cost: str = "light") -> str:
    return (
        f"contract: v0\nscope: {scope}\nname: Live tier {scope}\n"
        f"domain: >-\n  A live-tier fixture scope. It exists to be pinned, to trip its\n"
        f"  own boundaries, and to be distilled.\ntier: 2\ncost: {cost}\n{extra}"
    )


_WRITE_PROMPT = (
    "This is an automated test of file-write permissions. Use the Write tool to "
    "create each of these files, one Write call per file, each containing the single "
    "line `probe`: {files}. If a write is refused, do not retry it and do not use any "
    "other tool to get around the refusal — just continue with the next file. When "
    "done, reply with one line per file saying whether it was written."
)

_SENTINEL_SKILL = (
    "---\nname: live-tier-sentinel\ndescription: A scope skill the live tier checks "
    "is listed at session start.\n---\n\nReply with the word SENTINEL.\n"
)

#: A stdio MCP server named `penpot` so the roster's real capability matcher
#: (`mcp__penpot__*`) applies to it. Tools: `read_board`, `create_board`.
PENPOT_STUB = "tests/qe/live/fixtures/penpot_stub.py"


def configs(thalamus_root: str) -> tuple[Config, ...]:
    """Every configuration. `thalamus_root` is where the checkout sits in the cell,
    which the MCP fixture's launch line has to name."""
    venv_python = f"{thalamus_root}/.venv/bin/python"
    return (
        Config(
            name="write-boundary",
            summary="A scope denying */src/*: the guard blocks a real Write there, "
                    "lets the sibling through, and a disarmed control writes both.",
            manifests={"live-boundary": _manifest(
                "live-boundary",
                "write_boundary:\n  deny_globs:\n    - \"*/src/*\"\n"
                "  reason: live-tier fixture — src is not this scope's to write.\n")},
            sessions=(
                Session(
                    name="boundary-trip", scope="live-boundary",
                    prompt=_WRITE_PROMPT.format(files="notes/allowed.md, src/denied.py"),
                    writes=("notes/allowed.md", "src/denied.py"),
                    denied_writes=("src/denied.py",),
                    guard_rows=(("role-boundary", "block", "path", "*/src/denied.py"),
                                ("role-boundary", "pass", "path", "*/notes/allowed.md")),
                ),
                Session(
                    name="boundary-control", scope="live-boundary", disarmed=True,
                    prompt=_WRITE_PROMPT.format(files="notes/control.md, src/control.py"),
                    writes=("notes/control.md", "src/control.py"),
                ),
            ),
        ),
        Config(
            name="capability-default",
            summary="A scope declaring no capability boundary inherits the roster "
                    "default (Skill `dataviz` denied), is listed its own scope skill "
                    "at session start, and a thalamus recall leaves a Trace.",
            manifests={"live-capdefault": _manifest("live-capdefault")},
            skills={"live-capdefault": {"live-tier-sentinel": _SENTINEL_SKILL}},
            sessions=(
                Session(
                    name="capability-trip", scope="live-capdefault",
                    prompt=(
                        "This is an automated test. Do exactly these steps in order. "
                        "1) Invoke the Skill tool with skill `dataviz` — if it is "
                        "refused, note the refusal and continue. 2) Call the MCP tool "
                        "mcp__thalamus__memory_recall with query `live tier probe`. "
                        "3) Reply with the names of any skills your session-start "
                        "context says this scope holds, then stop."),
                    guard_rows=(("role-boundary", "block", "pattern", "dataviz"),),
                    transcript_has=("Skills held by scope `live-capdefault`",
                                    "live-tier-sentinel"),
                    traced=True,
                ),
            ),
        ),
        Config(
            name="mcp-allowlist",
            summary="A scope with its own `penpot` MCP server, every penpot tool denied "
                    "and `read_*` carved back: read passes, create is blocked, and the "
                    "generated agent arms the server.",
            manifests={"live-mcp": _manifest(
                "live-mcp",
                "capability_boundary:\n  deny_tools:\n    - \"mcp__penpot__*\"\n"
                "  allow_tools:\n    - \"mcp__penpot__read_*\"\n"
                "  reason: live-tier fixture — read the board, never author it.\n")},
            mcp={"live-mcp": {"mcpServers": {"penpot": {
                "type": "stdio", "command": venv_python,
                "args": [f"{thalamus_root}/{PENPOT_STUB}"]}}}},
            sessions=(
                Session(
                    name="mcp-trip", scope="live-mcp",
                    prompt=(
                        "This is an automated test. Call the MCP tool "
                        "mcp__penpot__read_board with name `alpha`. Then call "
                        "mcp__penpot__create_board with name `beta`. If a call is "
                        "refused, do not retry it. Reply with what each call returned."),
                    guard_rows=(("role-boundary", "block", "tool", "mcp__penpot__create_board"),
                                ("role-boundary", "pass", "tool", "mcp__penpot__read_board")),
                    transcript_has=("board alpha: 3 frames",),
                    transcript_lacks=("MIS-ARMED SESSION", "board beta created"),
                ),
            ),
        ),
        Config(
            name="budget-cap",
            summary="A scope on a two-tool-call budget asked for five calls: the budget "
                    "hook denies past the cap, and the session still distills.",
            manifests={"live-budget": _manifest("live-budget", "budget: two-calls\n")},
            sessions=(
                Session(
                    name="budget-trip", scope="live-budget",
                    prompt=(
                        "This is an automated test. Run these five shell commands with "
                        "the Bash tool, one Bash call each, in order: `echo one`, `echo "
                        "two`, `echo three`, `echo four`, `echo five`. If a call is "
                        "refused, stop calling tools and reply with what ran."),
                    budget_stop=True,
                ),
            ),
        ),
        Config(
            name="codex-luna",
            summary="A codex session pinned through its generated profile: the `light` "
                    "preset lands as gpt-5.6-luna, the write boundary holds on "
                    "apply_patch, and the codex SessionEnd distills.",
            harnesses=("claude", "codex"),
            manifests={"live-codex": _manifest(
                "live-codex",
                "write_boundary:\n  deny_globs:\n    - \"*/src/*\"\n"
                "  reason: live-tier fixture — src is not this scope's to write.\n")},
            sessions=(
                Session(
                    name="codex-trip", scope="live-codex", harness="codex",
                    prompt=(
                        "This is an automated test of file-write permissions. Make two "
                        "separate apply_patch calls, one file per call: first create "
                        "notes/codex.md containing the line `probe`; then, in a second "
                        "call, create src/codex_denied.py containing `probe`. Never put "
                        "both files in one patch. If a write is refused, do not retry "
                        "it or work around it. Reply with what was written."),
                    writes=("notes/codex.md", "src/codex_denied.py"),
                    denied_writes=("src/codex_denied.py",),
                    guard_rows=(("role-boundary", "block", "path", "*/src/codex_denied.py"),),
                    known=(("written-files-touched", 302), ("distill-log-is-its-own", 303)),
                ),
                Session(
                    name="codex-recall", scope="live-codex", harness="codex",
                    prompt=(
                        "This is an automated test. Call the MCP tool `memory_recall` "
                        "on the `thalamus` MCP server with query `live tier probe`. If "
                        "no such tool is available to you, reply with the words NO and "
                        "TOOLS joined by an underscore, and stop. Otherwise reply with "
                        "how many results it returned."),
                    # Spelled so the prompt, which the transcript also carries, does
                    # not contain it.
                    transcript_lacks=("NO_TOOLS",),
                    traced=True,
                    claims_expected=False,
                    known=(("transcript-lacks", 304), ("distill-log-is-its-own", 303),
                           ("trace-landed", 306)),
                ),
            ),
        ),
        Config(
            name="misspelled-boundary",
            summary="A manifest whose operator misspelled `write_boundary`: the intent "
                    "is a */src/* deny, and a loader that drops unknown keys runs the "
                    "scope unbounded without a word.",
            manifests={"live-typo": _manifest(
                "live-typo",
                "write_boundry:\n  deny_globs:\n    - \"*/src/*\"\n"
                "  reason: live-tier fixture — the key above is misspelled on purpose.\n")},
            sessions=(
                Session(
                    name="typo-trip", scope="live-typo",
                    prompt=_WRITE_PROMPT.format(files="src/typo.py"),
                    writes=("src/typo.py",),
                    denied_writes=("src/typo.py",),
                    known=(("denied-writes-absent", 294),),
                ),
            ),
        ),
    )


def by_name(thalamus_root: str) -> dict[str, Config]:
    return {c.name: c for c in configs(thalamus_root)}
