# 023 — The first campaign where memory-on could actually reach memory

**Date:** 2026-07-27 · **Component:** eval loop layer 2 (`thalamus eval run
--sandbox --isolate-store`) · **Status:** **pre-registration — written and
committed before the campaign ran.** Results append below in a later commit.

## Why this is the first one worth pre-registering

Every memory-on arm before today ran without reaching memory. lab/013 recorded it
and blamed the agent; the confined re-run of 2026-07-27 showed the mechanism:
the image had no `jq`, every retained hook parses its stdin payload with `jq`
under `set -euo pipefail`, and a SessionStart hook that aborts does not stop the
session — it simply never injects. The arm was never told a memory surface
existed, and `recall_calls: 0` is indistinguishable from a candidate that was
offered memory and declined it.

With `jq` in the image the same task, arm and ref records
`{thalamus: 2, tool_search: 1}`. The `tool_search: 1` is the load-bearing part:
the MCP tools genuinely *are* deferred inside an arm session, so the hook's
ToolSearch instruction was never redundant — it had never been delivered.

So this is the first campaign in which the treatment is actually applied. That
is the only reason it is worth its cost, and it is also why nothing before it
should be read as evidence about memory.

## Pre-registration

**Task.** `arm-runner-session-death-classification` — the only battery task with
a validated interior ladder (4 mutants, 5 acceptance levels) and 27 unconfined
arms of history to compare against. `reader-case-insensitive-recall` is excluded
deliberately: lab/021 established that its memory-on arms call `memory_recall`
through the very bug they are asked to fix, which biases *against* memory-on.

**Design.** 12 memory-on, 12 memory-off, alternating rather than blocked, so
that any drift over the campaign's ~70 minutes falls on both arms equally.
`order_index` is recorded per arm.

**Treatment.** memory-on = MCP surface present. memory-off = `.mcp.json`
removed **and `--network bridge`** (`--isolate-store`).

> **Amendment, before any endpoint data existed.** As first written this said
> `--network none`, which is what `--isolate-store` shipped. The first attempt
> at this campaign halted at arm 2: `none` isolates the model API along with the
> store, so the memory-off arm died on turn 1 with `Unable to connect to API
> (ENOTIMP)`, stamped `void` and ungraded. The shipped verification had
> confirmed the graph was unreachable and never asked whether the arm could
> still run. `--isolate-store` now selects `bridge`, re-verified at the TCP
> layer: the graph is closed on `localhost:8182` and on the gateway
> `172.17.0.1:8182` (the server binds loopback-only), while `api.anthropic.com`
> answers. The aborted attempt produced one graded memory-on arm and no
> memory-off arm, so it yields no comparison; it is **discarded** rather than
> pooled, and the campaign restarts from zero. The endpoint, threshold and
> analysis above are unchanged.

**Primary endpoint, fixed in advance.** The share of gradeable arms reaching
**rung ≥ 4**, reported as a distribution over rungs. Same threshold lab/020
pre-registered, so the two are comparable. `mean rung` is not computed — ordinal
rungs are not averaged (docs/index 2026-07-27).

**Analysis.** Intention-to-treat keeps every arm. `contaminated` is the
pre-registered exclusion key for a secondary per-protocol read. Arms with
`attributable: false` are not graded at all — an infra fault means the verdict is
not about the candidate. A `void` or `interrupted` session halts the campaign.

## Declared threats, before seeing any number

- **`--isolate-store` is a second factor.** memory-off differs from memory-on in
  both the memory surface and network reachability. It is taken knowingly: the
  alternative leaves the measured store hole open, where a memory-off session
  reaches the graph by ad-hoc gremlin and "memory-off" is not memory-off. A null
  result is interpretable under this design; under the single-factor one it
  would not have been.
- **Memorization stratum only.** All three battery tasks are `overlap:
  memorization`; there are no `transferable` tasks. Any result is scoped to that
  stratum and cannot support a claim that memory improves agent work generally.
- **The confound the task declares about itself.** `literal-convergence` flags
  that a memory-on arm can reach the marker class by recalling the answer rather
  than by reasoning about failure classes, and that the probe *cannot* separate
  the two. This is why it is a flag and not a rung.
- **Not powered.** n = 12 per arm is chosen for comparability with lab/020, not
  from a sample-size calculation. The ordinal power anchors (Whitehead 1993) sit
  outside the ingest allowlist and are unprocured, so no power claim is made and
  no stopping rule is derived from the data.
- **Escape rates are a lower bound.** The detector reads absolute paths and git
  subcommands; a symlink, a `cd` then a relative path, or a shell variable slips
  past it.

## Results

Pending — appended after the run, in a separate commit, so the record shows the
predictions were fixed before the data existed.
