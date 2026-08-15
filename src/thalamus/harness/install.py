"""Install the Thalamus harness so it arms in any working directory.

The problem this solves: the harness was wired for sessions opened *inside* the
checkout. `.claude/settings.json` reaches its hook scripts through
`$CLAUDE_PROJECT_DIR`, and `.mcp.json` starts the server with a cwd-relative
`uv run`. Both name the session's *working* project, which is a different repo
whenever a session is opened elsewhere (`thalamus spawn --dir`) — so the hooks
silently no-op and the MCP server never starts. Memory is supposed to span
projects (docs/02); the install is what makes that true in practice.

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
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from thalamus.harness import agents
from thalamus.harness.agents import HARNESSES as AGENT_HARNESSES
from thalamus.harness.pin import PROJECT_ROOT, USER_AGENTS_DIR, write_all_agents

USER_SETTINGS = Path.home() / ".claude" / "settings.json"
PROJECT_SETTINGS = PROJECT_ROOT / ".claude" / "settings.json"
PROJECT_MCP = PROJECT_ROOT / ".mcp.json"

HOOK_DIR = PROJECT_ROOT / "src" / "thalamus" / "harness" / "hooks" / "claude-code"
SKILL_DIR = PROJECT_ROOT / "src" / "thalamus" / "harness" / "skills"
USER_SKILLS_DIR = Path.home() / ".claude" / "skills"

CURSOR_HOOK_DIR = PROJECT_ROOT / "src" / "thalamus" / "harness" / "hooks" / "cursor"
USER_CURSOR_HOOKS = Path.home() / ".cursor" / "hooks.json"
USER_CURSOR_MCP = Path.home() / ".cursor" / "mcp.json"
PROJECT_CURSOR_HOOKS = PROJECT_ROOT / ".cursor" / "hooks.json"
PROJECT_CURSOR_MCP = PROJECT_ROOT / ".cursor" / "mcp.json"

# One list, so a third harness cannot arrive in the agent registry and be
# silently uninstallable.
HARNESSES = AGENT_HARNESSES

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
    ("PreToolUse", "Edit|Write|NotebookEdit|Skill|Artifact", "role-guard.sh"),
    ("PostToolUse", "mcp__thalamus__.*", "post-tool-use.sh"),
    ("PostToolUse", "Bash", "gremlin-tap.sh"),
    ("PostToolUse", "TaskCreate", "conditioning.sh"),
    ("PostToolUse", "mcp__thalamus__memory_query", "conditioning.sh"),
    ("PostToolUse", "mcp__thalamus__memory_query", "recipe-stage.sh"),
    ("PostToolUse", "Bash", "recipe-stage.sh"),
]

# The Cursor wiring, as (event, script). Event names and their I/O shapes were
# re-verified against cursor.com/docs/hooks.md on 2026-07-29 (lab/027).
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
# which is the drift this tier exists to prevent (lab/054). It stays wired
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
# both members of its pair too (lab/061). The generic events are not exclusive with
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


@dataclass(frozen=True)
class HookParity:
    """What the two wirings above are believed to add up to — the tables, only.

    Written as data so it can be re-derived and disagreed with. The same claim as a
    comment was wrong for three scripts and no test could notice, because a comment
    is not compared to anything.

    It is not circular to pin a hand-written expectation beside the tables it
    describes and then recompute it: the derivation reads `HOOK_WIRING` and
    `CURSOR_HOOK_WIRING`, this record does not, so adding a script to either table
    moves one and not the other. That divergence is precisely the event that went
    unnoticed before.

    **The subject is the wiring, never the obligation.** This record cannot say
    whether a boundary binds, and a reader who takes it for that gets a false answer
    in both directions: it over-reported gaps until `renames` was added, and it
    under-reported enforcement until `native` was, because a script absent from both
    tables can still be running through the vendor's own compatibility path.
    `contract/boundaries.py` is the record that speaks about obligations.
    """

    claude_scripts: int
    cursor_scripts: int
    shared: int
    claude_only: tuple[str, ...]
    cursor_only: tuple[str, ...]
    # A name-set difference cannot tell a rename from a gap — the two are the same
    # shape — so the renames are named. Without this, `post-tool-use.sh` reads as a
    # missing MCP tap on Cursor when `mcp-tap.sh` is doing that job under a different
    # filename, which is a capability the adapter *has* being reported as one it lacks.
    renames: tuple[tuple[str, str], ...]
    # Scripts wired for Claude Code only *on purpose*, because Cursor already runs
    # them: it translates `~/.claude/settings.json` into its own event names, so a
    # second registration under `.cursor/` would run the same guard twice on one
    # call. Absence from `CURSOR_HOOK_WIRING` is the decision here, not the gap —
    # and without this field the two are the same shape, exactly as a rename was.
    native: tuple[str, ...] = ()

    @property
    def real_gaps(self) -> tuple[str, ...]:
        """Claude-only scripts with no Cursor path, renames and natives excluded.

        A name lands here by *default*, so this is a floor on the gaps and not a
        measurement of them: a script nobody has probed on Cursor is indistinguishable
        from one probed and found missing. `role-guard.sh` sat here for a release
        while it was in fact binding.
        """
        accounted = {claude_name for claude_name, _ in self.renames} | set(self.native)
        return tuple(name for name in self.claude_only if name not in accounted)


DECLARED_HOOK_PARITY = HookParity(
    claude_scripts=13,
    cursor_scripts=14,
    shared=9,
    claude_only=("post-tool-use.sh", "recipe-stage.sh", "role-guard.sh", "room-guard.sh"),
    cursor_only=(
        "distill.sh", "inject.sh", "mcp-tap.sh",
        # Cursor-only because Claude Code needs no bracket: its harness writes `status`
        # into the session descriptor from inside its own event loop, so readiness there
        # is a first-party signal already. These two exist to give Cursor the same
        # answer, not a better one.
        "readiness-pending.sh", "readiness-ready.sh",
    ),
    renames=(("post-tool-use.sh", "mcp-tap.sh"),),
    native=("role-guard.sh",),
)


def derive_hook_parity() -> dict:
    """Recompute the parity claim from the wirings themselves."""
    claude = {script for _, _, script in HOOK_WIRING}
    cursor = {script for _, script in CURSOR_HOOK_WIRING}
    return {
        "claude_scripts": len(claude),
        "cursor_scripts": len(cursor),
        "shared": len(claude & cursor),
        "claude_only": tuple(sorted(claude - cursor)),
        "cursor_only": tuple(sorted(cursor - claude)),
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
    """
    name: str
    ok: bool
    detail: str
    advisory: bool = False

    def render(self) -> str:
        mark = "✓" if self.ok else ("!" if self.advisory else "✗")
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


