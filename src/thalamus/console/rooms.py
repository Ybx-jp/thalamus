"""Rooms — a private set of live sessions that see and message only each other.

A room's boundary is its harness's config root: on Claude Code peer discovery
enumerates `$CLAUDE_CONFIG_DIR/sessions/*.json`, so members of one room see only each
other. This module makes that directory (`ensure_room`) and spells the launch that
enters it (`_room_env`, `launch_flags`). Core knows a room only as a label and a
location — `harness/pin.py`'s `resolve_room` and `room_config_dir` — so the graph can
stamp it on a session and the cost report can find a member's transcripts without
this module installed.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from thalamus.harness import pin

# What a room dir owns outright, and what it borrows. Measured: every entry here is
# load-bearing, and the split is the whole design.
#
# OWNED are the trees that must NOT be shared, because sharing one is a channel.
# `projects/` is the sharp one: `claude --resume` consults neither the discovery
# roster nor the send path, it reads transcripts off disk, so a room that symlinks
# `projects/` hands its members' context to any non-member who forks their session
# — measured in both directions. It must also be on persistent disk, or a room
# silently costs its members their distillation (that trade has been got wrong in
# the other direction once, and it is why ROOMS_DIR is under $HOME).
ROOM_OWNED = ("sessions", "projects", "todos", "statsig")

# LINKED are the trees where sharing IS the point — the member should track the
# operator's own, so an edit reaches a live room. `settings.json` is not optional
# decor: every Thalamus hook is registered user-scope, and that scope moves with
# the config dir, so a room without it arms *zero* hooks and distills nothing.
# `.credentials.json` holds the OAuth token — without it a fresh config dir cannot
# authenticate at all.
#
# `settings.local.json` is deliberately NOT here: the permission allowlist is
# room-*owned*, because a room's permission surface has to be declared for
# the room rather than inherited from whatever the operator's own session happened to
# accumulate. Borrowing it would also make the room's policy move under it whenever
# the operator accepted a prompt elsewhere.
ROOM_LINKED = ("skills", "agents", "plugins", "commands",
               "settings.json", ".credentials.json")

# The seed allowlist a fresh room is provisioned with, written once and never
# overwritten.
#
# Under `auto` this is no longer what keeps Bash working — the classifier handles what
# no rule matches. What an allow rule still buys is determinism: it resolves at step one
# and never reaches the classifier, so a room's routine verification commands cannot be
# held up by a judgement call, and the room's policy stays something declared rather
# than inferred per call.
#
# The shape is read-mostly plus this project's own verification commands: enough to
# inspect the repo and check its own work, and nothing that reaches the network or
# rewrites history. `curl`/`wget` are absent on purpose rather than by oversight —
# transcript-mediated laundering is closed for WebFetch/WebSearch and Bash curl is a
# residual channel still open, so a room is not where it gets widened. Commit and push
# are absent for a different reason: a room member's commit is a decision the operator
# should see happen.
ROOM_ALLOWLIST = (
    "Bash(uv run pytest:*)",
    "Bash(uv run thalamus:*)",
    "Bash(uv run ruff:*)",
    "Bash(git status:*)",
    "Bash(git diff:*)",
    "Bash(git log:*)",
    "Bash(git show:*)",
    "Bash(rg:*)",
    "Bash(ls:*)",
)

# `.claude.json` is the one that must be a *copy*: members write to it. Copying it
# is also what carries `mcpServers`, so a member keeps the `thalamus` MCP server —
# an empty one means a room with no memory tools at all.
ROOM_COPIED = ".claude.json"


def host_config_dir() -> Path:
    """The operator's own config dir — what a room borrows from.

    `CLAUDE_CONFIG_DIR` is honoured so an operator who already moved their config
    tree is provisioned from the real one, but a room dir is refused as a source:
    provisioning from inside a member (a nested `thalamus spawn`) would otherwise
    chain symlinks through one room into another and copy a `.claude.json` already
    scoped to somebody else's collaboration.
    """
    env = os.environ.get("CLAUDE_CONFIG_DIR", "")
    if env:
        candidate = Path(env).expanduser()
        if pin.ROOMS_DIR not in candidate.parents:
            return candidate
    return Path.home() / ".claude"


def host_claude_json(config_dir: Path | None = None) -> Path:
    """Where `.claude.json` lives for the host — inside the config dir, or $HOME.

    Measured 2026-08-08: with `CLAUDE_CONFIG_DIR` set, the harness reads and writes
    `$CLAUDE_CONFIG_DIR/.claude.json`; with it unset it stays at `$HOME/.claude.json`
    rather than moving into the default `~/.claude`. Both are checked because
    picking the wrong one is silent — a stale empty `~/.claude/.claude.json` copies
    a room that starts fine and has no MCP servers.
    """
    config_dir = config_dir or host_config_dir()
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        inside = config_dir / ROOM_COPIED
        if inside.is_file():
            return inside
    home_level = Path.home() / ROOM_COPIED
    if home_level.is_file():
        return home_level
    return config_dir / ROOM_COPIED


def ensure_room(room: str, host: Path | None = None, harness: str = "claude") -> Path:
    """Build (or repair) a room's config dir. Idempotent — safe on every launch.

    Called from the launchers rather than left to an explicit create step, because
    the failure it prevents is silent: a config root pointed at a directory that does
    not exist is not an error the harness reports, it is a member that starts,
    authenticates as nobody, arms no hooks and distills nowhere. The room is only ever
    as real as its directory, so the directory is made where the room is entered.
    """
    if not pin.valid_room(room):
        raise ValueError(
            f"invalid room name {room!r}: lowercase letters, digits and hyphens, "
            "starting with a letter or digit"
        )
    if harness == "cursor":
        return _ensure_cursor_room(room)
    if harness == "codex":
        # Refused rather than provisioned, and the refusal is the honest state: codex
        # resolves `auth.json`, `hooks.json` and `sessions/` *all* from `CODEX_HOME`
        # (measured 2026-08-17), so a member under a relocated root is logged out and
        # arms no hooks — the exact failure `ROOM_LINKED` exists to prevent on Claude
        # Code, and the one Cursor is immune to because it resolves both from a fixed
        # path. Making that work is a room-provisioning arm nobody has built or
        # measured, and a directory alone would produce a member that starts, fails to
        # authenticate, and distills nothing.
        raise RuntimeError(
            "codex rooms are not built: codex resolves credentials and hooks from "
            "CODEX_HOME, so a room member under its own config root would start "
            "logged out with no hooks armed. Launch codex outside a room, or use "
            "claude or cursor for this room."
        )
    host = host or host_config_dir()
    creds = host / ".credentials.json"
    if not creds.exists():
        # Refused here rather than discovered by the operator watching a window
        # exit: a member without the token starts, reports "Not logged in", and
        # dies in well under a second, which on a phone reads as nothing happening.
        raise RuntimeError(
            f"no credentials at {creds} — a room member gets its own config dir, so "
            "it cannot reach a login that is not there. Run `claude` and `/login` "
            "first, then launch the room."
        )

    config = pin.room_config_dir(room)
    config.mkdir(parents=True, exist_ok=True)

    for name in ROOM_OWNED:
        owned = config / name
        if owned.is_symlink():
            # A withdrawn earlier shape, or a hand-made room. Unlinking removes
            # the link and never the target, so repairing here cannot lose data —
            # and leaving it is the transcript channel standing open.
            owned.unlink()
        owned.mkdir(exist_ok=True)

    for name in ROOM_LINKED:
        link, target = config / name, host / name
        if not target.exists():
            continue  # an operator without plugins/ should not be given a dead link
        if link.is_symlink():
            if link.readlink() == target:
                continue
            link.unlink()
        elif link.exists():
            # A real file where a link belongs: the member has been tracking a
            # frozen copy of the operator's settings, which is the failure mode
            # symlinking was chosen to avoid. Replaced, not merged.
            shutil.rmtree(link) if link.is_dir() else link.unlink()
        link.symlink_to(target)

    _seed_room_settings(config)
    _sync_mcp_servers(config / ROOM_COPIED, host_claude_json(host))
    return config


def _ensure_cursor_room(room: str) -> Path:
    """A Cursor room is a directory and nothing else — measured, not minimised.

    Every entry Claude Code's arm has to provision is absent here for a reason that
    was checked live against cursor/2026.08.11-e8db854, and the absences
    are the interesting part:

    - **No credentials.** `auth.json` is resolved from `$XDG_CONFIG_HOME/cursor`, by a
      different function than the one `CURSOR_CONFIG_DIR` overrides, so a member under
      a relocated config root is already logged in. `ensure_room`'s Claude Code arm
      refuses a launch when `.credentials.json` is missing; there is nothing here to
      refuse for.
    - **No hooks, no MCP.** `hooks.json` and `mcp.json` resolve from a hardcoded
      `homedir()/.cursor`, so a member arms the operator's hooks and servers without
      a link. The failure `ROOM_LINKED` exists to prevent — a room that arms zero
      hooks and distills nothing — cannot occur on this harness. Verified rather than
      reasoned: a session launched under a relocated root wrote its own pin-ledger row,
      which only the `sessionStart` hook writes.
    - **No permission seed.** The posture rides the argv (`harness/launcher.py`), which
      is deliberate: `cli-config.json` is state a session rewrites mid-run through
      `/config` and `/run-everything`, so a room expressing policy there would be
      expressing a preference rather than a constraint. A member that stalls at a
      prompt is caught at dispatch pre-flight instead of pre-empted here.

    What the directory does buy is the one thing that was never in doubt: `chats/`
    follows the config root, and `chats/` is what `--resume` reads. That is the same
    cross-read channel `ROOM_OWNED`'s `projects/` exists for, so the boundary is
    load-bearing even though almost nothing has to be built behind it.
    """
    config = pin.room_config_dir(room, "cursor")
    config.mkdir(parents=True, exist_ok=True)
    return config


def _seed_room_settings(config: Path) -> Path:
    """Write the room's own `settings.local.json`, once.

    Seeded and never repaired, unlike everything else `ensure_room` touches. The rest
    of the room dir is idempotently rebuilt because drift there is corruption; this
    file is the one an operator is *expected* to edit — widening a room's allowlist is
    how a room gets work done — so rewriting it on the next launch would silently
    revert that. A room whose policy has been tuned keeps it.
    """
    settings = config / "settings.local.json"
    if settings.exists():
        return settings
    settings.write_text(
        json.dumps({"permissions": {"allow": list(ROOM_ALLOWLIST)}}, indent=2) + "\n"
    )
    return settings


def _sync_mcp_servers(copied: Path, source: Path) -> None:
    """Seed the member's `.claude.json`, and keep its `mcpServers` current after.

    A copy taken once goes stale, and the way it goes stale is silent: an MCP
    server the operator adds later — `thalamus` itself, on a fresh install — is
    simply absent in every room, so members run without memory tools and nothing
    says so. Only `mcpServers` is carried over, because the rest of the file is
    the member's own state (its project list, its trust and onboarding flags) and
    overwriting that would reset the room on every launch.
    """
    if not source.is_file():
        return
    if not copied.exists():
        shutil.copy2(source, copied)
        copied.chmod(0o600)
        return
    try:
        current = json.loads(copied.read_text())
        wanted = json.loads(source.read_text()).get("mcpServers", {})
    except (json.JSONDecodeError, OSError):
        return  # a member mid-write; the next launch tries again
    if not wanted or current.get("mcpServers") == wanted:
        return
    current["mcpServers"] = {**current.get("mcpServers", {}), **wanted}
    copied.write_text(json.dumps(current, indent=2))


def rooms() -> list[str]:
    """Every room that has a config dir, newest first — the launcher's own record.

    Read off the filesystem rather than a registry, for the same reason the pin is
    read off the process: a room exists exactly when its directory does, and a
    separate list could disagree with that.
    """
    if not pin.ROOMS_DIR.is_dir():
        return []
    return sorted(
        (d.name for d in pin.ROOMS_DIR.iterdir() if d.is_dir() and pin.valid_room(d.name)),
        key=lambda name: (-(pin.ROOMS_DIR / name).stat().st_mtime, name),
    )


def _room_env(room: str, harness: str = "claude") -> list[tuple[str, str]]:
    """The launch variables that put a process in a room, or nothing at all.

    `THALAMUS_ROOM` is ours and reads the same everywhere; the config-root variable
    is the harness's, and naming the wrong one is silent — a Cursor member handed
    `CLAUDE_CONFIG_DIR` reads its own default root, joins no room, and looks exactly
    like a member from every surface that reports one.
    """
    if not room:
        return []
    variable = pin.ROOM_CONFIG_VAR.get(harness)
    if variable is None:
        raise ValueError(
            f"harness `{harness}` declares no config-root variable, so a room cannot "
            "be spelled for it — add one to ROOM_CONFIG_VAR rather than launching a "
            "member whose boundary is nothing"
        )
    return [
        ("THALAMUS_ROOM", room),
        (variable, str(pin.room_config_dir(room, harness))),
    ]


def _room_clear(harness: str = "claude") -> list[str]:
    """The `env` prefix that states "this window is in no room", explicitly.

    Silence is not the same as "no room", because `new-session -e` — unlike
    `new-window -e` — *does* populate the tmux session environment, and every later
    window in that session inherits it. Measured on tmux 3.4 (consultation
    `81176421bb8e409a`): a session created for a room hands `THALAMUS_ROOM` and
    `CLAUDE_CONFIG_DIR` to the next roomless window, which then joins the room's
    roster and writes its transcripts into the room's `projects/` while every
    surface still shows it as an ordinary session. Unsetting is what makes a
    roomless launch mean it.

    `-u` rather than `CLAUDE_CONFIG_DIR=$HOME/.claude`: naming the default is not
    a no-op. Measured 2026-08-08 — with the variable set, the harness reads
    `$CLAUDE_CONFIG_DIR/.claude.json`, and `~/.claude/.claude.json` is an empty
    file, so "helpfully" spelling out the default gives the session zero MCP
    servers. An operator's own deliberate override is passed through untouched.

    The variable cleared is the launched harness's own: unsetting Claude Code's in
    front of a Cursor binary clears nothing that binary reads, and would leave a
    roomless Cursor window inheriting a room's `CURSOR_CONFIG_DIR` from the session
    environment — the leak this function exists to stop, one harness over.
    """
    variable = pin.ROOM_CONFIG_VAR.get(harness, pin.ROOM_CONFIG_VAR["claude"])
    override = os.environ.get(variable, "")
    deliberate = override and pin.ROOMS_DIR not in Path(override).expanduser().parents
    config = [f"{variable}={override}"] if deliberate else ["-u", variable]
    return ["env", "-u", "THALAMUS_ROOM", *config]


def _with_room(argv: list[str], room: str, harness: str = "claude") -> list[str]:
    """Carry the room in the window's own argv, not only in its tmux env.

    tmux `-e` on `new-window` sets the initial process environment and is *not*
    stored in the session environment, so `respawn-window` — which is exactly what
    the console's recycle button runs — re-executes this argv with those
    variables gone (measured on tmux 3.4; `new-session -e` does survive, since that
    one does populate the session env). The pin already survives a recycle for this
    reason: `--agent thalamus-<scope>` rides the argv. `resolve_room` is env-only by
    design and has no such second channel, so without this prefix a recycled member
    silently drops back onto `~/.claude` — out of its room, still looking like a
    member. `set-environment -g` is not the alternative: it reaches every window
    created without `-e`, which is the shape that has already misfired here once.
    """
    pairs = _room_env(room, harness)
    if not pairs:
        return [*_room_clear(harness), *argv]
    return ["env", *(f"{k}={v}" for k, v in pairs), *argv]


def _in_room(room: str) -> str:
    """The clause every launcher appends when there is a room, and omits when not."""
    return f" in room `{room}`" if room else ""


def room_member_name(room: str, scope: str) -> str:
    """The display name a room member launches under, and the address it answers to.

    `SendMessage` routes on the session's name, and `room-guard.sh` decides whether
    a target is a room-mate by matching this exact prefix — so a member that does
    not carry the name is a member the guard can only ever block. Two members with
    the same scope in one room share a name, which the harness disambiguates with
    the `name [ref]` form the guard's pattern already allows.
    """
    return f"{room}-{scope}"


def launch_flags(room: str, scope: str, harness: str = "claude") -> list[str]:
    """The room-membership half of a launch. The permission mode is the harness's.

    One function because there are two launch paths — `_session_argv` for the roster
    and `spawn` for the console's on-demand button — and a flag added to only one of
    them is a divergence nothing reports: the console spawn button is how room members
    actually get made from a phone, so a flag missing there is missing where it counts.

    `--name` is the address `SendMessage` routes on and the prefix `room-guard.sh`
    matches, so a solo session has nothing to answer to. It is Claude-Code-only
    because the *address* is, not because the room is: a Cursor member is addressed
    by the tmux pane this launcher creates for it, which `window_room` recovers from
    the window's own start command, so there is no name for a flag to carry
    (`console/panes.py`, `contract/boundaries.py`).

    The permission mode moved to `harness/launcher.py`, because the harnesses do
    not merely spell it differently — Cursor's non-stalling flag is `auto` minus the
    safety classifier, so which one a pinned window gets is a decision about that
    control and not a translation.
    """
    if room and harness == "claude":
        return ["--name", room_member_name(room, scope)]
    return []


def _entered_room(room: str | None, harness: str = "claude") -> str:
    """The room this launch enters, provisioned and ready — flag first, env second.

    The flag wins because it is the launch decision being made right now, while the
    environment is whatever the launching shell (or the console's own long-
    lived server process) happened to carry; the plane in particular must be able to
    put a window in a room without being in one. Passing `None` asks for the
    environment, `""` says explicitly not in a room.

    Provisioning happens here, on the way in, so no launch path can reach
    `CLAUDE_CONFIG_DIR` without the directory behind it existing.
    """
    room = pin.resolve_room() if room is None else room
    if room:
        ensure_room(room, harness=harness)
    return room
