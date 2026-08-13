---
name: track-open-work
description: Where unfinished work goes — the Linear tracker, not a Thread written mid-session. Use BEFORE recording anything a future session should pick up (a known gap, a deferred decision, a defect you are not fixing now), when you are about to reach for `thalamus write`, and when reporting a finding the operator will want to act on later. Covers the boundary a session may not cross, what belongs in the tracker versus the graph, and the Linear mechanics that silently mangle an issue body.
---

# Track Open Work — the tracker is the entrypoint, not the graph

## The boundary

**A session does not write its own memory** (docs/index.md, 2026-08-03). Episodic
writes happen *after* a session ends, by `thalamus extract` over the retained
transcript. `thalamus write` and `thalamus extract --force --write` survive as
operator actions **from outside a session**, and `write-guard.sh` blocks both from
inside one.

Reading `thalamus write` as a general permission is the specific mistake this exists
to stop. The decision's own rationale prices it: distillation writes the session
regardless, so a live write is a *second* pass over the same session — claims are
content-addressed on (kind, normalized description) so a re-phrased one mints a new
node instead of converging, and **threads get fresh ids, so both stay open in
`memory_open_threads`, the surface the next session reads first.** The 2026-08-11
close design rejected an alternative for the same reason: "a synthetic Session
corrupts the entrypoint the 2026-08-03 decision protects."

The one write verb a session does hold is **closing** a thread, and only through
approval: `thalamus thread propose` writes a ledger row and nothing to the graph, then
the operator approves. Report the title, a 1–2 sentence description, **and** the
proposal id — all three, every time. The operator approves remotely and cannot read
the ledger to find out what they are approving.

## Where a thing goes

| It is… | Where |
|---|---|
| Work a future session should pick up | **Linear** — file it |
| Something this session learned or decided | Say it plainly in the final message; distillation writes it once, properly |
| A thread that is now finished | `thalamus thread propose` → operator approves |
| A design decision that is settled | The decision log in `docs/index.md`, in the same change |
| A measured finding | `lab/`, and the graph via `thalamus ingest` if it is literature |

The split is about *audience*. The graph is what an agent recalls; the tracker is what
the operator reads to decide what a session should do next. An open thread is served
into briefs and recall whether or not anyone intends to act on it — which is why 402
open threads against 97 closed became unworkable, and why the operator asked for a
tracker they can see and order.

## Filing to Linear

Workspace `nodeglass`, project **Claude Code Agent Reports**
(`886f6608-1318-4ad0-9b10-b42a266cb7c1`), team **Thalamus** / `THA`. Resolve it by id
or by listing; never create a project or team. The tools are deferred — load them in
one call:

```
ToolSearch: select:mcp__linear-server__get_issue,mcp__linear-server__save_issue,mcp__linear-server__save_comment,mcp__linear-server__list_issues
```

**Write the whole body in one `save_issue` call.** `patch` operations were observed
failing *per operation* while the call still returned success, and the response echoed
the unapplied state — so only an independent re-read catches it. If you must patch,
re-read with `get_issue` afterwards and do not trust the echo.

### The autolinker will eat your file references

Linear's autolinker runs **after** markdown parsing and strips the code mark from
anything shaped like `host:port`. So a bare `attribution.py:167` becomes a dead
`http://attribution.py:167` link — and backticking the whole reference does **not**
save it.

- **Broken:** `` `attribution.py:167` ``
- **Works:** `` `attribution.py` ``\:167 — close the code span before the colon
- Also safe: anything inside a fenced code block, and a bare `:NNN` on its own

**Comment bodies round-trip raw markdown untouched**, so a comment needs none of this.
That also means comments cannot be used to test how a description will render — the
two go through different pipelines.

### What a good issue carries

Write it for someone starting a session cold, with no context from yours:

- **The defect or gap, stated as a claim** — not "look into X".
- **How it was measured**, with the numbers and the corpus. `999 cases / 8,446
  verdicts` is actionable; "seems biased" is not.
- **What was already decided**, and by whom — a consultation ticket id, a decision-log
  date. This is what stops the next session re-litigating it.
- **What is deliberately NOT to be done**, when a plausible approach has been ruled
  out. The reason a rejected option was rejected is the most expensive thing to
  rediscover.
- **Whose call the open decision is.** If it is the operator's, say so and leave the
  issue open on that, not on the work.

## Before you file

Check the graph first — `memory_exchanges(query=...)` for a question an expert has
already settled, `memory_open_threads(topic=...)` for work already tracked. A tracker
entry that duplicates a settled consultation costs the next session the same rounds
over again (lab/055).
