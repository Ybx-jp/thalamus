---
name: gremlin-python
description: The fine details agents get wrong when writing Gremlin against the Thalamus graph — terminal steps (lazy traversals that silently do nothing), the gremlin-lang vs gremlin-python dialect split, Python's renamed steps, and the house connection idiom. Use BEFORE writing any gremlin-python code (lab scripts, eval/substrate code, ad-hoc Bash python), when a traversal "ran" but returned nothing or a GraphTraversal repr, when memory_query rejects a dialect slip, or before writing a new ad-hoc query at all — proven ones live in RECIPES.md.
---

# Gremlin for Agents — the Details That Bite

Two query surfaces exist in this project, and they speak **different dialects**.
Most doomed queries are one dialect written on the other surface.

| | `memory_query` (MCP) | gremlin-python (code) |
|---|---|---|
| What you write | gremlin-lang **string** | Python method chain |
| Step names | camelCase: `hasLabel`, `outE`, `valueMap` | snake_case: `has_label`, `out_e`, `value_map` |
| Terminal step | **None — the server iterates** | **Required — nothing runs without one** |
| Keyword clashes | none | underscore-suffixed: `as_`, `in_`, `not_`, … |
| Guard | lexical guard in `substrate/query.py` rejects mutation *and* python dialect | `gremlin-guard.sh` PreToolUse hook blocks inline traversals with no terminal step |

For `memory_query` strategy (when to use it at all, cost discipline), see the
`recall-strategy` skill. This skill is the *authoring* reference, and its rules
below are gremlin-python's.

## Rule 1 — every traversal ends in a terminal step

gremlin-python traversals are **lazy**. `g.V().has_label('Claim')` builds
bytecode and sends **nothing** to the server. No error. Silently nothing.

Terminate every traversal with exactly one of:

- `.to_list()` — run it, return all results as a list
- `.next()` — run it, return the next (usually only) result
- `.iterate()` — run it for its effects, discard results (the writer's idiom)
- `.has_next()` — run it, return whether a result exists
- consuming it as an iterator (`for x in t`, `list(t)`, `next(t)`) also runs it

`count()`, `fold()`, `value_map()` are **not** terminal — `g.V().count()` still
needs `.next()`. The PreToolUse guard (`gremlin-guard.sh`) blocks inline Bash
python that builds a traversal and never terminates it.

## Rule 2 — Python renames clashing steps with a trailing underscore

Steps: `all_() and_() any_() as_() filter_() from_() id_() is_() in_() max_()
min_() not_() or_() range_() sum_() with_()`.
Tokens: `Scope.global_`, `Direction.from_`, `Operator.sum_`.
Cardinality value functions live on `CardinalityValue`, not `Cardinality`.

Writing `g.V().as('a')` is a Python `SyntaxError`; writing `as_` inside a
`memory_query` string is a server parse error. Direction matters.

## Rule 3 — connect the house way

```python
from thalamus.substrate.writer import connect, close_connection

g = connect()  # DEFAULT_URL ws://localhost:8182/gremlin
try:
    rows = g.V().has_label("Trace").limit(5).element_map().to_list()
finally:
    close_connection(g)
```

Anonymous traversals and predicates when needed:

```python
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import P, T, Order, TextP
g.V().where(__.in_("CONTAINS").count().is_(P.gte(2)))
g.V().has("identifier", TextP.containing("reader.py"))
```

## Rule 4 — ad-hoc queries are read-only

The graph's write paths are distillation (`thalamus extract`), `thalamus ingest`
and `thalamus write` only — all of them outside a live session. An
ad-hoc query that mutates is a contract violation even though
gremlin-python will happily do it — the `memory_query` guard's denied-step list
(`substrate/query.py`) is the norm for ad-hoc python too: no `add_v`, `add_e`,
`merge_v`, `merge_e`, `drop`, `property`.

## Rule 5 — check RECIPES.md before writing, add to it after validating

[RECIPES.md](RECIPES.md) is the store of ad-hoc queries that earned reuse: each
entry records the **question it answered** (so future sessions can match by use
case, not just by query text — example selection by question *and* query is the
measured win of DAIL-SQL, arXiv 2308.15363), the surface, the query, and its
validation. Admission threshold: it ran against the live graph and answered a
real question a session actually had. Copy, adapt, and when a new query clears
that bar, append it. `memory_query`-surface recipes in the `recall-strategy`
skill remain canonical there; RECIPES.md indexes them rather than duplicating.

You do not have to remember the second half mid-task, and measurably will not:
a PostToolUse hook stages every `memory_query` and inline-gremlin Bash call that
ran and returned something. Review the queue with `thalamus eval recipes
--staged` and promote by hand. The hook checks only that a query *ran* — whether
it answered a real question is the half that stays yours, which is why nothing
is written to RECIPES.md automatically.

The store is measured, not trusted: `thalamus eval recipes` smoke-runs every
entry read-only (a recipe that stops executing is an eviction candidate;
eviction is archival, never deletion), and `thalamus eval gremlin` tags live
queries recipe-derived vs from-scratch by traversal shape — reuse is the
store's earn-its-keep signal, weighted by what it displaces, never raw entry
count.

## Rule 6 — a slow traversal is a measurement, not an impression

Every traversal the house issues is timed by *shape* (the folded step sequence, the
same key rule 5 uses) and aggregated into `~/.thalamus/profiles/`. Two commands,
and they answer different questions:

```bash
thalamus eval profile                       # which shapes this system spends its time in
thalamus eval profile --query "g.V()..."    # where one traversal spends it, step by step
thalamus eval profile --corpus              # the same, over every gremlin-lang recipe
```

The first is wall time, always on, near-free (measured overhead is printed with the
report). The second asks the *server* for its own per-step metrics via TinkerPop's
`profile()`, which reports each step's element count, traverser count, duration and
share of total — the step whose `%dur` is large is where the query is expensive, and
the element count beside it usually says why.

Three things to hold when reading either:

- **Do not compare the two channels' milliseconds.** `profile()` impedes the
  traversal it measures ("durations are best considered in relation to each other" —
  TinkerPop reference). This repo has the same artifact measured on itself:
  `contract check` runs 10.29/10.35/10.36 s plain and 37.69/38.02 s under cProfile.
- **One reading is not a finding.** The report gives p50/p95/max and a call count for
  exactly this reason; a single pair of runs cannot support "X is faster than Y".
- **Element counts transfer off this machine; milliseconds do not.** Quote the counts
  when you are describing why a traversal is expensive.

The common finding this surfaces is a full-graph materialisation hiding behind a
short query — `g.V().valueMap()` and `g.E().elementMap()` are two steps and most of a
`contract check`'s wall time. The second common one is an unindexed `has()` filtering
a large edge sweep: the `HasStep` carries the `%dur`, the `VertexStep` above it
carries the element count that explains it.

## Deeper reference

`gremlin-docs/`, beside this skill, is a local gremlin-python-focused subset of the
TinkerPop reference — routing table in [its index](gremlin-docs/index.md).
Read the *specific file* for your problem, not the tree: steps are in
`06-steps/` by category; the python driver (connection options, statics,
lambdas, DSLs, event-loop limitations) is `12-gremlin-python.md`.

## Grounding

Schema-aware LLM-written graph queries: Multi-Agent GraphRAG (arXiv 2511.08274).
Deterministic pre-execution feedback as the cheap half of execution-feedback
self-correction: Self-Debugging (arXiv 2304.05128). Question+query example
stores for generation: DAIL-SQL (arXiv 2308.15363).

Reporting a timing at all: distributions with their n rather than a mean (Hoefler &
Belli, SC 2015; Georges, Buytaert & Eeckhout, OOPSLA 2007), and a machine-independent
count reported beside the machine-dependent duration (HELM separates an *idealized*
runtime that compares across systems from the per-request runtime a user experiences
— Liang et al., arXiv 2211.09110, TMLR 2023). Profilers are themselves biased measurements — Mytkowicz,
Diwan, Hauswirth & Sweeney, "Evaluating the Accuracy of Java Profilers" (PLDI 2010).
