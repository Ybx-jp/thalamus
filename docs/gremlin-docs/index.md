# Gremlin Reference Documentation

This is a filtered subset of the [Apache TinkerPop Gremlin Reference Documentation](https://tinkerpop.apache.org/docs/current/reference/),
focused on Gremlin Server implementations and the Python driver.

## Agent routing — read the one file your problem lives in

The working rules (terminal steps, dialect split, renamed steps, house
connection idiom) are in the `gremlin-python` skill
(`.claude/skills/gremlin-python/SKILL.md`); proven queries are in its
`RECIPES.md`. Come here for depth the skill doesn't carry:

| You need | Read |
| --- | --- |
| Why a traversal returned nothing / `iterate` vs `next` vs `toList` semantics | [terminal steps](06-steps/terminal-steps.md), [basic gremlin](03-basic-gremlin.md) |
| The exact signature/behavior of a step | the matching category file in [06-steps/](06-steps/index.md) |
| Predicates (`P`, `TextP`), scopes, type coercion | [traversal concepts](05a-traversal-concepts.md) |
| Connection options, statics, lambdas, event-loop limits, python↔java renames | [gremlin-python driver](12-gremlin-python.md) |
| Submitting script strings via `Client` / per-request timeouts | [gremlin-python driver](12-gremlin-python.md), [connecting](02-connecting.md) |
| Why a query is slow (`profile`, `explain`, barriers) | [terminal steps](06-steps/terminal-steps.md), [traversal strategies](07-traversal-strategies.md) |

## Contents

### Core Concepts
- [Introduction](01-introduction.md) - Graph computing fundamentals
- [Connecting to Gremlin](02-connecting.md) - Server and RGP connections
- [Basic Gremlin](03-basic-gremlin.md) - Getting started with traversals
- [Graph Structure](04-graph-structure.md) - Vertices, edges, and properties

### Traversal Reference
- [Traversal Overview](05-traversal-overview.md) - Transactions, configuration, start steps
- [Traversal Concepts](05a-traversal-concepts.md) - Predicates, types, scopes, lambdas
- [Steps Reference](06-steps/index.md) - Complete step documentation
  - [Start Steps](06-steps/start-steps.md) - V, E, addV, addE, inject, etc.
  - [Filter Steps](06-steps/filter-steps.md) - has, where, is, dedup, limit, etc.
  - [Map Steps](06-steps/map-steps.md) - values, select, project, path, etc.
  - [SideEffect Steps](06-steps/sideeffect-steps.md) - aggregate, group, property, etc.
  - [Branch Steps](06-steps/branch-steps.md) - choose, union, repeat, coalesce, etc.
  - [Terminal Steps](06-steps/terminal-steps.md) - iterate, next, toList, etc.
  - [Modulator Steps](06-steps/modulator-steps.md) - by, as, from, to, option, etc.

### Advanced Topics
- [Traversal Strategies](07-traversal-strategies.md) - Query optimization
- [Domain Specific Languages](08-dsl.md) - Custom DSLs and translators
- [GraphComputer](09-graphcomputer.md) - OLAP, VertexProgram, MapReduce
- [SparkGraphComputer](10-spark.md) - Distributed processing with Spark

### Server and Drivers
- [Gremlin Server](11-gremlin-server.md) - Server configuration and usage
- [Gremlin-Python](12-gremlin-python.md) - Python driver reference

### Implementations
- [TinkerGraph](13-tinkergraph.md) - Reference implementation
- [Hadoop-Gremlin](14-hadoop.md) - Hadoop integration

---
*Generated from TinkerPop documentation. Some language variants and sections removed for focus.*
