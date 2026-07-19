# 010 — Cursor harness port: four of six hook events cross; two walls

**Date:** 2026-07-19 · **Component:** harness hooks (Cursor suite, `hooks/cursor/`) · **Status:** ported as adapters, contract-tested synthetically; live-Cursor validation pending (no Cursor on this machine)

## What broke

Nothing broke at runtime — this entry maps where the Claude Code hook suite
*cannot* follow Thalamus onto Cursor. The port target: nine Claude Code scripts
across six events (SessionStart, SessionEnd, UserPromptSubmit, PreToolUse:Bash,
PostToolUse:Bash, PostToolUse:mcp). Cursor's 2026 hook surface
(hooks.json v1; contract read from docs.cursor.com 2026-07-19) carries
equivalents for most of it: `sessionStart`/`sessionEnd`,
`beforeShellExecution`/`afterShellExecution`, `afterMCPExecution`,
`beforeSubmitPrompt`.

## What crossed (workaround: thin adapters)

Every ported hook is a stdin/stdout **adapter over the Claude Code script** —
one detection logic, one set of on-disk records (`~/.thalamus/pins|traces|guards`),
two harness dialects. Field mappings that matter:

- session identity: Cursor `conversation_id` (or `session_id` where present) →
  the ledger's `session_id`.
- `beforeShellExecution` sends `{command}` bare, not `{tool_input: {command}}`;
  the guard's exit-2 + stderr protocol maps onto Cursor's
  `{"permission": "deny", "agent_message": ...}`.
- `afterShellExecution` has one combined `output` string → the trace record's
  stdout leg.
- `afterMCPExecution` reports **bare** tool names (no `mcp__thalamus__` prefix);
  the adapter gates on the tool roster and restores the prefix so `eval sync`
  stays harness-blind.
- Pin resolution collapses to env-only (`THALAMUS_SCOPE`, default `main`) —
  Cursor has no agent picker, so the picked-agent-first rule has no first leg.

Conformance is pytest-driven with synthetic payloads (`tests/test_cursor_hooks.py`).
That verifies our side of the contract, not Cursor's: first live Cursor session
should confirm payload shapes before trusting the ledger/traces it produces.

## Wall 1: no per-prompt context injection

`beforeSubmitPrompt` returns only `{continue, user_message}` — it can block a
prompt but cannot inject agent-visible context. Claude Code's UserPromptSubmit
carries three Thalamus tiers (timestamp, conditioning, pin-engaged); on Cursor
only the side-effect tier (pin-engaged) survives. The timestamp and
conditioning tiers have **no Cursor carrier**. Consequences: long-running
Cursor sessions will drift on wall-clock (the failure timestamp.sh exists to
prevent), and utilization conditioning is Claude-Code-only, so cross-harness
utilization comparisons are confounded by design. Possible partial workaround,
deliberately not built: `postToolUse` *can* inject `additional_context`, so a
throttled per-tool-call injection could carry the clock — per-tool-call
cadence and measurement pollution need thinking through first.

## Wall 2: no distillation — Cursor transcripts are a foreign format

`thalamus extract` and the whole evidence archive parse Claude Code's JSONL
transcript format (`harness/transcripts.py`, hard-coupled to
`~/.claude/projects/<flattened-cwd>/<session-id>.jsonl` and its
user/assistant record types). Cursor's `transcript_path` points at a different
format. Until a Cursor transcript adapter exists, **a Cursor session leaves no
episodic memory**: the cursor session-end hook records the ended session
(scope ledger-first, `transcript_path` preserved, `distilled: false`) to
`~/.thalamus/logs/cursor-session-end.jsonl` instead of silently dropping it,
so a future adapter can backfill. This is the single biggest functional gap of
running Thalamus under Cursor: retrieval works, traces work, but the memory
graph stops growing from Cursor sessions.

## Also noted

- Cursor **cloud agents** don't load `sessionStart`/`sessionEnd`/
  `beforeMCPExecution`/`afterMCPExecution` at all — no priming, no pin ledger,
  no MCP trace tap there. Local Cursor only.
- Project-level `.cursor/hooks.json` is committed and runs for **anyone who
  opens the repo in Cursor** (after workspace trust) — a distribution channel
  and a consent question at the same time; flagged in the multi-user threat
  review (docs/05 thread `transcript-mediated-laundering-gap` is adjacent).
