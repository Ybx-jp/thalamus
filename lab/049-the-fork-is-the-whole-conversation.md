# 049 — The fork is the whole conversation

**Ends in: the quick protocol's transport works and its premise survives, but a fork is
not "the parent's context plus an answer" — it is a full rewrite of the parent's
conversation with the fork's own session id stamped on every record. Distilling one as
an ordinary session mints a second Session re-asserting the parent's entire episode.
Five silent failures found before shipping. A first cost finding — "$1.35 per call, and
money is the binding constraint" — is **withdrawn below**: it forked stale transcripts
and never read the cache-hit field. A warm fork reads the parent's whole prefix and
creates only the new turn, at 16× less. Cost is bimodal, and the discriminator is parent
*recency*, not parent size.**

**Date:** 2026-08-09 · **Harness:** Claude Code 2.1.226 · Ubuntu, `ybx-MS-7A63` ·
**Status:** measured, live, on real transcripts and the real pin ledger; 16 further arms
after a withdrawal

## Why

[lab/043](043-two-forks-and-i-measured-the-wrong-one.md) established the transport,
[lab/046](046-the-third-channel-is-the-transcript.md) confirmed it survives inside a
room, and [lab/047](047-the-room-that-was-only-a-variable.md) built the room it runs
in. What none of them asked is what a fork *costs* and what its transcript *is* — the
two questions that decide whether the quick protocol
([docs/02](../docs/02-expert-subgraphs.md)) can distill at all.

The design under test: a caller inside a room resolves a live expert session, runs
`claude -p --resume <sid> --fork-session`, blocks on stdout, and closes a `kind: quick`
Exchange. The parent is never signalled.

## The sandbox collision: refuted as posed, real in the form you will hit

`agents.sandbox_env()` has **exactly one call site** in the tree
(`harness/extraction.py:407`). `THALAMUS_SANDBOX` is inherited by children of a marked
process; a room member is not marked, so a quick fork launched from inside one arms its
hooks normally. The "a sandbox is not a session" decision does not fire here.

It fires if you copy the only in-repo example of launching a headless `claude`, which
runs its child in `tempfile.TemporaryDirectory(prefix="thalamus-extract-")`:

| probe | result |
|---|---|
| fork with cwd `/tmp/thalamus-extract-quickprobe` | filed under project `-tmp-thalamus-extract-quickprobe`; `discover()` withholds it |
| the same fork's parsed `cwd` | the **fork's** cwd, not the parent's — `is_sandbox_cwd()` also refuses |
| fork with cwd `/tmp/quick-fork_probe2` | project `-tmp-quick-fork-probe2` is listed — a junk project minted instead |

Both refusals agree, so the failure is total rather than partial, and it surfaces as
`Unknown project dir(s) under …` and `sys.exit(1)` into a detached
`~/.thalamus/logs/session-end-<8>.log`. Same shape as the plane's spawn API returning
`ok: true` for a window that never appeared.

**The fix is not a third trust category and not an opt-out: run the fork with
`cwd` = the parent's cwd.** That keeps the transcript in the parent's project dir,
keeps both refusals `False`, and keeps `facts.project` correct.

## A fork is a full rewrite, and that is the finding

Forking parent `76d985b8` (1,772,440 bytes, 822 lines):

| | parent | fork |
|---|---|---|
| raw JSONL lines | 822 | 581 |
| `message_count` | 509 | **511** |
| `user_turns` | 4 | **5** |
| `tool_calls` | 198 | **198** |
| `touched` artifacts | 15 | **15** |
| `ai-title` | `Complete rooms implementation` | **identical** |
| distinct message UUIDs | 562 | 567 |
| **parent UUIDs present in the fork** | — | **562 / 562** |
| `sessionId` values in the file | 1 | **1 — the fork's, on every record** |

The fork carries the parent's conversation complete, re-stamped. Nothing in the file
names the parent, which *measures* rather than assumes docs/09's claim that the launcher
is the only channel `forked_from` can travel on.

So distilling a quick fork does not write "the answer, plus a `forked_from` edge". It
writes **a second Session re-asserting the parent's whole episode** — same title, same
15 Artifacts, `TOUCHES` edges on the *same anchor UUIDs*, and a second archived Source.
`witnesses.corroboration()` still collapses the fork into the parent for claims the
parent also asserted, so docs/09's PosBool reading holds. Three other things do not:

1. `session-end.sh` passes `--force` unconditionally, so every quick call runs a full
   model extraction over the parent's entire transcript rather than over the one Q&A.
