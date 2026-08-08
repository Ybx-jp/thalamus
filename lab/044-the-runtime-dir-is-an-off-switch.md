# 044 — The runtime dir is an off switch, not a room

**Ends in: the cheap route is closed. Overriding `XDG_RUNTIME_DIR` does not relocate the
cross-session messaging registry — it stops the session binding a socket at all, so the
session runs normally and becomes invisible and unreachable. Room isolation by shared
registry needs a bind mount or a container, and unprivileged mount namespaces are
blocked on this box.**

**Date:** 2026-08-08 · **Harness:** Claude Code · **Status:** measured, clean A/B, one
negative result and one blocked follow-up

## Why

A room is a set of pinned windows whose members can reach each other and nobody else,
and the quick protocol is allowed only inside it. The messaging docs say membership is
really a filesystem question:

> Each session registers itself in files on disk and binds its inbox socket there. When
> Claude lists or messages your local sessions, Claude Code reads those files to find
> them, so **two sessions can reach each other only when they can see the same files.**

That is isolation by construction rather than by policy — outsiders are not blocked,
they are unaddressable. The registry is `$XDG_RUNTIME_DIR/cc-socks`, mode 0700. If the
location follows the environment variable, a room is one `env` away.

## Measured

Identical prompt (five separate `echo` calls, enough to keep the session alive several
seconds), identical flags, polled at 0.05s. `THALAMUS_SANDBOX=1` on both arms to keep
probes out of the pin ledger.

| arm | `XDG_RUNTIME_DIR` | socket appeared | where |
|---|---|---|---|
| control | default | **yes**, poll #10 (~0.5s) | `/run/user/1000/cc-socks/<pid>.sock` |
| treatment | a private dir, `cc-socks` pre-created 0700 | **no** | nowhere |

Both arms completed normally — each printed `DONE`. A `find` for `*.sock` modified in
the last five minutes across `/tmp`, `/run/user/1000` and the scratch tree returned
nothing, and the default registry stayed empty during the treatment arm, so the socket
did not silently land back in the default location either.

**Overriding the variable suppresses socket binding entirely.** Why is not established
here — only that it does. The session still works; it just leaves the fabric.

## The follow-up is blocked on this box

If the path is fixed, the surgical move is to change what is *at* the path: a per-room
directory bind-mounted over `/run/user/1000/cc-socks` inside a mount namespace, so
members see the room's registry under the name Claude Code already looks for. That needs
a mount namespace, and unprivileged ones are unavailable here —
`unshare -m --map-root-user` fails with `write failed /proc/self/uid_map: Operation not
permitted`, despite `unprivileged_userns_clone = 1`. So the bind mount needs root, or a
container per room, which the docs confirm isolates for the same reason.

## Consequences

- **Registry isolation is not free.** It costs privilege (a root-held bind mount at room
  launch) or a container per room. Neither is an `env` line in the launcher, which is
  what the design assumed.
- **The `PreToolUse` guard on `SendMessage` is promoted from defence-in-depth to the
  primary boundary**, at least until one of the above is built. It governs outbound only
  — an outsider can still message in — so pair it with `crossSessionInbound` on room
  members if inbound needs closing too.
- **One useful byproduct.** The negative result is itself a mechanism: a session launched
  with a private `XDG_RUNTIME_DIR` cannot send or receive at all, with no settings file
  and no deny rule. Blunt — it isolates absolutely rather than scoping — but it is the
  cheapest way to keep a session out of the fabric entirely.
- Measured on `claude -p` sessions. Interactive sessions were not tested and could
  differ; the A/B is two commands if it matters.
