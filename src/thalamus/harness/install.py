"""Install the Thalamus harness so it arms in any working directory.

The problem this solves: the harness was wired for sessions opened *inside* the
checkout. `.claude/settings.json` reaches its hook scripts through
`$CLAUDE_PROJECT_DIR`, and `.mcp.json` starts the server with a cwd-relative
`uv run`. Both name the session's *working* project, which is a different repo
whenever a session is opened elsewhere (`thalamus spawn --dir`) — so the hooks
silently no-op and the MCP server never starts. Memory is supposed to span
projects; the install is what makes that true in practice.

**Prior work.** Configuration errors are a well-studied failure class, and the
two properties that make this one expensive are both named in it. Xu et al.
(OSDI 2016, "Early Detection of Configuration Errors to Reduce Failure Damage")
define a **latent configuration error**: a parameter set at startup but not
exercised until much later, so the failure surfaces far from its cause — they
measure that latent errors take substantially longer to diagnose than
non-latent ones, and that 14.0%-93.2% of critically important RAS parameters in
six deployed systems were vulnerable to them. Every fault this module installs
against is latent in exactly that sense: a wrong hook path is inert until
SessionEnd, and SessionEnd runs detached, so the first symptom is memory that
quietly stopped accumulating. The empirical study of 772 real-world
misconfigurations (arXiv:2412.11121) puts numbers on the other half — 317 of
them produced *no error message at all*, which is the behaviour of a hook whose
`command` does not exist.

PCheck's remedy is to emulate the late usage early, at initialization, rather
than to check syntax. `verify()` below is an **instantiation** of that idea, not
an extension of it: it does not merely confirm the files exist, it spawns the
real interpreter against the real checkout the way SessionEnd will. What we give
up relative to PCheck is generality — it derives checkers from source
automatically, whereas these are hand-written for one harness.

Scope choice: hooks are installed at **user** scope and the checkout's
project-scope hook block is removed, so exactly one definition exists. Claude
Code documents that identical handlers are deduplicated by command string, but
the two definitions cannot be made textually identical (the whole point is that
one of them stops using `$CLAUDE_PROJECT_DIR`), and the docs do not state
whether hook arrays across scopes merge or override. Mutual exclusion means that
undocumented behaviour is not load-bearing either way.

Skills are the exception to that mutual exclusion, because the two scopes are not
rival definitions: both are symlinks onto the same package directory, so there is
one source of truth whichever one a session resolves. Keeping the checkout's links
means a fresh clone has its skills before `thalamus init` has ever run.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from thalamus.harness import agents
from thalamus.harness.agents import HARNESSES as AGENT_HARNESSES
from thalamus.harness.pin import (
    PROJECT_ROOT,
    USER_AGENTS_DIR,
    write_all_agents,
    write_all_codex_profiles,
)
from thalamus.substrate.writer import graph_down_detail, probe_socket, split_ws

USER_SETTINGS = Path.home() / ".claude" / "settings.json"
PROJECT_SETTINGS = PROJECT_ROOT / ".claude" / "settings.json"
PROJECT_MCP = PROJECT_ROOT / ".mcp.json"

HOOK_DIR = PROJECT_ROOT / "src" / "thalamus" / "harness" / "hooks" / "claude-code"
SKILL_DIR = PROJECT_ROOT / "src" / "thalamus" / "harness" / "skills"
USER_SKILLS_DIR = Path.home() / ".claude" / "skills"

# Where a hook records that it could not run at all. Written by
# `thalamus_require_binaries` (hooks/claude-code/resolve-scope.sh), read by
# `recorded_hook_failures`.
HOOK_FAILURE_LOG = Path.home() / ".thalamus" / "logs" / "hook-failures.log"

CURSOR_HOOK_DIR = PROJECT_ROOT / "src" / "thalamus" / "harness" / "hooks" / "cursor"
USER_CURSOR_HOOKS = Path.home() / ".cursor" / "hooks.json"
USER_CURSOR_MCP = Path.home() / ".cursor" / "mcp.json"
PROJECT_CURSOR_HOOKS = PROJECT_ROOT / ".cursor" / "hooks.json"
PROJECT_CURSOR_MCP = PROJECT_ROOT / ".cursor" / "mcp.json"

CODEX_HOOK_DIR = PROJECT_ROOT / "src" / "thalamus" / "harness" / "hooks" / "codex"

# Codex's config root, and the one file that arms its hooks. Measured 2026-08-17
# (codex-cli 0.147.0): `$CODEX_HOME/hooks.json` is the **only** path that works — a
# project-level `./.codex/hooks.json` is not discovered, and hooks declared in
# `config.toml` do not fire. So codex has no project scope at all, and the
# strip-the-project-duplicate half of the Cursor and Claude Code legs has nothing to
# mirror here: there is exactly one definition because there is exactly one place.
#
# CODEX_HOME is read at import, which is what makes a room's or a test's throwaway
# home reachable — the same seam `CLAUDE_CONFIG_DIR` gives the Claude Code leg.
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
USER_CODEX_HOOKS = CODEX_HOME / "hooks.json"
# Not written by us. `codex mcp add|remove` owns this file — it also holds the
# per-project trust records codex writes on its own, so a read-modify-write of it
# would be the `~/.claude.json` hazard again in TOML. Named here because `verify` and
# the consent text must be able to say where the registration lands.
USER_CODEX_MCP = CODEX_HOME / "config.toml"

# One list, so a harness cannot arrive in the agent registry and be silently
# uninstallable. The sentinel for "every one of them" is `all`, not `both`: the word
# stopped being true the moment there were three, and a flag whose name asserts a
# count is a flag that has to be renamed each time the count moves.
HARNESSES = AGENT_HARNESSES
ALL_HARNESSES = "all"

# What to call each harness when addressing the operator. A dict rather than a
# conditional expression for the reason the old `"Claude Code" if h == "claude" else
# "Cursor"` is gone: a two-way conditional does not fail on a third name, it
# mislabels it.
EDITOR_NAMES = {"claude": "Claude Code", "cursor": "Cursor", "codex": "codex"}


def _other_harnesses(harness: str) -> str:
    """The harnesses a transcript could be extracted with instead of this one.

    Written out rather than inlined as `'cursor' if harness == 'claude' else 'claude'`,
    which was true only while there were two and silently advised the wrong CLI on the
    third. The suggestion is a real fallback: extraction reads a transcript handed to
    it on stdin, so any installed CLI can distill any harness's session.
    """
    return "|".join(h for h in HARNESSES if h != harness)

# The hook wiring, as (event, matcher, script). Matcher None = all tools.
HOOK_WIRING: list[tuple[str, str | None, str]] = [
    ("SessionStart", None, "session-start.sh"),
    ("SessionEnd", None, "session-end.sh"),
    ("UserPromptSubmit", None, "timestamp.sh"),
    ("UserPromptSubmit", None, "conditioning.sh"),
    ("UserPromptSubmit", None, "pin-engaged.sh"),
    ("PreToolUse", "Bash", "gremlin-guard.sh"),
    ("PreToolUse", "Bash", "write-guard.sh"),
    ("PreToolUse", "SendMessage", "room-guard.sh"),
    ("PreToolUse", "Bash", "room-command-guard.sh"),
    ("PreToolUse", "Edit|Write|NotebookEdit|Skill|Artifact|mcp__penpot__.*", "role-guard.sh"),
    ("PostToolUse", "mcp__thalamus__.*", "post-tool-use.sh"),
    ("PostToolUse", "Bash", "gremlin-tap.sh"),
    ("PostToolUse", "TaskCreate", "conditioning.sh"),
    ("PostToolUse", "mcp__thalamus__memory_query", "conditioning.sh"),
    ("PostToolUse", "mcp__thalamus__memory_query", "recipe-stage.sh"),
    ("PostToolUse", "Bash", "recipe-stage.sh"),
]

# The Cursor wiring, as (event, script). Event names and their I/O shapes were
# re-verified against cursor.com/docs/hooks.md on 2026-07-29.
#
# Parity between the two tables is declared in `DECLARED_HOOK_PARITY` below and re-derived
# by `thalamus contract check --capabilities`, because stating it here in prose is
# what failed: the count was wrong for the three scripts that joined the Claude list
# after it was written, and nothing failed with it.
#
# What that record is about is **these two tables and nothing else**. It cannot say
# whether an obligation binds, because a boundary can bind through a path in neither
# table — Cursor runs `role-guard.sh` off `~/.claude/settings.json` with nothing wired
# under `.cursor/`, so this list's silence about it is correct and reads as a gap
# only to someone asking the wrong question. `contract/boundaries.py` answers the
# right one, per boundary and per harness, and carries the evidence.
#
# The prompt-side tiers reach Cursor through the spool: `beforeSubmitPrompt` can read
# the prompt but not inject, so timestamp.sh and conditioning.sh record there and
# `inject.sh` delivers on the next `postToolUse` — one of only two Cursor events that
# can inject at all.
#
# ⚠️ The clock tier may be redundant on Cursor, and wired anyway pending one
# probe. A live headless session's transcript carried a `<timestamp>` element
# inside the user query text, written before any Thalamus hook was installed, so
# in `agent -p` the clock is Cursor's own and ours is a second one arriving a
# tool call later in the tool-result slot — two disagreeing clocks in one prompt,
# which is the drift this tier exists to prevent. It stays wired
# because that was measured in **print mode only**, and unwiring it on one
# observation would strip the clock from interactive sessions if Cursor injects
# only in `-p` — and long-running interactive sessions are exactly what the tier
# was built for. The probe that settles it is an interactive Cursor session.
#
# Either answer needs somewhere to be recorded, and `contract/boundaries.py` is where:
# `NATIVE` is a capability the adapter must *decline* because the harness already
# provides it, and it is a different state from `ABSENT` and from `UNKNOWN`.
#
# The taps stay on the *specialized* events, and the reason is now measured rather
# than cautious: a single `echo` fires `preToolUse` **and** `beforeShellExecution`,
# and completes into `postToolUse` **and** `afterShellExecution`; one MCP call fires
# both members of its pair too. The generic events are not exclusive with
# the specialized ones, so moving a tap to `postToolUse` while the specialized tap
# stands would double-count every retrieval in `eval sync`. The cost stands with it:
# tracing does not reach Cursor cloud agents, where only the generic event loads.
#
# No carrier: Claude Code's PostToolUse:TaskCreate milestone class. TaskCreate
# is task-list UI; Cursor's `Task` tool type is subagent spawning, which is a
# different event and would fire on the wrong thing.
CURSOR_HOOK_WIRING: list[tuple[str, str]] = [
    ("sessionStart", "session-start.sh"),
    ("sessionEnd", "session-end.sh"),
    # A second sessionEnd entry rather than a branch inside the first: logging the
    # pointer is free and must always happen, while distilling costs a model call per
    # session. Separate entries mean auto-distill is disarmed by removing one line,
    # leaving the ledger row — and the session's routing — intact.
    ("sessionEnd", "distill.sh"),
    ("beforeSubmitPrompt", "pin-engaged.sh"),
    ("beforeSubmitPrompt", "timestamp.sh"),
    ("beforeSubmitPrompt", "conditioning.sh"),
    ("beforeShellExecution", "gremlin-guard.sh"),
    # Wired here as well as in the Claude table, following `gremlin-guard.sh`: both are
    # PreToolUse-on-Bash guards, and the boundary this one enforces is a decision about
    # the graph, which does not care which harness ran the command.
    ("beforeShellExecution", "write-guard.sh"),
    # The room boundary's only possible shape on this harness: `room-guard.sh` matches
    # the `SendMessage` tool name and Cursor has no such tool, so peer traffic is a
    # shell command or it is nothing.
    ("beforeShellExecution", "room-command-guard.sh"),
    ("afterShellExecution", "gremlin-tap.sh"),
    ("afterMCPExecution", "mcp-tap.sh"),
    ("postToolUse", "inject.sh"),
    # The readiness bracket (harness/readiness.py). Five entries for two scripts,
    # because the interval a modal can occupy is delimited by pairs: the shell pair and
    # the MCP pair open it, and `sessionStart` establishes the resting state so a
    # member is addressable before it has run anything. The events are the specialized
    # ones for the same reason the taps use them — `preToolUse`/`postToolUse` also fire
    # on a shell call, so bracketing there as well would open a second bracket inside
    # the first and close it early.
    ("sessionStart", "readiness-ready.sh"),
    ("beforeShellExecution", "readiness-pending.sh"),
    ("afterShellExecution", "readiness-ready.sh"),
    ("beforeMCPExecution", "readiness-pending.sh"),
    ("afterMCPExecution", "readiness-ready.sh"),
]


# The codex wiring, in Claude Code's shape — (event, matcher, script) — because
# codex's `hooks.json` *is* Claude Code's schema: matcher groups under an event key,
# `{"type": "command", "command": ...}` entries, and matchers that are regexes rather
# than literals. Measured 2026-08-17 (codex-cli 0.147.0) by wiring three matchers on
# PostToolUse in a throwaway CODEX_HOME: `Bash`, `mcp__thalamus__.*` and
# `Edit|Write|apply_patch` each fired for exactly the tool names they describe, and a
# group with no matcher fired for all three.
#
# **No `native=` entries, and that is the important difference from Cursor.** Codex
# does not read `~/.claude/settings.json`: three codex sessions ran on a box with the
# Claude Code suite installed at user scope and wrote zero pin-ledger rows and zero
# log lines. So there is no vendor compatibility path to decline an adapter in favour
# of, no double-fire hazard, and anything wanted on codex is wired here or does not
# run at all.
#
# The tool vocabulary is measured, not assumed. A live `codex exec` turn that ran a
# shell command, edited a file and called an MCP tool produced exactly three tool
# names in its hook payloads: `Bash` (with `tool_input.command`), `apply_patch` (with
# the patch envelope on `tool_input.command`) and
# `mcp__thalamus__memory_open_threads`. The rollout transcript disagrees — there every
# call is a `custom_tool_call` named `exec` carrying a JavaScript program — so the
# matchers here follow the hook layer, which is the surface they are matched against.
#
# What is deliberately absent:
#
#   `room-guard.sh` — it matches the `SendMessage` tool name and codex has no such
#   tool, the same reason it is unwired on Cursor. Peer traffic here is a shell
#   command, which `room-command-guard.sh` covers.
#
#   The readiness bracket (`readiness-pending.sh` / `readiness-ready.sh`). Rooms and
#   dispatch are not built for codex, and a bracket exists to make a member
#   addressable *within* a room. Building one now would publish a readiness signal
#   for a member nothing can address.
#
#   `PostToolUse:TaskCreate` for conditioning's milestone class. That is Claude Code
#   task-list UI; codex ships no analogous tool, so the class has no carrier — the
#   same absence Cursor has, for the same reason.
#
#   `Skill` and `Artifact` on `role-guard.sh`'s matcher. Codex's skill and artifact
#   surfaces have not been measured, and a matcher naming a tool nobody has observed
#   is a guess that reads as enforcement. `apply_patch` is the measured editing tool,
#   so the path half of the role boundary binds and the capability half does not.
CODEX_HOOK_WIRING: list[tuple[str, str | None, str]] = [
    ("SessionStart", None, "session-start.sh"),
    ("SessionEnd", None, "session-end.sh"),
    ("UserPromptSubmit", None, "timestamp.sh"),
    ("UserPromptSubmit", None, "conditioning.sh"),
    ("UserPromptSubmit", None, "pin-engaged.sh"),
    ("PreToolUse", "Bash", "gremlin-guard.sh"),
    ("PreToolUse", "Bash", "write-guard.sh"),
    ("PreToolUse", "Bash", "room-command-guard.sh"),
    # `mcp__penpot__.*` rides along on measured grounds rather than by analogy: codex
    # registers an MCP tool as `mcp__<server>__<tool>` (observed for `thalamus`), so
    # the name a `designer` session's Penpot calls arrive under is the one the Claude
    # Code matcher already names.
    ("PreToolUse", "apply_patch|mcp__penpot__.*", "role-guard.sh"),
    ("PostToolUse", "mcp__thalamus__.*", "post-tool-use.sh"),
    ("PostToolUse", "Bash", "gremlin-tap.sh"),
    ("PostToolUse", "mcp__thalamus__memory_query", "recipe-stage.sh"),
    ("PostToolUse", "Bash", "recipe-stage.sh"),
]


@dataclass(frozen=True)
class HookParity:
    """What the wirings above are believed to add up to — the tables, only.

    Written as data so it can be re-derived and disagreed with. The same claim as a
    comment was wrong for three scripts and no test could notice, because a comment
    is not compared to anything.

    It is not circular to pin a hand-written expectation beside the tables it
    describes and then recompute it: the derivation reads the wiring tables, this
    record does not, so adding a script to one table moves one and not the other.
    That divergence is precisely the event that went unnoticed before.

    **Per harness, with the differences taken pairwise against Claude Code.** The
    record used to be two-harness by construction — `claude_scripts`,
    `cursor_scripts`, `claude_only`, `cursor_only` — and a third table it had no field
    for would have reproduced the original failure exactly: a wiring compared to
    nothing. Claude Code is the reference not by seniority but because it is the only
    table where a script's absence is always a decision rather than a translation, and
    the old fields are the two-harness case of the new ones (`claude_only` was
    `missing["cursor"]`, `cursor_only` was `extra["cursor"]`).

    A per-harness set also carries what a shared/only split cannot: a script in two
    tables and not the third is invisible to that split, and it is the commonest shape
    now there are three — `role-guard.sh` is wired on Claude Code and on codex and not
    on Cursor.

    **The subject is the wiring, never the obligation.** This record cannot say
    whether a boundary binds, and a reader who takes it for that gets a false answer
    in both directions: it over-reported gaps until `renames` was added, and it
    under-reported enforcement until `native` was, because a script absent from a
    table can still be running through the vendor's own compatibility path.
    `contract/boundaries.py` is the record that speaks about obligations.
    """

    # harness -> how many distinct scripts its table names.
    scripts: dict[str, int]
    # Scripts every table names.
    shared: int
    # harness -> Claude Code scripts its table does not name.
    missing: dict[str, tuple[str, ...]]
    # harness -> scripts its table names that Claude Code's does not.
    extra: dict[str, tuple[str, ...]]
    # A name-set difference cannot tell a rename from a gap — the two are the same
    # shape — so the renames are named, per harness, as (claude_name, local_name).
    # Without this, `post-tool-use.sh` reads as a missing MCP tap on Cursor when
    # `mcp-tap.sh` is doing that job under a different filename, which is a capability
    # the adapter *has* being reported as one it lacks.
    renames: dict[str, tuple[tuple[str, str], ...]]
    # harness -> Claude Code scripts it runs with no wiring of its own, because the
    # vendor already runs them: Cursor translates `~/.claude/settings.json` into its
    # own event names, so a second registration under `.cursor/` would run the same
    # guard twice on one call. Absence from that table is the decision there, not the
    # gap — and without this field the two are the same shape, exactly as a rename was.
    #
    # Codex has no entry here and cannot have one: it does not read
    # `~/.claude/settings.json` at all (measured — three codex sessions ran with the
    # suite installed at user scope and fired none of it), so every script it runs is
    # one this module wired.
    native: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def real_gaps(self, harness: str) -> tuple[str, ...]:
        """Claude Code scripts with no path on `harness`, renames and natives excluded.

        A name lands here by *default*, so this is a floor on the gaps and not a
        measurement of them: a script nobody has probed on a harness is
        indistinguishable from one probed and found missing. `role-guard.sh` sat here
        for a release while it was in fact binding on Cursor.
        """
        accounted = (
            {claude_name for claude_name, _ in self.renames.get(harness, ())}
            | set(self.native.get(harness, ()))
        )
        return tuple(name for name in self.missing.get(harness, ())
                     if name not in accounted)


DECLARED_HOOK_PARITY = HookParity(
    scripts={"claude": 13, "codex": 12, "cursor": 14},
    shared=9,
    missing={
        "codex": ("room-guard.sh",),
        "cursor": ("post-tool-use.sh", "recipe-stage.sh", "role-guard.sh",
                   "room-guard.sh"),
    },
    extra={
        # Codex needs no script Claude Code does not have: its payloads are Claude
        # Code's, so every entry in its table delegates into `hooks/claude-code/`.
        "codex": (),
        "cursor": (
            "distill.sh", "inject.sh", "mcp-tap.sh",
            # Cursor-only because neither other harness needs a bracket: Claude Code
            # writes `status` into the session descriptor from inside its own event
            # loop, so readiness there is a first-party signal already, and codex has
            # no room for a member to be addressable in. These two exist to give
            # Cursor the same answer, not a better one.
            "readiness-pending.sh", "readiness-ready.sh",
        ),
    },
    renames={"cursor": (("post-tool-use.sh", "mcp-tap.sh"),)},
    native={"cursor": ("role-guard.sh",)},
)


def derive_hook_parity() -> dict:
    """Recompute the parity claim from the wirings themselves."""
    sets = {
        "claude": {script for _, _, script in HOOK_WIRING},
        "codex": {script for _, _, script in CODEX_HOOK_WIRING},
        "cursor": {script for _, script in CURSOR_HOOK_WIRING},
    }
    reference = sets["claude"]
    others = {h: s for h, s in sorted(sets.items()) if h != "claude"}
    return {
        "scripts": {harness: len(s) for harness, s in sorted(sets.items())},
        "shared": len(set.intersection(*sets.values())),
        "missing": {h: tuple(sorted(reference - s)) for h, s in others.items()},
        "extra": {h: tuple(sorted(s - reference)) for h, s in others.items()},
    }


@dataclass
class Check:
    """One verification result. `ok=False` is a refusal to claim an install works.

    `advisory` marks a finding about the *environment* rather than the install:
    a graph that is not running, a coding-agent CLI that is not present. Install
    wires configuration; it does not own services or other vendors' binaries, so
    it reports those with the command that fixes them and leaves the exit code
    alone. Failing on them would make `thalamus init` refuse to wire a machine
    for the entirely ordinary reason that its containers are not up yet.

    `pending` marks the third state, and it exists because the other two could not
    say it: **not installed yet**. `--check` and `--dry-run` are the two commands a
    cautious operator runs *before* installing, and every absent thing they find is
    the expected shape of an uninstalled box — an agents directory with nothing in
    it, a `~/.cursor/hooks.json` that was never written. Reporting those as `✗`
    tells someone whose machine is fine that their install is broken, and exiting 1
    on them means the safe way to look is also the way that reports failure. A
    pending finding names the command that installs it and leaves the exit code
    alone; anything present and *wrong* stays a hard failure, which is the
    distinction the check is actually for.

    `blocked` is the fourth state and the one the other three could not say: **this
    check could not run.** A prerequisite it needs is absent, so the question was
    never asked and the answer is unknown — which is neither a pass, nor an install
    that is missing, nor a thing that is present and wrong. Two shapes reached it.
    A round trip that needs `jq` printed `✗` beside the word "skipped", against a
    legend that defines `✗` as something present and wrong. And an optional
    integration whose CLI is not installed reported `○` with `thalamus init` as the
    fix, on every run forever, on the ordinary machine that has Claude Code and not
    codex — an item the named command cannot clear devalues the whole `○` block.
    A blocked finding names the prerequisite that is missing and leaves the exit
    code alone.

    It gets `?` rather than sharing `!` with an advisory, because the two say
    different things and a reader scanning marks should not have to reach the closing
    summary to tell them apart. An advisory is a finding — the graph is down, a CLI
    is missing — and it is *true*. A blocked check has no finding at all: nobody
    looked. `?` is the only mark here that means "unknown" rather than a result.
    """
    name: str
    ok: bool
    detail: str
    advisory: bool = False
    pending: bool = False
    blocked: bool = False

    def render(self) -> str:
        if self.ok:
            mark = "✓"
        elif self.blocked:
            mark = "?"
        elif self.pending:
            mark = "○"
        elif self.advisory:
            mark = "!"
        else:
            mark = "✗"
        return f"  {mark} {self.name}: {self.detail}"


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} is not valid JSON ({exc}); refusing to overwrite it") from exc


def _write_json(path: Path, payload: dict) -> None:
    """Write via a temp file in the same dir, so an interrupted install cannot
    truncate the user's settings — a corrupted ~/.claude/settings.json breaks
    every session on the box, not just Thalamus ones."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".thalamus-tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(path)