2. **The archive cannot dedup it.** `archive_bytes` is content-addressed over the whole
   payload and every `sessionId` line differs, so byte-identity never occurs: the fork
   of a 1.77 MB parent archived 1.70 MB. Against a 299 MB / 200-transcript archive, N
   quick calls cost N × parent size — and any secret already in the parent's transcript
   is **copied into a second archived Source per call**, multiplying an exposure the
   homelab scope has already recorded once rather than containing it.
3. The duplicate lands in `main`, not the expert's scope — see below.

**The fix is exact, and needs no heuristic.** The fork's own records are the ones whose
UUIDs are absent from the parent: 567 − 562, with 562/562 of the parent's UUIDs re-used,
so the set difference is a set difference and not a timestamp guess. Distilling that
delta yields the answer as evidence in a few KB, with no duplicate title, artifact set
or TOUCHES edges.

`--no-session-persistence` exists on this CLI version (`--print` only) and would remove
the transcript entirely. Recorded as a considered rejection: it trades the collision for
having no evidence at all.

## Forking a live parent does not perturb it

Parent `11111111-…` was launched headless with codeword `ZINNIA-4` and made to write
records steadily for 60.7 s across 8 serial Bash calls. Two forks were taken mid-run.

| fork | taken at | parent bytes / lines then | codeword returned | fork lines | wall |
|---|---|---|---|---|---|
| a | t≈14 s | 26,666 / 11 | `ZINNIA-4` | 14 | 4.41 s |
| b | t≈24 s | 30,685 / 15 | `ZINNIA-4` | 24 | 4.12 s |
| parent final | t=60.7 s | 53,070 / 39 | — | — | rc 0, `is_error: false` |

Both forks of an actively-writing parent inherited context, extending lab/046 to the
mid-turn case. **`--resume` takes no lock and did not perturb the parent**, which ran to
completion through two concurrent forks. The fork is a point-in-time snapshot, monotone
in fork time, with no leakage forward.

A 200 Hz poller over a parent's whole run (13,994 samples) found
`partial_tail_observations=0` and `max_partial_bytes=0` across only 5 distinct file
sizes — the writer appends in a few large bursts, each landing whole. Bound on that:
the largest record produced was 39,855 bytes, because Claude Code truncates
`toolUseResult`. Records stay inside single-write territory, so 0/13,994 at 5 ms is
evidence and not a proof of atomicity, and it says nothing about a parent **compacting**
at the moment of the fork.

**The fork sees what is written, not what the parent believes.** An interactive parent
mid-turn holds un-flushed state in the process. That direction is what the probe
suggests, but its instrument was contaminated (the parent's own prompt named all 8
ticks), so it is recorded as suggestive rather than measured.

## The pin ledger is the wrong index for "which session is the expert"

`~/.thalamus/pins/pins.jsonl`, 1,246 rows: 585 `event:engaged`, 2 `event:rescope`, 659
start rows, in three shapes across the file's history. Rooms ever recorded: `alpha` (4),
`symtest` (1). Rows with a non-empty `forked_from`: **one, ever.**

**Nothing is appended when a session dies.** A ledger row is a birth certificate and
never a liveness signal. Live, at the time of the probe — newest ledger start-row per
scope against actually-running processes:

| scope | rows | newest row | alive? | actually live |
|---|---|---|---|---|
| teacher | 14 | `1b1a5486` | **no** | **3** (windows @12, @13, @14) |
| homelab | 18 | `5a491b72` | **no** | **0** |
| literature | 14 | `ecf14272` | **no** | **0** |
| eval-methodology | 19 | `8a7c4638` | yes | 1 |
| main | 588 | `a2564491` | yes | 2 |

"Newest ledger row for (room, scope)" is wrong for three of five scopes, and for
`teacher` it names a dead session while three live ones exist.

**Resolve against the live roster instead** — `$CLAUDE_CONFIG_DIR/sessions/<pid>.json`,
the same directory lab/045 located the room boundary on, which `pin.ROOM_OWNED` already
gives every room privately. Each entry carries `pid`, `procStart`, `sessionId`, `cwd`,
`tmux`, `messagingSocketPath`, `name`, `agent`, `status`. That is liveness (`pid` +
`procStart` against `/proc/<pid>/stat` field 22, which defeats pid reuse), the pin, the
window, and **the cwd the fork must run in**. Entries are removed on clean exit —
verified empty immediately after the probe sessions ended.

All three failure modes resolve to *refuse and name it*, never *pick*:

