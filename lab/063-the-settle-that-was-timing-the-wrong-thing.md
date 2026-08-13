# 063 — The settle that was timing the wrong thing

**Date:** 2026-08-12 · **Harness:** Cursor CLI `2026.08.11-e8db854`, Claude Code
`2.1.229` · **Verdict:** workaround — a per-harness deadline, and a named wall behind it

lab/062 shipped the Cursor launcher and left a residual: `SPAWN_SETTLE_S = 1.2`
under-covers `agent`, whose death modes resolve after network round trips. This entry
measures it. The constant survived by 73 ms, and only on a healthy network.

## What the settle is for

`tmux new-window` returns 0 once it has forked, before the command execs
(docs/console-hazards §4). So the only evidence a spawned window exists is that it is
still alive some time later. Get that time wrong in the generous direction and every
successful spawn makes an operator wait; wrong in the tight direction and a spawn that
died reports success — the 2026-08-08 shape, where the sheet said ok, no window
appeared, and the anchor being the only window took the tmux server down with it.

## The measurement

Every launch driven through the argv `pin` actually builds, in a throwaway tmux server
on its own socket, polled at 50 ms for `pane_dead`, ceiling 30 s.

| launch | outcome | time to death |
|---|---|---|
| missing binary (either CLI) | dies, status 127 | **0.010 s** |
| `claude`, rejected `--permission-mode` | dies, status 1 | **0.278 s** |
| `claude`, untrusted directory | **lives** — trust modal | alive at 30 s |
| `claude`, bogus `ANTHROPIC_API_KEY` + unreachable base URL | **lives** — "use this API key?" modal | alive at 30 s |
| `agent`, untrusted directory (no `--trust`) | **lives** — hotkey modal | alive at 30 s |
| `agent`, no credentials (`HOME` redirected) | **lives** — "press any key to log in" | alive at 30 s |
| `agent --trust`, rejected `CURSOR_API_KEY` | dies, status 1 | **1.07–1.14 s** (n=9) |

So the two CLIs fail at different depths. Everything that kills Claude Code is decided
locally. Cursor's *only* measured fatal case is an authentication rejection — and trust
and missing credentials, the two failures the residual named, do not kill it at all.
They park on a modal, which is a different hazard (§9) and not this one.

## The part that overturns the constant

The auth rejection is not a fixed cost. Behind a local CONNECT proxy that sleeps 2 s
before tunnelling — a stand-in for the degraded network that makes auth fail in the
first place — the same launch died at **3.14–3.20 s** (n=3). The death time moved by
exactly the latency put in front of it.

**A death decided by a round trip has no bound**, so no constant covers it. What a
constant can do is cover the local modes and buy headroom against a plausible round
trip, which makes the number a bet sized on a measurement rather than a guarantee.

## What shipped

`LaunchShape.settle_s` — 1.2 s for Claude Code (4x its slowest measured death), 4.0 s
for Cursor (3.5x its local one, and past the +2 s degraded case). `pin.confirm_started`
polls the new window until it dies or the deadline passes, so only a *successful* spawn
pays the full wait; the 127 case is still reported in ~15 ms.

Two mechanics were worth the trip. `new-window -P -F '#{window_id}'` returns the id of
the window just made, which replaces the window-list diff the console used — a diff can
only ask whether *some* new window is alive. And `remain-on-exit` held on for the
duration of the settle leaves a corpse to read, so a death reports the vendor's own
sentence instead of a shrug: `capture-pane -p -J -S -`, because a dying pane pushes its
output into history and leaves the "Pane is dead" banner alone on a 200-line screen,
and 60-column wrapping otherwise quotes a fragment starting mid-word.

Live, real binaries, private socket: a rejected key reported **failed at 1.15 s**
carrying *"The API key was loaded from the CURSOR_API_KEY environment variable"*; a
healthy `agent` reported **started at 4.04 s**.

## The wall

A Cursor window that dies between 4 s and whenever the network gets around to it is
still reported as started. Nothing catches it; the window list is what shows it. The
alternative — waiting long enough to be sure — is paid by an operator holding a phone
on every spawn that works, which is the overwhelming majority.

## Correction to lab/062

`env THALAMUS_SCOPE=qe -- agent --trust`, as written there and in docs/07, does not run
`agent` at all. GNU `env` stops scanning for options at the first `NAME=VALUE`, so the
later `--` is taken as the command name: `env: '--': No such file or directory`, exit
127. The launcher emits no `--` and is unaffected; the prose was wrong, and a reader
copying it got the hazard-4 failure by hand.
