# 043 — Two forks, and I measured the wrong one

**Ends in: the mechanism exists. `claude --resume <id> --fork-session --name <n>` forks
a session into its own process with warm context and a fresh session id, addressable by
name over the new cross-session messaging. An earlier draft of this entry declared a
wall from a measurement of a different primitive; that conclusion is withdrawn below.**

**Date:** 2026-08-08 · **Harness:** Claude Code, session `4a4b3c44` · **Status:**
measured, n=1 per arm, with a negative control and one withdrawal

## Why

The room's fast tier calls for **forking the consulted session into its own window** so
it answers immediately from warm context while the original continues uninterrupted —
attacking the real cost, which is cold-context reconstruction (tonight's consultations:
303s, 372s, 383s, 417s, 462s). Two things had to be true: the fork must exist, and its
relationship to its parent must be recorded, or a quick exchange mints an extra
apparently-independent witness of a conversation it merely inherited.

## Measured

**1. The mechanism exists, as three composable flags.**

| flag | behaviour |
|---|---|
| `-r, --resume <session-id>` | resume a conversation by session id |
| `--fork-session` | when resuming, **create a new session ID** instead of reusing the original |
| `-n, --name <name>` | display name — and the address `SendMessage` routes on |

`claude --resume <target> --fork-session --name <room>-<scope>-q` therefore yields a
warm-context process with its own identity and hooks, reachable by name from any peer
session. Nothing has to be built to get warm context; it ships.

**2. There is a second, unrelated "fork" and it does not exist here.**
`Agent(subagent_type: "fork")` returns `Agent type 'fork' not found`; the registry holds
only `claude`, `claude-code-guide`, `Explore`, `general-purpose`, `Plan`,
`statusline-setup` and the four generated `thalamus-<scope>` experts. The Agent tool's
documentation mentions `subagent_type: "fork"` in a parenthetical about model
inheritance; that mention is not a capability in this build.

**3. In-process subagents are not sessions.** A `general-purpose` subagent probing its
environment reported `SESSION_ID=4a4b3c44-79af-4c4b-b815-ee6a50b640a9` — **the parent's
id, verbatim**. Across the spawn: pin-ledger rows 1205 → 1205, transcript files 90 → 90.
No SessionStart, no hooks, no transcript of its own. This confirms docs/02's "sidechains
in the parent session's JSONL" by observation rather than by design intent. Asked what
it could see of the parent's in-flight work, it said nothing, and listed what it did
hold: task prompt, CLAUDE.md boilerplate, a git-status snapshot. Cold.

**4. Negative control — the sandbox guard holds.** `thalamus ingest` spawns a headless
`claude -p` for extraction; ledger delta was **0**. So (3)'s absence is the subagent
genuinely not being a session, not the ledger failing to watch.

## Withdrawn

An earlier version of this entry concluded **"there is no warm-context channel in this
harness"** and called it a wall. That is false. It generalised from measurement (2)+(3)
— the in-process subagent regime — to the harness as a whole, having never checked
`claude --help`. The room was always process-per-member, which is why `THALAMUS_ROOM` is
an env var in the first place; the in-process regime was never the subject. The
measurements above stand; the conclusion drawn from them does not.

The generalisable error is the same one this entry's (2) names: **a tool description is
not a harness measurement, and one regime is not the harness.** Two flags of `--help`
would have caught it.

## What it means

The corroboration question is live, not dodged — a fork **is** its own session, so it
arms hooks, distils, and mints a Session vertex. But it is the one case where the
dependence is **harness-recorded rather than inferred**: the fork exists because a named
parent was resumed. In the semiring terms of exchange `3ce5de8683d74787`, a fork is
`m(e)` — a mapping over the parent's context, not a new base fact — which is exactly the
event-as-source modeling that entry said Thalamus lacks. For forks, and only for forks,
we can have it for free.

That requires recording it. `room` groups co-witnesses; it does not say *this session
derives from that one*. A `forked_from` session property is the missing half, and it is
subject to the same argument that put `room` in first: nothing in a finished graph
distinguishes a fork from an independent session that happened to agree.

| regime | own session id | hooks arm | distils | context | dependence recoverable |
|---|---|---|---|---|---|
| In-process subagent | no — parent's | no | no | cold | n/a (never a separate witness) |
| Pinned window (`thalamus spawn`, roster) | yes | yes | yes | cold | only via `room` |
| **Forked session** (`--resume --fork-session`) | yes | yes | yes | **warm** | **exactly, if `forked_from` is written** |

## Consequences

- The quick protocol's transport is available today: fork into a window, address by
  `--name`, message with the new cross-session feature.
- **`forked_from` is the next schema decision**, and it is the same record-it-now-or-never
  shape as `room`.
- Room isolation is not free: `ListAgents` currently enumerates every peer on the
  machine (32 at the time of writing), so "members may only message members" is
  enforcement that does not exist yet.