- **Two live sessions.** `pin.room_member_name()` returns `<room>-<scope>` for both, so
  the caller cannot even address them apart without the `name [ref]` form. Print both
  with window and `startedAt`; require disambiguation. Not hypothetical — three
  `thalamus-teacher` sessions were live during the probe.
- **None live.** Refuse, and do **not** fall back to the ledger. Forking a dead
  session's transcript is asking a snapshot, not asking the expert, and it would still
  close an Exchange that reads as a live consultation. The honest fallback is the cold
  path at its real 303–462 s.
- **Respawned window.** A non-event for the roster — the new process registers a new
  `<pid>.json`. But the recycle path is `remain-on-exit` → `/exit` → poll `pane_dead` →
  `respawn-window`, and that `/exit` fires SessionEnd, so **a recycle destroys the
  resumable session**: transcript closed and distilled, new id, empty context. Any
  cached resolution must invalidate on `pid` change.

## Four things a room member's headless fork does, and one it does not

Probed in a room `qprobe` provisioned by `pin.ensure_room()`, with SessionEnd filtered
out of the symlinked `settings.json` so the probe could not write to the graph.

- **Room inherited: yes, for free.** `CLAUDE_CONFIG_DIR` is already exported in the
  member's environment; the fork's transcript landed under the room's `projects/` and
  `room=qprobe` was recorded with the launcher doing nothing.
- **Symlinked `settings.json` hooks armed: yes.** SessionStart wrote the row, and so did
  `pin-engaged.sh` — so **each quick call adds two ledger rows** and counts as an
  engaged session to anything reading the ledger.
- **`forked_from`: no, unless the launcher sets `THALAMUS_FORKED_FROM`.** Measured both
  ways. The room landing for free is what makes this trap plausible: an implementer who
  sees `room=` correct with no work will reasonably assume the environment handles the
  rest, and ship the one field whose absence turns a fork into a fake independent
  witness. One non-empty row in 1,246 means no historical data would flag the regression.
- **A fork does not inherit the parent's pin.** Forking a `scope=homelab` /
  `agent=thalamus-homelab` parent *without* re-passing `--agent` produced a session at
  **`scope=main`, `agent=""`** — while still returning the parent's codeword, i.e. with
  the expert's full context inherited. `--resume` restores the conversation, not the
  launch flags, and `resolve-scope.sh` reads `CLAUDE_CODE_AGENT` from the new process:
  a fork is a fresh arming decision, not an inherited one.

  Two consequences if `quick` omits `--agent`: the fork's MCP server serves `main`, so
  the answer is composed against the wrong memory; and the duplicated parent episode
  above distills **into `main`**, moving an expert session's entire conversation across
  a scope boundary with nothing recording the crossing.

## Latency holds, with a cliff

All `--model sonnet`, one-word prompt, sandbox-marked so no hook overhead, sequential on
a box already running six live Claude sessions. **These parents were all stale fixtures —
see the withdrawal below for what that does to the cost column.**

| parent transcript | bytes | wall (s) | cache-creation tokens | cost |
|---|---|---|---|---|
| *(cold `-p`, no resume)* | 0 | 4.04 | 14,363 | $0.093 |
| tiny | 2,108 | 3.90 | 8,832 | $0.062 |
| small | 4,958 | 4.34 | 9,099 | $0.064 |
| medium | 283,927 | 4.42 | 36,610 | $0.229 |
| large | 1,772,440 | **6.23** | 223,477 | **$1.350** |
| very large | 6,184,854 | **71.03** | 670,898 | **$4.047** |

**The latency premise holds, with a cliff.** ~2.3 s of CLI overhead plus a load term
that is free to a few hundred KB, 6.2 s at 1.8 MB, and **71 s at 6.2 MB** — an 11× jump
for 3.5× the size. The tell is 670,898 cache-creation tokens, past a 200 K window: that
fork was compacting. Still ~5× better than the cold baseline, but "far below" stops
being the right word. Caching does not explain the outlier — warm forks below ran
1.6–2.5 s against cold 2.0–2.5 s — so this reading survives the withdrawal intact.

## Withdrawn: "money is the binding constraint"

An earlier version of this entry concluded that **cost, not latency, is the wall, at
$1.35 per call**. That is wrong, and the error is in the probe rather than the arithmetic.
Every parent in the table above is a **stale fixture**, so any cache entry had long
expired; and the table reports `cache_creation_input_tokens` while never reading
`cache_read_input_tokens`. It measured the one case the quick protocol never runs in.

