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

The seven `memory_query`-surface recipes in the `recall-strategy` skill are
canonical there, not duplicated here: thread lifecycle, provenance walk,
artifact history, consultation audit, claim convergence, evidence head,
retrieval self-audit.

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
