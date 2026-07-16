# 004 — Agent Teams, first contact: pins inherit, coordination is invisible, and the lead woke up in the wrong repo

**Date:** 2026-07-16 · **Harness:** Claude Code 2.1.211, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (headless `-p` lead) · **Status:** measurements (T0, T5, T2 from docs/07's experiment table), n=1 each

## Setup

One headless run: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 THALAMUS_SCOPE=literature
claude -p "spawn one teammate to call memory_open_threads and report"`, launched
from the thalamus repo. Observables: the pin ledger (every process's SessionStart
writes a row), the tap (scope-stamped per call), `~/.claude/teams/*/`, and the graph.

## Measured

1. **T0 — teammates inherit the lead's env: CONFIRMED.** The teammate ran as its
   own session (`37aef344`, own transcript, own tap lines) and its ledger row says
   `scope: literature`. Its recall differential agreed ("No open threads found" —
   literature is thread-empty; main was not). Per-teammate *distinct* pins therefore
   need per-teammate launch control (env is uniform across the team unless the
   spawner varies it); a uniformly-pinned team comes free.
2. **T2 (free ride) — teammates distill per-process: CONFIRMED.** The teammate got
   its own SessionEnd: "distilling session 37aef344 into scope literature," 1 claim,
   1 thread. N teammates = N distillations into their pinned scopes — docs/02's
   "both sides remember" exists at process level with zero Thalamus code.
3. **T5 — coordination is invisible to the instrumentation: CONFIRMED, a fortiori.**
   The teammate's report reached the lead, yet `~/.claude/teams/session-c4acf93d/`
   holds only `config.json` — **no `inboxes/*.json` ever materialized** (the lead's
   `backendType` is `in-process`; delivery either never touches disk in this mode or
   is cleaned up). Zero Exchange vertices, zero CONSULTS edges. So in teams mode the
   collaboration graph currently sees *nothing*, and even the documented mailbox
   artifact isn't there to audit after the fact. The only durable record of the
   exchange is the two transcripts — which distill as tier-1: the
   agent-authored laundering path of [docs/05](../docs/05-trust-model.md), measured
   to exist with **no inspectable artifact in between**.
4. **Anomaly — the lead armed the wrong project's harness.** Launched from
   `/home/ybx/code/thalamus`, the team config recorded the lead's cwd as
   `/home/ybx/code/stepmania-chart-generator` and its transcript landed in *that*
   project's directory. Consequently the lead ran with no thalamus hooks and no
   thalamus MCP at all — no ledger row, invisible to every observable except the
   team config. The teammate was placed correctly. Cause unknown (possibly
   most-recently-used project state in the experimental teams path); n=1; re-measure
   before building anything on lead-side behavior.

## Consequences for the experiment table (docs/07)

- T1 (pin-quality A/B) and T3 (counterfactual arm) are **unblocked in design**: env
  is inherited, so differently-pinned teammates need the spawner to set env per
  teammate — or per-teammate launch via `thalamus pin` windows joined as a team —
  which is exactly what the launcher already produces. But the lead-cwd anomaly (4)
  says don't trust the lead's own placement in `-p` mode yet.
- T4 (mailbox canary) needs rescoping: there may be no mailbox *file* to plant
  anything in — the channel to red-team is transcript distillation itself, which is
  the docs/05 gap stated more sharply: **the laundering channel is the only channel.**

## Moral

The instrument worked better than the subject: the pin ledger and the scope-stamped
tap answered three experiments in one run, including one about a channel that left
no artifact of its own. Observability you built yesterday is what makes an
experimental feature measurable today.
