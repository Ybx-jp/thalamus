# Traversal Concepts

This document covers important conceptual topics for understanding Gremlin traversals, including parameterization,
predicates, types, and execution behaviors.

## Traversal Parameterization

A subset of gremlin steps are able to accept parameterized arguments also known as GValues. GValues can be used to
provide protection against gremlin-injection attacks in cases where untrusted and unsanitized inputs must be passed as
step arguments. Additionally, use of GValues may offer performance benefits in certain environments by making use of
some query caching capabilities. Note that the reference implementation of the gremlin language and `gremlin-server` do
not have such a query caching mechanism, and thus will not see any performance improvements through parameterization. Users
should consult the documentation of their specific graph system details of potential performance benefits via parameterization.

|  |  |
| --- | --- |
| Note | There are unique considerations regarding parameters when using `gremlin-groovy` scripts. Groovy allows for parameterization at arbitrary points in the query in addition to the subset of parameterizable steps documented here. Groovy is also bound by a comparatively slow script compilation, which makes parameterization essential for performant execution of `gremlin-groovy` scripts. |

| Step | Parameterizable arguments |
| --- | --- |
| [addE()](06-steps/start-steps.md#addedge-step) | String edgeLabel |
| [addV()](06-steps/start-steps.md#addvertex-step) | String vertexLabel |
| [both()](06-steps/map-steps.md#vertex-steps) | String… edgeLabels |
| [bothE()](06-steps/map-steps.md#vertex-steps) | String… edgeLabels |
| [call()](06-steps/start-steps.md#call-step) | Map params |
| [from()](06-steps/modulator-steps.md#from-step) | Vertex fromVertex |
| [has()](06-steps/filter-steps.md#has-step) | String label |
| [hasId()](06-steps/filter-steps.md#has-step) | Object id, Object… ids |
| [hasLabel()](06-steps/filter-steps.md#has-step) | String label, String… labels |
| [hasValue()](06-steps/filter-steps.md#has-step) | Object value, Object… values |
| [in()](06-steps/map-steps.md#vertex-steps) | String… edgeLabels |
| [inE()](06-steps/map-steps.md#vertex-steps) | String… edgeLabels |
| [is()](06-steps/filter-steps.md#is-step) | Object value |
| [limit()](06-steps/filter-steps.md#limit-step) | Long limit |
| [mergeE()](06-steps/start-steps.md#mergeedge-step) | Map searchCreate |
| [mergeV()](06-steps/start-steps.md#mergevertex-step) | Map searchCreate |
| [option()](06-steps/modulator-steps.md#option-step) | Map m |
| [out()](06-steps/map-steps.md#vertex-steps) | String… edgeLabels |
| [outE()](06-steps/map-steps.md#vertex-steps) | String… edgeLabels |
| [property()](06-steps/sideeffect-steps.md#property-step) | Object value, Object… values |
| [range()](06-steps/filter-steps.md#range-step) | Long low, Long high |
| [skip()](06-steps/filter-steps.md#skip-step) | Long limit |
| [tail()](06-steps/filter-steps.md#tail-step) | Long limit |
| [to()](06-steps/modulator-steps.md#to-step) | String… edgeLabels, Vertex toVertex |
| [toE()](06-steps/map-steps.md#vertex-steps) | String… edgeLabels |

**Additional References**

[Java](#gremlin-java-gvalue), [Server](#parameterized-scripts)

## A Note on Predicates

A `P` is a predicate of the form `Function<Object,Boolean>`. That is, given some object, return true or false. Gremlin
supports text predicates (`TextP`), which are specialized predicates that only work on String values and are of the form `Function<String,Boolean>`. Additionally, type predicate (`P.typeOf`) supports filtering traversers based on their runtime types. The provided predicates are outlined in the table below and are used in various steps such as [`has()`](06-steps/filter-steps.md#has-step)-step, [`where()`](06-steps/filter-steps.md#where-step)-step, [`is()`](06-steps/filter-steps.md#is-step)-step, etc.

| Predicate | Description |
| --- | --- |
| `P.eq(object)` | Is the incoming object equal to the provided object? |
| `P.neq(object)` | Is the incoming object not equal to the provided object? |
| `P.lt(number)` | Is the incoming number less than the provided number? |
| `P.lte(number)` | Is the incoming number less than or equal to the provided number? |
| `P.gt(number)` | Is the incoming number greater than the provided number? |
| `P.gte(number)` | Is the incoming number greater than or equal to the provided number? |
| `P.inside(number,number)` | Is the incoming number greater than the first provided number and less than the second? |
| `P.outside(number,number)` | Is the incoming number less than the first provided number or greater than the second? |
| `P.between(number,number)` | Is the incoming number greater than or equal to the first provided number and less than the second? |
| `P.within(objects…)` | Is the incoming object in the array of provided objects? |
| `P.without(objects…)` | Is the incoming object not in the array of the provided objects? |
| `P.typeOf(GType)` | Is the incoming object of the type indicated by the provided `GType` token? |
| `P.typeOf(string)` | Is the incoming object of the type indicated by the provided `String`? |
| `TextP.startingWith(string)` | Does the incoming `String` start with the provided `String`? |
| `TextP.endingWith(string)` | Does the incoming `String` end with the provided `String`? |
| `TextP.containing(string)` | Does the incoming `String` contain the provided `String`? |
| `TextP.notStartingWith(string)` | Does the incoming `String` not start with the provided `String`? |
| `TextP.notEndingWith(string)` | Does the incoming `String` not end with the provided `String`? |
| `TextP.notContaining(string)` | Does the incoming `String` not contain the provided `String`? |
| `TextP.regex(string)` | Does the incoming `String` match the regular expression in the provided `String`? |
| `TextP.notRegex(string)` | Does the incoming `String` fail to match the regular expression in the provided `String`? |

|  |  |
| --- | --- |
| Note | The TinkerPop reference implementation uses the Java `Pattern` and `Matcher` classes for it regular expression engine. Other implementations may decide to use a different regular expression engine. It's a good idea to check the documentation for the implementation you are using to verify the allowed regular expression syntax. |

```
gremlin> eq(2)
==>eq(2)
gremlin> not(neq(2)) //// (1)
==>not(neq(2))
gremlin> not(within('a','b','c'))
==>not(within([a, b, c]))
gremlin> not(within('a','b','c')).test('d') //// (2)
==>true
gremlin> not(within('a','b','c')).test('a')
==>false
gremlin> within(1,2,3).and(not(eq(2))).test(3) //// (3)
==>true
gremlin> inside(1,4).or(eq(5)).test(3) //// (4)
==>true
gremlin> inside(1,4).or(eq(5)).test(5)
==>true
gremlin> between(1,2) //// (5)
==>and(gte(1), lt(2))
gremlin> not(between(1,2))
==>or(not(gte(1)), not(lt(2)))
```

1. The `not()` of a `P`-predicate is another `P`-predicate.
2. `P`-predicates are arguments to various steps which internally `test()` the incoming value.
3. `P`-predicates can be and'd together.
4. `P`-predicates can be or' together.
5. `and()` is a `P`-predicate and thus, a `P`-predicate can be composed of multiple `P`-predicates.

|  |  |
| --- | --- |
| Tip | To reduce the verbosity of predicate expressions, it is good to `import static org.apache.tinkerpop.gremlin.process.traversal.P.*`. |

The following example demonstrates how the `regex()` predicate is used and it demonstrates an important point. When
using `regex()`, the string is considered a match to the pattern if any substring matches the pattern. It is therefore
important to use the appropriate boundary matchers (e.g. `$` for end of a line) to ensure a proper match.

```
gremlin> g.V().has('person', 'name', regex('peter')).values('name')
==>peter
gremlin> g.V().has('person', 'name', regex('r')).values('name')
==>marko
==>peter
gremlin> g.V().has('person', 'name', regex('r$')).values('name')
==>peter
```

Finally, note that [`where()`](06-steps/filter-steps.md#where-step)-step takes a `P<String>`. The provided string value refers to a variable
binding, not to the explicit string value.

```
gremlin> g.V().as('a').both().both().as('b').count()
==>30
gremlin> g.V().as('a').both().both().as('b').where('a',neq('b')).count()
==>18
```

## A Note on Types

Gremlin steps typically operate over a handful of types that are mostly standard across graph systems. There are the
common numeric types like `Integer`, `Long`, `Double`, general types like `String`, and `Boolean`, container types like
`List`, `Set`, and `Map`, and structural types particular to graphs such as `Vertex`, `Edge`, and `Property`. During
traversal execution, it's common to encounter mixed data types, especially when extracting values from multiple
properties or when working with heterogeneous data that may have been stored inconsistently over time.

Gremlin identifies these types in the `GType` enumeration, offering a clear presentation of the standard data types one
might typically encounter with Gremlin. This enumeration is an important part of the Gremlin language in that it acts
as the argument to the `typeOf()` predicate used for filtering values based on their runtime data type.

### GType Enums

`GType` consists of the following enumerations:

* **Numeric types**: `INT`, `LONG`, `DOUBLE`, `FLOAT`, `BYTE`, `SHORT`, `BIGDECIMAL`, `BIGINT`
* **General types**: `STRING`, `BOOLEAN`, `CHAR`, `UUID`, `BINARY`
* **Collection types**: `LIST`, `SET`, `MAP`
* **Graph types**: `VERTEX`, `EDGE`, `PROPERTY`, `VPROPERTY`, `PATH`, `TREE`, `GRAPH`
* **Temporal types**: `DATETIME`, `DURATION`
* **Special types**: `NULL`, `NUMBER` (supertype for all numeric types)

As mentioned, the `typeOf()` predicate becomes particularly useful when dealing with mixed data scenarios. For example,
you would like to only return the integer values of a set of properties for further processing:

```
gremlin> g.V().values('age','name').is(P.typeOf(GType.INT)).asNumber(GType.SHORT)
==>29
==>27
==>32
==>35
```

The `NUMBER` type allows for broader type-based filtering without needing to specify each individual numeric type:

```
gremlin> g.union(V(), E()).values().is(P.typeOf(GType.NUMBER))
==>29
==>27
==>32
==>35
==>0.5
==>1.0
==>0.4
==>1.0
==>0.4
==>0.2
```

Type filtering is also valuable when working with traversals that return mixed graph elements. For example, when a
traversal might return both vertices and edges, you can add filter or condition based on the elements of interest:

```
gremlin> g.V().outE().inV().path().unfold().is(P.typeOf(GType.EDGE))
==>e[9][1-created->3]
==>e[7][1-knows->2]
==>e[8][1-knows->4]
==>e[10][4-created->5]
==>e[11][4-created->3]
==>e[12][6-created->3]
gremlin> g.V().outE().inV().path().unfold().choose(typeOf(VERTEX), values('name'), values('weight'))
==>marko
==>0.4
==>lop
==>marko
==>0.5
==>vadas
==>marko
==>1.0
==>josh
==>josh
==>1.0
==>ripple
==>josh
==>0.4
==>lop
==>peter
==>0.2
==>lop
```

### GlobalTypeCache

The `GlobalTypeCache` stores custom types registered by database providers as string-to-class mappings. These registered
type names can then be used with `P.typeOf()` for type filtering in the traversal. Consult your provider's documentation
for the correct type names when using provider-specific types.

By default, `GType` enumerations are registered using their simple class names and can be used as shown below.

```
gremlin> g.V().values('age','name').is(P.typeOf('Integer'))
==>29
==>27
==>32
==>35
```

## A Note on Maps

Many steps in Gremlin return `Map`-based results. Commonly used steps like [`project()`](06-steps/map-steps.md#project-step),
['group()'](06-steps/sideeffect-steps.md#group-step), and [`select()`](06-steps/map-steps.md#select-step) are just some examples of steps that fall into this category.
When working with `Map` results there are a couple of important things to know.

First, it is important to recognize that there is a bit of a difference in behavior that occurs when using
[unfold()](06-steps/map-steps.md#unfold-step) on a `Map` in embedded contexts versus remote contexts. In embedded contexts, an unfolded `Map`
becomes its composite `Map.Entry` objects as is typical in Java. The following example demonstrates the basic name/value
pairs that returned:

```
gremlin> g.V().valueMap('name','age').unfold()
==>name=[marko]
==>age=[29]
==>name=[vadas]
==>age=[27]
==>name=[lop]
==>name=[josh]
==>age=[32]
==>name=[ripple]
==>name=[peter]
==>age=[35]
```

In remote contexts, an unfolded `Map` becomes `Map.Entry` on the server as in the embedded case, but is returned to the
application as a `Map` with one entry. The slight difference in notation in Gremlin Console is shown in the following
remote example:

```
gremlin> g.V().valueMap('name','age').unfold()
==>[name:[marko]]
==>[age:[29]]
==>[name:[vadas]]
==>[age:[27]]
==>[name:[lop]]
==>[name:[josh]]
==>[age:[32]]
==>[name:[ripple]]
==>[name:[peter]]
==>[age:[35]]
```

The primary reason for this difference lies in the fact that Gremlin Language Variants, like Python and Go, do not have
a native `Map.Entry` concept that can be used. The most universal data structure across programming languages is the
`Map` itself. It is important to note that this transformation from `Map.Entry` to `Map` only applies to results
received on the client-side. In other words, if a step was to follow `unfold()` in the prior example, it would be
dealing with `Map.Entry` and not a `Map`, so Gremlin semantics should remain consistent on the server side.

The second issues to consider with steps that return a `Map` is that access keys on a `Map` is not always as consistent
as expected. The issue is best demonstrated in some examples:

```
// note that elements can be grouped by(id), but that same pattern can't be applied to get
// a T.id in a Map
gremlin> g.V().hasLabel('person').both().group().by(id)
==>[1:[v[1],v[1]],2:[v[2]],3:[v[3],v[3],v[3]],4:[v[4]],5:[v[5]]]
gremlin> g.V().hasLabel('person').both().elementMap().group().by(id)
TokenTraversal support of java.util.LinkedHashMap does not allow selection by id
Type ':help' or ':h' for help.
Display stack trace? [yN]

// note that select() can't be used if the key is a non-string
gremlin> g.V().hasLabel('person').both().group().by('age').select(32)
No signature of method: org.apache.tinkerpop.gremlin.process.traversal.dsl.graph.DefaultGraphTraversal.select() is applicable for argument types: (Integer) values: [32]
Possible solutions: reset(), collect(), sleep(long), collect(groovy.lang.Closure), inject(groovy.lang.Closure), split(groovy.lang.Closure)
Type ':help' or ':h' for help.
Display stack trace? [yN]
```

While this problem might be solved in future versions, the workaround for both cases is to use
[constant()](06-steps/map-steps.md#constant-step) as shown in the following example:

```
gremlin> g.V().hasLabel('person').both().group().by(constant(id))
==>[id:[v[3],v[2],v[4],v[1],v[5],v[3],v[1],v[3]]]
gremlin> g.V().hasLabel('person').both().group().by('age').select(constant(32))
==>[v[4]]
```

## A Note on Barrier Steps

![barrier](../images/barrier.png) Gremlin is primarily a
[lazy](http://en.wikipedia.org/wiki/Lazy_evaluation), stream processing language. This means that Gremlin fully
processes (to the best of its abilities) any traversers currently in the traversal pipeline before getting more data
from the start/head of the traversal. However, there are numerous situations in which a completely lazy computation
is not possible (or impractical). When a computation is not lazy, a "barrier step" exists. There are three types of
barriers:

1. `CollectingBarrierStep`: All of the traversers prior to the step are put into a collection and then processed in
   some way (e.g. ordered) prior to the collection being "drained" one-by-one to the next step. Examples
   include: [`order()`](06-steps/map-steps.md#order-step), [`sample()`](06-steps/filter-steps.md#sample-step), [`aggregate()`](06-steps/sideeffect-steps.md#aggregate-step), [`barrier()`](06-steps/terminal-steps.md#barrier-step).
2. `ReducingBarrierStep`: All of the traversers prior to the step are processed by a reduce function and once all the
   previous traversers are processed, a single "reduced value" traverser is emitted to the next step. Note that the path
   history leading up to a reducing barrier step is destroyed given its many-to-one nature. Examples include:
   [`fold()`](06-steps/map-steps.md#fold-step), [`count()`](06-steps/map-steps.md#count-step), [`sum()`](06-steps/map-steps.md#sum-step), [`max()`](06-steps/map-steps.md#max-step), [`min()`](06-steps/map-steps.md#min-step).
3. `SupplyingBarrierStep`: All of the traversers prior to the step are iterated (no processing) and then some provided
   supplier yields a single traverser to continue to the next step. Examples include: [`cap()`](06-steps/sideeffect-steps.md#cap-step).

In Gremlin OLAP (see [`TraversalVertexProgram`](09-graphcomputer.md#traversalvertexprogram)), a barrier is introduced at the end of
every [adjacent vertex step](06-steps/map-steps.md#vertex-steps). This means that the traversal does its best to compute as much as
possible at the current, local vertex. What it can't compute without referencing an adjacent vertex is aggregated
into a barrier collection. When there are no more traversers at the local vertex, the barriered traversers are the
messages that are propagated to remote vertices for further processing.

## A Note on Scopes

The `Scope` enum has two constants: `Scope.local` and `Scope.global`. Scope determines whether the particular step
being scoped is with respects to the current object (`local`) at that step or to the entire stream of objects up to that
step (`global`).

|  |  |
| --- | --- |
| Python | The term `global` is a reserved word in Python, and therefore a `Scope` using that term must be referred as `global_`. |

```
gremlin> g.V().has('name','marko').out('knows').count() //// (1)
==>2
gremlin> g.V().has('name','marko').out('knows').fold().count() //// (2)
==>1
gremlin> g.V().has('name','marko').out('knows').fold().count(local) //// (3)
==>2
gremlin> g.V().has('name','marko').out('knows').fold().count(global) //// (4)
==>1
```

1. Marko knows 2 people.
2. A list of Marko's friends is created and thus, one object is counted (the single list).
3. A list of Marko's friends is created and a `local`-count yields the number of objects in that list.
4. `count(global)` is the same as `count()` as the default behavior for most scoped steps is `global`.

The steps that support scoping are:

* [`count()`](06-steps/map-steps.md#count-step): count the local collection or global stream.
* [`dedup()`](06-steps/filter-steps.md#dedup-step): dedup the local collection of global stream.
* [`max()`](06-steps/map-steps.md#max-step): get the max value in the local collection or global stream.
* [`mean()`](06-steps/map-steps.md#mean-step): get the mean value in the local collection or global stream.
* [`min()`](06-steps/map-steps.md#min-step): get the min value in the local collection or global stream.
* [`order()`](06-steps/map-steps.md#order-step): order the objects in the local collection or global stream.
* [`range()`](06-steps/filter-steps.md#range-step): clip the local collection or global stream.
* [`limit()`](06-steps/filter-steps.md#limit-step): clip the local collection or global stream.
* [`sample()`](06-steps/filter-steps.md#sample-step): sample objects from the local collection or global stream.
* [`tail()`](06-steps/filter-steps.md#tail-step): get the tail of the objects in the local collection or global stream.

A few more examples of the use of `Scope` are provided below:

```
gremlin> g.V().both().group().by(label).select('software').dedup(local)
==>[v[3],v[5]]
gremlin> g.V().groupCount().by(label).select(values).min(local)
==>2
gremlin> g.V().groupCount().by(label).order(local).by(values,desc)
==>[person:4,software:2]
gremlin> g.V().fold().sample(local,2)
==>[v[5],v[3]]
```

Finally, note that [`local()`](06-steps/branch-steps.md#local-step)-step is a "hard-scoped step" that transforms any internal traversal into a
locally-scoped operation. A contrived example is provided below:

```
gremlin> g.V().fold().local(unfold().count())
==>6
gremlin> g.V().fold().count(local)
==>6
```

## A Note On Lambdas

![lambda](../images/lambda.png) A [lambda](http://en.wikipedia.org/wiki/Anonymous_function) is a function
that can be referenced by software and thus, passed around like any other piece of data. In Gremlin, lambdas make it
possible to generalize the behavior of a step such that custom steps can be created (on-the-fly) by the user. However,
it is advised to avoid using lambdas if possible.

```
gremlin> g.V().filter{it.get().value('name') == 'marko'}.
               flatMap{it.get().vertices(OUT,'created')}.
               map {it.get().value('name')} //// (1)
==>lop
gremlin> g.V().has('name','marko').out('created').values('name') //// (2)
==>lop
```

1. A lambda-rich Gremlin traversal which should and can be avoided. (**bad**)
2. The same traversal (result), but without using lambdas. (**good**)

Gremlin attempts to provide the user a comprehensive collection of steps in the hopes that the user will never need to
leverage a lambda in practice. It is advised that users only leverage a lambda if and only if there is no
corresponding lambda-less step that encompasses the desired functionality. The reason being, lambdas can not be
optimized by Gremlin's compiler strategies as they can not be programmatically inspected (see
[traversal strategies](07-traversal-strategies.md#traversalstrategy)). It is also not currently possible to send a natively written lambda for
remote execution to Gremlin-Server or a driver that supports remote execution.

In many situations where a lambda could be used, either a corresponding step exists or a traversal can be provided in
its place. A `TraversalLambda` behaves like a typical lambda, but it can be optimized and it yields less objects than
the corresponding pure-lambda form.

```
gremlin> g.V().out().out().path().by {it.value('name')}.
                                  by {it.value('name')}.
                                  by {g.V(it).in('created').values('name').fold().next()} //// (1)
==>[marko,josh,[josh]]
==>[marko,josh,[marko,josh,peter]]
gremlin> g.V().out().out().path().by('name').
                                  by('name').
                                  by(__.in('created').values('name').fold()) //// (2)
==>[marko,josh,[josh]]
==>[marko,josh,[marko,josh,peter]]
```

1. The length-3 paths have each of their objects transformed by a lambda. (**bad**)
2. The length-3 paths have their objects transformed by a lambda-less step and a traversal lambda. (**good**)
