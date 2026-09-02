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

---

## Exchanges an expert answered
**Question:** What consultations has this expert already closed — so a session can
reuse what it said instead of re-deriving it, or audit what it committed to?
**Surface:** gremlin-python
**Validated:** 2026-07-30 against the live graph (3 rows for `literature`, 3 for
`eval-methodology`)

```python
from thalamus.substrate.writer import connect, close_connection
from gremlin_python.process.traversal import Order, T

g = connect()
try:
    rows = (
        g.V()
        .has_label("Exchange")
        .has("expert", "literature")
        .has("status", "answered")
        .order().by("answered_at", Order.desc)
        .limit(5)
        .value_map(True)
        .to_list()
    )
    for row in rows:
        print(row[T.id], row.get("from_scope"), row.get("answered_at"))
finally:
    close_connection(g)
```

**Notes:** Filter on the `expert` **property**, not on scope. An Exchange vertex is
always `scope:main:exchange:<ticket>` — consultation routes through `main`, never
expert-to-expert — so `.has("scope", "literature")` returns nothing and looks like
"this expert has never been consulted". `status` is `open` until `consult_answer`
lands, so the answered filter is what separates a record from a live question. The
shipped path is `reader.recall_exchanges` / the `memory_consultations` MCP tool.

## Exchanges a scope took part in — either side

**Question:** Has anyone been consulted about X already? Asked from `main`, which is the
*asker* of nearly every exchange and the answerer of none — so the `expert` filter above
returns nothing and reads as "never consulted".
**Surface:** gremlin-python
**Validated:** 2026-08-11 against the live graph (5 rows for `main` on "harness
capability contract", including the two rounds that settled a design a later session
then re-derived)

```python
from thalamus.substrate.writer import connect, close_connection
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import Order, T

g = connect()
try:
    rows = (
        g.V()
        .has_label("Exchange")
        .has("status", "answered")
        .or_(__.has("expert", "main"), __.has("from_scope", "main"))
        .order().by("answered_at", Order.desc)
        .limit(50)
        .value_map(True)
        .to_list()
    )
    for row in rows:
        print(row[T.id], row.get("from_scope"), str(row.get("question"))[:70])
finally:
    close_connection(g)
```

**Notes:** `or_`, not `or` — Rule 2. Both branches are anonymous `__.has(...)`, so the
import is `graph_traversal.__`, not the predicate module. Order by `answered_at` and
rank in Python afterwards: recency alone put the exchange that mattered sixth of seven.
Do **not** print the `answer` values — they run 15k–40k characters each and five of them
will bury the session that ran the query. Read one by id once the index names it. The
shipped path is `reader.search_exchanges` / `reader.read_exchange` and the
`memory_exchanges` MCP tool.

## One session's subgraph census, by exact vertex id
**Question:** For a named session, how much did it actually write — and does it have
a Source at all (i.e. was it distilled, or written some other way)?
**Surface:** gremlin-python
**Validated:** 2026-08-03 against the live graph

```python
from thalamus.substrate.writer import connect, close_connection
from gremlin_python.process.graph_traversal import __

vid = "scope:main:session:758d17ea-2b9e-45a8-b121-d4ce5568ef6b"
g = connect()
try:
    rows = (g.V(vid)
            .project("claims", "threads", "sources")
            .by(__.out("CONTAINS").count())
            .by(__.out("SPAWNS").count())
            .by(__.out("DERIVED_FROM").count())
            .to_list())
    print(rows)
finally:
    close_connection(g)
```

**Notes:** Build the id — `scope:<scope>:session:<full-uuid>` — and hand it to `g.V(id)`
for an O(1) lookup. Do **not** reach for a session by id prefix: `has(id,
TextP.containing("bc0ca43e"))` forces a full scan that does not return on a graph this
size. `sources=0` is the signal worth reading: distillation always writes the archived
transcript as a Source and a `DERIVED_FROM` edge to it, so a session with claims and no
Source got them from somewhere other than `thalamus extract`, and has no provenance
floor. `ingested_at` cannot tell you how many write passes a session saw — it carries
the *session's* timestamp and is overwritten on every re-upsert (decision log
2026-07-30) — and Claims carry no `written_at`, since content addressing means their
text never moves.

