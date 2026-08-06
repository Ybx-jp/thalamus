# 040 — The floor that skipped the entrypoint

**Ends in: gap, measured — the fix is a schema change, not a line.**

[lab/005](005-transcript-ingress-canary.md) canary-tested the transcript-ingress floor
and found a poisoned `WebFetch` result lands tier 2. That result holds. It is narrower
than the row it earned in [docs/05](../docs/05-trust-model.md): the floor covers
`Claim` subtypes and skips `Thread` — the one node type the graph serves first,
unprompted, to every new session.

## What broke

`apply_ingress_floor` (`harness/extraction.py:484`) returns a `model_copy` that updates
exactly three collections:

```python
update={
    "decisions": floor(graph.decisions),
    "problems":  floor(graph.problems),
    "solutions": floor(graph.solutions),
}
```

`graph.threads` is not among them. Probe — one poisoned string, one `Decision` and one
`Thread` carrying it verbatim, floored against that string as the external corpus:

```
DECISION external=True tier=2      # floored
THREAD   provenance=None           # untouched
```

`writer.py:330` then resolves `thread.provenance or session.default_provenance()`, and
`default_provenance()` is tier-1 `FIRST_PARTY` by construction. So the thread is written
first-party. The contract does not catch it either: the laundered-ingress audit at
`contract/conformance.py:223` keys on `vertex.label == "Claim"`, and a `Thread` vertex
never carries that label.

The exposure is worse than a missed node, because of *which* node it is. `Thread`'s own
docstring calls threads "the primary entrypoint into the graph," `_write_threads` merges
them by ID **across sessions within a scope**, and the SessionStart hook instructs every
session to open with `memory_open_threads`. An unfloored thread description is therefore
persistent, cross-session, and read before the session has any other context — the
strongest position in the graph, reached by the one path with no tier marking on it.

## Why (root cause)

Not an oversight in the update dict. `Thread` is a bare `BaseModel`
(`substrate/schema.py:278`), not a `Claim` subclass, and it has no `external` field —
only `provenance`. Three consequences line up behind that one fact:

- `floor()` sets `{"external": True, "provenance": floored}`; it cannot mark a `Thread`.
- `SessionGraph.claims()` is `[*decisions, *problems, *solutions]`, so threads are
  invisible to every guard written against `claims()`, including the early-return at
  `extraction.py:521`.
- The conformance audit's `external ∧ tier<2` rule has no field to test.

The floor and the audit agree with each other perfectly, and both are scoped to the
same node types. The mark is what the defense is made of, and `Thread` cannot carry it.

## The one-line fix does not work

Adding `"threads": floor(graph.threads)` type-checks, runs, and silently does nothing
on the write path. Measured:

```
naive model_copy external attr=True serialized=False
```

Pydantic's `model_copy(update=...)` skips validation, so it sets the attribute in memory
and `model_dump()` drops it — the thread would reach the writer with `provenance`
correctly floored but the `external` flag gone, which is precisely the half the
conformance audit reads. A guard that appears to be armed and is not is worse than the
current state, where the gap is at least legible in the source.

The real fix is `external: bool` on `Thread` (or lifting the two fields into a mixin
shared with `Claim`), plus widening the conformance predicate past `label == "Claim"`.
That is a schema change and a contract change, so it goes through
`uv run thalamus contract check`, not a patch.

## Status

Unmeasured as an attack. This entry is a code-path finding, not a canary — no poisoned
fetch has been driven end to end into a thread the way lab/005 drove one into a claim.
A third canary is queued in docs/05, and it is cheaper than the other
two: the ingress path is already closed and instrumented, so the canary only has to
show the extractor opening a thread that carries the fetched text.

## How it surfaced

Not from an audit. It fell out of checking a claim made in conversation — whether
session distillation can see tool results at all — while drafting a reply about
wrapping tool calls in a scanning sub-agent. The belief under test was that the digest
excludes tool results; it does not (`render_digest`, `extraction.py:69`, 400-char clip).
Reading the floor to confirm that is what exposed the node-type scope. Worth recording
because the prior for this class of finding is *re-reading a defense you already
believe is closed*, and lab/005's own success is what made it unlikely anyone would.