The generalisable error is the same shape as lab/043's: **a measurement of the cold
regime is not a measurement of the harness.** The operator caught it by asking whether
forks share the parent's cache. They do.

**The deciding arm.** Parent = one `-p` request carrying a 228,515-byte payload (~98 k
tokens of `messages[0]`), forked seconds later:

| arm | `cache_read` | `cache_creation` | hit | cost | dur |
|---|---|---|---|---|---|
| parent's own request (cold) | 24,018 | 97,920 | 19.7% | **$0.5948** | 2490 ms |
| fork #1, same model | **121,938** | **15** | **100.0%** | **$0.0367** | 1990 ms |
| fork #2 (+4 s) | 121,942 | 11 | 100.0% | $0.0367 | 1688 ms |
| fork #3 (+24 s, after divergent arms) | 121,942 | 11 | 100.0% | $0.0367 | 2502 ms |
| fork + `--agent` **added** (parent unpinned) | 21,100 | 92,241 | 18.6% | $0.5598 | 2268 ms |
| fork + **different model** (haiku, positive control) | 17,794 | 75,409 | 19.1% | $0.1528 | 2322 ms |

24,018 + 97,920 = 121,938 exactly: **a warm fork reads the parent's entire prefix and
creates 11–15 tokens — the new user turn only. 16× cheaper.** Three distinct fork session
ids reading one entry also settles that per-session volatile content — session id,
`--name` — is **not** in the cached prefix. The haiku arm misses as predicted, so the
instrument can see a miss.

Price constants derived from the envelopes and consistent across all 16 arms: **cache
read $0.30/MTok**, **1 h cache write $6.00/MTok** (every envelope showed `ephemeral_1h`,
`ephemeral_5m: 0`).

**Matching the parent's agent is free — mismatching it is what costs.** Against a
*pinned* parent with an identical payload:

| arm | read | create | hit | cost |
|---|---|---|---|---|
| pinned parent, cold | 21,100 | 92,226 | 18.6% | $0.5598 |
| fork, `--agent` matched | 113,330 | 11 | 100.0% | **$0.0341** |
| fork, `--agent` **dropped** | **113,330** | 11 | **100.0%** | $0.0341 |
| fork, matched again | 113,341 | 0 | 100.0% | $0.0341 |

So the apparent tension — "pass `--agent` to keep the pin" against "adding `--agent`
broke the cache" — dissolves: that arm missed because the fork's agent *differed from its
parent's*, not because pinning costs anything.