## Witnessed-vs-used: did an answer cite what its own brief served?
**Question:** A consultation is a two-party room — the brief is what the expert saw,
the validated answer's citations are what it provably used. Replaying a proposed
use-gate against those existing labels needs the (exchange, witnessed-claim) universe
and its positive rate, before any experiment is built.
**Surface:** gremlin-python
**Validated:** 2026-08-08 against the live graph (48/55 answered exchanges non-empty;
807 pairs, 89 positives, base rate 0.110)

```python
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T
from thalamus.substrate.writer import connect, close_connection

g = connect()
try:
    rows = (
        g.V().has_label("Exchange").has("status", "answered")
        .project("id", "expert", "witnessed", "cited")
        .by(T.id)
        .by("expert")
        .by(__.union(
            __.out_e("REFERENCES").has("role", "brief").in_v().has_label("Claim"),
            __.out_e("REFERENCES").has("role", "brief").in_v().has_label("Session")
              .out("CONTAINS").has_label("Claim"),
        ).id_().dedup().fold())
        .by(__.out_e("REFERENCES").has("role", "citation").in_v()
              .has_label("Claim").id_().dedup().fold())
        .to_list()
    )
    for row in rows:
        hit = set(row["witnessed"]) & set(row["cited"])
        print(row["expert"], len(row["witnessed"]), len(row["cited"]), len(hit))
finally:
    close_connection(g)
```

**Notes:** The union is load-bearing and was found by falsifying a wrong result. Using
`role:brief` targets *directly* as the universe returns a clean zero in all 55
exchanges, which reads as "experts ignore their briefs" but is pure schema: briefs
serve Threads (124) and Sessions (122) far more than Claims (77), while answers cite
Claims (999). The two roles point at near-disjoint label populations, so the direct
intersection is structurally empty. The real signal is one hop out, through
`Session -CONTAINS-> Claim`. Always check the label breakdown of both edge roles
before intersecting them. Cluster on the **exchange**, never the pair — 89 positives
sat in 12 exchanges with 79% in one expert's.

## Claims no session contains — knowledge, or orphans?

**Question it answered:** "Which claims does no `Session` contain, and is that by
design or is it damage?" `memory_open_problems` admits only session-contained claims,
so anything outside that set is invisible to it and the split decides whether that is
correct. (2026-08-13)

**Surface:** gremlin-python

```python
from gremlin_python.process.graph_traversal import __
from thalamus.substrate.writer import connect, close_connection
from collections import Counter

g = connect()
try:
    total = g.V().has_label("Claim").count().next()
    rows = (g.V().has_label("Claim").not_(__.in_e("CONTAINS"))
            .value_map("source", "kind", "scope").to_list())
    first = lambda r, k: (r.get(k)[0] if isinstance(r.get(k), list) and r.get(k) else "?")
    print(total, len(rows))
    print(Counter(first(r, "kind") for r in rows))          # knowledge vs episodic
    print(Counter(first(r, "source").split(":")[0] for r in rows))   # actor vs orphan
finally:
    close_connection(g)
```

**Validated:** 6163 of 9512 claims are session-less, but 6150 are `literature/*` from
`thalamus ingest` — served on purpose by the `not_(in_e("CONTAINS"))` knowledge branch
in `reader.py`. Only **13** are of an episodic kind, and `source` splits them cleanly:
`agent:` prefixes are written by a non-session actor, `session:` prefixes are claims
orphaned from a session that no longer holds them.

