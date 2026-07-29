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
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from thalamus.harness.pin import PROJECT_ROOT, USER_AGENTS_DIR, write_all_agents

USER_SETTINGS = Path.home() / ".claude" / "settings.json"
PROJECT_SETTINGS = PROJECT_ROOT / ".claude" / "settings.json"
PROJECT_MCP = PROJECT_ROOT / ".mcp.json"

HOOK_DIR = PROJECT_ROOT / "src" / "thalamus" / "harness" / "hooks" / "claude-code"

# The hook wiring, as (event, matcher, script). Matcher None = all tools.
HOOK_WIRING: list[tuple[str, str | None, str]] = [
    ("SessionStart", None, "session-start.sh"),
    ("SessionEnd", None, "session-end.sh"),
    ("UserPromptSubmit", None, "timestamp.sh"),
    ("UserPromptSubmit", None, "conditioning.sh"),
    ("UserPromptSubmit", None, "pin-engaged.sh"),
    ("PreToolUse", "Bash", "gremlin-guard.sh"),
    ("PostToolUse", "mcp__thalamus__.*", "post-tool-use.sh"),
    ("PostToolUse", "Bash", "gremlin-tap.sh"),
    ("PostToolUse", "TaskCreate", "conditioning.sh"),
]


@dataclass
class Check:
    """One verification result. `ok=False` is a refusal to claim an install works."""
    name: str
    ok: bool
    detail: str

    def render(self) -> str:
        return f"  {'✓' if self.ok else '✗'} {self.name}: {self.detail}"


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
    """
    return {
        "command": "uv",
        "args": ["run", "--project", str(PROJECT_ROOT), "thalamus-mcp"],
        "env": {"THALAMUS_GRAPH_URL": os.environ.get(
            "THALAMUS_GRAPH_URL", "ws://localhost:8182/gremlin")},
    }


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
    add_cmd = [cli, "mcp", "add", "--scope", "user", "thalamus",
               "-e", f"THALAMUS_GRAPH_URL={entry['env']['THALAMUS_GRAPH_URL']}",
               "--", entry["command"], *entry["args"]]
    if dry_run:
        return f"would register `thalamus` MCP server at user scope: {' '.join(add_cmd[1:])}"

    subprocess.run([cli, "mcp", "remove", "--scope", "user", "thalamus"],
                   capture_output=True, text=True, timeout=60)
    proc = subprocess.run(add_cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return f"MCP registration FAILED: {(proc.stderr or proc.stdout).strip()[:300]}"
    return "registered `thalamus` MCP server at user scope (via `claude mcp add`)"


def verify() -> list[Check]:
    """Exercise what would otherwise fail late (PCheck's early-detection idea).

    Each check runs the *real* mechanism, not a proxy for it: the point is that
    a path which merely exists can still be unrunnable, and a `uv` project that
    resolves from one cwd can fail from another.
    """
    checks: list[Check] = []

    missing = [s for _, _, s in HOOK_WIRING if not (HOOK_DIR / s).is_file()]
    checks.append(Check("hook scripts present", not missing,
                        "all 9 wired scripts found" if not missing else f"missing: {missing}"))

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

    return checks


def install(dry_run: bool = False) -> tuple[list[str], list[Check]]:
    """Install at user scope; strip the project-scope duplicate. Idempotent.

    Returns (actions, checks). Verification runs last and always, because an
    install that reports success without exercising anything is precisely the
    silent misconfiguration this module exists to prevent.
    """
    actions: list[str] = []

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

    actions.append(register_mcp(dry_run=dry_run))

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

    if not dry_run:
        write_all_agents(USER_AGENTS_DIR)
        actions.append(f"regenerated derived agents in {USER_AGENTS_DIR}")

    return actions, verify()


def run(dry_run: bool = False, check_only: bool = False) -> int:
    """CLI entry. Non-zero exit iff a check failed — install failures must be loud."""
    if check_only:
        actions, checks = [], verify()
    else:
        actions, checks = install(dry_run=dry_run)

    if actions:
        print("Actions:")
        for a in actions:
            print(f"  - {a}")
    print("\nVerification (exercised, not assumed):")
    for c in checks:
        print(c.render())

    failed = [c for c in checks if not c.ok]
    if failed:
        print(f"\n{len(failed)} check(s) FAILED — the harness will not arm correctly.")
        return 1
    if dry_run:
        print("\nDRY RUN — nothing written. Re-run without --dry-run to install.")
    elif not check_only:
        print("\nInstalled. Hooks and the MCP server arm per *process*: "
              "relaunch `claude` for existing sessions to pick this up.")
    return 0