**And the dropped-`--agent` row is a sharper version of the pin finding.** The unpinned
prefix totals 121,938 tokens; the pinned one totals 113,326, because `--agent` swaps in a
shorter system prompt. A fork of a pinned parent *without* `--agent` read **113,330** —
the **pinned** total. *Inferred* from that (the rendered prefix is not reachable): the
resumed session restores the expert's system prompt from its own record even with the
flag absent. *Measured* separately above: that same fork's ledger row says `scope=main,
agent=""`. So a fork that forgets `--agent` **speaks as the expert to the model and files
as `main` to Thalamus**, and nothing in the answer text shows the divergence. That is
worse than the visible failure originally described.

**A fork writes no competing entry.** First fork of a cold 1.14 MB fixture: 20,733 read /
108,076 created, 16.1%, $0.6547. Second fork seconds later: **127,924 read / 886 created,
99.3%, $0.0438.** N quick calls cost **one write plus N−1 reads**, and it does not matter
whether the writer was the parent or a sibling.

**But warmth decays well inside the nominal 1 h TTL.** Re-forking the `medium` fixture 38
minutes after an earlier fork of it: 29,712 read / 36,586 created — **44.8%, the
tools+system block only**, $0.2285. A never-forked size-matched fixture reads 25.3%. *Not
isolated*: the sibling-fork arm rules out writer identity, leaving time or eviction, but
the window between "seconds" and "38 minutes" was not bracketed.

## The mid-turn exception, and it is the case the design is for

Parent actively generating (`ps` state `Sl`, 15 transcript lines written), forked at
t+22 s:

| arm | read | create | hit | cost |
|---|---|---|---|---|
| fork **while parent generating** | 21,100 | 39,627 | **34.7%** | **$0.2441** |
| same parent, seconds **after** it finished | 61,175 | 16 | **100.0%** | **$0.0185** |

**A mid-turn fork misses the message body entirely — 13× the post-turn cost.** The prefix
totals differ (60,727 vs 61,191): the mid-turn fork snapshots a *truncated* conversation,
so its final block boundary is one no cache entry sits at. *Inferred* mechanism,
consistent with all 16 arms but not directly observed: breakpoints are placed relative to
the message list, and a truncated list can neither reach the parent's late breakpoint nor
find one of its own.

This lands on the design rather than beside it. Non-interruption is the stated reason to
fork, so if `quick` is reached for *because* the expert is mid-task, it lands in the
34.7% case by construction.

## The corrected cost, and why it is not one number

Warm cost is (parent context tokens) × $0.30/MTok:

| parent | withdrawn figure | corrected warm figure |
|---|---|---|
| 122 k-token context (measured directly) | — | **$0.034–0.037** |
| 1.77 MB / ~253 k tokens | $1.35 | **≈$0.076** (extrapolated at the measured read rate; 17.8×) |
| 6.18 MB / ~700 k tokens | $4.05 | **≈$0.21** (19×) |

**Cost is bimodal, and the discriminator is parent recency, not parent size:**

1. **Warm** (parent active within seconds): **$0.03–0.08**.
2. **Cold** (parent expired) or **agent-mismatched**: **$0.55–$1.35** on the same parent —
   16–20×.
3. **Mid-turn**: 13× the post-turn price.

And the distribution matters more than the rates. **The roster's normal state is idle** —
the three live `thalamus-teacher` sessions carry `updatedAt` ages of ~25,700 s. A quick
call against an expert nobody has typed at today is a *cold* call, and the 38-minute
decay says "today" is generous. The expected cost therefore depends on a usage
distribution nobody has measured, which is an instrument to build before any per-call
price goes in a design doc.

What caching does **not** touch: the duplicate-episode distillation above is a storage and
secret-duplication cost — a second ~1.7 MB archived Source per call — and it is unaffected
by any of this.

**The fork does not reliably answer the question you asked.** On the 6.2 MB run the fork
returned a refusal in full — it read the appended question as a prompt injection into
the parent's frame, declined it, and summarised the parent's open tasks instead. The
five smaller forks answered correctly, so this is not universal. But warm context and
this failure are *the same thing*: the fork inherits the parent's conversational frame,
including its system-reminders and its notion of who "you" is. A caller that blocks on
stdout and validates citations must treat "the fork answered the parent's question"
as a first-class outcome, which argues for an explicit frame-break rather than a bare
question.

## Consequences

- **Run the fork with the parent's cwd, from the live roster's `cwd` field.** Anything
  else either loses the transcript or mints a junk project.
- **Distillation must be delta-only** — records whose UUIDs are absent from the parent.
  Without it, every quick call duplicates the parent's episode and archives it again.
- **`THALAMUS_FORKED_FROM` and `--agent thalamus-<scope>` are both launcher obligations**,
  and both should be asserted against the resulting ledger row before the answer is
  accepted. `--agent` must carry the **parent's own** agent: matching is free, mismatching
  costs a full cache miss, and omitting it is silent — the fork answers in the expert's
  voice and files as `main`.
- **Resolve targets from `$CLAUDE_CONFIG_DIR/sessions/*.json`, not the pin ledger**, and
  refuse on 0 or ≥2 rather than picking. The roster's `updatedAt` is also the cost
  predictor: it is what separates a $0.03 call from a $0.60 one.
- **Prefer a parent between turns.** A mid-turn fork costs 13× a post-turn fork of the
  same parent, and non-interruption means `quick` is reached for exactly when the expert
  is busy. Waiting for the current turn to land is the cheapest available optimisation.
- **Record the call's own cost, and both cache fields.** A cost table without
  `cache_read_input_tokens` is what produced the withdrawal above.

## Not yet measured

- Whether a room-mate can `SendMessage` a quick fork mid-flight. Headless `-p` sessions
  *do* register in the live roster (`kind: "interactive"`, `entrypoint: "sdk-cli"`), so a
  fork is briefly discoverable under its `--name` and visible to `room-guard.sh`.
- A fork taken while the parent is **compacting**, which the atomicity poller says
  nothing about.
- Whether delta-only distillation interacts with the lab/033 problem, where
  distillation's own subprocess transcripts became memory.
- `claude --session-id <uuid>` works alongside `-p`, so the fork's id can be
  pre-assigned rather than parsed out of the envelope — used for both live-parent probes
  here, untested as a launcher contract.
- A `quick` launcher shelling into a room dir it did not provision gets a well-formed
  envelope containing **"Not logged in · Please run /login"** as the answer, with exit 0.
  Found by accident when a system `python3` could not import `harness.pin`; the result
  string needs checking, not just the exit code.