def build_hook_block() -> dict:
    """The hook block with absolute paths — no $CLAUDE_PROJECT_DIR anywhere.

    Grouped by (event, matcher) so several scripts on one event share a group,
    matching the shape Claude Code's settings schema expects.
    """
    block: dict = {}
    for event, matcher, script in HOOK_WIRING:
        entry = {"type": "command", "command": str(HOOK_DIR / script)}
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
    that pooled two rates is detectable rather than invisible (experiments/003).
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
    retires a consent problem lab/010 flagged: a committed `.cursor/hooks.json`
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

    reachable, detail = _probe_graph(url)
    if not reachable:
        detail = (
            f"{detail} — start it with `docker compose up -d` in {PROJECT_ROOT}, "
            "then re-run `thalamus init --check`"
        )
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
            f"`--harness {'cursor' if harness == 'claude' else 'claude'}`)",
            advisory=True,
        ))

    return checks


def _probe_graph(url: str) -> tuple[bool, str]:
    """Reachable, and answering? Exercised the real way, but bounded.

    Two stages because they fail differently and only one of them can hang: a
    closed port is settled by a 2s TCP connect, and only once something is
    listening is a real traversal worth attempting. The traversal runs in a
    subprocess so a peer that accepts the connection and then never completes the
    websocket handshake costs a timeout rather than a wedged install.

    A graph with zero vertices is a **pass**: every install is fresh, the graph is
    private to its operator and is never shipped, so an empty one is the normal
    starting state rather than a fault.
    """
    host, port = _split_ws(url)
    if host is None:
        return False, f"could not parse a host:port out of {url}"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(2.0)
        if probe.connect_ex((host, port)) != 0:
            return False, f"nothing listening on {host}:{port}"

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
        return False, f"{host}:{port} accepted a connection but did not answer ({exc})"

    if proc.returncode != 0:
        return False, f"{host}:{port} refused the query: {proc.stderr.strip()[-160:]}"

    count = proc.stdout.strip()
    fresh = " (fresh — every install starts empty)" if count == "0" else ""
    return True, f"{count} vertices at {url}{fresh}"