**Notes.** The headline count is the trap. "65% of claims have no session" sounds like
a systemic break and is almost entirely one deliberate representation; the real
population is found by filtering to episodic kinds first. Split on the `source` prefix
before concluding anything — a session-less claim whose provenance still names a
`session:` is an orphan, and one naming an `agent:` never had a session to lose.

Reach for `element_map()` when confirming *which* vertices came back. An early cut of
this query guessed `value_map("statement", "provenance_source")` and printed blank
rows — the properties are `description` and `source`. A guessed property name does not
error, it returns empty strings, which reads as "found nothing" when the truth was
"found everything and asked it the wrong question."


## What a Source actually holds — claims and excerpts hang off it, not under it

**Question it answered:** "Did that `thalamus ingest` run write anything?" The obvious
traversal — `Source` out through `CONTAINS` — returns a clean `0` for a source that in
fact carries dozens of claims, because the edge runs the other way and carries a
different name. (2026-08-22)

**Surface:** gremlin-python

```python
from gremlin_python.process.graph_traversal import __
from thalamus.substrate.writer import connect, close_connection

g = connect()
try:
    sid = "scope:designer:source:<hash>"
    claims = g.V(sid).in_("DERIVED_FROM").has_label("Claim").count().next()
    chunks = g.V(sid).in_("DERIVED_FROM").has_label("Chunk").count().next()
    # what the source is about, via its claims
    ents = (g.V(sid).in_("DERIVED_FROM").has_label("Claim")
            .out("ABOUT").values("name").dedup().to_list())
    print(claims, chunks, len(ents))
finally:
    close_connection(g)
```

**Validated:** 2026-08-22 against the live graph. On
`scope:designer:source:e854b6b9a497…` (Cutting 2016, *Narrative theory and the dynamics
of popular movies*), `out("CONTAINS")` returns **0** while `in_("DERIVED_FROM")` returns
**85 claims and 125 excerpts**, and walking on through `ABOUT` names 12 entities. The
same `0` came back for all nine sources of that ingest batch, which together hold 464
claims and 709 excerpts.

**Notes.** `CONTAINS` is the session-privacy edge (`Session -CONTAINS-> Claim`), and it
is the *only* thing that edge means; provenance to a document is a separate edge in the
opposite direction, `Claim -DERIVED_FROM-> Source`. Confusing them is easy because both
sound like containment in English.

The failure mode is the one this file keeps finding: a wrong-but-legal traversal returns
an empty result rather than an error, and an empty result reads as a finding. Before
concluding a write did not land, run the traversal against a source you *know* is
populated — if it also returns `0`, the query is wrong, not the data.

## Is memory being written? — counts and the newest Session
**Question it answered:** "After installing, how does anyone confirm distillation is
actually landing sessions in the graph?" — the read behind `thalamus status`
(harness/status.py).
**Surface:** gremlin-python
**Validated:** 2026-08-21 against the live graph — 303 sessions, 34313 vertices,
newest `d47288c9` at `2026-08-22T00:59:56` (project thalamus, scope designer).

```python
from gremlin_python.process.traversal import Order

from thalamus.substrate.writer import close_connection, connect

g = connect()
try:
    total = g.V().has_label("Session").count().next()
    newest = (g.V().has_label("Session")
              .order().by("timestamp", Order.desc).limit(1)
              .value_map("session_id", "timestamp", "project", "scope", "tool")
              .to_list())
    print(total, newest)
finally:
    close_connection(g)
```

**Notes.** `timestamp` is stored as an isoformat *string*, so `Order.desc` on it is a
lexical sort — which is the right answer only because every writer stamps the same
zero-padded UTC isoformat (`_upsert_session_vertex`, writer.py). A row written in any
other format would sort wrong rather than error.

Count first and read second, guarded on the count. `order().by(...).limit(1)` on an
empty label returns `[]` rather than raising, so an unguarded version of this reports
"no sessions" and "could not read the newest" as the same thing — and on a fresh
install those are the *only* rows there are.

