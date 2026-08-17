# Gremlin Steps Reference

Complete reference for all Gremlin traversal steps, organized by category.

## Categories

### [Start Steps](start-steps.md)
Steps that begin a traversal by reading from or writing to the graph.
- `V()`, `E()` - Read vertices/edges
- `addV()`, `addE()` - Add vertices/edges
- `mergeV()`, `mergeE()` - Upsert vertices/edges
- `inject()` - Insert arbitrary objects

### [Filter Steps](filter-steps.md)
Steps that filter traversers based on conditions.
- `has()`, `hasNot()`, `hasLabel()` - Property filtering
- `where()`, `is()` - Conditional filtering
- `and()`, `or()`, `not()` - Logical operations
- `dedup()`, `limit()`, `range()`, `tail()` - Result limiting

### [Map Steps](map-steps.md)
Steps that transform traversers to different values.
- `values()`, `properties()`, `valueMap()` - Property access
- `select()`, `project()` - Data shaping
- `path()` - Path information
- `count()`, `sum()`, `min()`, `max()`, `mean()` - Aggregations
- `order()` - Sorting

### [SideEffect Steps](sideeffect-steps.md)
Steps that perform side effects while passing traversers through.
- `aggregate()`, `store()` - Collection into side effects
- `group()`, `groupCount()` - Grouping operations
- `property()` - Setting properties
- `drop()` - Removing elements
- `sack()` - Traverser-local data

### [Branch Steps](branch-steps.md)
Steps that split or redirect the traversal flow.
- `choose()` - If-then-else branching
- `union()` - Merge multiple traversals
- `repeat()` - Looping
- `coalesce()` - First non-empty result
- `optional()` - Optional traversal
- `match()` - Pattern matching

### [Terminal Steps](terminal-steps.md)
Steps that end a traversal and produce results.
- `next()`, `toList()`, `toSet()` - Result collection
- `iterate()` - Execute without collecting
- `explain()`, `profile()` - Traversal analysis

### [Modulator Steps](modulator-steps.md)
Steps that modify the behavior of other steps.
- `by()` - Specify projections
- `as()` - Label steps for later reference
- `from()`, `to()` - Specify edge endpoints
- `option()` - Branch options
- `emit()`, `until()`, `times()` - Loop control
