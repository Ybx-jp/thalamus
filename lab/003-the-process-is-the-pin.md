# 003 — The process boundary that blocked pinning is the pinning mechanism

**Date:** 2026-07-16 · **Harness:** Claude Code 2.1.211 · **Status:** workaround (of lab/001's wall)

## What broke

Nothing this time — what broke was a conclusion. Session pinning had been parked as
*blocked* on lab/001: harness config arms per process, MCP tool calls don't carry
the caller's session id, so no mechanism visible from inside a session could retarget
a running server. All true. The error was reading "the pin can't change inside a
process" as a wall, when it is the enforcement property pinning needs: **one process
= one immutable pin**. docs/07 v1 wanted the pin immutable per session anyway; the
process boundary enforces that for free, in the one place the model can't reach.

## Measured, in harness terms

All from fresh processes (lab/001's moral: the session that wires a thing can never
test it). Claude Code 2.1.211, Linux:

1. **`${THALAMUS_SCOPE:-main}` expands in `.mcp.json` `env` blocks.** A headless
   `THALAMUS_SCOPE=literature claude -p` asked `memory_open_threads(project="thalamus")`
   — a query with 4+ hits in `main` — and got "No open threads found." The MCP child
   process received the launcher's env through the expansion; the pin reached the
   server without the server changing.
2. **Hooks inherit the launcher's env.** The same probe's tap line carried
   `scope: "literature"` (PostToolUse), the pin ledger row was written (SessionStart),
   and the SessionEnd log read "distilling session 95c60f4c into scope literature."
   All three hooks are children of the pinned process; nothing had to be passed.
3. **The whole write path respects the threaded pin.** `scope:literature:session:95c60f4c`
   exists; `scope:main:session:95c60f4c` does not. The distillation, the trace
   landing (first expert-scoped Trace vertex), and the contract audit all came out
   clean on the first live run.
4. **`claude --agent <name>` exists** and (per official docs) arms project MCP +
   settings hooks alongside the agent definition. Agent frontmatter cannot set env —
   the launcher owns the env, which is the design anyway.
5. **`subagent_type: "fork"` is not exposed to the model's Agent tool** in this
   session (available agents enumerated without it), despite 2.1.211 > the documented
   default-enable version. Model-spawned forks presumably still gate on
   `CLAUDE_CODE_FORK_SUBAGENT=1` here; untested. Not a pinning dependency — a fork
   shares the parent's MCP server, so it inherits the pin by construction when it
   does run.

## Incidental catch: the first real miss was invisible

The pinned probe produced the tap's first genuine recall miss — and `eval sync`
classified it *legacy* and skipped it. The MCP server wraps every result in
`{"result": ...}`; the tap records that envelope verbatim; the anchored miss
patterns can't match inside it. Every prior trace had returned vertex IDs (the vid
regex is unanchored and didn't care), so the bug was unreachable until a session
with an empty scope asked a question. Fixed in `eval/traces.py` (envelope unwrap)
with a regression test. Moral inside the moral: a code path that has never seen a
real event is untested no matter what the suite says.

## Workaround → mechanism

`thalamus pin <scope>` / `thalamus roster` launch env-pinned `claude` processes
(tmux windows when available, `execvp` otherwise); the SessionStart hook appends
the session→scope row to `~/.thalamus/pins/pins.jsonl`; SessionEnd resolves the
distillation scope **ledger-first, env fallback**, so a session recovered later
from an unpinned shell still lands in its pinned scope instead of forking its
Session vertex identity across scopes (`vid` includes scope — the same session id
in two scopes is two vertices).

## Moral

A measured limit is a fact about the harness, but "blocked" is a judgment about
the design — re-derive the judgment when the design changes. The boundary that
makes config invisible to a running process is exactly what makes a pin
unforgeable from inside one.