def _is_thalamus_hook(entry: dict) -> bool:
    """Ours iff it points into the harness hook dir, by either wiring convention."""
    cmd = entry.get("command", "")
    return "thalamus/harness/hooks" in cmd or "$CLAUDE_PROJECT_DIR/src/thalamus" in cmd


def _strip_thalamus_hooks(settings: dict) -> dict:
    """Remove every Thalamus hook, leaving any hooks the operator added alone."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings
    cleaned: dict = {}
    for event, groups in hooks.items():
        kept_groups = []
        for group in groups or []:
            kept = [h for h in group.get("hooks", []) if not _is_thalamus_hook(h)]
            if kept:
                new_group = dict(group)
                new_group["hooks"] = kept
                kept_groups.append(new_group)
        if kept_groups:
            cleaned[event] = kept_groups
    if cleaned:
        settings["hooks"] = cleaned
    else:
        settings.pop("hooks", None)
    return settings


def _build_matcher_block(wiring: list[tuple[str, str | None, str]],
                         hook_dir: Path) -> dict:
    """Claude Code's matcher-group schema, from a (event, matcher, script) table.

    Shared by the Claude Code and codex legs because codex's `hooks.json` is that
    schema — the same event keys, the same `{"type": "command", …}` entries, and
    matchers read as regexes (measured 2026-08-17). Two builders would be two places
    for the grouping rule to drift, and the grouping rule is load-bearing: one script
    serving two matchers must land in two groups, or it fires twice for one tool call.
    """
    block: dict = {}
    for event, matcher, script in wiring:
        entry = {"type": "command", "command": str(hook_dir / script)}
        groups = block.setdefault(event, [])
        for group in groups:
            if group.get("matcher") == matcher:
                group["hooks"].append(entry)
                break
        else:
            group = {"hooks": [entry]}
            if matcher is not None:
                group["matcher"] = matcher
            groups.append(group)
    return block


def build_hook_block() -> dict:
    """The hook block with absolute paths — no $CLAUDE_PROJECT_DIR anywhere."""
    return _build_matcher_block(HOOK_WIRING, HOOK_DIR)


def build_codex_hook_block() -> dict:
    """The same, for `$CODEX_HOME/hooks.json`.

    Absolute paths for a sharper reason than on Claude Code: `$CODEX_HOME` is
    expanded inside a `command`, but nothing else is, and codex resolves a relative
    command against the session's own cwd — which is some other repo entirely
    whenever a session is opened outside the checkout, the reach-past-the-checkout
    failure this module exists to fix.
    """
    return _build_matcher_block(CODEX_HOOK_WIRING, CODEX_HOOK_DIR)


def build_mcp_entry() -> dict:
    """The MCP server, anchored on the checkout rather than the session's cwd.

    THALAMUS_SCOPE is deliberately absent: `main` is the default for a plainly
    launched process, and a pinned session gets its scope from the picked agent
    (harness/pin.resolve_pin), which a static user-scope config cannot express.
    Baking a scope here would pin every session on the box to one expert.

    THALAMUS_WITHHOLD *is* baked in when it is set, because the opposite
    property applies: a randomized-withholding campaign is only interpretable if
    every session in it ran under the same rate, and an env var exported in one
    terminal would randomize some sessions and not others with nothing recording
    which. The rate lives on the server registration so it is a property of the
    machine for the duration of the campaign — and the records carry it, so a run
    that pooled two rates is detectable rather than invisible.
    """
    env = {
        "THALAMUS_GRAPH_URL": os.environ.get(
            "THALAMUS_GRAPH_URL", "ws://localhost:8182/gremlin")
    }
    rate = os.environ.get("THALAMUS_WITHHOLD", "").strip()
    if rate:
        env["THALAMUS_WITHHOLD"] = rate
    return {
        "command": "uv",
        "args": ["run", "--project", str(PROJECT_ROOT), "thalamus-mcp"],
        "env": env,
    }


def build_cursor_hook_block() -> dict:
    """Cursor's hooks.json `hooks` object, with absolute paths.

    Absolute is not a stylistic choice here: Cursor runs *project* hooks from
    the project root but *user* hooks from `~/.cursor/`, so a relative command
    that works in one scope is broken in the other. The checkout's committed
    `.cursor/hooks.json` uses `./src/...` and therefore only ever armed for a
    session whose workspace root was the checkout itself — which is exactly the
    reach-past-the-checkout failure this module exists to fix.

    `failClosed` is set explicitly on the guard rather than left to its `false`
    default: the fail-open posture matches Claude Code (a hook that errors does
    not block the command, only an exit-2 verdict does), and a security-shaped
    hook should state that rather than inherit it.
    """
    block: dict = {}
    for event, script in CURSOR_HOOK_WIRING:
        entry: dict = {"command": str(CURSOR_HOOK_DIR / script), "type": "command"}
        if script == "gremlin-guard.sh":
            entry["failClosed"] = False
        block.setdefault(event, []).append(entry)
    return block


def _strip_cursor_hooks(config: dict) -> dict:
    """Drop our hooks from a Cursor hooks.json, leaving the operator's alone."""
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        return config
    cleaned = {
        event: kept
        for event, entries in hooks.items()
        if (kept := [e for e in entries or [] if not _is_thalamus_hook(e)])
    }
    config["hooks"] = cleaned
    return config


