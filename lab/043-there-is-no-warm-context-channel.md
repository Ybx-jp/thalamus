# 043 — There is no warm-context channel

**Ends in: a wall. The `fork` subagent type does not exist in this harness, and the
spawn regime that *is* available gives cold context. The quick protocol's whole
latency argument rests on a primitive Claude Code does not expose — but the same
measurement clears in-process subagents of the corroboration hazard entirely.**

**Date:** 2026-08-08 · **Harness:** Claude Code, session `4a4b3c44` · **Status:**
measured, n=1 per arm, with a negative control

## Why

The room design needs a fast tier. The proposal was to **fork** the consulted session
so it answers immediately from warm context without losing its place — attacking the
real cost, which is cold-context reconstruction (tonight's consultations: 303s, 372s,
383s, 417s, 462s). Two things had to be true: forks must exist, and a fork must not
distil as its own session, or every quick exchange would mint an extra correlated
witness of a conversation it merely inherited.

## Measured

**1. `fork` is not available.** `Agent(subagent_type: "fork")` returns
`Agent type 'fork' not found`, and the registry lists only `claude`,
`claude-code-guide`, `Explore`, `general-purpose`, `Plan`, `statusline-setup`, and the
four generated `thalamus-<scope>` experts. The Agent tool's own documentation mentions
`subagent_type: "fork"` in a parenthetical about model inheritance; that mention is not
a capability in this build. **Reading a tool description is not measuring a harness.**

**2. In-process subagents are not sessions.** A `general-purpose` subagent probing its
own environment reported `SESSION_ID=4a4b3c44-79af-4c4b-b815-ee6a50b640a9` — **the
parent's id, verbatim**. Across the spawn: pin-ledger rows 1205 → 1205, transcript
files 90 → 90, zero rows appended since t0. No SessionStart fired, no hooks armed, no
transcript of its own. This confirms docs/02's "sidechains in the parent session's
JSONL" by direct observation rather than by design intent.

**3. And they are cold.** Asked whether it could see the parent's in-flight work, the
subagent said no, and enumerated what it *did* hold: its task prompt, CLAUDE.md and
environment boilerplate, and a git-status snapshot. Fresh context, not inherited.

**4. Negative control — the sandbox guard holds.** A `thalamus ingest` dry run spawns a
headless `claude -p` for extraction; ledger delta was **0**. So the absence in (2) is
the subagent genuinely not being a session, not the ledger being broken. (An earlier
cluster of six ledger rows during a batch ingest was other concurrent sessions on the
machine, not extraction subprocesses.)

## What it means

**The corroboration hazard is a property of the spawn regime, not of the room.**

| | own session id | hooks arm | own transcript | distils separately | context |
|---|---|---|---|---|---|
| In-process subagent (Agent tool) | no — parent's | no | no (sidechain) | **no** | cold |
| Separate process (Agent Teams teammate, lab/004 T2; pinned tmux window) | yes | yes | yes | **yes** | cold |

A room assembled from **in-process subagents cannot manufacture corroboration** — there
is only ever one Session vertex, so N witnesses of one conversation is not a state the
graph can enter. A room assembled from **pinned tmux windows can**, and that is exactly
what `thalamus roster` / `thalamus spawn` produce, so it is the likely shape of any real
room. The `room` property (docs/09) is aimed at the second regime and is unnecessary for
the first.

**The wall: neither regime gives warm context.** In-process subagents start cold;
separate processes start cold. There is no channel in this harness by which a session
answers a question *from its current working state* without reconstructing it. So the
latency the quick protocol was designed to avoid is not avoidable by forking here — it
is the price of the isolation that makes subagent answers independent in the first
place, which is also what lab/025 measured as worth paying (a self-answered ticket filed
8 citations against a voiced subagent's 25).

The two properties are coupled, and not by accident: the thing that makes a subagent's
answer *independent* is the same thing that makes it *slow*.

## Consequences

- The fork-based quick protocol is **not buildable on this harness today**. Recheck when
  a fork or resume-with-context primitive appears; the measurement is two tool calls.
- Cheap tier candidates that survive: skip the brief and the citation gate while keeping
  the Exchange record (the record costs microseconds — the grounding costs the minutes),
  or a warm channel built outside the harness rather than inside it.
- `room` remains correct for the process-per-member regime and is dead weight for the
  in-process one. Which regime a room uses is therefore a schema-relevant decision, not
  only an isolation one.