## Does `kind` behave like an identity criterion or like a role?
**Question it answered:** Claim identity is `(kind, normalized_description)`
(`schema.py`), so the same sentence asserted as a `problem` and as a `decision`
forks into two vertices. Does that actually happen in the live graph, and at what
rate? (schema-coherence design room, 2026-08-25)
**Surface:** gremlin-python
**Validated:** 2026-08-25 against the live graph — 2 cross-kind descriptions out of
17512 distinct (both `decision`/`solution`); 13 claims whose vertex id no longer
matches a recomputed `content_id`.

```python
from collections import Counter, defaultdict
from gremlin_python.process.traversal import T
from thalamus.substrate.schema import Claim, _normalized
from thalamus.substrate.writer import connect, close_connection

g = connect()
try:
    rows = (g.V().has_label("Claim").project("id", "kind", "description", "scope")
            .by(T.id).by("kind").by("description").by("scope").to_list())
finally:
    close_connection(g)

by_desc = defaultdict(list)
for r in rows:
    by_desc[_normalized(r["description"])].append(r)
multi = {d: rs for d, rs in by_desc.items() if len({r["kind"] for r in rs}) > 1}
print(len(by_desc), len(multi))          # denominator first, then the hits

mism = [r for r in rows
        if r["id"].rsplit(":", 1)[-1]
        != Claim(kind=r["kind"], description=r["description"]).content_id()]
print(len(mism), Counter(r["kind"] for r in mism))
```

**Notes.** Do the grouping in Python, not server-side: a `group().by('description')`
over every Claim materialises the whole corpus into one map and the counts you want
are one dict comprehension away anyway. Normalise with the schema's own
`_normalized` — grouping on the raw property answers a different question than the
identity function does, and here the two happen to agree only because no pair
differs by whitespace alone.

Report the denominator with the hit count. "2 collisions" is unreadable without
"of 17512 distinct descriptions"; a near-zero rate is a finding only when its base
is stated.

**Call `Claim(...).content_id()`, never a local reimplementation of the hash.** The
payload, the separators and the digest length are `schema.py`'s to change; a recipe
that inlines them keeps returning confident answers after they do.

The id-vs-recomputed-`content_id` check is the second half and catches a different
thing: a vertex whose identity-bearing text was written after the id was minted keeps
the old id, so identical `(kind, scope, description)` triples can sit on two distinct
vertices. Recomputing is the only way to see it — `thalamus contract check` passes
clean on all of them, because nothing verifies that a content-addressed vertex still
hashes to its own address.

