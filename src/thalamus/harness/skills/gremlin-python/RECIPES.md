# Gremlin Recipe Store — Queries That Earned Reuse

Ad-hoc queries that met the usefulness threshold: **ran against the live graph
and answered a real question a session actually had.** Copy or adapt before
writing a new query from scratch; append when a new one clears the bar. Each
entry records the question, not just the query — future sessions match recipes
by use case as much as by text (question+query example selection is DAIL-SQL's
measured win, arXiv 2308.15363).

Entry template:

```markdown
## <name>
**Question:** <the actual question the session had>
**Surface:** memory_query | gremlin-python
**Validated:** <date> against the live graph
<the query, fenced>
**Notes:** <gotchas, variations> (optional)
```

The ten `memory_query`-surface recipes in the `recall-strategy` skill are
canonical there, not duplicated here: thread lifecycle, provenance walk,
artifact history, consultation audit, claim convergence, evidence head,
retrieval self-audit, and the three contribution/coverage traversals (what a
paper contributed, corpus citation weight, cold sources).

---

## Graph census
**Question:** What does the graph hold right now — how many nodes of each label?
**Surface:** gremlin-python
**Validated:** 2026-07-17 against the live graph

```python
from thalamus.substrate.writer import connect, close_connection
from gremlin_python.process.traversal import T

g = connect()
try:
    print(g.V().group_count().by(T.label).next())
finally:
    close_connection(g)
```

**Notes:** `memory_query` equivalent: `g.V().groupCount().by(label)`.

## Recent sessions in a scope
**Question:** What are the latest distilled sessions on main (sanity check that
distillation is landing)?
**Surface:** gremlin-python
**Validated:** 2026-07-17 against the live graph

```python
from thalamus.substrate.writer import connect, close_connection
from gremlin_python.process.traversal import Order

g = connect()
try:
    rows = (g.V().has_label("Session").has("scope", "main")
            .order().by("timestamp", Order.desc).limit(3)
            .value_map("timestamp", "project").to_list())
    print(rows)
finally:
    close_connection(g)
```

**Notes:** `value_map` returns list-valued properties; take `[0]` when
unpacking.

## Case-insensitive text containment
**Question:** Does the server support case-insensitive text matching (needed
because `TextP.containing` is case-sensitive and recall lowercases keywords)?
**Surface:** gremlin-python
**Validated:** 2026-07-19 against the live graph (0 containing hits vs 4 regex
hits on the judge-survey claims)

```python
import re
from gremlin_python.process.traversal import TextP
from thalamus.substrate.writer import connect, close_connection

g = connect()
try:
    n = (g.V().has_label("Claim").has("scope", "eval-methodology")
         .has("description", TextP.regex("(?i)" + re.escape("llm-as-a-judge")))
         .count().next())
    print(n)
finally:
    close_connection(g)
```

**Notes:** `TextP.regex` uses find semantics (matches anywhere in the value);
always `re.escape` the term so it matches literally. This is what
`reader._keyword_predicate` does — reuse it in substrate code rather than
rebuilding the pattern.

---

## Find orphan vertices (no edges in either direction)

**Question it answered:** "`contract check` reports 1114 orphan Claim vertices —
do they actually exist, or is the checker wrong?" (2026-07-27)

**Surface:** gremlin-python

```python
from gremlin_python.process.graph_traversal import __
from thalamus.substrate.writer import connect, close_connection

g = connect()
try:
    print(g.V().not_(__.both_e()).count().next())
    rows = g.V().has_label("Claim").not_(__.both_e()).element_map().to_list()
finally:
    close_connection(g)
```

**Validated:** returns 1114, matching `thalamus contract check` exactly.

**Notes — the trap that makes this recipe worth storing.** The obvious
formulation is silently WRONG on this provider:

```python
g.V().where(__.both_e().count().is_(0)).count().next()   # returns 0. Always.
```

It does not error. It returns a clean, plausible `0` — which was read as "the
graph is clean" until a single-vertex probe (`g.V(vid).both_e().count().next()`
→ `0` on a vertex the same query claimed did not exist) exposed it. `both_e()`
on a vertex with no edges yields an empty stream, and the `where()` filter drops
the vertex before `count()` ever emits its zero, so the predicate can never be
satisfied by the very vertices it is meant to select.

Use `not_(__.both_e())`. It asks the question directly — "no incident edges" —
instead of asking for a count that an empty traversal never produces.

This is the same failure *class* as the missing-terminal-step bug this skill
opens with: not an error, just silence dressed as an answer. The terminal-step
guard cannot catch it, because the traversal does terminate — it terminates on
the wrong thing.

## Scope census + sessions in a scope before a cutoff
**Question:** How much content sits in `main` that may belong to an expert, and
which pre-fix sessions are the candidates? (the `mis-scoped-main-writes-audit`
thread — pre-`ed18887` agent-picker sessions resolved `main` in every hook)
**Surface:** gremlin-python
**Validated:** 2026-07-28 against the live graph

```python
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import Order
from thalamus.substrate.writer import connect, close_connection

g = connect()
try:
    for label in ("Session", "Claim", "Thread"):
        print(label, g.V().has_label(label).group()
              .by("scope").by(__.count()).next())
    rows = (g.V().has_label("Session").has("scope", "main")
            .order().by("timestamp", Order.asc)
            .value_map("session_id", "timestamp", "project", "summary")
            .to_list())
finally:
    close_connection(g)
```

**Notes:** `group().by(...).by(__.count())` needs the anonymous `__.count()` —
a bare `count()` is a different step and will not compose here. The census is
the denominator the audit needs: a raw main-scope count means nothing without
the per-scope totals beside it.

**Caveat the audit learned:** this identifies a session's *domain*, never its
launch channel. The pin ledger records the **resolved** scope — the very value
the bug got wrong — and the retained transcript's "pinned to the Thalamus
expert scope `X`" string is **confounded**: consultation subagents carry that
same text, so its presence does not mean the session itself was pinned. Neither
source can currently distinguish "mis-scoped expert session" from "main session
that consulted an expert."
