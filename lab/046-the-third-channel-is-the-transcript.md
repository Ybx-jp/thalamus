# 046 — The third channel is the transcript

**Ends in: the fix that saved the room's memory is what let its context out. A
room boundary drawn over live sessions governs two channels — discovery and
delivery — and `--resume` uses neither. A non-member forked a room member's
session and read its codeword straight out. The room dir must own its own
`projects/` on persistent disk, which closes the channel in both directions and
leaves `thalamus extract` needing to be pointed at it.**

**Date:** 2026-08-08 · **Harness:** Claude Code 2.1.226 · **Status:** measured,
both directions, both shapes; a shape shipped in lab/045 withdrawn

## Why

[lab/043](043-two-forks-and-i-measured-the-wrong-one.md) established the quick
protocol's transport: `claude --resume <id> --fork-session --name <n>` yields a
warm-context process with its own identity, addressable by name. It could not ask
how that interacts with a room, because the room boundary had not been located
yet — [lab/045](045-the-registry-that-was-not-the-socket.md) located it a session
later, in `CLAUDE_CONFIG_DIR`. This is that question.

The instrument is a codeword per parent, so a fork that says one has provably
inherited that parent's context and not guessed it.

## Both directions cross, and the outbound one is the bad one

Under lab/045 arm 3's shape — room dir owns `sessions/`, symlinks `projects/`:

| direction | fork | codeword returned | its roster |
|---|---|---|---|
| inbound | outside parent `ZEPHYR-7`, forked **into** the room | `ZEPHYR-7` | room only (`alpha-holder`) |
| outbound | room member `ORCHID-9`, forked **from outside** | `ORCHID-9` | outside only |

The outbound row is a non-member reading a room member's context verbatim. It
never messaged anyone, never appeared in the room's roster, and never touched the
guard — it resumed a transcript. The inbound row is the mirror: outside context
enters the room wearing a native member's roster, with no crossing recorded, so
the room's own graph cannot tell an inherited fact from a witnessed one.

## The mechanism, and why the previous fix caused it

lab/045's boundary is over **live sessions**: discovery enumerates
`$CLAUDE_CONFIG_DIR/sessions/*.json`, and delivery resolves names against that
same roster. `--resume` consults neither. It reads **transcripts**, under
`$CLAUDE_CONFIG_DIR/projects/`.

And lab/045 arm 3 had symlinked `projects/` back to the real config on purpose:
a room dir owning its own put every member's transcript on tmpfs, where
`thalamus extract` never looks and a reboot erases it. That fix — made to stop a
room silently costing its members their distillation — is exactly what put room
transcripts in the shared directory any non-member resumes from.

Two properties were traded against each other without noticing they were the same
directory. **A boundary drawn over one channel says nothing about a channel that
reads from disk.**

## The shape that closes it

Room config dir on **persistent disk**, owning `sessions/`, `projects/`, `todos/`
and `statsig/`; symlinking `skills`, `agents`, `plugins`, `commands`,
`settings.json`, `settings.local.json` and `.credentials.json`; copying
`.claude.json`. Measured at `~/.thalamus/rooms-lab045/alpha-cfg7` (ext4, not
tmpfs):

| probe | result |
|---|---|
| outsider resumes room session `TOPAZ-3` | `No conversation found with session ID: 68b0b8c0…` |
| room member resumes outside session `LARKSPUR-2` | `No conversation found with session ID: e3dcc01a…` |
| room member forks a **room** session | `TOPAZ-3` — warm, the quick protocol intact |
| transcripts | on ext4 under the room dir; survive a reboot |

Both directions are separately measured rather than one inferred from the other —
the same discipline lab/044 and lab/045 were written to enforce.

**Two entries in that symlink list are load-bearing and were found by the homelab
consultation** (`4d2ef0d3d7f74a4a`), which observed that a room omitting
`settings.json` arms **zero** Thalamus hooks: every hook is registered
user-scope in `~/.claude/settings.json`, and that scope moves with the config
dir. `settings.local.json` carries the permission allowlist, whose loss means a
member prompts for everything. Both work as **symlinks** — measured here, a room
member with symlinked settings wrote its pin ledger row normally — which is
better than the copy these labs used, since a copy silently stops tracking the
operator's own settings. `.claude.json` must stay a copy (members write to it),
and copying it is what carries `mcpServers`: a room member under this shape has
the `thalamus` MCP server connected, verified with `claude mcp list`.

**`forked_from` was not actually being recorded**, which this entry's own
premise assumed. `session-start.sh` returned early on `source=resume` *before*
the pin ledger write, and a fork arrives as `resume` — so `--fork-session`
recorded neither `room` nor `forked_from`, for exactly the sessions those fields
exist to describe. One early return was serving two concerns, priming and
recording. Fixed: recording is unconditional, priming still skips
resume/compact. A fork in a room now writes `room=alpha` and
`forked_from=<parent>`.

## Consequences

- **lab/045's `projects/` symlink is withdrawn.** The room dir owns `projects/`,
  and lives on persistent disk rather than under `/run/user/<uid>`.
- **`thalamus extract` must be pointed at room `projects/` dirs**, or room
  members distil nowhere and the original problem returns by another route. This
  is wiring, not architecture: `harness/transcripts.discover()` already takes a
  `projects_dir` argument, and `CLAUDE_PROJECTS` is its default, not an
  assumption baked through the module.
- **A room has three channels, not one**, and each needs its own answer:
  discovery (roster), delivery (name resolution), and **resumption
  (transcripts)**. The guard covers intent on the second only.
- The quick protocol's transport survives intact inside the room, which was the
  point of forking: warm context against consultation's measured cold-start cost
  (303–462s, lab/043).

## What the launcher still owes

From the homelab consultation (`4d2ef0d3d7f74a4a`), measured on this box and not
re-verified here:

- **tmux does not inherit the room.** An exported variable does not reach a new
  window; only `-e` does, and `pin.py`'s three window/session creation paths pass
  exactly one (`-e THALAMUS_SCOPE`). A room launcher must add
  `-e CLAUDE_CONFIG_DIR` and `-e THALAMUS_ROOM` to all three.
- **`respawn-window` drops `-e` entirely**, so the plane's recycle button would
  move a member back onto `~/.claude` mid-life. The pin survives this only
  because it has a second channel — `--agent` in the creation argv — and
  `resolve_room` is env-only by design, so a room has no such fallback.
- **Never `tmux set-environment -g`** for this: it reaches every window created
  without `-e`, the shape that already burned this box once with `VIRTUAL_ENV`.

## Not yet measured

- Cross-room resumption. Both probes tested room-vs-outside; two rooms with
  private `projects/` should be symmetric by the same mechanism, unmeasured.
- Whether pointing extract at room dirs reintroduces any of the lab/033 problem
  where distillation's own subprocess transcripts became memory.
- Whether an interactive room member hits a fresh trust dialog — its
  `.claude.json` is a copy carrying `hasTrustDialogAccepted`, but every probe
  here used `claude -p`.
- Retroactive sweeps: `thalamus bootstrap` and `rescore.py` still default to
  `~/.claude/projects`, so a manual re-extract of a room session needs
  `--projects-dir` passed by hand.
