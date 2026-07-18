### Barrier Step

The `barrier()`-step (**barrier**) turns the lazy traversal pipeline into a bulk-synchronous pipeline. This step is
useful in the following situations:

* When everything prior to `barrier()` needs to be executed before moving onto the steps after the `barrier()` (i.e. ordering).
* When "stalling" the traversal may lead to a "bulking optimization" in traversals that repeatedly touch many of the same elements (i.e. optimizing).

console (groovy)

groovy

```
gremlin> g.V().sideEffect{println "first: ${it}"}.sideEffect{println "second: ${it}"}.iterate()
first: v[1]
second: v[1]
first: v[2]
second: v[2]
first: v[3]
second: v[3]
first: v[4]
second: v[4]
first: v[5]
second: v[5]
first: v[6]
second: v[6]
gremlin> g.V().sideEffect{println "first: ${it}"}.barrier().sideEffect{println "second: ${it}"}.iterate()
first: v[1]
first: v[2]
first: v[3]
first: v[4]
first: v[5]
first: v[6]
second: v[1]
second: v[2]
second: v[3]
second: v[4]
second: v[5]
second: v[6]
```

```
g.V().sideEffect{println "first: ${it}"}.sideEffect{println "second: ${it}"}.iterate()
g.V().sideEffect{println "first: ${it}"}.barrier().sideEffect{println "second: ${it}"}.iterate()
```

