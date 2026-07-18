### As Step

The `as()`-step is not a real step, but a "step modulator" similar to [`by()`](06-steps/modulator-steps.md#by-step) and [`option()`](06-steps/modulator-steps.md#option-step).
With `as()`, it is possible to provide a label to the step that can later be accessed by steps and data structures
that make use of such labels — e.g., [`select()`](06-steps/map-steps.md#select-step), [`match()`](06-steps/branch-steps.md#match-step), and path.

|  |  |
| --- | --- |
| Groovy | The term `as` is a reserved word in Groovy, and when therefore used as part of an anonymous traversal must be referred to in Gremlin with the double underscore `__.as()`. |

|  |  |
| --- | --- |
| Python | The term `as` is a reserved word in Python, and therefore must be referred to in Gremlin with `as_()`. |

console (groovy)

groovy

```
gremlin> g.V().as('a').out('created').as('b').select('a','b') //// (1)
==>[a:v[1],b:v[3]]
==>[a:v[4],b:v[5]]
==>[a:v[4],b:v[3]]
==>[a:v[6],b:v[3]]
gremlin> g.V().as('a').out('created').as('b').select('a','b').by('name') //// (2)
==>[a:marko,b:lop]
==>[a:josh,b:ripple]
==>[a:josh,b:lop]
==>[a:peter,b:lop]
```

```
g.V().as('a').out('created').as('b').select('a','b') //// (1)
g.V().as('a').out('created').as('b').select('a','b').by('name') //2
```

1. Select the objects labeled "a" and "b" from the path.
2. Select the objects labeled "a" and "b" from the path and, for each object, project its name value.

A step can have any number of labels associated with it. This is useful for referencing the same step multiple times in a future step.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('software').as('a','b','c').
            select('a','b','c').
              by('name').
              by('lang').
              by(__.in('created').values('name').fold())
==>[a:lop,b:java,c:[marko,josh,peter]]
==>[a:ripple,b:java,c:[josh]]
```

```
g.V().hasLabel('software').as('a','b','c').
   select('a','b','c').
     by('name').
     by('lang').
     by(__.in('created').values('name').fold())
```

**Additional References**

[`as(String,String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#as(java.lang.String,java.lang.String...))

### By Step

The `by()`-step is not an actual step, but instead is a "step-modulator" similar to [`as()`](06-steps/modulator-steps.md#as-step) and
[`option()`](06-steps/modulator-steps.md#option-step). If a step is able to accept traversals, functions, comparators, etc. then `by()` is the
means by which they are added. The general pattern is `step().by()…​by()`. Some steps can only accept one `by()`
while others can take an arbitrary amount.

console (groovy)

groovy

```
gremlin> g.V().group().by(bothE().count()) //// (1)
==>[1:[v[2],v[5],v[6]],3:[v[1],v[3],v[4]]]
gremlin> g.V().group().by(bothE().count()).by('name') //// (2)
==>[1:[vadas,ripple,peter],3:[marko,lop,josh]]
gremlin> g.V().group().by(bothE().count()).by(count()) //// (3)
==>[1:3,3:3]
```

```
g.V().group().by(bothE().count()) //// (1)
g.V().group().by(bothE().count()).by('name') //// (2)
g.V().group().by(bothE().count()).by(count())  //3
```

1. `by(outE().count())` will group the elements by their edge count (**traversal**).
2. `by('name')` will process the grouped elements by their name (**element property projection**).
3. `by(count())` will count the number of elements in each group (**traversal**).

When a `by()` modulator does not produce a result, it is deemed "unproductive". An "unproductive" modulator will lead
to the filtering of the traverser it is currently working with. The filtering will manifest in various ways depending
on the step.

console (groovy)

groovy

```
gremlin> g.V().sample(1).by('age') //// (1)
==>v[4]
```

```
g.V().sample(1).by('age') //1
```

1. The "age" property key is not present for all vertices, therefore `sample()` will ignore (i.e. filter) such
   vertices for consideration in the sampling.

The following steps all support `by()`-modulation. Note that the semantics of such modulation should be understood
on a step-by-step level and thus, as discussed in their respective section of the documentation.

* [`aggregate()`](06-steps/sideeffect-steps.md#aggregate-step): aggregate all objects into a set but only store their `by()`-modulated values.
* [`cyclicPath()`](06-steps/filter-steps.md#cyclicpath-step): filter if the traverser’s path is cyclic given `by()`-modulation.
* [`dedup()`](06-steps/filter-steps.md#dedup-step): dedup on the results of a `by()`-modulation.
* [`format()`](06-steps/map-steps.md#format-step): transform a traverser provided to the step by way of the `by()` modulator before it is processed by it.
* [`group()`](06-steps/sideeffect-steps.md#group-step): create group keys and values according to `by()`-modulation.
* [`groupCount()`](06-steps/sideeffect-steps.md#groupcount-step): count those groups where the group keys are the result of `by()`-modulation.
* [`math()`](06-steps/map-steps.md#math-step): transform a traverser provided to the step by way of the `by()` modulator before it is processed by it.
* [`order()`](06-steps/map-steps.md#order-step): order the objects by the results of a `by()`-modulation.
* [`path()`](06-steps/map-steps.md#path-step): get the path of the traverser where each path element is `by()`-modulated.
* [`project()`](06-steps/map-steps.md#project-step): project a map of results given various `by()`-modulations off the current object.
* [`propertyMap()`](06-steps/map-steps.md#propertymap-step): transform the result of the values in the resulting `Map` using the `by()` modulator.
* [`sack()`](06-steps/sideeffect-steps.md#sack-step): provides the transformation for a traverser to a value to be stored in the sack.
* [`sample()`](06-steps/filter-steps.md#sample-step): sample using the value returned by `by()`-modulation.
* [`select()`](06-steps/map-steps.md#select-step): select path elements and transform them via `by()`-modulation.
* [`simplePath()`](06-steps/filter-steps.md#simplepath-step): filter if the traverser’s path is simple given `by()`-modulation.
* [`tree()`](06-steps/sideeffect-steps.md#tree-step): get a tree of traversers objects where the objects have been `by()`-modulated.
* [`valueMap()`](06-steps/map-steps.md#valuemap-step): transform the result of the values in the resulting `Map` using the `by()` modulator.
* [`where()`](06-steps/filter-steps.md#where-step): determine the predicate given the testing of the results of `by()`-modulation.

**Additional References**

[`by()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#by()),
[`by(Comparator)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#by(java.util.Comparator)),
[`by(Function,Comparator)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#by(java.util.function.Function,java.util.Comparator)),
[`by(Function)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#by(java.util.function.Function)),
[`by(Order)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#by(org.apache.tinkerpop.gremlin.process.traversal.Order)),
[`by(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#by(java.lang.String)),
[`by(String,Comparator)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#by(java.lang.String,java.util.Comparator)),
[`by(T)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#by(org.apache.tinkerpop.gremlin.structure.T)),
[`by(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#by(org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`by(Traversal,Comparator)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#by(org.apache.tinkerpop.gremlin.process.traversal.Traversal,java.util.Comparator)),
[`T`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/structure/T.html),
[`Order`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Order.html),
[A Note on Maps](../05a-traversal-concepts.md#a-note-on-maps)

### Emit Step

The `emit`-step is not an actual step, but is instead a step modulator for `repeat()` (find more
documentation on the `emit()` there).

**Additional References**

[`emit()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#emit()),
[`emit(Predicate)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#emit(java.util.function.Predicate)),
[`emit(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#emit(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### From Step

The `from()`-step is not an actual step, but instead is a "step-modulator" similar to [`as()`](06-steps/modulator-steps.md#as-step) and
[`by()`](06-steps/modulator-steps.md#by-step). If a step is able to accept traversals or strings then `from()` is the
means by which they are added. The general pattern is `step().from()`. See [`to()`](06-steps/modulator-steps.md#to-step)-step.

The list of steps that support `from()`-modulation are: [`simplePath()`](06-steps/filter-steps.md#simplepath-step), [`cyclicPath()`](06-steps/filter-steps.md#cyclicpath-step),
[`path()`](06-steps/map-steps.md#path-step), and [`addE()`](06-steps/start-steps.md#addedge-step).

|  |  |
| --- | --- |
| Javascript | The term `from` is a reserved word in Javascript, and therefore must be referred to in Gremlin with `from_()`. |

|  |  |
| --- | --- |
| Python | The term `from` is a reserved word in Python, and therefore must be referred to in Gremlin with `from_()`. |

**Additional References**

[`from(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#from(java.lang.String)),
[`from(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#from(org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`from(Vertex)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#from(org.apache.tinkerpop.gremlin.structure.Vertex))

### Option Step

An option to a [`branch()`](branch-steps.md#branch-step) or [`choose()`](06-steps/branch-steps.md#choose-step).

**Additional References**

[`option(Object,Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#option(M,org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`option(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#option(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### Times Step

The `times`-step is not an actual step, but is instead a step modulator for `repeat()` (find more
documentation on the `times()` there).

**Additional References**

[`until(Predicate)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#times(int)),
`emit()`, `repeat()`, `until()`

### To Step

The `to()`-step is not an actual step, but instead is a "step-modulator" similar to [`as()`](06-steps/modulator-steps.md#as-step) and
[`by()`](06-steps/modulator-steps.md#by-step). If a step is able to accept traversals or strings then `to()` is the
means by which they are added. The general pattern is `step().to()`. See [`from()`](06-steps/modulator-steps.md#from-step)-step.

The list of steps that support `to()`-modulation are: [`simplePath()`](06-steps/filter-steps.md#simplepath-step), [`cyclicPath()`](06-steps/filter-steps.md#cyclicpath-step),
[`path()`](06-steps/map-steps.md#path-step), and [`addE()`](06-steps/start-steps.md#addedge-step).

**Additional References**

[`to(Direction,String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#to(org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`to(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#to(org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`to(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#to(org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`to(Vertex)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#to(org.apache.tinkerpop.gremlin.structure.Vertex)),
[`toE(Direction,String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#toE(org.apache.tinkerpop.gremlin.structure.Direction,java.lang.String...)),
[`toV(Direction)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#toV(org.apache.tinkerpop.gremlin.structure.Direction)),
[`Direction`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/structure/Direction.html)

### Until Step

The `until`-step is not an actual step, but is instead a step modulator for `repeat()` (find more
documentation on the `until()` there).

**Additional References**

[`until(Predicate)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#until(java.util.function.Predicate)),
[`until(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#until(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### With Step

The `with()`-step is not an actual step, but is instead a "step modulator" which modifies the behavior of the step
prior to it. The `with()`-step provides additional "configuration" information to steps that implement the `Configuring`
interface. Steps that allow for this type of modulation will explicitly state so in their documentation.

|  |  |
| --- | --- |
| Javascript | The term `with` is a reserved word in Javascript, and therefore must be referred to in Gremlin with `with_()`. |

|  |  |
| --- | --- |
| Python | The term `with` is a reserved word in Python, and therefore must be referred to in Gremlin with `with_()`. |

