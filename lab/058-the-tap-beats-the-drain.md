# 058 — The tap beats the drain

**Date:** 2026-08-11 · **Verdict:** two intake defects, measured; the backlog they
produced is a symptom, and a close verb alone would not have touched either

The operator reported three annoyances: no way to close a thread, a freshly opened
session distilling the moment he closed it, and sessions with nothing in them being
distilled at all. Two were the same defect. The third opened a consultation whose
round-1 finding was that the thing being asked for — a drain — is not where the water
comes from.

## A session whose only turn was a slash command

Distillation's eligibility test was `user_turns > 0`. Slash commands count as user
turns deliberately: a `/teach` session is nothing but commands, and before that rule
it was silently ineligible (ef3e3d6a, 87 assistant messages, never distilled). The
same rule let `/usage` then `/clear` through.

Session `59c1da4b` is the clean instance. Its entire transcript is one `/clear`. It
paid for a headless `claude -p` and minted a Session node whose summary reads *"No
substantive session content was present in this session."*

Across the 447 distillations recorded in `~/.thalamus/logs/`, **28 were zero-yield**
(0 claims, 0 threads), $3.11 of model spend. The money is trivial. The 28 Session
vertices in the surface every next session reads are not.

**The gate.** `TranscriptFacts.has_substance`: at least one user turn, **and** either
a typed prompt or the assistant actually reaching for a tool. Structural, model-free,
checked before anything is paid for.

Validated against every transcript on this box with a recorded distillation yield
(n=133, 24 zero-yield / 109 productive):

| | blocked by the gate |
|---|---|
| zero-yield sessions | **20 of 24** |
| productive sessions | **0 of 109** |

The two apparent false kills were `/login`+`/model opus` and a bare `/clear`, each of
which had extracted exactly one junk claim ("Session contains only harness
initialization"). They are correct kills; the yield label was wrong, not the gate.

`/teach`'s ef3e3d6a survives on the second clause — 3 command turns, 0 typed prompts,
**49 tool calls**. The four junk sessions that still pass all carry a real typed
prompt ("reply with the single word DONE"), where the extractor's own decline is the
right backstop: a structural test cannot know that was not work.

**One refusal must not sound like another.** A withheld session named by `--session`
reports as skipped and exits 0. Collapsing it into `No session matching` would fire
the wrong-project-dir diagnostic — the one that once cost three sessions — on every
`/clear`-only close, until it meant nothing.

## The thread backlog is an intake problem

500 Thread vertices: **328 open, 74 in_progress, 96 resolved, 1 abandoned.** The only
closer is the extraction model at session end.

**The closer is fast or never.** Measured over all 500, thread open time taken from
its `SPAWNS` session and close time from its `RESOLVES` session:

| | n | p50 | p90 | max |
|---|---|---|---|---|
| closed (latency) | 97 | **0.7d** | 8.9d | 22.8d |
| open (age) | 402 | **23.1d** | 46.6d | 55.6d |

53 of 97 closes land inside a day. And **296 of 402 open threads (74%) are already
older than the closed p90** — so the overdue rule the staleness design proposes
(lab/009, consultation `2e0f6a574658470a`) flags three quarters of the backlog. That
is the backlog restated, not triage. The closed distribution is selected by the
closer's reach, not merely censored: a thread is settled by the transcript that
spawned it, or it is not settled.

**Where a dead thread actually costs.** `REFERENCES` from an Exchange carries a
`role`: `brief` at mint, `citation` at answer. Only the first is a cost. Split by the
scope the thread lives in:

| scope | brief | citation |
|---|---|---|
| literature | 161 | 1 |
| eval-methodology | 74 | 29 |
| homelab | 48 | 3 |
| teacher | 30 | 0 |
| architect | 12 | 0 |
| **main** | **0** | **0** |

Exchanges are written to the asking scope and reference the *consulted* scope's
nodes; `main` is never consulted. So 341 of the 402 open threads carry no
per-consultation cost at all, and the tax is concentrated where a scope is small
enough that its threads are not a sample but the whole population. Two problems, two
cost functions.

`_assemble_brief` called `recall_open_threads(g, None, 5, scope)` positionally,
leaving `topic` empty — the one section of the brief not ranked against the question.
In `literature`, five threads at limit five meant the section *was* the scope, at 40%
of the brief. One of the five was `thalamus-memory-empty`:

> Thalamus memory store currently has zero open threads … future sessions querying
> this project's thread backlog should expect an empty result until new threads are
> created.

It was minted from a probe subagent's return value. It rode **43 briefs** into the
scope whose job is grounding, while 402 threads were open. Born wrong, not left open.

**Retrieval counts cannot tell you a thread earned its place.** Of 784 `used=true`
verdicts on Thread `RETURNS`, **~84% rest on lexical overlap alone**; 97 on a thread
slug, 28 on a cited vertex id. The abandoned thread demonstrates it — all three of its
retrievals scored `used=true` on `matched 13/22 terms: changes, code, commit, control,
diff, git`.

**The one abandoned thread was itself a false close.** `plane-repo-not-under-git` was
abandoned by session `a759fd38`, which touched only console and docs artifacts —
nothing about `thalamus-plane` or version control. `RESOLVES` carries no properties,
so no citation was possible and none was recorded. The single close made outside the
fast path is an instance of the failure the staleness design bans by name.

## Two blockers standing in front of the design

**The contract forbids the close the design requires.** `EdgeType.may_cross_scope`
defaults `False`; `RESOLVES` does not override it; `conformance` enforces it. lab/009's
whole incident is an operator confirming in a `main` session for a `homelab` thread.
That edge is illegal as the contract stands, so the federation call is part of this
design rather than a detail after it.

**The closer could not reopen.** The extraction contract offered
`in_progress|resolved|abandoned`. Re-open rate is the Goodhart guard the staleness
design leans on, and a thread that came back had to be respawned under a fresh id,
which hides that a close did not hold. `open` is now a status the extractor may set.

## What was fixed here, and what was not

Fixed: the substance gate; the brief's thread ranking; the reopen status;
`thalamus-memory-empty` abandoned.

Not fixed, and the reason this entry exists: **spawn-versus-close ran 19/3, 24/6, 38/4
over three days.** A close verb drains. Every dead thread examined here was born
wrong — a probe's return value, a request to backfill an index that was already
backfilled. Draining faster than that fills is a different mechanism from closing a
thread correctly, and conflating them is how the backlog gets rebuilt behind the fix.
