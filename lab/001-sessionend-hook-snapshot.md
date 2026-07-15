# 001 — The session that installs a SessionEnd hook is never distilled by it

**Date:** 2026-07-15 · **Harness:** Claude Code 2.1.x · **Status:** workaround

## What broke

The session that wired SessionEnd distillation into the harness (commit `094fadb`,
session `16a29708`) ended without being distilled. No `session-end-*.log`, no
extraction, no memory formed — discovered only because the next session started by
asking "did the hook fire?" The only log present was the manual smoke test.

## Why, in harness terms

Claude Code snapshots hook configuration **at session startup**. A hook added to
`.claude/settings.json` mid-session is not part of the running session's config, so
it is inert for that session's own lifecycle events — including its end. Timeline
that proves it: session started 01:23 local, hook landed in settings at 02:04, session
ended (via `/clear`) at 08:35 with no SessionEnd fired. Every lifecycle hook you
install has a one-session blind spot: the session that installs it.

The failure is silent by construction. SessionEnd has no user-visible output, the
hook's own logging only exists once the hook runs, and the session that would have
noticed is the one that just ended.

## Workaround

Distillation was deliberately built as the same code path as the bootstrap — "a
session ending now is just a bootstrap of one" (`session-end.sh`). So the miss cost
one command and $0.34:

    thalamus extract --session 16a29708… --force --write -- -home-ybx-code-thalamus

Detection is the operator habit until it earns automation: a session id in
`~/.claude/projects/<project>/` with no matching `~/.thalamus/logs/session-end-*.log`
is an undistilled session. If misses recur for other reasons (hard kills also skip
SessionEnd), the fix is a sweep — `extract` over sessions missing claims — run at
SessionStart or by cron, not a smarter hook.

## Update (same day): the boundary is the process, not the session

The "one-session blind spot" prediction above is falsified — the blind spot is
**process-wide**. Session `73a17b59` started via `/clear` at 08:35, hours after the
hook landed, and its `/clear` at 11:56 also fired nothing. Its successor session was
equally blind: no SessionStart context injected, no `mcp__thalamus__` tools present.

Measured cause: Claude Code snapshots hooks and launches project MCP servers at
**process startup**, and `/clear` starts a new session inside the same process. The
terminal in question (pid 2579766) had been running since Jul 13 23:55 — ~26 hours
before `.mcp.json` and `.claude/settings.json` existed — so three consecutive
sessions ran with the entire harness wiring (SessionStart prime, PostToolUse traces,
SessionEnd distillation, the MCP server itself) inert. Timeline that proves it:
process start Jul 13 23:55 → hooks land Jul 15 02:04 → sessions `16a29708`,
`73a17b59`, and its successor all end or run with zero hook activity, while a
manual pipe of the same JSON into `session-end.sh` works immediately.

Consequence for the workaround: the miss is not one session but *every session
until the operator restarts the `claude` process*, and each miss is silent. That
upgrades the detection sweep from "operator habit" to necessary — the
undistilled-session check (transcript with no matching `session-end-*.log`) is the
only signal that fires regardless of process age. It also touches docs/07's pinning
problem: any pin mechanism that relies on env or hook config being re-read "next
session" actually means "next process", which the operator cannot observe from
inside the harness.

## Moral

Lifecycle instrumentation cannot verify itself from inside the lifecycle it
instruments. The recovery path mattering more than the trigger is exactly why the
trigger and the bootstrap were kept as one code path. And the unit that arms
harness config is the process, not the session — `/clear` crosses sessions
without crossing the config boundary.
