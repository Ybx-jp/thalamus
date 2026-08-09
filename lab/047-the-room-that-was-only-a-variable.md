# 047 — The room that was only a variable

**A room had a boundary, a guard and a schema field, and no directory. Building
the provisioner surfaced two silent failures that had nothing to do with the
boundary: `new-session -e` leaks a room into every later window of the session,
and naming `CLAUDE_CONFIG_DIR` at its own default costs a session its MCP
servers.**

**Date:** 2026-08-08 · **Harness:** Claude Code 2.1.226 · tmux 3.4 ·
**Status:** measured, live member end-to-end

## Why

[lab/045](045-the-registry-that-was-not-the-socket.md) located the room boundary
in `CLAUDE_CONFIG_DIR` and [lab/046](046-the-third-channel-is-the-transcript.md)
gave the config dir its final shape. Both measured that shape by hand, in
throwaway directories. Nothing built it: `room_config_dir()` computed a path,
`~/.thalamus/rooms/` was empty, and every launcher pointed `CLAUDE_CONFIG_DIR` at
a directory that did not exist. The guard's roommate pattern was in the same
position — `room-guard.sh` admits `<room>-<scope>`, and no launcher produced that
name, so its allow-path was unreachable and its only possible verdict was block.

## Two failures the boundary work did not predict

**`.claude.json` moves when you name the default.** With `CLAUDE_CONFIG_DIR` set,
the harness reads `$CLAUDE_CONFIG_DIR/.claude.json`; with it unset it stays at
`$HOME/.claude.json` rather than moving into `~/.claude`.

| config dir | `.claude.json` read from | `claude mcp list` |
|---|---|---|
| unset | `~/.claude.json` (90 KB) | `thalamus` connected |
| `~/.claude` (the default, named) | `~/.claude/.claude.json` (empty, a probe leftover) | none |
| a fresh empty dir | created empty | `No MCP servers configured` |

So the obvious way to write "no room" — `CLAUDE_CONFIG_DIR=$HOME/.claude` — is not
a no-op. It hands the session an empty file and no memory tools, and nothing about
the session looks wrong. The clear has to be an *unset*.

**`-e` is durable on `new-session`, which is the bug.** lab/046 measured that
`new-window -e` does not survive `respawn-window`, and fixed it with an argv
prefix. The other half went unexamined: `new-session -e` *does* store its
variables in the tmux session environment, where every later window inherits them.
Measured in a throwaway session — a window created with no room flags at all:

```
ROOM=[alpha] CFG=[/home/ybx/.thalamus/rooms/alpha] SCOPE=[homelab]
```

That session joins the room's roster, writes its transcripts into the room's
`projects/`, and distills as a member, while every surface shows an ordinary
session. It is the inverse of lab/046's leak — context entering a room rather than
leaving it — reached without `--resume`, through the launcher's own convenience.

Found by the homelab consultation (`81176421bb8e409a`), reproduced here before it
was fixed.

## Consequences

**Silence is not "no room", so a roomless launch states it.** Commands are wrapped
`env -u THALAMUS_ROOM -u CLAUDE_CONFIG_DIR`, and the launcher takes the variables
back out of the session environment after creating a session with them. An
operator's own deliberate `CLAUDE_CONFIG_DIR` is passed through rather than
stripped — the leak being closed is a *room's* dir arriving where no room was
asked for.

**Provisioning belongs at launch, not in a create step.** `ensure_room` is
idempotent and runs on every entry, including repairing a room built to the
withdrawn lab/045 shape by replacing a symlinked `projects/` with a directory the
room owns. The governing rule came from the same consultation: the phone surface
must never depend on a step only reachable from a keyboard. `.claude.json`'s
`mcpServers` is refreshed on each pass, because a copy taken once loses every
server the operator adds later and says nothing about it.

**The window name is not where the room goes.** `#{pane_start_command}` renders
the creation command, which already carries the room in its `env` prefix — so the
control plane reads a window's room the way it reads its cwd, the tmux window name
stays the bare scope, and roster idempotency keys on (name, room) instead.

## Live, end to end

`thalamus spawn homelab --room alpha` into a fresh tmux session:

| probe | result |
|---|---|
| member's process env | `THALAMUS_ROOM=alpha`, `CLAUDE_CONFIG_DIR=…/rooms/alpha` |
| session descriptor `name` | `alpha-homelab` — the address `SendMessage` resolves, and what the guard admits |
| descriptor location | the room's `sessions/`; 0 of 7 outside descriptors mention it |
| hooks armed through the symlinked `settings.json` | pin ledger row written, `room=alpha` |
| distillation at close | `thalamus extract --room alpha --projects-dir …/rooms/alpha/projects` |
| solo spawn into the same tmux session | `env -u …`; neither variable set; session env clean |

The descriptor's `name` field is the one that had never been tested: `--name` was
known to exist as a flag, but not that it reaches the field name resolution
answers from. It does, which is what makes the guard's allow-path reachable at all.

## Not yet measured

- Two members of one room actually messaging each other, and the guard's block
  verdict on a real non-member target. Every probe here was a single member.
- Whether an interactive member hits a fresh trust dialog — still open from
  lab/046, and still unmeasured: this entry's live member was interactive but
  never prompted, which is consistent with the copied `.claude.json` carrying
  `hasTrustDialogAccepted` and not proof of it.
- Deleting a room dir under a live member recreates it as a bare directory (seen
  during teardown). Harmless here because `ensure_room` runs on every launch, but
  the recreated shape is exactly the empty-config-dir failure, and nothing warns.