def _split_ws(url: str) -> tuple[str | None, int]:
    """host/port out of ws://host:port/path, without importing a URL parser."""
    rest = url.split("://", 1)[-1].split("/", 1)[0]
    host, _, port = rest.partition(":")
    if not host:
        return None, 0
    try:
        return host, int(port or 8182)
    except ValueError:
        return None, 0


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

    wired = _load_json(USER_CURSOR_HOOKS)
    commands = {e.get("command") for entries in wired.get("hooks", {}).values() for e in entries}
    unwired = [s for s in scripts if str(CURSOR_HOOK_DIR / s) not in commands]
    checks.append(Check("cursor hooks wired at user scope", not unwired and wired.get("version") == 1,
                        f"{len(scripts)} scripts in {USER_CURSOR_HOOKS}" if not unwired
                        else f"not wired: {unwired}"))

    served = _load_json(USER_CURSOR_MCP).get("mcpServers", {}).get("thalamus")
    checks.append(Check("cursor MCP server registered", served == build_mcp_entry(),
                        f"`thalamus` in {USER_CURSOR_MCP}" if served
                        else f"absent from {USER_CURSOR_MCP} — no retrieval on Cursor"))

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
        detail = "skipped (jq or inject.sh missing)"
    checks.append(Check("cursor deferred injection round trip", ok, detail))

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
                        f"{len(agents)} in {USER_AGENTS_DIR}" if agents else "none written"))

    # Read each skill *through* its user-scope path, the way a session outside
    # the checkout will. A symlink that exists can still dangle, and a dangling
    # one is invisible until a design goes ungrounded — so resolve it and read
    # the frontmatter rather than calling `.exists()` and believing it.
    unreadable = []
    for src in shipped_skills():
        dest = USER_SKILLS_DIR / src.name
        try:
            if "name:" not in (dest / "SKILL.md").read_text()[:400]:
                unreadable.append(f"{src.name} (no frontmatter)")
        except OSError as exc:
            unreadable.append(f"{src.name} ({exc.strerror or exc})")
    checks.append(Check(
        "skills load at user scope", not unreadable,
        f"{len(shipped_skills())} readable via {USER_SKILLS_DIR}" if not unreadable
        else f"unreadable: {unreadable}"))

    if "claude" in harnesses:
        checks.append(verify_armed())

    if "cursor" in harnesses:
        checks.extend(verify_cursor())

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

    Reported rather than repaired, and advisory rather than fatal: `thalamus init`
    without `--check` writes the block that fixes it, so the finding names that
    command. A stale settings file is not a reason to refuse to verify the rest.
    """
    declared = {(event, matcher, script) for event, matcher, script in HOOK_WIRING}
    missing = sorted(declared - armed_hooks())
    if not missing:
        return Check("declared hooks armed",
                     True, f"all {len(declared)} wirings present in {USER_SETTINGS}")
    named = ", ".join(
        f"{script} on {event}" + (f"/{matcher}" if matcher else "")
        for event, matcher, script in missing
    )
    return Check(
        "declared hooks armed", False,
        f"{len(missing)} of {len(declared)} declared wirings are NOT in "
        f"{USER_SETTINGS}: {named} — these fire for nothing, and a hook that "
        "writes an eval ledger silently zeroes it. Run `thalamus init` to arm them",
        advisory=True,
    )


def relaunch_checks(env_drift: list[str]) -> list[Check]:
    """Raise the per-process relaunch to a finding when the MCP env actually moved.

    The standing "arm per process" line at the end of an install is wallpaper: it
    prints on every run, including the many where nothing changed, so it stops being
    read. What it fails to catch is the case that costs data — the server's *env*
    changing while sessions are open. Those sessions keep the old config for their
    whole lifetime, and nothing about their behaviour looks wrong: a withholding rate
    that moved mid-campaign produces records at two rates with the operator believing
    it ran at one (experiments/003 needs the rate to be a property of the machine for
    the campaign's duration, which is exactly what a stale process breaks).

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

    Both harnesses by default: the hook scripts, the MCP server and the graph
    behind them are one installation, and a box that has only one of the two
    editors simply ends up with an inert config file for the other.

    Returns (actions, checks). Verification runs last and always, because an
    install that reports success without exercising anything is precisely the
    silent misconfiguration this module exists to prevent.
    """
    actions: list[str] = []

    if "cursor" in harnesses:
        actions.extend(install_cursor(dry_run=dry_run))
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
        "~/.claude.json — registers the `thalamus` MCP server (via `claude mcp add`)",
        f"{USER_SKILLS_DIR} — symlinks the shipped skills",
        f"{USER_AGENTS_DIR} — writes one derived agent per expert",
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

    cursor_mcp = _load_json(USER_CURSOR_MCP)
    if "thalamus" in cursor_mcp.get("mcpServers", {}):
        actions.append(f"{'would remove' if dry_run else 'removed'} `thalamus` from "
                       f"cursor MCP servers ({USER_CURSOR_MCP})")
        if not dry_run:
            cursor_mcp["mcpServers"].pop("thalamus")
            _write_json(USER_CURSOR_MCP, cursor_mcp)
    else:
        actions.append(f"no cursor MCP server to remove ({USER_CURSOR_MCP})")

    # Only our own symlinks: the same identity test link_skills uses to decide it
    # may write. A hand-written skill that happens to share a name is left alone.
    ours = {s.resolve() for s in shipped_skills()}
    removed = []
    for dest in sorted(USER_SKILLS_DIR.glob("*")) if USER_SKILLS_DIR.is_dir() else []:
        if dest.is_symlink() and dest.resolve() in ours:
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

    return actions


def run(dry_run: bool = False, check_only: bool = False,
        harness: str = "both", uninstall_mode: bool = False,
        assume_yes: bool = False) -> int:
    """CLI entry. Non-zero exit iff a check failed — install failures must be loud."""
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

    harnesses = HARNESSES if harness == "both" else (harness,)
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

    advisories = [c for c in checks if c.advisory and not c.ok]
    if advisories:
        print(f"\n{len(advisories)} advisory finding(s) — the install is wired, "
              "but these must be true before it does anything:")
        for c in advisories:
            print(f"  ! {c.name}: {c.detail}")

    failed = [c for c in checks if not c.ok and not c.advisory]
    if failed:
        print(f"\n{len(failed)} check(s) FAILED — the harness will not arm correctly.")
        return 1
    if dry_run:
        print("\nDRY RUN — nothing written. Re-run without --dry-run to install.")
    elif not check_only:
        editors = " and ".join("Claude Code" if h == "claude" else "Cursor" for h in harnesses)
        print(f"\nInstalled for {editors}. Hooks and the MCP server arm per *process*: "
              "every session already open keeps the old config until the editor is "
              "relaunched, and `/clear` is not enough.")
        if "cursor" in harnesses:
            print("Cursor: discovery reads the sessionEnd hook log, not the filesystem "
                  "(cursor_transcripts.discover), so sessions that ran on this box before "
                  "now will never be distilled — only ones ending from here on (lab/054).")
    return 0