The 13 this found are two populations, and the split is `twin exists / no twin`
(issue #111): 9 are pre-2026-07-15 vertices left behind by the `9e78ca2` identity
re-key, still reproducing their stored id under the *old* all-substance-fields
formula, each beside a byte-identical live twin; 4 had `description` rewritten in
place by the 2026-07-27 secret scrub and have no twin. Check twin existence before
concluding anything — an orphan mismatch and a duplicated one need opposite repairs.

## Ontology drift — declared vs observed, both directions

**Question:** Which declared node types, kinds, edge types and edge properties does
nothing actually write, and what do writers produce that the ontology never declared?
**Surface:** gremlin-python
**Validated:** 2026-08-25 against the live graph (47,399 vertices, 161,508 edges).
Found `BLOCKS` never written, `DERIVED_FROM.anchors` declared across 31,042
propertyless edges, `ANCHORS.start`/`end` against a model with no such field,
`RETURNS.judged_terms` written and undeclared, and `literature/finding` — a claim
kind — on 2 Entities.

```python
from collections import Counter

from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T

from thalamus.contract.ontology import CORE_EDGES, CORE_NODES
from thalamus.substrate.writer import close_connection, connect

g = connect()
try:
    vlabels = {str(k): v for k, v in g.V().group_count().by(T.label).next().items()}
    elabels = {str(k): v for k, v in g.E().group_count().by(T.label).next().items()}
    print("declared node types never written:",
          sorted({n.label for n in CORE_NODES} - set(vlabels)))
    print("declared edge types never written:",
          sorted({e.label for e in CORE_EDGES} - set(elabels)))

    for n in CORE_NODES:
        if not n.kinds:
            continue
        seen = {str(k) for k in g.V().has_label(n.label).group_count().by("kind").next()}
        print(f"{n.label}: unwritten={sorted(set(n.kinds) - seen)} "
              f"undeclared={sorted(seen - set(n.kinds))}")

    for label in sorted(elabels):
        keys = {str(k) for k in g.E().has_label(label).properties().key().dedup().to_list()}
        print(f"{label} properties observed: {sorted(keys)}")

    # Endpoint label pairs, for promoting `note` prose to from_labels/to_labels.
    rows = (g.E().project("e", "o", "i").by(T.label)
            .by(__.out_v().label()).by(__.in_v().label()).to_list())
    for pair, n in sorted(Counter(
        (str(r["e"]), str(r["o"]), str(r["i"])) for r in rows
    ).items()):
        print(f"  {pair[0]}: {pair[1]} -> {pair[2]}   ({n})")
finally:
    close_connection(g)
```

**Notes.** `properties().key().dedup()` per edge label is the cheap way to the
observed property vocabulary — `element_map()` over 161k edges materialises the whole
edge set to answer a question about ~14 strings.

Run the endpoint-pair census **before** promoting any `note` direction string to a
`from_labels`/`to_labels` field. The notes were not a reliable statement of intent:
`DERIVED_FROM` said `Session/Claim -> Source` and omitted `Chunk`, which is 17,753 of
its 31,042 edges, and `RETURNS` named four targets where the reader serves eight.
Three wrong invariants would have landed without this pass.

Both directions matter and they fail differently. Declared-and-unwritten is a broken
promise to consumers; written-and-undeclared is a surface the ontology cannot be read
to discover, and it is the direction that carries actual wrong data. This is the query
behind `conformance.audit_declarations`, so `thalamus contract check` now answers it
without the ad-hoc run — reach for this version when you need the raw counts or the
endpoint pairs, which the check does not print.

---

## What does `contract check`'s whole-graph fetch cost, and what is cheaper?

**Question it answered.** `contract check` spends ~14 s per invocation in two start
steps that materialise the entire graph, and the audit rules above them read nine
vertex property keys and two edge ones. Which narrowings actually pay, and by how much?

**Surface:** gremlin-python
**Validated:** 2026-08-25 against the live graph — 47,450 vertices, 161,904 edges,
TinkerGraph 3.7.3, n=5 per arm (n=3 for the edge arms), medians reported.

```python
import statistics, time
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T
from thalamus.substrate.writer import close_connection, connect

KEYS = ("tier", "source", "ingested_at", "external", "scope",
        "kind", "status", "protocol", "content_hash")

g = connect()
try:
    # vertices: 5,054 ms -> 2,443 ms  (2.1x)
    g.V().value_map(True).to_list()
    g.V().element_map(*KEYS).to_list()

    # edges: 11,422 ms -> 5,654 ms  (2.0x)
    g.E().element_map().to_list()
    (g.E().project("label", "from", "to", "from_label", "to_label")
     .by(T.label).by(__.out_v().id_()).by(__.in_v().id_())
     .by(__.out_v().label()).by(__.in_v().label()).to_list())

    # aggregates that replace whole scans
    g.E().group_count().by(T.label).next()                                    #    85 ms
    g.E().group().by(T.label).by(__.properties().key().dedup().fold()).next() #   230 ms
    g.V().not_(__.both_e()).element_map("protocol", "status").to_list()       #    77 ms
finally:
    close_connection(g)
```

**Measured, medians over the n above:**

| traversal | elements | median |
|---|---|---|
| `g.V().value_map(True)` | 47,450 | 5,054 ms |
| `g.V().element_map(*9 keys)` | 47,450 | 2,443 ms |
| `g.E().element_map()` | 161,904 | 11,422 ms |
| `g.E().element_map("role","basis")` | 161,904 | 10,660 ms |
| `g.E().project(label, from, to, from_label, to_label)` | 161,904 | 5,654 ms |
| `g.E().group_count().by(T.label)` | 1 | 85 ms |
| `g.E().group().by(label).by(property keys)` | 1 | 230 ms |
| `g.V().not_(both_e()).element_map(...)` | 0 | 77 ms |

**Notes.** Two results are counter-intuitive and are the reason to keep this entry.

*Narrowing edge **properties** buys almost nothing* — 1.1x. Most edges carry no
properties at all (`ABOUT`, `DERIVED_FROM`), so `elementMap`'s cost is the 161,904
nested maps themselves: `T.id`, `T.label`, and an `IN`/`OUT` sub-map each. Selecting
fewer properties does not remove a map that was already nearly empty.

*Replacing `elementMap` with `project` **does** pay* — 2.0x, even though it adds four
sub-traversals per edge where `elementMap` resolves the endpoints natively. Five flat
strings beat a nested map with two sub-maps, on the wire and in Python
deserialisation. The prediction before measuring was that it might come out slower; it
did not, which is the whole reason to run the arm rather than reason about it.

An aggregate beats both by an order of magnitude when the question is aggregate:
`group_count().by(T.label)` answers "which edge labels exist" in 85 ms against a scan
that costs 11 s. Reach for the scan only when a rule genuinely needs per-element rows.

None of these is an index question. TinkerGraph's only index is an exact-value hash
map (`graph.createIndex`), no index is declared in `config/tinkergraph.properties`, and
`hasLabel` has no index in TinkerGraph at all — every one of these is a full scan by
construction, so what varies is only how much crosses the wire.

## How many keywords does a real recall query carry?
**Question:** `recall()` costs four traversals *per keyword*. Is a per-keyword
optimisation worth anything — i.e. what is the keyword count of the queries that
actually arrive?
**Surface:** gremlin-python
**Validated:** 2026-08-26 against the live graph (2,963 `Trace` vertices)

```python
from collections import Counter

from thalamus.substrate.reader import _extract_keywords
from thalamus.substrate.writer import close_connection, connect

g = connect()
try:
    queries = g.V().has_label("Trace").values("query").to_list()
finally:
    close_connection(g)

counts = Counter(len(_extract_keywords(str(q))) for q in queries)
total = sum(counts.values())
for n in sorted(counts):
    print(f"{n:>3} keywords: {counts[n]:>5} ({counts[n] / total:.1%})")
```

**Notes:** The point is to size a cost that is invisible in any single query.
Measured 2026-08-26: median 7; 1–2 keywords 18.7%, ≥4 keywords 80.5%, tail to 340 —
a 340-keyword query issues 1,360 traversals under the current per-keyword loop.
`Trace.query` covers every recorded retrieval, not only `memory_recall`, so read the
distribution as "queries the reader is asked", not "recall calls".
The same shape sizes any other per-input cost: swap `_extract_keywords` for whatever
the code under test derives from `query`.

## Would moving a vertex's edges onto another vertex merge any of them?

**Question it answered:** Before repairing the duplicate Claims in #111 — rewiring a
stale vertex's in-edges onto its twin and dropping it — does any of those edges already
exist on the twin? A merge is not an addition: it silently removes one edge and drops
the far endpoint's fan-out by one. (2026-08-26)

**Surface:** gremlin-python

```python
from gremlin_python.process.graph_traversal import __
from thalamus.substrate.writer import connect, close_connection

def edge_keys(g, vertex_id):
    """`(label, other endpoint, incoming)` — what makes two edges the same edge."""
    incoming = (g.V(vertex_id).in_e().project("label", "other")
                .by(__.label()).by(__.out_v().id_()).to_list())
    outgoing = (g.V(vertex_id).out_e().project("label", "other")
                .by(__.label()).by(__.in_v().id_()).to_list())
    return ({(r["label"], str(r["other"]), True) for r in incoming}
            | {(r["label"], str(r["other"]), False) for r in outgoing})

g = connect()
try:
    source, destination = "scope:main:claim:4fdb5cf205991d78", "scope:main:claim:6cfb75945a47b6a1"
    collapse = edge_keys(g, source) & edge_keys(g, destination)
    print(f"{len(collapse)} edge(s) would merge rather than move: {sorted(collapse)}")
finally:
    close_connection(g)
```

**Validated:** 2026-08-26 against the live graph, over the 9 stale/twin pairs #111
names. Predicted 5 collapses; the migration's own plan reported 5, and the edge count
fell by exactly 5 (163,038 → 163,033) after `thalamus repair-claim-addresses --write`.

**Notes — direction is part of the key, and forgetting it under-counts.** A `TOUCHES`
out to an artifact and a `RETURNS` in from a trace can name the same neighbour; keying
on `(label, other)` alone reads them as the same edge and predicts a collapse that will
not happen. Keying on the neighbour alone is worse in the other direction.

The finding this shape produces is usually more interesting than the merge itself. Here,
5 traces held a `RETURNS` to *both* members of a duplicate pair — one recall returned the
same claim twice under two ids and the eval ledger counted fan-out 2. Run this before any
vertex merge and read the overlap as a measurement, not as an obstacle.

Do **not** reach for `where(__.both_e().count().is_(0))`-style formulations near this;
see the orphan recipe above for why an empty stream never satisfies a count predicate.

## The withholding draw and the trace it produced, joined

**Question it answered:** "Did a node the retrieval policy suppressed come back later
in the same session?" (#107). Needs both halves of a withholding event, and neither
side holds both: the graph knows the session and what the retrieval surfaced, the
ledger knows which nodes were offered.
**Surface:** gremlin-python
**Validated:** 2026-09-01 against the live graph — 738 traces carry `policy_seed`,
738 of 738 join to a ledger row, 40 distinct non-empty session ids, sums 822 withheld
/ 3,565 offered.

```python
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T

from thalamus.eval import policy as policy_mod
from thalamus.substrate.writer import connect, close_connection

by_seed = {r.seed: r for r in policy_mod.load().values()}
g = connect()
try:
    rows = (
        g.V().has_label("Trace").has("policy_seed")
        .project("id", "session", "scope", "ts", "seed", "withheld", "oc", "returned")
        .by(T.id).by("session_id").by("scope").by("ts")
        .by("policy_seed").by("withheld").by("offered_count")
        .by(__.out("RETURNS").id_().dedup().fold())
        .to_list()
    )
    for row in rows:
        record = by_seed[row["seed"]]
        offered = set(record.offered)                       # the draw's own universe
        surfaced = set(row["returned"]) | set(record.withheld)  # all the ranker showed
        print(row["session"], len(offered), len(surfaced))
finally:
    close_connection(g)
```

**Notes — the trace's `RETURNS` set is a SUPERSET of what the draw covered, and
reconstructing `offered` from it is wrong.** A rendered response is assembled from more
retrieval than the one `policy.apply` call sees: 277 of 738 traces return nodes that
were never in the draw. `eval sync` lands `offered_count` and drops the ids, so the
only correct source for the offered list is the ledger. Rebuilding it as
RETURNS-plus-withheld inflates the offered set on 37% of events and sweeps
never-randomized nodes into whichever arm you call the control.

Join on `policy_seed`, not on `session_id`: the ledger's own `session_id` is the empty
string on every row **by design** (`policy.py` — the MCP server cannot see its caller's
session, and `eval sync` fills it in on the Trace instead). Seeds are unique across the
ledger. `response_sha256` is the key `sync.py` itself joins on and works too, but it
collides on 9 hashes covering 10 rows (#143), where `policy_seed` does not.
