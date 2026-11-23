"""Session preflight — is this process armed the way its pin and its job promise?

A mis-armed session looks exactly like an armed one until something it needs turns out
to be absent (#253: 2 of 43 interactive sessions in four days came up without their
MCP servers, and both ran to completion unnoticed). An autonomous session has nobody
watching it at all, so it runs to completion and distils into the graph looking like a
healthy one. This module checks, at the session's first tool call, the five things a
pin and a job promise:

- **tool surface** — every MCP server and tool required is in the process, read from
  the harness's own record of what connected (the transcript's `deferred_tools_delta`
  and `api-request-shape` records), never from the configuration meant to produce it;
- **hooks runnable** — every hook command the settings files wire resolves to a file
  that can run (a hook whose script moved fails with exit 127 on every call, and the
  harness reports that as a non-blocking error nobody reads). Advisory: it is told to an
  attended session and recorded, and stops nothing;
- **guards armed** — where the scope has a write, capability or ownership boundary to
  enforce, `role-guard.sh` is wired for the tools it bounds and, handed a synthetic
  call its boundary forbids, denies it;
- **budget** — the caps the budget hook will enforce match the preset the job names,
  and a cap in force has its hook wired;
- **write path** — the pin-ledger row distillation will read exists and resolves to the
  session type this process runs as, and to that type's tier, so a run cannot be
  recorded as attended by misconfiguration.

What a failure does depends on who is there to read it (#395, #396). An autonomous
session's preflight **aborts**: the first tool call is denied and the run is stopped,
since a warning with no operator to read it changes nothing. An attended session's
preflight **reports**, and reports before the operator has typed anything: it runs once
at session start, with every check but the tool surface (whose record the harness has
not written yet), and again at the first tool call, which adds the tool surface and
tells only what the first run did not. Each report reaches the operator on screen and
the session as context, and the operator decides. Every run is recorded, pass or fail,
at `~/.thalamus/preflight/<session_id>.json` (`<session_id>.start.json` for the
session-start run) and one line in `preflight.jsonl` beside them.

Where the checks read files rather than the process — the settings files a hook is
wired in — they read the files Claude Code loads by default, or those named by
`THALAMUS_SETTING_SOURCES` (`user,project,local`, Claude Code's own names) for a
launcher that narrowed them with `--setting-sources`. Nothing visible to a hook says
which sources the process actually loaded.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from thalamus.contract import ownership
from thalamus.contract.manifest import (
    config_root,
    load_manifest,
)
from thalamus.harness import pin
from thalamus.harness.budget import limits
from thalamus.substrate.schema import SessionType, session_type_tier

PREFLIGHT_DIR = Path.home() / ".thalamus" / "preflight"
HOOK_DIR = Path(__file__).resolve().parent / "hooks" / "claude-code"

# The tools role-guard.sh is wired for (harness/install.HOOK_WIRING). A synthetic call
# to one of these is how the guard is shown to be armed.
_ROLE_GUARD = "role-guard.sh"
_BUDGET_HOOK = "budget.sh"

# The two points a preflight runs at. The tool surface is checked only at the second:
# at session start the harness has not yet written its record of it.
SESSION_START = "session-start"
FIRST_TOOL_CALL = "first-tool-call"
_HOOK_EVENT = {SESSION_START: "SessionStart", FIRST_TOOL_CALL: "PreToolUse"}


@dataclass
class Check:
    """One check's outcome. `ok` is None when it could not be decided.

    An advisory check is reported and recorded and never fails the preflight: it finds
    something wrong with the box rather than with the promise this session was
    launched under, and stopping every unattended run on it would make one stale hook
    anywhere in the settings a stop for all of them.
    """

    name: str
    ok: bool | None
    detail: str
    advisory: bool = False


@dataclass
class Report:
    """The checks' outcomes for one session at one phase. An autonomous session fails
    on any check not shown to pass; an attended one only on a check that failed.
    (A0253, cites-as-live)"""

    session_id: str
    scope: str
    session_type: str
    checks: list[Check] = field(default_factory=list)
    phase: str = FIRST_TOOL_CALL
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def aborts(self) -> bool:
        """An autonomous session aborts on anything not shown to pass."""
        return self.session_type == SessionType.AUTONOMOUS.value

    @property
    def failures(self) -> list[Check]:
        if self.aborts:
            return [c for c in self.checks if c.ok is not True and not c.advisory]
        return [c for c in self.checks if c.ok is False and not c.advisory]

    @property
    def advisories(self) -> list[Check]:
        return [c for c in self.checks if c.advisory and c.ok is False]

    @property
    def passed(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        lines = [f"{c.name}: {c.detail}" for c in self.failures]
        return "; ".join(lines)

    def as_dict(self) -> dict:
        return {**asdict(self), "passed": self.passed, "aborts": self.aborts}


# ---------------------------------------------------------------------------
# Tool surface


@dataclass
class Surface:
    tools: set[str]
    failed_servers: set[str]
    pending_servers: set[str]


def _server_names(entries: object) -> set[str]:
    out: set[str] = set()
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, str):
            out.add(entry)
        elif isinstance(entry, dict) and entry.get("name"):
            out.add(str(entry["name"]))
    return out


def observed_surface(transcript: Path) -> Surface | None:
    """The tools this process has, from the harness's own record; None when it wrote
    none yet.

    Claude Code records the surface in two places, and either may be the only one: a
    `deferred_tools_delta` attachment lists the tools it deferred (all of them, when
    there are many — an interactive session), and an `api-request-shape` record lists
    the tools sent with a request (all of them when none were deferred — a run
    narrowed by `--tools`, which writes no delta at all). Both are written before the
    first tool call (measured on Claude Code 2.1.330, 2026-11-23). Deltas accumulate,
    and a server still connecting arrives in a later one. (A0250, cites-as-live)
    """
    try:
        handle = transcript.open(errors="ignore")
    except OSError:
        return None
    tools: set[str] = set()
    failed: set[str] = set()
    pending: set[str] = set()
    recorded = False
    with handle:
        for line in handle:
            if "deferred_tools_delta" not in line and "api-request-shape" not in line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            attachment = record.get("attachment")
            if isinstance(attachment, dict) and attachment.get("type") == "deferred_tools_delta":
                recorded = True
                tools |= set(attachment.get("addedNames") or [])
                tools |= set(attachment.get("readdedNames") or [])
                tools -= set(attachment.get("removedNames") or [])
                failed |= _server_names(attachment.get("failedMcpServers"))
                pending = _server_names(attachment.get("pendingMcpServers"))
            elif record.get("type") == "api-request-shape":
                shape = record.get("shape") or {}
                recorded = True
                for tool in shape.get("tools") or []:
                    if isinstance(tool, dict) and tool.get("name"):
                        tools.add(str(tool["name"]))
    return Surface(tools, failed, pending) if recorded else None


def _tool_prefix(server: str) -> str:
    """The prefix Claude Code gives a server's tools: `claude.ai Gmail` ->
    `mcp__claude_ai_Gmail__`."""
    return f"mcp__{re.sub(r'[^A-Za-z0-9_-]', '_', server)}__"


def required_tools(scope: str, session_type: SessionType,
                   environ: Mapping[str, str], base: Path | None = None) -> list[str]:
    """What this session must have: its scope's own MCP servers, the house `thalamus`
    server for an attended session (its session-start context directs it there), and
    whatever the launcher names in `THALAMUS_PREFLIGHT_REQUIRES` — comma-separated, each
    an MCP server name or an exact tool name."""
    required = list(pin.scope_mcp_servers(scope, base))
    if session_type is SessionType.ATTENDED:
        required.append("thalamus")
    declared = environ.get("THALAMUS_PREFLIGHT_REQUIRES", "")
    required += [item.strip() for item in declared.split(",") if item.strip()]
    return list(dict.fromkeys(required))


def check_tool_surface(transcript: Path | None, required: list[str]) -> Check:
    if not required:
        return Check("tool surface", True, "nothing required")
    surface = observed_surface(transcript) if transcript else None
    if surface is None:
        return Check("tool surface", None,
                     "the harness recorded no tool surface (no transcript, or session "
                     "persistence off), so the required tools could not be confirmed: "
                     + ", ".join(required))
    missing = []
    for item in required:
        prefix = _tool_prefix(item)
        if item in surface.tools or any(t.startswith(prefix) for t in surface.tools):
            continue
        state = (" (failed to connect)" if item in surface.failed_servers
                 else " (still connecting)" if item in surface.pending_servers else "")
        missing.append(item + state)
    if missing:
        return Check("tool surface", False, "missing " + ", ".join(missing))
    return Check("tool surface", True, f"{len(required)} required, all present")


# ---------------------------------------------------------------------------
# Settings files and the hooks they wire

SETTING_SOURCES = ("user", "project", "local")


def settings_files(environ: Mapping[str, str], project_dir: str) -> list[Path]:
    """The Claude Code settings files this process would load, by source."""
    sources = [s.strip() for s in environ.get("THALAMUS_SETTING_SOURCES", "").split(",")
               if s.strip()] or list(SETTING_SOURCES)
    user_dir = Path(environ.get("CLAUDE_CONFIG_DIR") or Path(environ.get("HOME", "~")) / ".claude")
    candidates = {
        "user": user_dir.expanduser() / "settings.json",
        "project": Path(project_dir) / ".claude" / "settings.json" if project_dir else None,
        "local": Path(project_dir) / ".claude" / "settings.local.json" if project_dir else None,
    }
    return [p for s in sources if (p := candidates.get(s)) is not None and p.is_file()]


@dataclass
class Wired:
    event: str
    matcher: str
    command: str
    source: Path


def wired_hooks(files: list[Path]) -> list[Wired]:
    out: list[Wired] = []
    for path in files:
        try:
            hooks = (json.loads(path.read_text()) or {}).get("hooks") or {}
        except (OSError, ValueError):
            continue
        for event, groups in hooks.items():
            for group in groups if isinstance(groups, list) else []:
                matcher = str(group.get("matcher") or "") if isinstance(group, dict) else ""
                for hook in (group.get("hooks") or []) if isinstance(group, dict) else []:
                    if isinstance(hook, dict) and hook.get("type") == "command":
                        out.append(Wired(event, matcher, str(hook.get("command", "")), path))
    return out


def _executable(command: str, environ: Mapping[str, str], project_dir: str) -> str | None:
    """The path a hook command runs, when its first word is one; None otherwise."""
    expanded = (command.replace("${CLAUDE_PROJECT_DIR}", project_dir)
                .replace("$CLAUDE_PROJECT_DIR", project_dir))
    try:
        words = shlex.split(expanded)
    except ValueError:
        return None
    if not words or "/" not in words[0]:
        return None
    return os.path.expanduser(words[0])


def check_hooks_runnable(wired: list[Wired], environ: Mapping[str, str],
                         project_dir: str) -> Check:
    """Each wired hook command whose script is not a runnable file, one entry per
    script with the events it is wired on and the files that wire it."""
    broken: dict[str, tuple[list[str], list[str]]] = {}
    for hook in wired:
        path = _executable(hook.command, environ, project_dir)
        if path is None:
            continue
        if not (os.path.isfile(path) and os.access(path, os.X_OK)):
            events, sources = broken.setdefault(path, ([], []))
            events.append(hook.event)
            sources.append(str(hook.source))
    if broken:
        entries = [f"{path} (on {', '.join(dict.fromkeys(events))}; wired in "
                   f"{', '.join(dict.fromkeys(sources))})"
                   for path, (events, sources) in broken.items()]
        return Check("hooks runnable", False,
                     f"{len(entries)} wired hook script(s) cannot run: " + "; ".join(entries),
                     advisory=True)
    return Check("hooks runnable", True, f"{len(wired)} wired hook(s) resolve", advisory=True)


def _matches(matcher: str, tool: str) -> bool:
    if matcher in ("", "*"):
        return True
    try:
        return re.fullmatch(matcher, tool) is not None
    except re.error:
        return False


# ---------------------------------------------------------------------------
# Guards


def _instance(glob: str) -> str:
    """A path a glob matches: each wildcard filled with a placeholder segment."""
    path = re.sub(r"\[[^\]]*\]", "x", glob).replace("*", "preflight").replace("?", "x")
    return path if path.startswith("/") else "/" + path


def forbidden_call(scope: str, base: Path | None = None) -> dict | None:
    """A tool call this scope's boundaries forbid, or None when they forbid nothing.

    Ownership first (it binds `main` too), then the write boundary, then the capability
    boundary — whichever the scope declares. The call is synthetic and never runs.
    """
    for glob, owner, _reason in ownership_rows(base):
        if owner != scope:
            return {"tool_name": "Write", "tool_input": {"file_path": _instance(glob)}}
    try:
        manifest = load_manifest(scope, base)
    except (FileNotFoundError, ValueError):
        return None
    for glob in manifest.write_boundary.deny_globs:
        path = _instance(glob)
        if manifest.write_boundary.denies(path):
            return {"tool_name": "Write", "tool_input": {"file_path": path}}
    capability = manifest.effective_capability_boundary
    for pattern in capability.deny_skills:
        skill = pattern.replace("*", "preflight")
        if capability.denies_skill(skill):
            return {"tool_name": "Skill", "tool_input": {"skill": skill}}
    for pattern in capability.deny_tools:
        # The two tool families role-guard.sh is wired for besides the editors.
        tool = pattern.replace("*", "preflight")
        if not capability.denies_tool(tool):
            continue
        if tool == "Artifact":
            return {"tool_name": tool, "tool_input": {"action": "create"}}
        if tool.startswith("mcp__penpot__"):
            return {"tool_name": tool, "tool_input": {}}
    return None


def ownership_rows(base: Path | None = None) -> list[tuple[str, str, str]]:
    """(glob, owner, reason) for each ownership row, from the config root."""
    try:
        return list(ownership.rows(config_root(base)))
    except (OSError, ValueError):
        return []


def probe_guard(script: str, scope: str, call: dict, base: Path | None = None) -> bool:
    """Whether `script`, handed `call`, denies it. Run with a scratch HOME so the
    probe leaves no row in the operator's guard log."""
    payload = {"session_id": "preflight-probe", "hook_event_name": "PreToolUse",
               "cwd": "/", **call}
    with tempfile.TemporaryDirectory(prefix="thalamus-preflight-") as home:
        env = {"HOME": home, "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "THALAMUS_SCOPE": scope, "THALAMUS_CONFIG_DIR": str(config_root(base))}
        try:
            result = subprocess.run([script], input=json.dumps(payload), env=env,
                                    capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return False
    # A PreToolUse hook blocks either way: exit 2 with the reason on stderr, which is
    # role-guard.sh's form, or a JSON `permissionDecision: deny` on stdout.
    if result.returncode == 2:
        return True
    try:
        output = json.loads(result.stdout or "{}")
    except ValueError:
        return False
    decision = (output.get("hookSpecificOutput") or {}).get("permissionDecision")
    return decision == "deny" or output.get("decision") == "block"


def check_guards(scope: str, wired: list[Wired], environ: Mapping[str, str],
                 project_dir: str, base: Path | None = None) -> Check:
    call = forbidden_call(scope, base)
    if call is None:
        return Check("guards armed", True, f"scope `{scope}` declares no boundary to enforce")
    tool = call["tool_name"]
    guards = [w for w in wired if w.event == "PreToolUse"
              and w.command.rstrip().endswith(_ROLE_GUARD) and _matches(w.matcher, tool)]
    if not guards:
        return Check("guards armed", False,
                     f"no {_ROLE_GUARD} is wired for `{tool}` in the settings this process "
                     f"loads, so scope `{scope}`'s boundaries are not enforced")
    script = _executable(guards[0].command, environ, project_dir)
    if script is None or not probe_guard(script, scope, call, base):
        return Check("guards armed", False,
                     f"{_ROLE_GUARD} is wired but did not deny a `{tool}` call scope "
                     f"`{scope}`'s boundary forbids")
    return Check("guards armed", True, f"{_ROLE_GUARD} denied a forbidden `{tool}` call")


# ---------------------------------------------------------------------------
# Budget


def check_budget(scope: str, wired: list[Wired], environ: Mapping[str, str],
                 base: Path | None = None) -> Check:
    """The caps in force against the preset the launcher names, if it names one.

    `THALAMUS_BUDGET_PRESET` names the preset a job promises to run under; the caps in
    force are what `budget.limits` computes, which is what the budget hook enforces —
    the scope's own preset with any `THALAMUS_MAX_*` over it. A job that names no
    preset promises nothing here, and a cap in force still needs its hook wired.
    """
    from thalamus.contract.capabilities import BUDGET, read_presets
    from thalamus.contract.manifest import presets_file

    root = config_root(base)
    try:
        in_force = limits(scope, root, environ)
    except (OSError, ValueError) as exc:
        return Check("budget", None, f"the caps in force could not be read: {exc}")
    named = environ.get("THALAMUS_BUDGET_PRESET", "")
    if named:
        try:
            preset = BUDGET.resolve(named, read_presets(BUDGET, presets_file(BUDGET, base)))
        except (OSError, ValueError) as exc:
            return Check("budget", False, f"preset `{named}` does not resolve: {exc}")
        promised = {k: int(v) for k, v in preset.sets.items() if k != "max_tool_output_tokens"}
        actual = {k: v for k, v in in_force.items() if k in promised}
        if actual != promised:
            return Check("budget", False,
                         f"preset `{named}` promises {promised}, the hooks enforce {actual}")
    enforced = {k: v for k, v in in_force.items() if k != "max_tool_output_tokens"}
    if enforced and not any(w.command.rstrip().endswith(_BUDGET_HOOK)
                            and w.event == "PreToolUse" for w in wired):
        return Check("budget", False,
                     f"caps {enforced} are set but no {_BUDGET_HOOK} is wired to enforce them")
    return Check("budget", True, f"caps in force: {enforced or 'none'}")


# ---------------------------------------------------------------------------
# The write path


def check_write_path(session_id: str, session_type: SessionType,
                     pins_file: Path | None = None) -> Check:
    """Resolve this session's type the way `thalamus extract` will, from its ledger row."""
    facts = pin.ledger_facts(session_id, pins_file)
    recorded = pin.ledger_session_type(facts) if facts else None
    if recorded is None:
        return Check("write path", False,
                     "no pin-ledger row for this session, so distillation would record it "
                     "as attended")
    tier = int(session_type_tier(recorded))
    if recorded is not session_type:
        return Check("write path", False,
                     f"this process runs as {session_type.value}, and distillation would "
                     f"record it as {recorded.value} at tier {tier}")
    return Check("write path", True, f"distils as {recorded.value} at tier {tier}")


# ---------------------------------------------------------------------------
# Running it


def run(session_id: str, scope: str, session_type: SessionType, *,
        transcript: Path | None, project_dir: str, phase: str = FIRST_TOOL_CALL,
        environ: Mapping[str, str] | None = None, base: Path | None = None,
        pins_file: Path | None = None) -> Report:
    """The checks for one phase: all five at the first tool call, and at session start
    all but the tool surface, which the harness has not recorded by then.
    (A0253, cites-as-live)"""
    env = os.environ if environ is None else environ
    files = settings_files(env, project_dir)
    wired = wired_hooks(files)
    report = Report(session_id, scope, session_type.value, phase=phase)
    surface = ([check_tool_surface(transcript, required_tools(scope, session_type, env, base))]
               if phase == FIRST_TOOL_CALL else [])
    report.checks = [
        *surface,
        check_hooks_runnable(wired, env, project_dir),
        check_guards(scope, wired, env, project_dir, base),
        check_budget(scope, wired, env, base),
        check_write_path(session_id, session_type, pins_file),
    ]
    return report


def state_path(session_id: str, phase: str = FIRST_TOOL_CALL,
               directory: Path | None = None) -> Path:
    """Where a phase's report is recorded. The first-tool-call file is also the
    PreToolUse hook's state: once it exists the check is not run again."""
    suffix = ".start.json" if phase == SESSION_START else ".json"
    return (directory or PREFLIGHT_DIR) / f"{session_id}{suffix}"


def record(report: Report, directory: Path | None = None) -> Path:
    """Write the report beside the run and append one line to the log."""
    out = directory or PREFLIGHT_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = state_path(report.session_id, report.phase, out)
    path.write_text(json.dumps(report.as_dict(), indent=1))
    with (out / "preflight.jsonl").open("a") as log:
        log.write(json.dumps({"ts": report.ts, "session_id": report.session_id,
                              "scope": report.scope, "session_type": report.session_type,
                              "phase": report.phase, "passed": report.passed,
                              "failures": [c.name for c in report.failures]}) + "\n")
    return path


def told_at_start(session_id: str, directory: Path | None = None) -> set[tuple[str, str]]:
    """The (check, detail) pairs the session-start run already told this session, so
    the first-tool-call run repeats none of them. Empty when there was no such run."""
    try:
        recorded = json.loads(state_path(session_id, SESSION_START, directory).read_text())
    except (OSError, ValueError):
        return set()
    return {(c.get("name", ""), c.get("detail", "")) for c in recorded.get("checks") or []
            if isinstance(c, dict) and c.get("ok") is False}


def operator_message(checks: list[Check]) -> str:
    """The on-screen notice for an attended session: one line per finding."""
    return "\n".join([
        "Thalamus preflight — this session is not armed the way its pin promises:",
        *(f"  • {c.name}: {c.detail}" for c in checks),
        "MCP servers and hooks arm per process; a relaunch is the repair.",
    ])


def hook_output(report: Report, told: set[tuple[str, str]] | frozenset = frozenset()) -> dict:
    """What the hook prints for this report: PreToolUse's at the first tool call,
    SessionStart's at session start.

    An aborting failure denies the call and stops the run: a deny alone lets the model
    carry on without the tool, and `continue: false` alone lets this very call run
    first (both measured on Claude Code 2.1.330, 2026-11-23). It is decided at the first
    tool call only; at session start an autonomous report prints nothing. A reporting
    failure reaches the session as context, which a hook's `additionalContext` does, and
    the operator as a `systemMessage`, which Claude Code shows on screen, at
    SessionStart before the first prompt. A finding in `told` was reported at session
    start and is not reported again.
    (A0250, cites-as-live) (A0252, cites-as-live) (A0253, cites-as-live)
    """
    if report.phase == SESSION_START and report.aborts:
        return {}
    if report.aborts and not report.passed:
        reason = f"Thalamus preflight failed — {report.summary()}"
        return {
            "continue": False,
            "stopReason": reason,
            "hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason},
        }
    new = [c for c in (*report.failures, *report.advisories)
           if (c.name, c.detail) not in told] if not report.aborts else []
    if not new:
        return {}
    return {
        "systemMessage": operator_message(new),
        "hookSpecificOutput": {
            "hookEventName": _HOOK_EVENT[report.phase],
            "additionalContext": (
                "PREFLIGHT — this session is not armed the way its pin promises. The "
                "operator has been shown this; do not rely on what is missing: "
                + "; ".join(f"{c.name}: {c.detail}" for c in new) + ". "
                "MCP servers and hooks arm per process; a relaunch is the repair."
            ),
        },
    }
