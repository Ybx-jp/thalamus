# 044 — The 103-byte cliff

**Ends in: a room is one launcher argument. `XDG_RUNTIME_DIR` *is* honoured, and
relocating the messaging registry needs no container, no orchestrator and no
privilege. The first version of this entry concluded the opposite from an invalid
A/B — the treatment path was 115 bytes against a 103-byte limit, so the socket
silently landed in a shared `/tmp` fallback I never looked in.**

**Date:** 2026-08-08 · **Harness:** Claude Code 2.1.225 · **Status:** measured; an
earlier conclusion refuted and replaced, refutation sourced to the homelab
consultation `4cce72f57c964f16` and re-verified here

## The mechanism

Claude Code builds the peer-discovery socket path as
`$XDG_RUNTIME_DIR/cc-socks/<pid>.sock`, and **falls back when the result exceeds 103
bytes** to `/tmp/cc-socks-<uid>/<pid>.sock`. The fallback is silent: the session binds
normally, appears normally, and is simply somewhere else.

## What went wrong the first time

The original A/B pointed `XDG_RUNTIME_DIR` at a scratchpad directory, watched that
directory, saw nothing, checked the default registry, saw nothing, ran a `find` for
recent `*.sock`, saw nothing — and concluded the override *disabled* socket binding.

Every one of those observations was correct and the conclusion was wrong:

- the treatment socket path was **115 bytes**, over the limit, so it bound at
  `/tmp/cc-socks-1000/<pid>.sock`;
- the `find` ran *after* the probe exited, and the socket is unlinked at exit;
- `/tmp/cc-socks-1000/` exists on this box mode 0700, **dated 03:02** — precisely the
  A/B window. The evidence that the arm bound a socket was sitting on disk the whole
  time, one directory outside where the experiment was looking.

The generalisable error: the experiment watched **the location the hypothesis
predicted** rather than the whole space the process could write to. A negative
observation confined to the predicted location cannot distinguish "did not happen"
from "happened elsewhere". Watching `/tmp` as well would have cost nothing.

## Re-measured

| arm | `XDG_RUNTIME_DIR` | path bytes | result |
|---|---|---|---|
| control | default | — | `/run/user/1000/cc-socks/<pid>.sock`, ~0.5s |
| short path | `/run/user/1000/rooms/gamma` | 47 | **bound at `/run/user/1000/rooms/gamma/cc-socks/503461.sock`**, ~0.5s |
| long path (original) | scratchpad tree | 115 | fell back to `/tmp/cc-socks-1000/` |

The short-path arm is re-run and verified in this entry. From the consultation and
not independently re-run here: a hidden `--messaging-socket-path` flag binds at exactly
the path given, and the boundary the code enforces is the socket's **directory** — a
reply address in a different directory is rejected as outside the socket namespace.
`--messaging-socket-path` is absent from `--help`, which is consistent with it being
hidden rather than absent.

## The hazard the first version created

That entry offered its own error as a feature: "a private `XDG_RUNTIME_DIR` takes a
session out of the fabric entirely." **That is false and actively dangerous.** A long
private path does not remove a session from the fabric — it moves it to
`/tmp/cc-socks-<uid>/`, the one directory *every other overflowed session on the box
also falls into*. A room scheme built on long per-room paths would silently merge all
of its rooms into one, while looking isolated. Deep scratch-tree paths are exactly the
shape that overflows, so this is a live trap, not a theoretical one.

**Any room launcher must assert its socket path length**, and short-path room dirs
(`/run/user/<uid>/rooms/<room>`) are the shape to use.

## Consequences

- **Rooms need no containers, no k8s, no privilege.** Per-room `XDG_RUNTIME_DIR` under
  a short path, or the explicit flag. The operator loses nothing: the window command
  gains one argument, and tmux window-index addressing, `capture-pane`, `send-keys` and
  the phone PWA are untouched.
- **`room-guard.sh` returns to its intended role** — defence-in-depth over a structural
  boundary, not the primary boundary standing in for one. It still earns its place:
  the structural boundary governs *discovery*, the guard governs *intent*, and the
  guard's ledger is what makes either measurable.
- **The mount-namespace dead end was also mis-stated.** Unprivileged userns is refused
  here by `kernel.apparmor_restrict_unprivileged_userns = 1` — a settable sysctl, not a
  kernel wall. It is moot for rooms now, but it was recorded as a harder limit than it is.

## Measured since, and it refutes the discovery half

[lab/045](045-the-registry-that-was-not-the-socket.md) ran the cross-visibility A/B.
The binding result above stands — sockets partition exactly as described — but
**discovery does not read a socket directory at all**, so a per-room
`XDG_RUNTIME_DIR` isolates nothing: peers are enumerated from
`$CLAUDE_CONFIG_DIR/sessions/*.json`, each descriptor publishing its own
`messagingSocketPath`. Every "rooms need no containers" consequence below is
therefore about the *transport*, not about isolation.