def install_cursor(dry_run: bool = False) -> list[str]:
    """Wire Cursor at user scope and strip the checkout's project-scope copy.

    Same mutual-exclusion argument as the Claude Code leg, and Cursor states the
    precedence the Claude Code docs leave open — Enterprise > Team > Project >
    User — so a surviving project block would silently outrank the user-scope
    one we just wrote. Removing it leaves exactly one definition. It also
    retires a consent problem: a committed `.cursor/hooks.json`
    runs for anyone who opens this repo in Cursor.
    """
    actions: list[str] = []

    current = _load_json(USER_CURSOR_HOOKS)
    desired = build_cursor_hook_block()
    merged = _strip_cursor_hooks(json.loads(json.dumps(current)))
    merged["version"] = 1
    for event, entries in desired.items():
        merged.setdefault("hooks", {}).setdefault(event, []).extend(entries)

    if current == merged:
        actions.append(f"cursor user hooks already current ({USER_CURSOR_HOOKS})")
    else:
        actions.append(f"{'would write' if dry_run else 'wrote'} cursor hooks to {USER_CURSOR_HOOKS}")
        if not dry_run:
            _write_json(USER_CURSOR_HOOKS, merged)

    # Cursor has no `cursor mcp add` CLI, so this file is edited directly —
    # safe in a way `~/.claude.json` is not, because it holds only MCP servers
    # rather than every project's history, and `_write_json` replaces it
    # atomically.
    cursor_mcp = _load_json(USER_CURSOR_MCP)
    servers = cursor_mcp.setdefault("mcpServers", {})
    if servers.get("thalamus") == build_mcp_entry():
        actions.append(f"cursor MCP server already current ({USER_CURSOR_MCP})")
    else:
        servers["thalamus"] = build_mcp_entry()
        actions.append(f"{'would register' if dry_run else 'registered'} `thalamus` MCP server "
                       f"at cursor user scope ({USER_CURSOR_MCP})")
        if not dry_run:
            _write_json(USER_CURSOR_MCP, cursor_mcp)

    project = _load_json(PROJECT_CURSOR_HOOKS)
    if project.get("hooks"):
        stripped = _strip_cursor_hooks(json.loads(json.dumps(project)))
        if stripped != project:
            actions.append(
                f"{'would strip' if dry_run else 'stripped'} project-scope cursor hooks "
                f"({PROJECT_CURSOR_HOOKS}) — user scope is now the single definition")
            if not dry_run:
                _write_json(PROJECT_CURSOR_HOOKS, stripped)
    else:
        actions.append("project-scope cursor hook block already absent")

    project_mcp = _load_json(PROJECT_CURSOR_MCP)
    if "thalamus" in project_mcp.get("mcpServers", {}):
        remaining = {k: v for k, v in project_mcp["mcpServers"].items() if k != "thalamus"}
        actions.append(
            f"{'would remove' if dry_run else 'removed'} project-scope `thalamus` cursor MCP "
            f"server ({PROJECT_CURSOR_MCP}) — its `uv run` was cwd-relative anyway")
        if not dry_run:
            if remaining:
                project_mcp["mcpServers"] = remaining
                _write_json(PROJECT_CURSOR_MCP, project_mcp)
            else:
                PROJECT_CURSOR_MCP.unlink()
    else:
        actions.append("project-scope cursor MCP server already absent")

    return actions