The theory behind a "bulking optimization" is simple. If there are one million traversers at vertex 1, then there is
no need to calculate one million `both()`-computations. Instead, represent those one million traversers as a single
traverser with a `Traverser.bulk()` equal to one million and execute `both()` once. A bulking optimization example is
made more salient on a larger graph. Therefore, the example below leverages the [Grateful Dead graph](#grateful-dead).

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.io('data/grateful-dead.xml').read().iterate()
gremlin> g = traversal().with(graph).withoutStrategies(LazyBarrierStrategy) //// (1)
==>graphtraversalsource[tinkergraph[vertices:808 edges:8049], standard]
gremlin> clockWithResult(1){g.V().both().both().both().count().next()} //// (2)
==>7464.912458
==>126653966
gremlin> clockWithResult(1){g.V().repeat(both()).times(3).count().next()} //// (3)
==>7596.467084
==>126653966
gremlin> clockWithResult(1){g.V().both().barrier().both().barrier().both().barrier().count().next()} //// (4)
==>8.247
==>126653966
```

```
graph = TinkerGraph.open()
g = traversal().with(graph)
g.io('data/grateful-dead.xml').read().iterate()
g = traversal().with(graph).withoutStrategies(LazyBarrierStrategy) //// (1)
clockWithResult(1){g.V().both().both().both().count().next()} //// (2)
clockWithResult(1){g.V().repeat(both()).times(3).count().next()} //// (3)
clockWithResult(1){g.V().both().barrier().both().barrier().both().barrier().count().next()} //4
```

1. Explicitly remove `LazyBarrierStrategy` which yields a bulking optimization.
2. A non-bulking traversal where each traverser is processed.
3. Each traverser entering `repeat()` has its recursion bulked.
4. A bulking traversal where implicit traversers are not processed.

If `barrier()` is provided an integer argument, then the barrier will only hold `n`-number of unique traversers in its
barrier before draining the aggregated traversers to the next step. This is useful in the aforementioned bulking
optimization scenario with the added benefit of reducing the risk of an out-of-memory exception.

`LazyBarrierStrategy` inserts `barrier()`-steps into a traversal where appropriate in order to gain the
"bulking optimization."

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph) //// (1)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.io('data/grateful-dead.xml').read().iterate()
gremlin> clockWithResult(1){g.V().both().both().both().count().next()}
==>6.139416
==>126653966
gremlin> g.V().both().both().both().count().iterate().toString() //// (2)
==>[TinkerGraphStep(vertex,[]), VertexStep(BOTH,vertex), NoOpBarrierStep(2500), VertexStep(BOTH,vertex), NoOpBarrierStep(2500), VertexStep(BOTH,edge), CountGlobalStep, DiscardStep]
```

```
graph = TinkerGraph.open()
g = traversal().with(graph) //// (1)
g.io('data/grateful-dead.xml').read().iterate()
clockWithResult(1){g.V().both().both().both().count().next()}
g.V().both().both().both().count().iterate().toString()  //2
```

1. `LazyBarrierStrategy` is a default strategy and thus, does not need to be explicitly activated.
2. With `LazyBarrierStrategy` activated, `barrier()`-steps are automatically inserted where appropriate.

**Additional References**

[`barrier()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#barrier()),
[`barrier(Consumer)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#barrier(java.util.function.Consumer)),
[`barrier(int)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#barrier(int))

### Explain Step

The `explain()`-step (**terminal**) will return a `TraversalExplanation`. A traversal explanation details how the
traversal (prior to `explain()`) will be compiled given the registered [traversal strategies](07-traversal-strategies.md#traversalstrategy).
A `TraversalExplanation` has a `toString()` representation with 3-columns. The first column is the
traversal strategy being applied. The second column is the traversal strategy category: [D]ecoration, [O]ptimization,
[P]rovider optimization, [F]inalization, and [V]erification. Finally, the third column is the state of the traversal
post strategy application. The final traversal is the resultant execution plan.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person').outE().identity().inV().count().is(gt(5)).explain()
==>Traversal Explanation
==================================================================================================================================================================================
Original Traversal                    [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStep(OUT,edge), IdentityStep, EdgeVertexStep(IN), CountGlobalStep, IsStep(gt(5))]

ConnectiveStrategy              [D]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStep(OUT,edge), IdentityStep, EdgeVertexStep(IN), CountGlobalStep, IsStep(gt(5))]
IdentityRemovalStrategy         [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStep(OUT,edge), EdgeVertexStep(IN), CountGlobalStep, IsStep(gt(5))]
MatchPredicateStrategy          [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStep(OUT,edge), EdgeVertexStep(IN), CountGlobalStep, IsStep(gt(5))]
FilterRankingStrategy           [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStep(OUT,edge), EdgeVertexStep(IN), CountGlobalStep, IsStep(gt(5))]
InlineFilterStrategy            [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStep(OUT,edge), EdgeVertexStep(IN), CountGlobalStep, IsStep(gt(5))]
IncidentToAdjacentStrategy      [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStepPlaceholder(OUT,vertex), CountGlobalStep, IsStep(gt(5))]
AdjacentToIncidentStrategy      [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStepPlaceholder(OUT,edge), CountGlobalStep, IsStep(gt(5))]
RepeatUnrollStrategy            [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStepPlaceholder(OUT,edge), CountGlobalStep, IsStep(gt(5))]
CountStrategy                   [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStepPlaceholder(OUT,edge), RangeGlobalStep(0,6), CountGlobalStep, IsStep(gt(5))]
PathRetractionStrategy          [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStepPlaceholder(OUT,edge), RangeGlobalStep(0,6), CountGlobalStep, IsStep(gt(5))]
EarlyLimitStrategy              [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStepPlaceholder(OUT,edge), RangeGlobalStep(0,6), CountGlobalStep, IsStep(gt(5))]
LazyBarrierStrategy             [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStepPlaceholder(OUT,edge), RangeGlobalStep(0,6), CountGlobalStep, IsStep(gt(5))]
ByModulatorOptimizationStrategy [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStepPlaceholder(OUT,edge), RangeGlobalStep(0,6), CountGlobalStep, IsStep(gt(5))]
GValueReductionStrategy         [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStep(OUT,edge), RangeGlobalStep(0,6), CountGlobalStep, IsStep(gt(5))]
TinkerGraphCountStrategy        [P]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), VertexStep(OUT,edge), RangeGlobalStep(0,6), CountGlobalStep, IsStep(gt(5))]
TinkerGraphStepStrategy         [P]   [TinkerGraphStep(vertex,[~label.eq(person)]), VertexStep(OUT,edge), RangeGlobalStep(0,6), CountGlobalStep, IsStep(gt(5))]
ProfileStrategy                 [F]   [TinkerGraphStep(vertex,[~label.eq(person)]), VertexStep(OUT,edge), RangeGlobalStep(0,6), CountGlobalStep, IsStep(gt(5))]
StandardVerificationStrategy    [V]   [TinkerGraphStep(vertex,[~label.eq(person)]), VertexStep(OUT,edge), RangeGlobalStep(0,6), CountGlobalStep, IsStep(gt(5))]

Final Traversal                       [TinkerGraphStep(vertex,[~label.eq(person)]), VertexStep(OUT,edge), RangeGlobalStep(0,6), CountGlobalStep, IsStep(gt(5))]
```

```
g.V().hasLabel('person').outE().identity().inV().count().is(gt(5)).explain()
```

For traversal profiling information, please see [`profile()`](06-steps/terminal-steps.md#profile-step)-step.

### Profile Step

The `profile()`-step (**sideEffect**) exists to allow developers to profile their traversals to determine statistical
information like step runtime, counts, etc.

|  |  |
| --- | --- |
| Warning | Profiling a Traversal will impede the Traversal’s performance. This overhead is mostly excluded from the profile results, but durations are not exact. Thus, durations are best considered in relation to each other. |

console (groovy)

groovy

```
gremlin> g.V().out('created').repeat(both()).times(3).hasLabel('person').values('age').sum().profile()
==>Traversal Metrics
Step                                                               Count  Traversers       Time (ms)    % Dur
=============================================================================================================
TinkerGraphStep(vertex,[])                                             6           6           0.071    22.03
VertexStep(OUT,[created],vertex)                                       4           4           0.035    11.01
NoOpBarrierStep(2500)                                                  4           2           0.023     7.10
VertexStep(BOTH,vertex)                                               10           4           0.013     4.18
NoOpBarrierStep(2500)                                                 10           3           0.010     3.29
VertexStep(BOTH,vertex)                                               24           7           0.015     4.71
NoOpBarrierStep(2500)                                                 24           5           0.013     4.03
VertexStep(BOTH,vertex)                                               58          11           0.019     5.96
NoOpBarrierStep(2500)                                                 58           6           0.018     5.86
HasStep([~label.eq(person)])                                          48           4           0.025     7.84
PropertiesStep([age],value)                                           48           4           0.019     5.96
SumGlobalStep                                                          1           1           0.058    18.04
                                            >TOTAL                     -           -           0.323        -
```

```
g.V().out('created').repeat(both()).times(3).hasLabel('person').values('age').sum().profile()
```

The `profile()`-step generates a `TraversalMetrics` sideEffect object that contains the following information:

* `Step`: A step within the traversal being profiled.
* `Count`: The number of *represented* traversers that passed through the step.
* `Traversers`: The number of traversers that passed through the step.
* `Time (ms)`: The total time the step was actively executing its behavior.
* `% Dur`: The percentage of total time spent in the step.

![gremlin exercise](../images/gremlin-exercise.png) It is important to understand the difference between "Count"
and "Traversers". Traversers can be merged and as such, when two traversers are "the same" they may be aggregated
into a single traverser. That new traverser has a `Traverser.bulk()` that is the sum of the two merged traverser
bulks. On the other hand, the `Count` represents the sum of all `Traverser.bulk()` results and thus, expresses the
number of "represented" (not enumerated) traversers. `Traversers` will always be less than or equal to `Count`.

For traversal compilation information, please see [`explain()`](06-steps/terminal-steps.md#explain-step)-step.

**Additional References**

[`profile()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#profile()),
[`profile(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#profile(java.lang.String))

