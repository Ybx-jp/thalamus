# 030 — The miss rate was the consultation, and the floor never cut fan-out

**Date:** 2026-07-29 · **Component:** retrieval (`recall()`), consultation coverage · **Status:** measured. Corrects [lab/029](029-the-bleed-that-was-not-a-leak.md)'s attribution of the fan-out drop.

## What was asked

lab/029 verified lab/007's fan-out prediction and reported, as an unpredicted
cost, that `memory_recall`'s miss rate went 0% → 41% after the match floor
shipped. This entry is that number, taken apart.

## The 41% is consultation, not recall quality

Post-floor `memory_recall` traces in scope `main`, split by whether the call
carried a consultation ticket (`exchange_id` on the Trace):

| | recalls | misses | rate |
|---|---|---|---|
| under a ticket — searches one **expert's** subgraph | 110 | 64 | **58%** |
| no ticket — searches main + knowledge scopes | 71 | 10 | **14%** |

**64 of the 74 misses are consultation recalls.** A ticket redirects retrieval
into a single expert subgraph holding tens of nodes rather than thousands, and
the `ground-in-literature` protocol explicitly tells the voiced expert to run
several distinct recalls and to report what it could not find. A miss under a
ticket is the coverage-gap signal doing its job, not a retrieval defect.

By consulted expert:

| expert | recalls | misses | rate |
|---|---|---|---|
| eval-methodology | 68 | 51 | **75%** |
| homelab | 21 | 8 | 38% |
| literature | 23 | 5 | 22% |

The eval-methodology subgraph does not hold what its consultations ask of it.
That is the quantitative form of something the scope already says about itself
in prose — `scope:eval-methodology:claim:95cd7991b3b59282` records off-policy
evaluation and counterfactual learning-to-rank as an unprocured hole, and the
2026-07-29 ticket said so again unprompted. **Consultation miss rate is a
per-expert coverage metric that costs nothing to compute**, and it belongs
beside the cold-sources count in
`cold-literature-sources-attribution-followup`.

The floor's own contribution to empties, replaying all 181 post-floor queries
against today's graph in the live configuration: **3 queries, 1.7%.** Not the
cause of anything here.

## The floor never cut fan-out — the correction to lab/029

lab/029 credited the floor with the fan-out drop, on the strength of an
untreated control (`memory_open_threads`, which the floor does not touch, moved
the opposite way). **That control was weaker than the entry claimed.** It holds
corpus growth fixed, but `memory_open_threads` takes a *project parameter*, not
free text — an agent cannot write a narrower one. So it does not control for
query shape, and query shape is the variable that actually moved.

Replaying real logged queries against today's graph, one dial at a time:

| held fixed | varied | fan-out | empty |
|---|---|---|---|
| cap=8 | floor 1 → 2 | 27.5 → **27.3** | 2 → 17 |
| floor=2 | cap off → 8 | 29.7 → **27.3** | 17 → 17 |
| floor=2, cap=8 | pre-floor → post-floor **queries** | 38.0 → **27.3** | — |

- **The match floor cuts no fan-out at all** (−1%, inside noise; +4% once
  knowledge scopes are served). It is a query-level gate, not a per-result
  trimmer: either enough sessions clear two distinct hits and nothing changes,
  or none do and the result is empty. It cannot trim a result it does not empty.
- **The detail cap cuts 8%** — the same cap lab/007 called arbitrary and nobody
  has tuned.
- **Query shape cuts 28%**, the largest single factor, holding graph and dials
  constant. Median keywords per recall fell 9 → 5 and mean length 111 → 45 chars
  across the same boundary. The `recall-strategy` skill, which teaches narrow
  lexical queries, shipped in that window.

So the honest attribution of lab/029's 41.9 → 11.2: **mostly the agent learning
to ask narrower questions, some detail cap, none of it the floor.** lab/007
predicted the right outcome from the wrong mechanism, and lab/029 confirmed the
outcome without separating the mechanisms.

## The floor is still worth keeping

Inspecting what it suppresses settles it. The queries it turns into misses are
literature-shaped, and their top suppressed hit is an unrelated session that
matched on one accidental term:

    "hierarchical community detection Leiden modularity" -> a WezTerm terminal-theme session
    "LLM-as-a-Judge survey"                              -> a SessionEnd hook fix
    "graphrag community summarization"                   -> a readiness-advisor draft correction

That is precisely the noise lab/007 built the floor to reject. **The floor earns
its place on precision, not on fan-out** — it converts an accidental one-word
match into an honest empty. Its cost concentrates at the narrowest widths it
does not exempt (`floor = min(2, len(keywords))` lets a 1-keyword query
through but demands *both* terms of a 2-keyword one), which is worth watching
now that the skill actively teaches narrow queries.

## Three instrument errors, all caught, all cheap

Recorded because the checklist added to `recall-strategy` this same day is
exactly what caught them, and because each produced a confident wrong number
first:

1. **`_DETAIL_CAP` is bound as a default argument** (`def _select_details(...,
   cap: int = _DETAIL_CAP)`), so patching the module constant changed nothing
   and the first 2×2 showed the cap having *zero* effect. Python binds defaults
   at definition time; the dial is `__defaults__`.
2. **The tap stores `f"{tool}: {query}"`**, not the query. Replaying the stored
   string prepends a token matching nothing in the corpus, which under a
   two-distinct-hit floor guarantees an empty — manufacturing a "100% of
   2-keyword queries miss" result that was entirely the instrument.
3. **The replay omitted `knowledge_scopes`**, which the live server always
   passes. Serving knowledge as production does dropped the measured empty rate
   from 9.4% to 2.2% — a 4× error, concentrated in exactly the
   literature-flavored queries the analysis was about.

Each was caught by the same move: the result was surprising, so the instrument
was suspected before the system. The first two inverted a conclusion; the third
changed it by 4×.