def register_codex_mcp(dry_run: bool = False) -> str:
    """Register the server through `codex mcp add`, never by editing config.toml.

    Same reasoning as `register_mcp`, with the file changed: `$CODEX_HOME/config.toml`
    is codex's own, not ours. It carries the per-project `trust_level` records and the
    `[hooks.state]` trust hashes codex writes for itself, so a read-modify-write of it
    would drop whatever the CLI put there between our read and our replace — and it is
    TOML, where a naive round-trip loses comments and ordering as well.

    Idempotent with no remove-first, unlike the Claude Code leg: `codex mcp add`
    overwrites an existing name rather than refusing it (measured — two adds under one
    name left one `[mcp_servers.thalamus]` table carrying the second one's values).

    A named function for the reason `deregister_mcp` is one: it reaches a real file on
    a real machine, so the test suite needs exactly one seam to stub.
    """
    cli = shutil.which("codex")
    if cli is None:
        return "SKIPPED codex MCP registration: `codex` not on PATH"

    entry = build_mcp_entry()
    add_cmd = [cli, "mcp", "add", "thalamus"]
    for name, value in entry["env"].items():
        add_cmd += ["--env", f"{name}={value}"]
    add_cmd += ["--", entry["command"], *entry["args"]]
    if dry_run:
        return f"would register `thalamus` MCP server with codex: {' '.join(add_cmd[1:])}"

    proc = subprocess.run(add_cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return f"codex MCP registration FAILED: {(proc.stderr or proc.stdout).strip()[:300]}"
    return f"registered `thalamus` MCP server with codex ({USER_CODEX_MCP})"


def deregister_codex_mcp(dry_run: bool = False) -> str:
    """Remove the server, through the CLI for the reason it was added through it."""
    cli = shutil.which("codex")
    if cli is None:
        return "SKIPPED codex MCP deregistration: `codex` not on PATH"
    if dry_run:
        return "would deregister `thalamus` MCP server (codex mcp remove thalamus)"
    proc = subprocess.run([cli, "mcp", "remove", "thalamus"],
                          capture_output=True, text=True, timeout=60)
    out = f"{proc.stdout}{proc.stderr}"
    return ("deregistered `thalamus` MCP server from codex" if "Removed" in out
            else "`thalamus` MCP server was not registered with codex")


def codex_mcp_registration() -> str:
    """What `codex mcp get thalamus` reports, or "" when nothing is registered.

    Read through the CLI rather than by parsing `config.toml`, mirroring
    `registered_mcp_env`. One thing it cannot answer: codex **masks env values** in
    this output (`THALAMUS_GRAPH_URL=*****`), so the env-drift check that raises a
    relaunch advisory on the Claude Code leg has no codex counterpart — a withholding
    rate that moved under a codex session is not detectable from here.
    """
    cli = shutil.which("codex")
    if cli is None:
        return ""
    try:
        proc = subprocess.run([cli, "mcp", "get", "thalamus"],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    out = f"{proc.stdout}{proc.stderr}"
    return "" if "No MCP server named" in out else proc.stdout


def install_codex(dry_run: bool = False) -> list[str]:
    """Wire codex at its config root. There is no project scope to strip.

    Measured 2026-08-17: `$CODEX_HOME/hooks.json` is the only file codex loads hooks
    from — a project-level `./.codex/hooks.json` is not discovered, and hooks declared
    in `config.toml` do not fire. So the mutual-exclusion problem the other two legs
    solve by removing a second definition does not arise: there is one place, and this
    writes it.

    Codex also does not read `~/.claude/settings.json` (measured — three codex
    sessions ran with the Claude Code suite installed at user scope and left no
    ledger row and no log line), so nothing here can be left to a vendor
    compatibility path the way `role-guard.sh` is on Cursor.
    """
    actions: list[str] = []

    current = _load_json(USER_CODEX_HOOKS)
    desired = build_codex_hook_block()
    merged = _strip_thalamus_hooks(json.loads(json.dumps(current)))
    merged.setdefault("hooks", {})
    for event, groups in desired.items():
        merged["hooks"].setdefault(event, []).extend(groups)

    if current == merged:
        actions.append(f"codex hooks already current ({USER_CODEX_HOOKS})")
    else:
        actions.append(f"{'would write' if dry_run else 'wrote'} codex hooks to "
                       f"{USER_CODEX_HOOKS}")
        if not dry_run:
            _write_json(USER_CODEX_HOOKS, merged)

    actions.append(register_codex_mcp(dry_run=dry_run))

    # The persona half, and the codex twin of `write_all_agents`. Installed rather than
    # left to `thalamus pin` because `--profile` is reachable without a launcher, and a
    # profile that does not exist is not an error there — `codex --profile
    # thalamus-designer` in a fresh shell would open a session indistinguishable from
    # the designer and carrying none of the charter.
    if dry_run:
        actions.append(f"would write derived codex profiles to {CODEX_HOME}")
    else:
        written = write_all_codex_profiles()
        actions.append(f"wrote {len(written)} derived codex profiles to {CODEX_HOME}")
    return actions


def registered_mcp_env() -> dict[str, str]:
    """The env the *currently registered* server would launch with.

    Read through `claude mcp get` rather than `~/.claude.json` for the same reason
    registration goes through `claude mcp add`: the CLI owns that file. Read-only
    here, so the concurrency argument is weaker, but parsing a private schema we
    are told not to write is a dependency worth not taking twice.

    Returns {} when the server is unregistered or the CLI is absent — both mean
    "nothing is running the old config", which is the same as no drift.
    """
    cli = shutil.which("claude")
    if cli is None:
        return {}
    try:
        proc = subprocess.run([cli, "mcp", "get", "thalamus"],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return {}
    if proc.returncode != 0:
        return {}
    env: dict[str, str] = {}
    in_env = False
    for line in (proc.stdout or "").splitlines():
        if line.strip() == "Environment:":
            in_env = True
            continue
        if in_env:
            # The block ends at the first line that is not an indented KEY=VALUE.
            if not line.startswith(" ") or "=" not in line:
                break
            name, _, value = line.strip().partition("=")
            env[name] = value
    return env


def mcp_env_drift(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """What changed in the MCP server's env, named one variable at a time."""
    changes = []
    for name in sorted(set(before) | set(after)):
        was, now = before.get(name), after.get(name)
        if was == now:
            continue
        if was is None:
            changes.append(f"{name} set to `{now}`")
        elif now is None:
            changes.append(f"{name} unset (was `{was}`)")
        else:
            changes.append(f"{name} `{was}` -> `{now}`")
    return changes


def register_mcp(dry_run: bool = False) -> str:
    """Register the server through `claude mcp add`, never by editing the file.

    `~/.claude.json` is not ours: it holds every project's history and is written
    by every live `claude` process on the box, including the one running this
    install. A read-modify-write of an 80KB shared file loses whatever a
    concurrent session wrote between our read and our replace. The CLI owns that
    file and serializes access to it, so it is the only safe writer.

    Idempotent by remove-then-add, because `add` refuses an existing name.
    """
    cli = shutil.which("claude")
    if cli is None:
        return "SKIPPED MCP registration: `claude` not on PATH"

    entry = build_mcp_entry()
    add_cmd = [cli, "mcp", "add", "--scope", "user", "thalamus"]
    for name, value in entry["env"].items():
        add_cmd += ["-e", f"{name}={value}"]
    add_cmd += ["--", entry["command"], *entry["args"]]
    if dry_run:
        return f"would register `thalamus` MCP server at user scope: {' '.join(add_cmd[1:])}"

    subprocess.run([cli, "mcp", "remove", "--scope", "user", "thalamus"],
                   capture_output=True, text=True, timeout=60)
    proc = subprocess.run(add_cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return f"MCP registration FAILED: {(proc.stderr or proc.stdout).strip()[:300]}"
    return "registered `thalamus` MCP server at user scope (via `claude mcp add`)"


def deregister_mcp(dry_run: bool = False) -> str:
    """Remove the user-scope server, through the CLI for the same reason `register_mcp` adds through it.

    A named function rather than an inline `subprocess.run`, because this reaches
    a real file on a real machine and every caller that must *not* — the test
    suite above all — needs one seam to stub. `~/.claude.json` is not reliably
    contained by overriding `HOME` for the child process, so a test that lets
    this run deregisters the server of whoever ran the test.
    """
    cli = shutil.which("claude")
    if cli is None:
        return "SKIPPED MCP deregistration: `claude` not on PATH"
    if dry_run:
        return "would deregister `thalamus` MCP server (claude mcp remove --scope user)"
    proc = subprocess.run([cli, "mcp", "remove", "--scope", "user", "thalamus"],
                          capture_output=True, text=True, timeout=60)
    return ("deregistered `thalamus` MCP server at user scope" if proc.returncode == 0
            else "`thalamus` MCP server was not registered at user scope")


def shipped_skills() -> list[Path]:
    """The invocable skills that travel with the package.

    YAML frontmatter is the discriminator, not the presence of a SKILL.md.
    Frontmatter is what makes a directory invocable at all, so a SKILL.md
    without it is prose — a prompt template or a note — and installing it would
    advertise something no session can call.
    """
    if not SKILL_DIR.is_dir():
        return []
    return sorted(d for d in SKILL_DIR.iterdir()
                  if (d / "SKILL.md").is_file()
                  and (d / "SKILL.md").read_text(errors="replace").startswith("---"))


def installed_skill_links() -> list[Path]:
    """Every link in the user's skills directory that points into this checkout.

    Identity is where the link *points*, not whether its target is in
    `shipped_skills()`. A link whose skill has since been renamed or dropped
    resolves to a path in no shipped set, so a resolves-to-a-shipped-skill test
    passes over it twice: `--uninstall` leaves it behind and `verify` never looks
    at it, and it sits in the user's skills directory dangling and unreported.

    Scoping to `SKILL_DIR` keeps the half of the promise that test was protecting.
    A hand-written skill that happens to share a name points somewhere else, and so
    does a link installed from a different checkout; both are still left alone.
    """
    if not USER_SKILLS_DIR.is_dir():
        return []
    root = SKILL_DIR.resolve()
    return [dest for dest in sorted(USER_SKILLS_DIR.glob("*"))
            if dest.is_symlink() and root in dest.resolve().parents]


def stale_skill_links() -> list[Path]:
    """Our links whose target is gone — the residue of a rename or a removal."""
    return [dest for dest in installed_skill_links() if not dest.exists()]


def link_skills(dry_run: bool = False) -> list[str]:
    """Symlink each shipped skill into user scope, so it arms outside the checkout.

    Same reasoning as the hooks: a session opened elsewhere (`thalamus spawn
    --dir`) gets the hooks, the MCP server and the derived agents, and without
    this it gets no `recall-strategy`, `ground-in-literature` or
    `gremlin-python` — the three that govern how it queries the graph and
    grounds a design. That absence is silent in the Xu et al. sense: nothing
    errors, the session just writes lazy traversals and uncited designs.

    Symlinks rather than copies, and the checkout's own `.claude/skills` links
    are left alone: both point at the same package files, so there is exactly
    one source of truth, an edit lands on every scope at once, and a fresh clone
    still has its skills before anyone runs `thalamus init`.

    A user-scope name that is *not* our symlink is never touched — that
    directory holds hand-written skills, and clobbering one to install ours
    would be a worse failure than the one being fixed.
    """
    actions: list[str] = []
    skills = shipped_skills()
    if not skills:
        return [f"no shipped skills found under {SKILL_DIR}"]

    # Pruning before linking, so an upgrade that renames or drops a skill does not
    # leave its link behind: `verify` reports one as a hard failure, and this is the
    # command that clears it. It is the same identity test uninstall uses, and it
    # only ever unlinks — the target is already gone.
    pruned = []
    for dest in stale_skill_links():
        pruned.append(dest.name)
        if not dry_run:
            dest.unlink()

    linked, refused = [], []
    for src in skills:
        dest = USER_SKILLS_DIR / src.name
        if dest.is_symlink() and dest.resolve() == src.resolve():
            continue
        if dest.exists() or dest.is_symlink():
            refused.append(f"{src.name} (exists, not ours)")
            continue
        linked.append(src.name)
        if not dry_run:
            USER_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
            dest.symlink_to(src)

    if linked:
        actions.append(f"{'would link' if dry_run else 'linked'} {len(linked)} skill(s) into "
                       f"{USER_SKILLS_DIR}: {', '.join(linked)}")
    else:
        actions.append(f"skills already linked at user scope ({USER_SKILLS_DIR})")
    if pruned:
        actions.append(f"{'would unlink' if dry_run else 'unlinked'} {len(pruned)} skill "
                       f"link(s) whose skill no longer ships: {', '.join(pruned)}")
    if refused:
        actions.append(f"left alone (not installed by us): {', '.join(refused)}")
    return actions


def graph_url() -> str:
    return os.environ.get("THALAMUS_GRAPH_URL", "ws://localhost:8182/gremlin")


def verify_runtime(harnesses: tuple[str, ...] = HARNESSES) -> list[Check]:
    """Advisory checks on the things install wires *toward* but does not own.

    Both failures here are silent in exactly the way the rest of this module
    guards against. A graph that is not running does not announce itself at
    install time — the first symptom is a recall that returns nothing, which
    reads as "no memory yet" rather than as an error. A missing coding-agent CLI
    is worse: distillation runs detached from SessionEnd, so its absence surfaces
    as memory that quietly stopped accumulating. Neither is checked anywhere else,
    and neither is a reason to refuse to wire the machine — so they report, with
    the command that fixes them, and leave the exit code alone.
    """
    checks: list[Check] = []
    url = graph_url()

    # Three outcomes, not two. Nothing listening is the container being down and
    # gets the command that starts it. A port that is up while the query fails is
    # the boot window, and the correct action there is to wait — telling that
    # operator to `docker compose up -d` contradicts what he can see, on the one
    # step of the documented sequence he has no way to debug.
    reachable, detail, nothing_listening = _probe_graph(url)
    if not reachable and nothing_listening:
        detail = graph_down_detail(detail)
    elif not reachable:
        detail = (f"{detail} — the port is published before the server finishes "
                  "starting, which takes a few seconds. Check `docker compose ps` "
                  "shows the graph healthy, then re-run `thalamus init --check`")
    checks.append(Check("graph reachable", reachable, detail, advisory=True))

    # One CLI per harness being installed. `agent` missing on a box without
    # Cursor is expected and not a fault, which is why this is advisory even
    # when the harness is being wired: the config is still correct, and it
    # starts working the day the binary appears.
    for harness in harnesses:
        cli = agents.cli_for(harness)
        found = shutil.which(cli.binary)
        checks.append(Check(
            f"{harness} distillation CLI",
            found is not None,
            f"`{cli.binary}` at {found}" if found else
            f"`{cli.binary}` not on PATH — {harness} sessions will retrieve and "
            f"trace but never distill (install it, or extract with "
            f"`--harness {_other_harnesses(harness)}`)",
            advisory=True,
        ))

    checks.append(recorded_hook_failures())

    return checks


def recorded_hook_failures() -> Check:
    """Sessions that ended without distilling because a binary a hook needs was gone.

    The other direction of the same problem the two PATH checks above cover, and the
    half they cannot answer. `jq on PATH` reports the state of this machine at the
    moment `--check` runs; if jq was missing over the weekend and is back now, it
    passes, and the sessions lost in between are invisible — distillation is
    detached, so nothing announced them. The hooks record the loss themselves
    (`thalamus_require_binaries`, hooks/claude-code/resolve-scope.sh), and this reads
    the record back on the surface an operator already runs when memory looks stale.

    Advisory: the file is a history of the environment, not a fault in the wiring.
    """
    try:
        lines = [ln for ln in HOOK_FAILURE_LOG.read_text(errors="replace").splitlines()
                 if ln.strip()]
    except OSError:
        lines = []
    if not lines:
        return Check("sessions lost to a missing binary", True,
                     f"none recorded in {HOOK_FAILURE_LOG}", advisory=True)
    return Check(
        "sessions lost to a missing binary", False,
        f"{len(lines)} ended undistilled — most recently: {lines[-1]} "
        f"(the record is {HOOK_FAILURE_LOG}; delete it to clear this)",
        advisory=True,
    )


def _probe_graph(url: str) -> tuple[bool, str, bool]:
    """Reachable, and answering? Exercised the real way, but bounded.

    Two stages because they fail differently and only one of them can hang: a
    closed port is settled by a 2s TCP connect, and only once something is
    listening is a real traversal worth attempting. The traversal runs in a
    subprocess so a peer that accepts the connection and then never completes the
    websocket handshake costs a timeout rather than a wedged install.

    A graph with zero vertices is a **pass**: every install is fresh, the graph is
    private to its operator and is never shipped, so an empty one is the normal
    starting state rather than a fault.

    The third element is what the caller needs to say the right sentence: whether
    *nothing was listening*. Docker publishes the port the moment the container
    starts, and the JVM then takes another 3.5-4s to reach `Channel started at port
    8182` — measured from container logs on this box, before any image pull. In that
    window the socket check passes and the traversal does not, and the old text told
    the operator to start a container he could see running.
    """
    down = probe_socket(url)
    if down is not None:
        return False, down, True
    host, port = split_ws(url)

    script = (
        "import sys;"
        "from thalamus.substrate.writer import connect, close_connection;"
        "g = connect(sys.argv[1]);"
        "n = g.V().count().next();"
        "close_connection(g);"
        "print(n)"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script, url],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"{host}:{port} accepted a connection but did not answer ({exc})", False

    if proc.returncode != 0:
        return False, f"{host}:{port} refused the query: {proc.stderr.strip()[-160:]}", False

    count = proc.stdout.strip()
    fresh = " (fresh — every install starts empty)" if count == "0" else ""
    return True, f"{count} vertices at {url}{fresh}", False


def verify_cursor() -> list[Check]:
    """Exercise the Cursor leg the way the Claude Code leg is exercised.

    The deferred-injection pair gets a real round trip rather than a file-exists
    check, because its failure mode is the silent one: a broken spool costs the
    session its clock and its conditioning and reports nothing at all.
    """
    checks: list[Check] = []
    scripts = sorted({s for _, s in CURSOR_HOOK_WIRING})

    missing = [s for s in scripts if not (CURSOR_HOOK_DIR / s).is_file()]
    checks.append(Check("cursor hook scripts present", not missing,
                        f"all {len(scripts)} wired scripts found" if not missing
                        else f"missing: {missing}"))

    unexec = [s for s in scripts
              if (CURSOR_HOOK_DIR / s).is_file() and not os.access(CURSOR_HOOK_DIR / s, os.X_OK)]
    checks.append(Check("cursor hook scripts executable", not unexec,
                        "all executable" if not unexec else f"not executable: {unexec}"))

    # A hooks file with none of our scripts in it is an uninstalled Cursor, not a
    # broken one; one holding *some* of them has drifted and is a real failure.
    wired = _load_json(USER_CURSOR_HOOKS)
    commands = {e.get("command") for entries in wired.get("hooks", {}).values() for e in entries}
    unwired = [s for s in scripts if str(CURSOR_HOOK_DIR / s) not in commands]
    checks.append(Check(
        "cursor hooks wired at user scope",
        not unwired and wired.get("version") == 1,
        f"{len(scripts)} scripts in {USER_CURSOR_HOOKS}" if not unwired
        else f"not written yet ({USER_CURSOR_HOOKS}) — `thalamus init` writes it"
        if len(unwired) == len(scripts)
        else f"not wired: {unwired}",
        pending=len(unwired) == len(scripts),
    ))

    # The absent case is tested *first*, and the healthy case second. Read the other
    # way round a stale entry is a non-empty dict, so it is truthy, so it takes the
    # healthy branch: the run prints `✗` beside the text for a working install and
    # the drifted case is unreachable. Reached by moving or renaming the checkout
    # after `thalamus init`, so the detail names the fields that differ — the
    # failure is almost always one stale path inside `args`.
    served = _load_json(USER_CURSOR_MCP).get("mcpServers", {}).get("thalamus")
    expected = build_mcp_entry()
    drifted = sorted({k for k in set(served or {}) | set(expected)
                      if (served or {}).get(k) != expected.get(k)})
    checks.append(Check(
        "cursor MCP server registered", served == expected,
        f"not registered yet in {USER_CURSOR_MCP} — `thalamus init` registers it"
        if served is None
        else f"`thalamus` in {USER_CURSOR_MCP}" if served == expected
        else f"`thalamus` in {USER_CURSOR_MCP} does not match the entry this checkout "
             f"builds — differing: {', '.join(drifted)}; re-run `thalamus init`",
        pending=served is None,
    ))

    # The load-bearing Cursor check: spool a turn on beforeSubmitPrompt, then
    # drain it on postToolUse, in a throwaway HOME. This is the mechanism that
    # replaces an event Cursor does not have, so nothing else proves it works.
    ok, detail = False, "not run"
    if shutil.which("jq") and (CURSOR_HOOK_DIR / "inject.sh").is_file():
        import tempfile
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env = {**os.environ, "HOME": tmp}
                payload = json.dumps({"session_id": "verify", "prompt": "hello"})
                subprocess.run([str(CURSOR_HOOK_DIR / "timestamp.sh")], input=payload,
                               capture_output=True, text=True, timeout=30, env=env, check=True)
                drained = subprocess.run([str(CURSOR_HOOK_DIR / "inject.sh")],
                                         input=json.dumps({"session_id": "verify"}),
                                         capture_output=True, text=True, timeout=30, env=env)
                got = json.loads(drained.stdout or "{}").get("additional_context", "")
                ok = "Current date and time" in got
                detail = ("clock spooled and delivered through postToolUse" if ok
                          else f"spool did not round-trip: {drained.stdout[:120]!r}")
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            detail = f"round trip failed: {exc}"
    else:
        missing = [name for name, present in (("jq", shutil.which("jq")),
                                              ("inject.sh", (CURSOR_HOOK_DIR / "inject.sh").is_file()))
                   if not present]
        detail = f"could not run: {', '.join(missing)} missing on this machine"
    checks.append(Check("cursor deferred injection round trip", ok, detail,
                        blocked=not ok and detail.startswith("could not run")))

    return checks


def _codex_event_key(event: str) -> str:
    """`PreToolUse` -> `pre_tool_use` — the spelling codex uses in a trust key."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", event).lower()


def codex_trust_keys() -> set[str]:
    """The hook coordinates codex has a trust record for, from its own config.

    Measured 2026-08-17. Trust is persisted in `$CODEX_HOME/config.toml` as

        [hooks.state."<hooks.json path>:<event_snake>:<group_index>:<hook_index>"]
        trusted_hash = "sha256:…"

    and it is **load-bearing in the silent direction**: with a hooks.json present and
    untrusted, a headless `codex exec` ran to completion, exited 0, printed nothing
    about hooks, and fired none of them. That is the Xu et al. latent error exactly —
    the wiring is right, the memory simply stops accumulating — so it is checked here
    rather than assumed.

    What this cannot answer is whether a record is *current*. The key carries the
    coordinates and the hash covers the entry, and we cannot recompute codex's hash;
    a record left from an earlier wiring has the same key as a fresh one. Editing a
    hook *script* does not invalidate anything (measured: a trusted hook still ran
    after its script was edited), so the stale case is a changed wiring table, which
    is exactly when `thalamus init` rewrites the file and codex asks again.
    """
    try:
        import tomllib

        with USER_CODEX_MCP.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, ValueError):
        return set()
    state = (data.get("hooks") or {}).get("state") or {}
    return {key for key in state if isinstance(state.get(key), dict)}


def verify_codex() -> list[Check]:
    """Exercise the codex leg the way the other two are exercised.

    Three of these are the shared shape — scripts present, executable, wired. The two
    that are codex's own are the trust state, which no other harness has, and one live
    delegation, which is the mechanism that replaces Cursor's eight adapters and so
    the one thing nothing else here proves.
    """
    checks: list[Check] = []
    scripts = sorted({s for _, _, s in CODEX_HOOK_WIRING})

    missing = [s for s in scripts if not (CODEX_HOOK_DIR / s).is_file()]
    checks.append(Check("codex hook scripts present", not missing,
                        f"all {len(scripts)} wired scripts found" if not missing
                        else f"missing: {missing}"))

    unexec = [s for s in scripts
              if (CODEX_HOOK_DIR / s).is_file() and not os.access(CODEX_HOOK_DIR / s, os.X_OK)]
    checks.append(Check("codex hook scripts executable", not unexec,
                        "all executable" if not unexec else f"not executable: {unexec}"))

    wired = _load_json(USER_CODEX_HOOKS)
    commands = {h.get("command")
                for groups in (wired.get("hooks") or {}).values()
                for group in groups or []
                for h in group.get("hooks") or []}
    unwired = [s for s in scripts if str(CODEX_HOOK_DIR / s) not in commands]
    checks.append(Check(
        "codex hooks wired at user scope",
        not unwired,
        f"{len(scripts)} scripts in {USER_CODEX_HOOKS}" if not unwired
        else f"not written yet ({USER_CODEX_HOOKS}) — `thalamus init` writes it"
        if len(unwired) == len(scripts)
        else f"not wired: {unwired}",
        pending=len(unwired) == len(scripts),
    ))

    # The trust state, reported as its own finding rather than folded into the wiring
    # check: a wired-and-untrusted codex is fully installed and completely inert, and
    # the fix is the operator's to make in a TUI — nothing this installer can write
    # would grant it, and building a wrapper whose text never changes so the hash
    # stays green would be routing around a supply-chain control.
    #
    # Which of the three states it reports matters, because each names a different
    # fix. Nothing wired is `pending`: `thalamus init` is the command, and the trust
    # question does not exist yet. Wired and untrusted is **advisory** — the install
    # is correct and something outside it must become true before it does anything,
    # which is the same shape as an unreachable graph, and telling the operator to
    # re-run `thalamus init` would be sending them to a command that cannot grant it.
    # Wired and *partly* trusted is a hard failure: codex was asked and the answer
    # covered only part of the table, so some hooks fire and some silently do not.
    expected = {
        f"{USER_CODEX_HOOKS}:{_codex_event_key(event)}:{gi}:{hi}"
        for event, groups in build_codex_hook_block().items()
        for gi, group in enumerate(groups)
        for hi, _ in enumerate(group["hooks"])
    }
    trusted = expected & codex_trust_keys()
    never_wired = len(unwired) == len(scripts)
    checks.append(Check(
        "codex hooks trusted", trusted == expected,
        f"all {len(expected)} entries carry a trust record in {USER_CODEX_MCP}"
        if trusted == expected
        else f"no hooks written yet ({USER_CODEX_HOOKS}) — `thalamus init` writes "
             "them, and codex then asks you to trust them"
        if never_wired
        else "could not run: `codex` is not on this machine, and trust is granted "
             "in its own hooks-review prompt"
        if shutil.which("codex") is None
        else "codex has not been asked to trust these hooks yet — launch `codex` once "
             "and take the trust-all option on the hooks-review prompt. Until then "
             "codex loads them and fires none of them: a headless `codex exec` with "
             "an untrusted hooks.json ran to completion, exited 0, said nothing about "
             "hooks, and distilled nothing"
        if not trusted
        else f"{len(trusted)} of {len(expected)} entries are trusted — launch `codex` "
             "and trust the rest; the untrusted ones do not fire",
        pending=never_wired,
        blocked=not never_wired and shutil.which("codex") is None,
        advisory=not never_wired and not trusted,
    ))

    # The load-bearing codex check: one real delegation, in a throwaway HOME. Codex
    # needs no payload adapters *except* on a shell result, which it sends as one
    # string where Claude Code sends `{stdout, stderr}` — so this drives the reshape
    # and the hand-off together. A silent failure here would price every ad-hoc
    # gremlin query at zero and read as a traversal that returned nothing.
    ok, detail = False, "not run"
    tap = CODEX_HOOK_DIR / "gremlin-tap.sh"
    if shutil.which("jq") and tap.is_file():
        import tempfile
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env = {**os.environ, "HOME": tmp}
                env.pop("THALAMUS_SANDBOX", None)
                payload = json.dumps({
                    "hook_event_name": "PostToolUse",
                    "session_id": "verify",
                    "cwd": tmp,
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -c 'from gremlin_python import x'"},
                    "tool_response": "verify-marker",
                })
                subprocess.run([str(tap)], input=payload, capture_output=True,
                               text=True, timeout=30, env=env, check=True)
                traces = list((Path(tmp) / ".thalamus" / "traces").glob("*.jsonl"))
                landed = traces and "verify-marker" in traces[0].read_text()
                ok = bool(landed)
                detail = ("a codex shell payload reshaped and delegated into the "
                          "shared trace log" if ok
                          else "the delegation left no trace record")
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            detail = f"delegation failed: {exc}"
    else:
        missing = [name for name, present in (("jq", shutil.which("jq")),
                                              ("gremlin-tap.sh", tap.is_file()))
                   if not present]
        detail = f"could not run: {', '.join(missing)} missing on this machine"
    checks.append(Check("codex delegation round trip", ok, detail,
                        blocked=not ok and detail.startswith("could not run")))

    # `thalamus init` registers this by shelling out to `codex mcp add`, so on a box
    # without the binary it is not a pending item: the command the pending text names
    # runs, skips the registration, and leaves the check exactly where it was. Every
    # `--check` on an ordinary Claude-Code-only machine carried it forever, under a
    # closing line telling the operator to run `thalamus init` to clear it.
    codex_cli = shutil.which("codex")
    served = codex_mcp_registration()
    checks.append(Check(
        "codex MCP server registered", str(PROJECT_ROOT) in served,
        f"`thalamus` in {USER_CODEX_MCP}" if str(PROJECT_ROOT) in served
        else "could not run: `codex` is not on this machine, and the registration "
             "goes in through `codex mcp add`" if codex_cli is None
        else f"not registered yet ({USER_CODEX_MCP}) — `thalamus init` registers it"
        if not served
        else f"registered with codex but not against this checkout ({PROJECT_ROOT}) "
             "— re-run `thalamus init`",
        pending=not served and codex_cli is not None,
        blocked=codex_cli is None and str(PROJECT_ROOT) not in served,
    ))

    # Checked rather than assumed because the failure is silent on this harness
    # specifically: `codex --profile thalamus-designer` for a profile that was never
    # written starts an ordinary session with no charter and no arming, exits 0, and
    # says nothing. There is no error for the operator to notice, so the check is the
    # notice.
    profiles = (sorted(CODEX_HOME.glob("thalamus-*.config.toml"))
                if CODEX_HOME.is_dir() else [])
    checks.append(Check(
        "derived codex profiles installed", bool(profiles),
        f"{len(profiles)} in {CODEX_HOME}" if profiles
        else f"none written yet to {CODEX_HOME} — `thalamus init` writes one per "
             "expert manifest, and until it does a `--profile` pin carries no charter "
             "and reports no error",
        pending=not profiles,
    ))

    return checks


def verify(harnesses: tuple[str, ...] = HARNESSES) -> list[Check]:
    """Exercise what would otherwise fail late (PCheck's early-detection idea).

    Each check runs the *real* mechanism, not a proxy for it: the point is that
    a path which merely exists can still be unrunnable, and a `uv` project that
    resolves from one cwd can fail from another.
    """
    checks: list[Check] = []

    wired = sorted({s for _, _, s in HOOK_WIRING})
    missing = [s for s in wired if not (HOOK_DIR / s).is_file()]
    checks.append(Check("hook scripts present", not missing,
                        f"all {len(wired)} wired scripts found" if not missing
                        else f"missing: {missing}"))

    unexec = sorted({s for _, _, s in HOOK_WIRING
                     if (HOOK_DIR / s).is_file() and not os.access(HOOK_DIR / s, os.X_OK)})
    checks.append(Check("hook scripts executable", not unexec,
                        "all executable" if not unexec else f"not executable: {unexec}"))

    # jq: every retained hook parses stdin with it under `set -euo pipefail`,
    # so without it the whole hook layer dies on the first event.
    jq = shutil.which("jq")
    checks.append(Check("jq on PATH", jq is not None, jq or "NOT FOUND — every hook will fail"))

    uv = shutil.which("uv")
    checks.append(Check("uv on PATH", uv is not None, uv or "NOT FOUND — distillation cannot run"))

    # The load-bearing one: SessionEnd's exact invocation, from a cwd that is
    # deliberately not the checkout. This is the call that used to die detached.
    if uv:
        try:
            proc = subprocess.run(
                ["uv", "run", "--project", str(PROJECT_ROOT), "thalamus", "--help"],
                capture_output=True, text=True, timeout=180, cwd=str(Path.home()),
            )
            ok = proc.returncode == 0
            detail = ("`thalamus` resolves from a foreign cwd"
                      if ok else f"exit {proc.returncode}: {proc.stderr.strip()[:200]}")
        except (subprocess.TimeoutExpired, OSError) as exc:
            ok, detail = False, f"could not run: {exc}"
        checks.append(Check("distillation entry point", ok, detail))

    agents = sorted(USER_AGENTS_DIR.glob("thalamus-*.md")) if USER_AGENTS_DIR.is_dir() else []
    checks.append(Check("derived agents installed", bool(agents),
                        f"{len(agents)} in {USER_AGENTS_DIR}" if agents
                        else f"none written yet to {USER_AGENTS_DIR} — `thalamus init` "
                             "writes one per expert manifest",
                        pending=not agents))

    # Read each skill *through* its user-scope path, the way a session outside
    # the checkout will. A symlink that exists can still dangle, and a dangling
    # one is invisible until a design goes ungrounded — so resolve it and read
    # the frontmatter rather than calling `.exists()` and believing it.
    #
    # A name with nothing at it at all is the uninstalled case and is reported as
    # such. A name that *exists* and cannot be read is the dangling link, and stays
    # a hard failure: it passes `.exists()`, so nothing else catches it.
    unlinked, unreadable = [], []
    for src in shipped_skills():
        dest = USER_SKILLS_DIR / src.name
        try:
            if "name:" not in (dest / "SKILL.md").read_text()[:400]:
                unreadable.append(f"{src.name} (no frontmatter)")
        except OSError as exc:
            if dest.exists() or dest.is_symlink():
                unreadable.append(f"{src.name} ({exc.strerror or exc})")
            else:
                unlinked.append(src.name)
    # A link of ours whose skill no longer ships: present, wrong, and clearable by
    # `thalamus init`, so it is a hard failure rather than an advisory. The loop
    # above cannot see it — it walks the shipped set, and this name is not in it.
    stale = [d.name for d in stale_skill_links()]

    if unreadable or stale:
        detail = ", ".join(
            part for part in (f"unreadable: {unreadable}" if unreadable else "",
                              f"links to skills that no longer ship: {stale} — "
                              "`thalamus init` unlinks them" if stale else "") if part)
    elif unlinked:
        detail = (f"{len(unlinked)} of {len(shipped_skills())} not linked yet into "
                  f"{USER_SKILLS_DIR} — `thalamus init` links them")
    else:
        detail = f"{len(shipped_skills())} readable via {USER_SKILLS_DIR}"
    checks.append(Check("skills load at user scope", not (unreadable or stale or unlinked),
                        detail,
                        pending=bool(unlinked) and not (unreadable or stale)))

    if "claude" in harnesses:
        checks.append(verify_armed())

    if "cursor" in harnesses:
        checks.extend(verify_cursor())

    if "codex" in harnesses:
        checks.extend(verify_codex())

    checks.extend(verify_runtime(harnesses))

    return checks


def armed_hooks(settings: dict | None = None) -> set[tuple[str, str | None, str]]:
    """The wirings actually present in the settings file, in `HOOK_WIRING`'s shape.

    Read back out of the file rather than assumed from what install last computed:
    the whole point is to catch a settings.json that has drifted from the module,
    including by an edit nothing here made.
    """
    data = _load_json(USER_SETTINGS) if settings is None else settings
    armed = set()
    for event, groups in (data.get("hooks") or {}).items():
        for group in groups:
            matcher = group.get("matcher")
            for hook in group.get("hooks") or []:
                command = hook.get("command") or ""
                script = command.rsplit("/", 1)[-1].strip('"')
                if script:
                    armed.add((event, matcher or None, script))
    return armed


def verify_armed() -> Check:
    """Every declared wiring is actually armed in the settings file.

    The gap this closes is one that corrupted a real measurement. `room-guard.sh`
    was declared in `HOOK_WIRING` and absent from `~/.claude/settings.json`, so it
    had never once run — and because `eval/rooms.py` builds a room's realized edges
    exclusively from the rows that guard writes, every real room read as
    *"TREATMENT DID NOT OCCUR — a set of solo sessions wearing a room label"*. The
    manipulation check was reporting on the hook's installation, not on the room.

    Nothing caught it, and that is the structural part: `verify()` already checked
    that each wired script **exists** and is **executable**, which `room-guard.sh`
    both was. A hook that is present, runnable, and unwired passes every check
    written about the filesystem and fires for nothing. Declared-versus-armed is a
    different question from present-versus-absent, and only the second was asked.

    Reported rather than repaired, and fatal rather than advisory. `advisory` is for
    the environment — a graph that is not up, another vendor's binary that is not
    installed — and a settings file holding some of our declared wirings and not the
    rest is not the environment: it is this install, present and wrong, which is the
    one state `--check` exists to fail on. Advisory would leave the signal wired to
    nothing that enforces it, and a run with no human reading the output (CI) would
    pass with a hook firing for nothing, which is the shape of the bug above. Failing
    costs nothing else: `verify()` runs and prints every check regardless of this
    one's verdict, and the detail names `thalamus init`, the command that writes the
    block that fixes it.

    *None* of them armed is a different fact from *some* of them missing, and it is
    the one a pre-install check finds: nothing has drifted, nothing has been written
    yet. Listing every wiring at someone who has not installed is a wall of text
    about a machine that is fine.
    """
    declared = {(event, matcher, script) for event, matcher, script in HOOK_WIRING}
    missing = sorted(declared - armed_hooks())
    if not missing:
        return Check("declared hooks armed",
                     True, f"all {len(declared)} wirings present in {USER_SETTINGS}")
    if len(missing) == len(declared):
        return Check(
            "declared hooks armed", False,
            f"none of the {len(declared)} wirings are in {USER_SETTINGS} yet — "
            "`thalamus init` writes them",
            pending=True,
        )
    named = ", ".join(
        f"{script} on {event}" + (f"/{matcher}" if matcher else "")
        for event, matcher, script in missing
    )
    return Check(
        "declared hooks armed", False,
        f"{len(missing)} of {len(declared)} declared wirings are NOT in "
        f"{USER_SETTINGS}: {named} — these fire for nothing, and a hook that "
        "writes an eval ledger silently zeroes it. Run `thalamus init` to arm them",
    )


def relaunch_checks(env_drift: list[str]) -> list[Check]:
    """Raise the per-process relaunch to a finding when the MCP env actually moved.

    The standing "arm per process" line at the end of an install is wallpaper: it
    prints on every run, including the many where nothing changed, so it stops being
    read. What it fails to catch is the case that costs data — the server's *env*
    changing while sessions are open. Those sessions keep the old config for their
    whole lifetime, and nothing about their behaviour looks wrong: a withholding rate
    that moved mid-campaign produces records at two rates with the operator believing
    it ran at one (the withholding study needs the rate to be a property of the
    machine for the campaign's duration, which is exactly what a stale process
    breaks).

    Advisory, not a failure: the install *is* wired correctly. What is not yet true
    is that anything is running it, which is the shape `advisory` already carries.
    """
    if not env_drift:
        return []
    return [Check(
        "MCP env changed — relaunch required",
        ok=False,
        detail=(
            f"{'; '.join(env_drift)}. This arms per *process*: every session already "
            "open keeps the OLD config until the editor is relaunched, and `/clear` is "
            "not enough. Records written by those sessions carry the old env."
        ),
        advisory=True,
    )]


def install(dry_run: bool = False,
            harnesses: tuple[str, ...] = HARNESSES) -> tuple[list[str], list[Check]]:
    """Install at user scope; strip the project-scope duplicate. Idempotent.

    Every harness by default: the hook scripts, the MCP server and the graph behind
    them are one installation, and a box that has only one of the three editors simply
    ends up with an inert config file for the others.

    Returns (actions, checks). Verification runs last and always, because an
    install that reports success without exercising anything is precisely the
    silent misconfiguration this module exists to prevent.
    """
    actions: list[str] = []

    if "cursor" in harnesses:
        actions.extend(install_cursor(dry_run=dry_run))
    if "codex" in harnesses:
        actions.extend(install_codex(dry_run=dry_run))
    if "claude" not in harnesses:
        if not dry_run:
            write_all_agents(USER_AGENTS_DIR)
            actions.append(f"regenerated derived agents in {USER_AGENTS_DIR}")
        actions.extend(link_skills(dry_run=dry_run))
        return actions, verify(harnesses)

    user_settings = _load_json(USER_SETTINGS)
    desired_hooks = build_hook_block()
    current = _strip_thalamus_hooks(json.loads(json.dumps(user_settings)))
    merged = json.loads(json.dumps(current))
    merged.setdefault("hooks", {})
    for event, groups in desired_hooks.items():
        merged["hooks"].setdefault(event, []).extend(groups)

    if user_settings.get("hooks") == merged.get("hooks"):
        actions.append(f"user hooks already current ({USER_SETTINGS})")
    else:
        actions.append(f"{'would write' if dry_run else 'wrote'} hooks to {USER_SETTINGS}")
        if not dry_run:
            _write_json(USER_SETTINGS, merged)

    # Captured *before* re-registering: `register_mcp` is remove-then-add, so after
    # it runs there is nothing left to compare against.
    env_before = {} if dry_run else registered_mcp_env()
    actions.append(register_mcp(dry_run=dry_run))
    # A dry run changes nothing, so no session is stale and there is nothing to
    # relaunch for; drift is only meaningful once the registration has moved.
    env_drift = [] if dry_run else mcp_env_drift(env_before, build_mcp_entry()["env"])

    # Mutual exclusion: with hooks at user scope, the project block would be a
    # second definition whose command string differs, so dedup would not collapse
    # it. Removing it keeps the merge-vs-override question off the critical path.
    project = _load_json(PROJECT_SETTINGS)
    if project.get("hooks"):
        stripped = _strip_thalamus_hooks(json.loads(json.dumps(project)))
        if stripped != project:
            actions.append(
                f"{'would strip' if dry_run else 'stripped'} project-scope Thalamus hooks "
                f"({PROJECT_SETTINGS}) — user scope is now the single definition")
            if not dry_run:
                _write_json(PROJECT_SETTINGS, stripped)
    else:
        actions.append("project-scope hook block already absent")

    # Same argument for the MCP server: a project `.mcp.json` naming `thalamus`
    # and a user-scope server of the same name are two definitions, and the docs
    # do not say which wins. Its `uv run` is cwd-relative anyway, so it is the
    # broken one — remove the whole file if it holds nothing else.
    project_mcp = _load_json(PROJECT_MCP)
    if "thalamus" in project_mcp.get("mcpServers", {}):
        remaining = {k: v for k, v in project_mcp["mcpServers"].items() if k != "thalamus"}
        actions.append(
            f"{'would remove' if dry_run else 'removed'} project-scope `thalamus` MCP server "
            f"({PROJECT_MCP}) — user scope is now the single definition")
        if not dry_run:
            if remaining:
                project_mcp["mcpServers"] = remaining
                _write_json(PROJECT_MCP, project_mcp)
            else:
                PROJECT_MCP.unlink()
    else:
        actions.append("project-scope MCP server already absent")

    actions.extend(link_skills(dry_run=dry_run))

    if not dry_run:
        write_all_agents(USER_AGENTS_DIR)
        actions.append(f"regenerated derived agents in {USER_AGENTS_DIR}")

    return actions, verify(harnesses) + relaunch_checks(env_drift)


def _confirm() -> bool:
    """Name the blast radius, then ask. Declining is the default on anything odd.

    This writes outside the checkout — into files two editors read in *every*
    directory on the box, not just this one — and the hooks it registers run on
    every session from then on. That is a reasonable thing to want and an
    unreasonable thing to discover afterwards, so it is stated before it happens
    rather than described in a README the installer never opened.

    A non-interactive stdin answers no: a script that meant to install can pass
    `--yes`, and one that did not mean to should not be silently taken as
    consenting. `--dry-run` shows the same actions without reaching this at all.
    """
    print("`thalamus init` writes outside this checkout:")
    for line in (
        f"{USER_SETTINGS} — registers {len(HOOK_WIRING)} hook entries",
        f"{USER_CURSOR_HOOKS} and {USER_CURSOR_MCP} — the same for Cursor",
        f"{USER_CODEX_HOOKS} — registers {len(CODEX_HOOK_WIRING)} hook entries for codex",
        f"{USER_CODEX_MCP} — registers the `thalamus` MCP server (via `codex mcp add`)",
        "~/.claude.json — registers the `thalamus` MCP server (via `claude mcp add`)",
        f"{USER_SKILLS_DIR} — symlinks the shipped skills",
        f"{USER_AGENTS_DIR} — writes one derived agent per expert",
        f"{CODEX_HOME} — writes one derived codex profile per expert",
    ):
        print(f"  - {line}")
    print("\nThose hooks then run in every session on this box, in every directory,\n"
          "until you remove them with `thalamus init --uninstall`.\n"
          "Your graph and transcript archive are not touched by either.\n")
    try:
        if not sys.stdin.isatty():
            print("stdin is not a terminal — re-run with --yes to install non-interactively.")
            return False
        return input("Proceed? [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def uninstall(dry_run: bool = False) -> list[str]:
    """Take back everything `install` wrote outside the checkout.

    The mirror of `install`, and it removes only what we can prove is ours: hook
    entries are dropped by the same `_strip_*` helpers the install uses to avoid
    duplicating itself, a skill link is removed only when it is a symlink
    resolving into this package's skill dir, and the MCP server goes out through
    `claude mcp remove` for the same reason it went in that way — `~/.claude.json`
    belongs to the CLI.

    What it deliberately does not touch: the graph, `~/.thalamus/` and the
    transcript archive. Uninstalling the harness is a statement about wiring, not
    a request to delete an operator's memory — and a command that quietly took
    the archive with it could not be undone.
    """
    actions: list[str] = []

    for path, strip, label in (
        (USER_SETTINGS, _strip_thalamus_hooks, "Claude Code user hooks"),
        (USER_CURSOR_HOOKS, _strip_cursor_hooks, "Cursor user hooks"),
        # Codex's file takes the Claude Code stripper because it is the Claude Code
        # schema. There is no project-scope leg to mirror: `$CODEX_HOME/hooks.json` is
        # the only file codex loads hooks from.
        (USER_CODEX_HOOKS, _strip_thalamus_hooks, "codex user hooks"),
    ):
        current = _load_json(path)
        stripped = strip(json.loads(json.dumps(current)))
        if stripped == current:
            actions.append(f"no {label} to remove ({path})")
            continue
        actions.append(f"{'would remove' if dry_run else 'removed'} {label} ({path})")
        if not dry_run:
            _write_json(path, stripped)

    actions.append(deregister_mcp(dry_run=dry_run))
    actions.append(deregister_codex_mcp(dry_run=dry_run))

    # The hook-trust records in `$CODEX_HOME/config.toml` are deliberately left where
    # they are. They are codex's own state about a decision the operator made, the
    # file is codex's to write, and a stale record is inert once the hooks it names
    # are gone — while a partial edit of that file would take the per-project
    # `trust_level` records with it.

    cursor_mcp = _load_json(USER_CURSOR_MCP)
    if "thalamus" in cursor_mcp.get("mcpServers", {}):
        actions.append(f"{'would remove' if dry_run else 'removed'} `thalamus` from "
                       f"cursor MCP servers ({USER_CURSOR_MCP})")
        if not dry_run:
            cursor_mcp["mcpServers"].pop("thalamus")
            _write_json(USER_CURSOR_MCP, cursor_mcp)
    else:
        actions.append(f"no cursor MCP server to remove ({USER_CURSOR_MCP})")

    # Only our own symlinks — links pointing into this checkout's skill dir, which
    # covers the ones whose skill has since been renamed away. A hand-written skill
    # that happens to share a name points elsewhere and is left alone.
    removed = []
    for dest in installed_skill_links():
        removed.append(dest.name)
        if not dry_run:
            dest.unlink()
    actions.append(f"{'would unlink' if dry_run else 'unlinked'} {len(removed)} skill(s) from "
                   f"{USER_SKILLS_DIR}: {', '.join(removed)}" if removed
                   else f"no skill links of ours in {USER_SKILLS_DIR}")

    agents = sorted(USER_AGENTS_DIR.glob("thalamus-*.md")) if USER_AGENTS_DIR.is_dir() else []
    if agents:
        actions.append(f"{'would remove' if dry_run else 'removed'} {len(agents)} derived "
                       f"agent(s) from {USER_AGENTS_DIR}")
        if not dry_run:
            for a in agents:
                a.unlink()
    else:
        actions.append(f"no derived agents in {USER_AGENTS_DIR}")

    # Matched to the generator's own name, not to `*.config.toml`: the operator's own
    # profiles live in the same directory under names of their choosing, and a glob
    # wide enough to catch those would make uninstall destructive.
    profiles = (sorted(CODEX_HOME.glob("thalamus-*.config.toml"))
                if CODEX_HOME.is_dir() else [])
    if profiles:
        actions.append(f"{'would remove' if dry_run else 'removed'} {len(profiles)} derived "
                       f"codex profile(s) from {CODEX_HOME}")
        if not dry_run:
            for profile in profiles:
                profile.unlink()
    else:
        actions.append(f"no derived codex profiles in {CODEX_HOME}")

    return actions


def run(dry_run: bool = False, check_only: bool = False,
        harness: str = ALL_HARNESSES, uninstall_mode: bool = False,
        assume_yes: bool = False) -> int:
    """CLI entry. Non-zero exit iff a check failed — install failures must be loud.

    "Failed" is narrower than "not ok". A pending finding is the uninstalled state
    (`Check.pending`) and an advisory is the environment, and neither is the harness
    arming wrongly; only a present-and-broken install exits 1. `--dry-run` prints its
    closing line whatever the checks said, because the one thing it promises is that
    nothing was written, and that is most worth saying on the run that found faults.
    """
    if uninstall_mode:
        for a in uninstall(dry_run=dry_run):
            print(f"  - {a}")
        print("\nDRY RUN — nothing removed." if dry_run else
              "\nRemoved. Your graph, ~/.thalamus/ and the transcript archive are untouched.\n"
              "Sessions already open keep the old wiring until the editor is relaunched.")
        return 0

    if not (dry_run or check_only or assume_yes) and not _confirm():
        print("Nothing written.")
        return 1

    harnesses = HARNESSES if harness == ALL_HARNESSES else (harness,)
    if check_only:
        actions, checks = [], verify(harnesses)
    else:
        actions, checks = install(dry_run=dry_run, harnesses=harnesses)

    if actions:
        print("Actions:")
        for a in actions:
            print(f"  - {a}")
    print("\nVerification (exercised, not assumed):")
    for c in checks:
        print(c.render())

    pending = [c for c in checks if c.pending and not c.ok]
    if pending:
        print(f"\n{len(pending)} item(s) are NOT INSTALLED YET. This is what an "
              "uninstalled machine looks like, not a broken one:")
        for c in pending:
            print(f"  ○ {c.name}: {c.detail}")
        print("Run `thalamus init` to install them.")

    advisories = [c for c in checks if c.advisory and not c.ok and not c.blocked]
    if advisories:
        print(f"\n{len(advisories)} advisory finding(s) — the install is wired, "
              "but these must be true before it does anything:")
        for c in advisories:
            print(f"  ! {c.name}: {c.detail}")

    blocked = [c for c in checks if c.blocked and not c.ok]
    if blocked:
        print(f"\n{len(blocked)} check(s) COULD NOT RUN — something they need is "
              "not on this machine, so their answer is unknown rather than bad:")
        for c in blocked:
            print(f"  ? {c.name}: {c.detail}")

    failed = [c for c in checks
              if not c.ok and not c.advisory and not c.pending and not c.blocked]
    if failed:
        print(f"\n{len(failed)} check(s) FAILED — the harness will not arm correctly.")

    if dry_run:
        print("\nDRY RUN — nothing written. Re-run without --dry-run to install.")
        return 1 if failed else 0
    if failed:
        return 1
    if not check_only:
        editors = " and ".join(EDITOR_NAMES.get(h, h) for h in harnesses)
        print(f"\nInstalled for {editors}. Hooks and the MCP server arm per *process*: "
              "every session already open keeps the old config until the editor is "
              "relaunched, and `/clear` is not enough.")
        if "cursor" in harnesses:
            print("Cursor: discovery reads the sessionEnd hook log, not the filesystem "
                  "(cursor_transcripts.discover), so sessions that ran on this box before "
                  "now will never be distilled — only ones ending from here on.")
        if "codex" in harnesses:
            # Two gates stand between a correct install and a codex session that
            # actually distills, and both are the operator's to clear. Neither is
            # written here: trusting a directory and trusting a hook are consent
            # decisions, and an installer that granted them for you would be routing
            # around the control rather than satisfying it.
            print("codex: the next `codex` you launch asks you to review these hooks "
                  "(`Trust all and continue`). Choosing to continue without trusting "
                  "leaves them installed and silent — a headless run then exits 0, "
                  "says nothing, and distills nothing. A directory codex has not seen "
                  "asks separately, before that, and the answer is remembered against "
                  "the repository root.")
    return 0
