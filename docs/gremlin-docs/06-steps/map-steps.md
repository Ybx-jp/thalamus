### AsString Step

The `asString()`-step (**map**) returns the value of incoming traverser as strings. Any `null` value will cause an `IllegalArgumentException`.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person').values('age').asString() //// (1)
==>29
==>27
==>32
==>35
gremlin> g.V().hasLabel('person').values('age').asString().concat(' years old') //// (2)
==>29 years old
==>27 years old
==>32 years old
==>35 years old
gremlin> g.V().hasLabel('person').values('age').fold().asString(local) //// (3)
==>[29,27,32,35]
```

```
g.V().hasLabel('person').values('age').asString() //// (1)
g.V().hasLabel('person').values('age').asString().concat(' years old') //// (2)
g.V().hasLabel('person').values('age').fold().asString(local) //3
```

1. Return ages as string.
2. Return ages as string and use concat to generate phrases.
3. Use `Scope.local` to operate on individual string elements inside incoming list, which will return a list.

**Additional References**

[`asString()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#asString())
[`asString(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#asString(org.apache.tinkerpop.gremlin.process.traversal.Scope))

### AsBool Step

The `asBool()`-step (**map**) converts the incoming traverser to a boolean value. If the traverser is already a boolean value, it is passed as-is. Numbers evaluate to
`true` if non-zero, and to `false` if zero or `NaN`. Strings are only accepted when
equal to `"true"` or `"false"` (case-insensitive), otherwise an `IllegalArgumentException` is thrown.
All other types (including `null`) will throw an `IllegalArgumentException`.

console (groovy)

groovy

```
gremlin> g.inject(1).asBool() //// (1)
==>true
gremlin> g.inject("false").asBool() //// (2)
==>false
```

```
g.inject(1).asBool() //// (1)
g.inject("false").asBool() //2
```

1. Convert number to boolean
2. Convert string to boolean

**Additional References**

[`asBool()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#asBool())

### AsDate Step

The `asDate()`-step (**map**) converts string or numeric input to Date.

For string input only ISO-8601 format is supported. For numbers, the value is considered as the number of the
milliseconds since "the epoch" (January 1, 1970, 00:00:00 GMT). Date input is passed without changes.

If the incoming traverser is not a string, number, Date or OffsetDateTime then an `IllegalArgumentException` will be thrown.

console (groovy)

groovy

```
gremlin> g.inject(1690934400000).asDate() //// (1)
==>2023-08-02T00:00Z
gremlin> g.inject("2023-08-02T00:00:00Z").asDate() //// (2)
==>2023-08-02T00:00Z
gremlin> g.inject(datetime("2023-08-24T00:00:00Z")).asDate() //// (3)
==>2023-08-24T00:00Z
```

```
g.inject(1690934400000).asDate() //// (1)
g.inject("2023-08-02T00:00:00Z").asDate() //// (2)
g.inject(datetime("2023-08-24T00:00:00Z")).asDate() //3
```

1. Convert number to Date
2. Convert ISO-8601 string to Date
3. Pass Date without modification

**Additional References**

[`asDate()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#asDate())

### AsNumber Step

The `asNumber()`-step (**map**) converts the incoming traverser to the nearest parsable type if no argument is provided,
or to the desired numerical type, based on the type token (`GType`) provided. If a type token entered isn’t a numerical type, an `IllegalArgumentException` will be thrown.

Numerical input will pass through unless a type is specified by the number token. `ArithmeticException` will be thrown
for any overflow during narrowing of types.

String inputs are parsed into numeric values. By default, the value will be parsed as an integer if it represents a
whole number, or as a double if it contains a decimal point. A `NumberFormatException` will be thrown if the string
cannot be parsed into a valid number format.

Date inputs are converted to milliseconds since epoch (January 1, 1970, 00:00:00 GMT).

All other input types will result in `IllegalArgumentException`.

console (groovy)

groovy

```
gremlin> g.inject(1234).asNumber() //// (1)
==>1234
gremlin> g.inject(1.76d).asNumber() //// (2)
==>1.76
gremlin> g.inject(1.76d).asNumber(GType.INT) //// (3)
==>1
gremlin> g.inject("2023-08-02T00:00:00Z").asDate().asNumber() //// (4)
==>1690934400000
```

```
g.inject(1234).asNumber() //// (1)
g.inject(1.76d).asNumber() //// (2)
g.inject(1.76d).asNumber(GType.INT) //// (3)
g.inject("2023-08-02T00:00:00Z").asDate().asNumber() //4
```

1. An int will be passed through.
2. A double will be passed through.
3. A double is converted into an int.
4. A date is converted into milliseconds since epoch.

|  |  |
| --- | --- |
| Java | The enums values `byte`, `short`, `int`, `long`, `float`, `double` are reserved word in Java, and therefore must be referred to in Gremlin with an underscore appended as a suffix: `byte_`, `short_`, `int_`, `long_`, `float_`, `double_`. |

|  |  |
| --- | --- |
| Groovy & Gremlin Console | The enums values `byte`, `short`, `int`, `long`, `float`, `double` are reserved word in Groovy, therefore as the Gremlin Console is Groovy-based, they must be referred to in Gremlin with an underscore appended as a suffix: `byte_`, `short_`, `int_`, `long_`, `float_`, `double_`. |

|  |  |
| --- | --- |
| JavaScript | The enums values `byte`, `short`, `int`, `long`, `float`, `double` are reserved word in Javascript, and therefore must be referred to in Gremlin with an underscore appended as a suffix: `byte_`, `short_`, `int_`, `long_`, `float_`, `double_`. |

**Additional References**

[`asNumber()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#asNumber())
[`asNumber(N)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#asNumber(org.apache.tinkerpop.gremlin.process.traversal.N))

### Combine Step

The `combine()`-step (**map**) combines the elements of the incoming list traverser and the provided list argument into
one list. This is also known as appending or concatenating. This step only expects list data (array or Iterable) and
will throw an `IllegalArgumentException` if any other type is encountered (including `null`). This differs from the
`merge()`-step in that it allows duplicates to exist.

console (groovy)

groovy

```
gremlin> g.V().values("name").fold().combine(["james","jen","marko","vadas"])
==>[marko,vadas,lop,josh,ripple,peter,james,jen,marko,vadas]
gremlin> g.V().values("name").fold().combine(__.constant("stephen").fold())
==>[marko,vadas,lop,josh,ripple,peter,stephen]
```

```
g.V().values("name").fold().combine(["james","jen","marko","vadas"])
g.V().values("name").fold().combine(__.constant("stephen").fold())
```

**Additional References**

[`combine(Object)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#combine(java.lang.Object))
[`Semantics`](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#combine-step)

### Concat Step

The `concat()`-step (**map**) concatenates one or more String values together to the incoming String traverser. This step
can take either String varargs or Traversal varargs.
Any `null` String values will be skipped when concatenated with non-`null` String values. If two `null` value are
concatenated, the `null` value will be propagated and returned.
If the incoming traverser is a non-String value then an `IllegalArgumentException` will be thrown.

console (groovy)

groovy

```
gremlin> g.addV(constant('prefix_').concat(__.V(1).label())).property(id, 10) //// (1)
==>v[10]
gremlin> g.V(10).label()
==>prefix_person
gremlin> g.V().hasLabel('person').values('name').as('a').
             constant('Mr.').concat(__.select('a')) //// (2)
==>Mr.marko
==>Mr.vadas
==>Mr.josh
==>Mr.peter
gremlin> g.V().hasLabel('software').as('a').values('name').
             concat(' uses ').
             concat(select('a').values('lang')) //// (3)
==>lop uses java
==>ripple uses java
gremlin> g.V(1).outE().as('a').V(1).values('name').
             concat(' ').
             concat(select('a').label()).
             concat(' ').
             concat(select("a").inV().values('name')) //// (4)
==>marko created lop
==>marko knows vadas
==>marko knows josh
gremlin> g.V(1).outE().as('a').V(1).values('name').
             concat(constant(' '),
                 select("a").label(),
                 constant(' '),
                 select('a').inV().values('name')) //// (5)
==>marko created lop
==>marko knows vadas
==>marko knows josh
gremlin> g.inject('hello', 'hi').concat(__.V().values('name')) //// (6)
==>hellomarko
==>himarko
gremlin> g.inject('This').concat(' ').concat('is a ', 'gremlin.') //// (7)
==>This is a gremlin.
```

```
g.addV(constant('prefix_').concat(__.V(1).label())).property(id, 10) //// (1)
g.V(10).label()
g.V().hasLabel('person').values('name').as('a').
    constant('Mr.').concat(__.select('a')) //// (2)
g.V().hasLabel('software').as('a').values('name').
    concat(' uses ').
    concat(select('a').values('lang')) //// (3)
g.V(1).outE().as('a').V(1).values('name').
    concat(' ').
    concat(select('a').label()).
    concat(' ').
    concat(select("a").inV().values('name')) //// (4)
g.V(1).outE().as('a').V(1).values('name').
    concat(constant(' '),
        select("a").label(),
        constant(' '),
        select('a').inV().values('name')) //// (5)
g.inject('hello', 'hi').concat(__.V().values('name')) //// (6)
g.inject('This').concat(' ').concat('is a ', 'gremlin.') //7
```

1. Add a new vertex with id 10 which should be labeled like an existing vertex but with some prefix attached
2. Attach the prefix "Mr." to all the names using the `constant()`-step
3. Generate a string of software names and the language they use
4. Generate a string description for each of marko’s outgoing edges
5. Alternative way to generate the string description by using traversal varargs. Use the `constant()` step to add
   desired strings between arguments.
6. The `concat()` step will append the first result from the child traversal to the incoming traverser
7. A generic use of `concat()` to join strings together

**Additional References**

[`concat(String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#concat(java.lang.String))
[`concat(Taversal, Traversal…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#concat(org.apache.tinkerpop.gremlin.process.traversal.Traversal,org.apache.tinkerpop.gremlin.process.traversal.Traversal...))
[`Semantics`](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#concat-step)

### Conjoin Step

The `conjoin()`-step (**map**) joins together the elements in the incoming list traverser together with the provided argument
as a delimiter. The resulting `String` is added to the Traversal Stream. This step only expects list data (array or
Iterable) in the incoming traverser and will throw an `IllegalArgumentException` if any other type is encountered
(including `null`). Null values are skipped and not included in the result.

console (groovy)

groovy

```
gremlin> g.V().values("name").fold().conjoin("+")
==>marko+vadas+lop+josh+ripple+peter
```

```
g.V().values("name").fold().conjoin("+")
```

**Additional References**

[`conjoin(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#conjoin(java.lang.String))
[`Semantics`](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#conjoin-step)

### ConnectedComponent Step

The `connectedComponent()` step performs a computation to identify [Connected Component](https://en.wikipedia.org/wiki/Connected_component_(graph_theory))
instances in a graph. When this step completes, the vertices will be labelled with a component identifier to denote
the component to which they are associated.

|  |  |
| --- | --- |
| Important | The `connectedComponent()`-step is a `VertexComputing`-step and as such, can only be used against a graph that supports `GraphComputer` (OLAP). |

console (groovy)

groovy

```
gremlin> g = traversal().with(graph).withComputer()
==>graphtraversalsource[tinkergraph[vertices:6 edges:6], graphcomputer]
gremlin> g.V().
           connectedComponent().
             with(ConnectedComponent.propertyName, 'component').
           project('name','component').
             by('name').
             by('component')
==>[name:josh,component:1]
==>[name:marko,component:1]
==>[name:ripple,component:1]
==>[name:peter,component:1]
==>[name:vadas,component:1]
==>[name:lop,component:1]
gremlin> g.V().hasLabel('person').
           connectedComponent().
             with(ConnectedComponent.propertyName, 'component').
             with(ConnectedComponent.edges, outE('knows')).
           project('name','component').
             by('name').
             by('component')
==>[name:vadas,component:1]
==>[name:josh,component:1]
==>[name:marko,component:1]
==>[name:peter,component:6]
```

```
g = traversal().with(graph).withComputer()
g.V().
  connectedComponent().
    with(ConnectedComponent.propertyName, 'component').
  project('name','component').
    by('name').
    by('component')
g.V().hasLabel('person').
  connectedComponent().
    with(ConnectedComponent.propertyName, 'component').
    with(ConnectedComponent.edges, outE('knows')).
  project('name','component').
    by('name').
    by('component')
```

Note the use of the `with()` modulating step which provides configuration options to the algorithm. It takes
configuration keys from the `ConnectedComponent` class and is automatically imported to the Gremlin Console.

**Additional References**

[`connectedComponent()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#connectedComponent())

### Constant Step

To specify a constant value for a traverser, use the `constant()`-step (**map**). This is often useful with conditional
steps like [`choose()`-step](06-steps/branch-steps.md#choose-step) or [`coalesce()`-step](06-steps/branch-steps.md#coalesce-step).

console (groovy)

groovy

```
gremlin> g.V().choose(hasLabel('person'),
             values('name'),
             constant('inhuman')) //// (1)
==>marko
==>vadas
==>inhuman
==>josh
==>inhuman
==>peter
gremlin> g.V().coalesce(
             hasLabel('person').values('name'),
             constant('inhuman')) //// (2)
==>marko
==>vadas
==>inhuman
==>josh
==>inhuman
==>peter
```

```
g.V().choose(hasLabel('person'),
    values('name'),
    constant('inhuman')) //// (1)
g.V().coalesce(
    hasLabel('person').values('name'),
    constant('inhuman')) //2
```

1. Show the names of people, but show "inhuman" for other vertices.
2. Same as statement 1 (unless there is a person vertex with no name).

**Additional References**

[`constant(Object)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#constant(E2))

### Count Step

![count step](../images/count-step.png)

The `count()`-step (**map**) counts the total number of represented traversers in the streams (i.e. the bulk count).

console (groovy)

groovy

```
gremlin> g.V().count()
==>6
gremlin> g.V().hasLabel('person').count()
==>4
gremlin> g.V().hasLabel('person').outE('created').count().path() //// (1)
==>[4]
gremlin> g.V().hasLabel('person').outE('created').count().map {it.get() * 10}.path() //// (2)
==>[4,40]
```

```
g.V().count()
g.V().hasLabel('person').count()
g.V().hasLabel('person').outE('created').count().path() //// (1)
g.V().hasLabel('person').outE('created').count().map {it.get() * 10}.path() //2
```

1. `count()`-step is a [reducing barrier step](../05a-traversal-concepts.md#a-note-on-barrier-steps) meaning that all of the previous traversers are folded into a new traverser.
2. The path of the traverser emanating from `count()` starts at `count()`.

|  |  |
| --- | --- |
| Important | `count(local)` counts the current, local object (not the objects in the traversal stream). This works for `Collection`- and `Map`-type objects. For any other object, a count of 1 is returned. |

**Additional References**

[`count()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#count()),
[`count(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#count(org.apache.tinkerpop.gremlin.process.traversal.Scope)),
[`Scope`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Scope.html)

### DateAdd Step

The `dateAdd()`-step (**map**) returns the value with the addition of the value number of units as specified by the DateToken.
If the incoming traverser is not a Date or OffsetDateTime, then an `IllegalArgumentException` will be thrown.

console (groovy)

groovy

```
gremlin> g.inject("2023-08-02T00:00:00Z").asDate().dateAdd(DT.day, 7) //// (1)
==>2023-08-09T00:00Z
gremlin> g.inject(["2023-08-02T00:00:00Z", "2023-08-03T00:00:00Z"]).unfold().asDate().dateAdd(DT.minute, 1) //// (2)
==>2023-08-02T00:01Z
==>2023-08-03T00:01Z
```

```
g.inject("2023-08-02T00:00:00Z").asDate().dateAdd(DT.day, 7) //// (1)
g.inject(["2023-08-02T00:00:00Z", "2023-08-03T00:00:00Z"]).unfold().asDate().dateAdd(DT.minute, 1) //2
```

1. Add 7 days to Date
2. Add 1 minute to incoming dates

**Additional References**

[`dateAdd(DT,int)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#dateAdd(org.apache.tinkerpop.gremlin.process.traversal.DT,int))

### DateDiff Step

The `dateDiff()`-step (**map**) returns the difference between two Dates in epoch time in milliseconds.
If the incoming traverser is not a Date or OffsetDateTime, then an `IllegalArgumentException` will be thrown.

console (groovy)

groovy

```
gremlin> g.inject("2023-08-02T00:00:00Z").asDate().dateDiff(constant("2023-08-03T00:00:00Z").asDate()) //// (1)
==>-86400000
```

```
g.inject("2023-08-02T00:00:00Z").asDate().dateDiff(constant("2023-08-03T00:00:00Z").asDate()) //1
```

1. Find difference between two dates in milliseconds

**Additional References**

[`dateDiff(Date)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#dateDiff(java.util.Date)),
[`dateDiff(OffsetDateTime)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#dateDiff(java.util.Date)),
[`dateDiff(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#dateDiff(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### Difference Step

The `difference()`-step (**map**) calculates the difference between the incoming list traverser and the provided list
argument. More specifically, this provides the set operation A-B where A is the traverser and B is the argument. This
step only expects list data (array or Iterable) and will throw an `IllegalArgumentException` if any other type is
encountered (including `null`).

console (groovy)

groovy

```
gremlin> g.V().values("name").fold().difference(["lop","ripple"])
==>[peter,vadas,josh,marko]
gremlin> g.V().values("name").fold().difference(__.V().limit(2).values("name").fold())
==>[ripple,peter,josh,lop]
```

```
g.V().values("name").fold().difference(["lop","ripple"])
g.V().values("name").fold().difference(__.V().limit(2).values("name").fold())
```

**Additional References**

[`difference(Object)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#difference(java.lang.Object))
[`Semantics`](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#difference-step)

### Disjunct Step

The `disjunct()`-step (**map**) calculates the disjunct set between the incoming list traverser and the provided list
argument. This step only expects list data (array or Iterable) and will throw an `IllegalArgumentException` if any other
type is encountered (including `null`).

console (groovy)

groovy

```
gremlin> g.V().values("name").fold().disjunct(["lop","peter","sam"]) //// (1)
==>[ripple,vadas,josh,sam,marko]
gremlin> g.V().values("name").fold().disjunct(__.V().limit(3).values("name").fold())
==>[ripple,peter,josh]
```

```
g.V().values("name").fold().disjunct(["lop","peter","sam"]) //// (1)
g.V().values("name").fold().disjunct(__.V().limit(3).values("name").fold())
```

1. Find the unique names between two group of names

**Additional References**

[`disjunct(Object)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#disjunct(java.lang.Object))
[`Semantics`](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#disjunct-step)

### Element Step

The `element()` step is a no-argument step that traverses from a `Property` to the `Element` that owns it.

console (groovy)

groovy

```
gremlin> g.V().properties().element() //// (1)
==>v[1]
==>v[1]
==>v[1]
==>v[1]
==>v[1]
==>v[7]
==>v[7]
==>v[7]
==>v[7]
==>v[8]
==>v[8]
==>v[8]
==>v[8]
==>v[8]
==>v[9]
==>v[9]
==>v[9]
==>v[9]
==>v[10]
==>v[11]
gremlin> g.E().properties().element() //// (2)
==>e[13][1-develops->10]
==>e[14][1-develops->11]
==>e[15][1-uses->10]
==>e[16][1-uses->11]
==>e[17][7-develops->10]
==>e[18][7-develops->11]
==>e[19][7-uses->10]
==>e[20][7-uses->11]
==>e[21][8-develops->10]
==>e[22][8-uses->10]
==>e[23][8-uses->11]
==>e[24][9-uses->10]
==>e[25][9-uses->11]
gremlin> g.V().properties().properties().element() //// (3)
==>vp[location->san diego]
==>vp[location->san diego]
==>vp[location->santa cruz]
==>vp[location->santa cruz]
==>vp[location->brussels]
==>vp[location->brussels]
==>vp[location->santa fe]
==>vp[location->centreville]
==>vp[location->centreville]
==>vp[location->dulles]
==>vp[location->dulles]
==>vp[location->purcellville]
==>vp[location->bremen]
==>vp[location->bremen]
==>vp[location->baltimore]
==>vp[location->baltimore]
==>vp[location->oakland]
==>vp[location->oakland]
==>vp[location->seattle]
==>vp[location->spremberg]
==>vp[location->spremberg]
==>vp[location->kaiserslautern]
==>vp[location->kaiserslautern]
==>vp[location->aachen]
```

```
g.V().properties().element() //// (1)
g.E().properties().element() //// (2)
g.V().properties().properties().element() //3
```

1. Traverse from `VertexProperty` to `Vertex`
2. Traverse from `Property` (edge property) to `Edge`
3. Traverse from `Property` (meta property) to `VertexProperty`

**Additional References**

[`element()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#element())

### ElementMap Step

The `elementMap()`-step yields a `Map` representation of the structure of an element.

console (groovy)

groovy

```
gremlin> g.V().elementMap()
==>[id:1,label:person,name:marko,age:29]
==>[id:2,label:person,name:vadas,age:27]
==>[id:3,label:software,name:lop,lang:java]
==>[id:4,label:person,name:josh,age:32]
==>[id:5,label:software,name:ripple,lang:java]
==>[id:6,label:person,name:peter,age:35]
gremlin> g.V().elementMap('age')
==>[id:1,label:person,age:29]
==>[id:2,label:person,age:27]
==>[id:3,label:software]
==>[id:4,label:person,age:32]
==>[id:5,label:software]
==>[id:6,label:person,age:35]
gremlin> g.V().elementMap('age','blah')
==>[id:1,label:person,age:29]
==>[id:2,label:person,age:27]
==>[id:3,label:software]
==>[id:4,label:person,age:32]
==>[id:5,label:software]
==>[id:6,label:person,age:35]
gremlin> g.E().elementMap()
==>[id:7,label:knows,IN:[id:2,label:person],OUT:[id:1,label:person],weight:0.5]
==>[id:8,label:knows,IN:[id:4,label:person],OUT:[id:1,label:person],weight:1.0]
==>[id:9,label:created,IN:[id:3,label:software],OUT:[id:1,label:person],weight:0.4]
==>[id:10,label:created,IN:[id:5,label:software],OUT:[id:4,label:person],weight:1.0]
==>[id:11,label:created,IN:[id:3,label:software],OUT:[id:4,label:person],weight:0.4]
==>[id:12,label:created,IN:[id:3,label:software],OUT:[id:6,label:person],weight:0.2]
```

```
g.V().elementMap()
g.V().elementMap('age')
g.V().elementMap('age','blah')
g.E().elementMap()
```

It is important to note that the map of a vertex assumes that cardinality for each key is `single` and if it is `list`
then only the first item encountered will be returned. As `single` is the more common cardinality for properties this
assumption should serve the greatest number of use cases.

console (groovy)

groovy

```
gremlin> g.V().elementMap()
==>[id:1,label:person,name:marko,location:santa fe]
==>[id:7,label:person,name:stephen,location:purcellville]
==>[id:8,label:person,name:matthias,location:seattle]
==>[id:9,label:person,name:daniel,location:aachen]
==>[id:10,label:software,name:gremlin]
==>[id:11,label:software,name:tinkergraph]
gremlin> g.V().has('name','marko').properties('location')
==>vp[location->san diego]
==>vp[location->santa cruz]
==>vp[location->brussels]
==>vp[location->santa fe]
gremlin> g.V().has('name','marko').properties('location').elementMap()
==>[id:6,key:location,value:san diego,startTime:1997,endTime:2001]
==>[id:7,key:location,value:santa cruz,startTime:2001,endTime:2004]
==>[id:8,key:location,value:brussels,startTime:2004,endTime:2005]
==>[id:9,key:location,value:santa fe,startTime:2005]
```

```
g.V().elementMap()
g.V().has('name','marko').properties('location')
g.V().has('name','marko').properties('location').elementMap()
```

|  |  |
| --- | --- |
| Important | The `elementMap()`-step does not return the vertex labels for incident vertices when using `GraphComputer` as the `id` is the only available data to the star graph. |

**Additional References**

[`elementMap(String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#elementMap(java.lang.String...))

### FlatMap Step

The `flatMap()` step maps the traverser from the current object to an `Iterator` of objects for the next step in the
process. Please see the [Steps Reference](index.md) for more information.

Be aware that the current traverser behavior where the traverser appears to be unaffected by state modifying steps or
account as a single bulk to side effects inside the `flatMap()` traversal is subject to change. The following are
examples of some traversals on the "modern" graph whose output may change:

```
gremlin> g.V(1, 1).barrier().flatMap(aggregate("x")).cap("x")
==>[v[1]]

gremlin> g.withSack(1.0f).V(1).barrier().flatMap(sack(mult).by("age")).sack()
==>1.0
```

**Additional References**

[`map(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#flatMap(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### Format Step

This step is designed to simplify some string operations. In general, it is similar to the string formatting function
available in many programming languages. Variable values can be picked up from Element properties, maps and scope variables.

console (groovy)

groovy

```
gremlin> g.V().format("%{name} is %{age} years old") //// (1)
==>marko is 29 years old
==>vadas is 27 years old
==>josh is 32 years old
==>peter is 35 years old
gremlin> g.V().hasLabel("person").as("a").values("name").as("p1").select("a").in("knows").format("%{p1} knows %{name}") //// (2)
==>vadas knows marko
==>josh knows marko
gremlin> g.V().format("%{name} has %{_} connections").by(bothE().count()) //// (3)
==>marko has 3 connections
==>vadas has 1 connections
==>lop has 3 connections
==>josh has 3 connections
==>ripple has 1 connections
==>peter has 1 connections
gremlin> g.V().project("name","count").by(values("name")).by(bothE().count()).format("%{name} has %{count} connections") //// (4)
==>marko has 3 connections
==>vadas has 1 connections
==>lop has 3 connections
==>josh has 3 connections
==>ripple has 1 connections
==>peter has 1 connections
```

```
g.V().format("%{name} is %{age} years old") //// (1)
g.V().hasLabel("person").as("a").values("name").as("p1").select("a").in("knows").format("%{p1} knows %{name}") //// (2)
g.V().format("%{name} has %{_} connections").by(bothE().count()) //// (3)
g.V().project("name","count").by(values("name")).by(bothE().count()).format("%{name} has %{count} connections") //4
```

1. A `format()` will use property values from incoming Element to produce String result.
2. A `format()` will use scope variable `p1` and property `name` to resolve variable values.
3. A `format()` will use property `name` and traversal product for positional argument to resolve variable values.
4. A `format()` will use map produced by `project` step to resolve variable values.

**Additional References**

[`format(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#format(java.lang.String)),

### Fold Step

There are situations when the traversal stream needs a "barrier" to aggregate all the objects and emit a computation
that is a function of the aggregate. The `fold()`-step (**map**) is one particular instance of this. Please see
[`unfold()`](06-steps/map-steps.md#unfold-step)-step for the inverse functionality.

console (groovy)

groovy

```
gremlin> g.V(1).out('knows').values('name')
==>vadas
==>josh
gremlin> g.V(1).out('knows').values('name').fold() //// (1)
==>[vadas,josh]
gremlin> g.V(1).out('knows').values('name').fold().next().getClass() //// (2)
==>class java.util.ArrayList
gremlin> g.V(1).out('knows').values('name').fold(0) {a,b -> a + b.length()} //// (3)
==>9
gremlin> g.V().values('age').fold(0) {a,b -> a + b} //// (4)
==>123
gremlin> g.V().values('age').fold(0, sum) //// (5)
==>123
gremlin> g.V().values('age').sum() //// (6)
==>123
gremlin> g.inject(["a":1],["b":2]).fold([], addAll) //// (7)
==>[[a:1],[b:2]]
```

```
g.V(1).out('knows').values('name')
g.V(1).out('knows').values('name').fold() //// (1)
g.V(1).out('knows').values('name').fold().next().getClass() //// (2)
g.V(1).out('knows').values('name').fold(0) {a,b -> a + b.length()} //// (3)
g.V().values('age').fold(0) {a,b -> a + b} //// (4)
g.V().values('age').fold(0, sum) //// (5)
g.V().values('age').sum() //// (6)
g.inject(["a":1],["b":2]).fold([], addAll) //7
```

1. A parameterless `fold()` will aggregate all the objects into a list and then emit the list.
2. A verification of the type of list returned.
3. `fold()` can be provided two arguments —  a seed value and a reduce bi-function ("vadas" is 5 characters + "josh" with 4 characters).
4. What is the total age of the people in the graph?
5. The same as before, but using a built-in bi-function.
6. The same as before, but using the [`sum()`-step](06-steps/map-steps.md#sum-step).
7. A mechanism for merging `Map` instances. If a key occurs in more than a single `Map`, the later occurrence will replace the earlier.

**Additional References**

[`fold()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#fold()),
[`fold(Object,BiFunction)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#fold(E2,java.util.function.BiFunction))

### Id Step

The `id()`-step (**map**) takes an `Element` and extracts its identifier from it.

console (groovy)

groovy

```
gremlin> g.V().id()
==>1
==>2
==>3
==>4
==>5
==>6
gremlin> g.V(1).out().id().is(2)
==>2
gremlin> g.V(1).outE().id()
==>9
==>7
==>8
gremlin> g.V(1).properties().id()
==>0
==>1
```

```
g.V().id()
g.V(1).out().id().is(2)
g.V(1).outE().id()
g.V(1).properties().id()
```

**Additional References**

[`id()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#id())

### Identity Step

The `identity()`-step (**map**) is an [identity function](https://en.wikipedia.org/wiki/Identity_function) which maps
the current object to itself.

console (groovy)

groovy

```
gremlin> g.V().identity()
==>v[1]
==>v[2]
==>v[3]
==>v[4]
==>v[5]
==>v[6]
```

```
g.V().identity()
```

**Additional References**

[`identity()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#identity())

### Index Step

The `index()`-step (**map**) indexes each element in the current collection. If the current traverser’s value is not a collection, then it’s treated as a single-item collection. There are two indexers
available, which can be chosen using the `with()` modulator. The list indexer (default) creates a list for each collection item, with the first item being the original element and the second element
being the index. The map indexer created a linked hash map in which the index represents the key and the original item is used as the value.

console (groovy)

groovy

```
gremlin> g.V().hasLabel("software").index() //// (1)
==>[[v[3],0]]
==>[[v[5],0]]
gremlin> g.V().hasLabel("software").values("name").fold().
           order(Scope.local).
           index().
           unfold().
           order().
             by(__.tail(Scope.local, 1)) //// (2)
==>[lop,0]
==>[ripple,1]
gremlin> g.V().hasLabel("software").values("name").fold().
           order(Scope.local).
           index().
             with(WithOptions.indexer, WithOptions.list).
           unfold().
           order().
             by(__.tail(Scope.local, 1)) //// (3)
==>[lop,0]
==>[ripple,1]
gremlin> g.V().hasLabel("person").values("name").fold().
           order(Scope.local).
           index().
             with(WithOptions.indexer, WithOptions.map) //// (4)
==>[0:josh,1:marko,2:peter,3:vadas]
```

```
g.V().hasLabel("software").index() //// (1)
g.V().hasLabel("software").values("name").fold().
  order(Scope.local).
  index().
  unfold().
  order().
    by(__.tail(Scope.local, 1)) //// (2)
g.V().hasLabel("software").values("name").fold().
  order(Scope.local).
  index().
    with(WithOptions.indexer, WithOptions.list).
  unfold().
  order().
    by(__.tail(Scope.local, 1)) //// (3)
g.V().hasLabel("person").values("name").fold().
  order(Scope.local).
  index().
    with(WithOptions.indexer, WithOptions.map)  //4
```

1. Indexing non-collection items results in multiple indexed single-item collections.
2. Index all software names in their alphabetical order.
3. Same as statement 1, but with an explicitely specified list indexer.
4. Index all person names in their alphabetical order and store the result in an ordered map.

**Additional References**

[`index()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#index())

### Intersect Step

The `intersect()`-step (**map**) calculates the intersection between the incoming list traverser and the provided list
argument. This step only expects list data (array or Iterable) and will throw an `IllegalArgumentException` if any other
type is encountered (including `null`).

console (groovy)

groovy

```
gremlin> g.V().values("name").fold().intersect(["marko","josh","james","jen"])
==>[josh,marko]
gremlin> g.V().values("name").fold().intersect(__.V().limit(2).values("name").fold())
==>[vadas,marko]
```

```
g.V().values("name").fold().intersect(["marko","josh","james","jen"])
g.V().values("name").fold().intersect(__.V().limit(2).values("name").fold())
```

**Additional References**

[`intersect(Object)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#intersect(java.lang.Object))
[`Semantics`](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#intersect-step)

### Key Step

The `key()`-step (**map**) takes a `Property` and extracts the key from it.

console (groovy)

groovy

```
gremlin> g.V(1).properties().key()
==>name
==>location
==>location
==>location
==>location
gremlin> g.V(1).properties().properties().key()
==>startTime
==>endTime
==>startTime
==>endTime
==>startTime
==>endTime
==>startTime
```

```
g.V(1).properties().key()
g.V(1).properties().properties().key()
```

**Additional References**

[`key()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#key())

### Label Step

The `label()`-step (**map**) takes an `Element` and extracts its label from it.

console (groovy)

groovy

```
gremlin> g.V().label()
==>person
==>person
==>software
==>person
==>software
==>person
gremlin> g.V(1).outE().label()
==>created
==>knows
==>knows
gremlin> g.V(1).properties().label()
==>name
==>age
```

```
g.V().label()
g.V(1).outE().label()
g.V(1).properties().label()
```

**Additional References**

[`label()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#label())

### Length Step

The `length()`-step (**map**) returns the length incoming string or list of string traverser. Null values are not processed and remain as null when returned.
If the incoming traverser is a non-String value then an `IllegalArgumentException` will be thrown.

console (groovy)

groovy

```
gremlin> g.V().values('name').length() //// (1)
==>5
==>5
==>3
==>4
==>6
==>5
gremlin> g.V().values('name').fold().length(local) //// (2)
==>[5,5,3,4,6,5]
```

```
g.V().values('name').length() //// (1)
g.V().values('name').fold().length(local) //2
```

1. Return the string length of all vertex names.
2. Use `Scope.local` to operate on individual string elements inside incoming list, which will return a list.

**Additional References**

[`length()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#length())
[`length(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#length(org.apache.tinkerpop.gremlin.process.traversal.Scope))

### Loops Step

The `loops()`-step (**map**) extracts the number of times the `Traverser` has gone through the current loop.

console (groovy)

groovy

```
gremlin> g.V().emit(__.has("name", "marko").or().loops().is(2)).repeat(__.out()).values("name")
==>marko
==>ripple
==>lop
```

```
g.V().emit(__.has("name", "marko").or().loops().is(2)).repeat(__.out()).values("name")
```

**Additional References**

[`loops()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#loops()),
[`Looping Recipes`](https://tinkerpop.apache.org/docs/3.8.0/recipes/#looping)

### LTrim Step

The `lTrim()`-step (**map**) returns a string with leading whitespace removed. Null values are not processed and remain
as null when returned. If the incoming traverser is a non-String value then an `IllegalArgumentException` will be thrown.

console (groovy)

groovy

```
gremlin> g.inject("   hello   ", " world ", null).lTrim()
==>hello
==>world
==>null
gremlin> g.inject(["   hello   ", " world ", null]).lTrim(local) //// (1)
==>[hello   ,world ,null]
```

```
g.inject("   hello   ", " world ", null).lTrim()
g.inject(["   hello   ", " world ", null]).lTrim(local) //1
```

1. Use `Scope.local` to operate on individual string elements inside incoming list, which will return a list.

[`lTrim()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#lTrim())
[`lTrim(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#lTrim(org.apache.tinkerpop.gremlin.process.traversal.Scope))

### Map Step

The `map()` step maps the traverser from the current object to the next step in the process. Please see the
[Steps Reference](index.md) for more information.

**Additional References**

[`map(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#map(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### Math Step

The `math()`-step (**math**) enables scientific calculator functionality within Gremlin. This step deviates from the common
function composition and nesting formalisms to provide an easy to read string-based math processor. Variables within the
equation map to scopes in Gremlin — e.g. path labels, side-effects, or incoming map keys. This step supports
`by()`-modulation where the `by()`-modulators are applied in the order in which the variables are first referenced
within the equation. Note that the reserved variable `_` refers to the current numeric traverser object incoming to the
`math()`-step.

console (groovy)

groovy

```
gremlin> g.V().as('a').out('knows').as('b').math('a + b').by('age')
==>56.0
==>61.0
gremlin> g.V().as('a').out('created').as('b').
           math('b + a').
             by(both().count().math('_ + 100')).
             by('age')
==>132.0
==>133.0
==>135.0
==>138.0
gremlin> g.withSideEffect('x',10).V().values('age').math('_ / x')
==>2.9
==>2.7
==>3.2
==>3.5
gremlin> g.withSack(1).V(1).repeat(sack(sum).by(constant(1))).times(10).emit().sack().math('sin _')
==>0.9092974268256817
==>0.1411200080598672
==>-0.7568024953079282
==>-0.9589242746631385
==>-0.27941549819892586
==>0.6569865987187891
==>0.9893582466233818
==>0.4121184852417566
==>-0.5440211108893698
==>-0.9999902065507035
gremlin> g.V().math('_+1').by('age') //// (1)
==>30.0
==>28.0
==>33.0
==>36.0
```

```
g.V().as('a').out('knows').as('b').math('a + b').by('age')
g.V().as('a').out('created').as('b').
  math('b + a').
    by(both().count().math('_ + 100')).
    by('age')
g.withSideEffect('x',10).V().values('age').math('_ / x')
g.withSack(1).V(1).repeat(sack(sum).by(constant(1))).times(10).emit().sack().math('sin _')
g.V().math('_+1').by('age') //1
```

1. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are filtered.

The operators supported by the calculator include: `*`, `+`, `/`, `^`, and `%`. Furthermore, the following built in
functions are provided:

* `abs`: absolute value
* `acos`: arc cosine
* `asin`: arc sine
* `atan`: arc tangent
* `cbrt`: cubic root
* `ceil`: nearest upper integer
* `cos`: cosine
* `cosh`: hyperbolic cosine
* `exp`: euler’s number raised to the power (`e^x`)
* `floor`: nearest lower integer
* `log`: logarithmus naturalis (base e)
* `log10`: logarithm (base 10)
* `log2`: logarithm (base 2)
* `sin`: sine
* `sinh`: hyperbolic sine
* `sqrt`: square root
* `tan`: tangent
* `tanh`: hyperbolic tangent
* `signum`: signum function

**Additional References**

[`math(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#math(java.lang.String))

### Max Step

The `max()`-step (**map**) operates on a stream of comparable objects and determines which is the last object according
to its natural order in the stream.

console (groovy)

groovy

```
gremlin> g.V().values('age').max()
==>35
gremlin> g.V().repeat(both()).times(3).values('age').max()
==>35
gremlin> g.V().values('name').max()
==>vadas
```

```
g.V().values('age').max()
g.V().repeat(both()).times(3).values('age').max()
g.V().values('name').max()
```

When called as `max(local)` it determines the maximum value of the current, local object (not the objects in the
traversal stream). This works for `Collection` and `Comparable`-type objects.

console (groovy)

groovy

```
gremlin> g.V().values('age').fold().max(local)
==>35
```

```
g.V().values('age').fold().max(local)
```

When there are `null` values being evaluated the `null` objects are ignored, but if all values are recognized as `null`
the return value is `null`.

console (groovy)

groovy

```
gremlin> g.inject(null,10, 9, null).max()
==>10
gremlin> g.inject([null,null,null]).max(local)
==>null
```

```
g.inject(null,10, 9, null).max()
g.inject([null,null,null]).max(local)
```

**Additional References**

[`max()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#max()),
[`max(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#max(org.apache.tinkerpop.gremlin.process.traversal.Scope)),
[`Scope`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Scope.html)

### Mean Step

The `mean()`-step (**map**) operates on a stream of numbers and determines the average of those numbers.

console (groovy)

groovy

```
gremlin> g.V().values('age').mean()
==>30.75
gremlin> g.V().repeat(both()).times(3).values('age').mean() //// (1)
==>30.645833333333332
gremlin> g.V().repeat(both()).times(3).values('age').dedup().mean()
==>30.75
```

```
g.V().values('age').mean()
g.V().repeat(both()).times(3).values('age').mean() //// (1)
g.V().repeat(both()).times(3).values('age').dedup().mean()
```

1. Realize that traversers are being bulked by `repeat()`. There may be more of a particular number than another,
   thus altering the average.

When called as `mean(local)` it determines the mean of the current, local object (not the objects in the traversal
stream). This works for `Collection` and `Number`-type objects.

console (groovy)

groovy

```
gremlin> g.V().values('age').fold().mean(local)
==>30.75
```

```
g.V().values('age').fold().mean(local)
```

If `mean()` encounters `null` values, they will be ignored (i.e. their traversers not counted toward toward the
divisor). If all traversers are `null` then the stream will return `null`.

console (groovy)

groovy

```
gremlin> g.inject(null,10, 9, null).mean()
==>9.5
gremlin> g.inject([null,null,null]).mean(local)
==>null
```

```
g.inject(null,10, 9, null).mean()
g.inject([null,null,null]).mean(local)
```

**Additional References**

[`mean()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#mean()),
[`mean(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#mean(org.apache.tinkerpop.gremlin.process.traversal.Scope)),
[`Scope`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Scope.html)

### Merge Step

The `merge()`-step (**map**) combines collections like lists and maps. It expects an incoming traverser to contain a
collection objection and will combine that object with its specified argument which must be of a matching type. This is
also known as the union operation. If the incoming traverser or its associated argument do not meet the expected type,
the step will throw an `IllegalArgumentException` if any other type is encountered (including `null`). This step differs
from the `combine()`-step in that it doesn’t allow duplicates.

console (groovy)

groovy

```
gremlin> g.V().values("name").fold().merge(["james","jen","marko","vadas"])
==>[jen,ripple,peter,vadas,james,josh,lop,marko]
gremlin> g.V().values("name").fold().merge(__.constant("james").fold())
==>[ripple,peter,vadas,james,josh,lop,marko]
gremlin> g.V().hasLabel('software').elementMap().merge([year:2009])
==>[id:3,name:lop,lang:java,label:software,year:2009]
==>[id:5,name:ripple,lang:java,label:software,year:2009]
```

```
g.V().values("name").fold().merge(["james","jen","marko","vadas"])
g.V().values("name").fold().merge(__.constant("james").fold())
g.V().hasLabel('software').elementMap().merge([year:2009])
```

**Additional References**

[`merge(Object)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#merge(java.lang.Object))
[`Semantics`](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#merge-step)

### Min Step

The `min()`-step (**map**) operates on a stream of comparable objects and determines which is the first object according
to its natural order in the stream.

console (groovy)

groovy

```
gremlin> g.V().values('age').min()
==>27
gremlin> g.V().repeat(both()).times(3).values('age').min()
==>27
gremlin> g.V().values('name').min()
==>josh
```

```
g.V().values('age').min()
g.V().repeat(both()).times(3).values('age').min()
g.V().values('name').min()
```

When called as `min(local)` it determines the minimum value of the current, local object (not the objects in the
traversal stream). This works for `Collection` and `Comparable`-type objects.

console (groovy)

groovy

```
gremlin> g.V().values('age').fold().min(local)
==>27
```

```
g.V().values('age').fold().min(local)
```

When there are `null` values being evaluated the `null` objects are ignored, but if all values are recognized as `null`
the return value is `null`.

console (groovy)

groovy

```
gremlin> g.inject(null,10, 9, null).min()
==>9
gremlin> g.inject([null,null,null]).min(local)
==>null
```

```
g.inject(null,10, 9, null).min()
g.inject([null,null,null]).min(local)
```

**Additional References**

[`min()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#min()),
[`min(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#min(org.apache.tinkerpop.gremlin.process.traversal.Scope)),
[`Scope`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Scope.html)

### Order Step

When the objects of the traversal stream need to be sorted, `order()`-step (**map**) can be leveraged.

console (groovy)

groovy

```
gremlin> g.V().values('name').order()
==>josh
==>lop
==>marko
==>peter
==>ripple
==>vadas
gremlin> g.V().values('name').order().by(desc)
==>vadas
==>ripple
==>peter
==>marko
==>lop
==>josh
gremlin> g.V().hasLabel('person').order().by('age', asc).values('name')
==>vadas
==>marko
==>josh
==>peter
```

```
g.V().values('name').order()
g.V().values('name').order().by(desc)
g.V().hasLabel('person').order().by('age', asc).values('name')
```

One of the most traversed objects in a traversal is an `Element`. An element can have properties associated with it
(i.e. key/value pairs). In many situations, it is desirable to sort an element traversal stream according to a
comparison of their properties.

console (groovy)

groovy

```
gremlin> g.V().values('name')
==>marko
==>vadas
==>lop
==>josh
==>ripple
==>peter
gremlin> g.V().order().by('name',asc).values('name')
==>josh
==>lop
==>marko
==>peter
==>ripple
==>vadas
gremlin> g.V().order().by('name',desc).values('name')
==>vadas
==>ripple
==>peter
==>marko
==>lop
==>josh
gremlin> g.V().both().order().by('age') //// (1)
==>v[2]
==>v[1]
==>v[1]
==>v[1]
==>v[4]
==>v[4]
==>v[4]
==>v[6]
```

```
g.V().values('name')
g.V().order().by('name',asc).values('name')
g.V().order().by('name',desc).values('name')
g.V().both().order().by('age') //1
```

1. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are filtered.

The `order()`-step allows the user to provide an arbitrary number of comparators for primary, secondary, etc. sorting.
In the example below, the primary ordering is based on the outgoing created-edge count. The secondary ordering is
based on the age of the person.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person').order().by(outE('created').count(), asc).
                                          by('age', asc).values('name')
==>vadas
==>marko
==>peter
==>josh
gremlin> g.V().hasLabel('person').order().by(outE('created').count(), asc).
                                          by('age', desc).values('name')
==>vadas
==>peter
==>marko
==>josh
```

```
g.V().hasLabel('person').order().by(outE('created').count(), asc).
                                 by('age', asc).values('name')
g.V().hasLabel('person').order().by(outE('created').count(), asc).
                                 by('age', desc).values('name')
```

Randomizing the order of the traversers at a particular point in the traversal is possible with `Order.shuffle`.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person').order().by(shuffle)
==>v[2]
==>v[1]
==>v[6]
==>v[4]
gremlin> g.V().hasLabel('person').order().by(shuffle)
==>v[4]
==>v[1]
==>v[2]
==>v[6]
```

```
g.V().hasLabel('person').order().by(shuffle)
g.V().hasLabel('person').order().by(shuffle)
```

It is possible to use `order(local)` to order the current local object and not the entire traversal stream. This works for
`Collection`- and `Map`-type objects. For any other object, the object is returned unchanged.

console (groovy)

groovy

```
gremlin> g.V().values('age').fold().order(local).by(desc) //// (1)
==>[35,32,29,27]
gremlin> g.V().values('age').order(local).by(desc) //// (2)
==>29
==>27
==>32
==>35
gremlin> g.V().groupCount().by(inE().count()).order(local).by(values, desc) //// (3)
==>[1:3,0:2,3:1]
gremlin> g.V().groupCount().by(inE().count()).order(local).by(keys, asc) //// (4)
==>[0:2,1:3,3:1]
```

```
g.V().values('age').fold().order(local).by(desc) //// (1)
g.V().values('age').order(local).by(desc) //// (2)
g.V().groupCount().by(inE().count()).order(local).by(values, desc) //// (3)
g.V().groupCount().by(inE().count()).order(local).by(keys, asc) //4
```

1. The ages are gathered into a list and then that list is sorted in decreasing order.
2. The ages are not gathered and thus `order(local)` is "ordering" single integers and thus, does nothing.
3. The `groupCount()` map is ordered by its values in decreasing order.
4. The `groupCount()` map is ordered by its keys in increasing order.

|  |  |
| --- | --- |
| Note | The `values` and `keys` enums are from `Column` which is used to select "columns" from a `Map`, `Map.Entry`, or `Path`. |

If a property key does not exist, then it will be treated as `null` which will sort it first for `Order.asc` and last
for `Order.desc`.

console (groovy)

groovy

```
gremlin> g.V().order().by("age").elementMap()
==>[id:2,label:person,name:vadas,age:27]
==>[id:1,label:person,name:marko,age:29]
==>[id:4,label:person,name:josh,age:32]
==>[id:6,label:person,name:peter,age:35]
```

```
g.V().order().by("age").elementMap()
```

|  |  |
| --- | --- |
| Note | Prior to version 3.3.4, ordering was defined by `Order.incr` for ascending order and `Order.decr` for descending order. Those tokens were deprecated and eventually removed in 3.5.0. |

**Additional References**

[`order()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#order()),
[`order(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#order(org.apache.tinkerpop.gremlin.process.traversal.Scope)),
[`Scope`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Scope.html),
[`Order`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Order.html)

### PageRank Step

The `pageRank()`-step (**map**/**sideEffect**) calculates [PageRank](http://en.wikipedia.org/wiki/PageRank) using
[`PageRankVertexProgram`](#pagerankvertexprogram).

|  |  |
| --- | --- |
| Important | The `pageRank()`-step is a `VertexComputing`-step and as such, can only be used against a graph that supports `GraphComputer` (OLAP). |

console (groovy)

groovy

```
gremlin> g = traversal().with(graph).withComputer()
==>graphtraversalsource[tinkergraph[vertices:6 edges:6], graphcomputer]
gremlin> g.V().pageRank().with(PageRank.propertyName, 'friendRank').values('pageRank')
gremlin> g.V().hasLabel('person').
           pageRank().
             with(PageRank.edges, __.outE('knows')).
             with(PageRank.propertyName, 'friendRank').
           order().by('friendRank',desc).
           elementMap('name','friendRank')
==>[id:1,label:person,friendRank:0.5839416733381598,name:marko]
==>[id:2,label:person,friendRank:0.8321166533236799,name:vadas]
==>[id:4,label:person,friendRank:0.8321166533236799,name:josh]
==>[id:6,label:person,friendRank:0.5839416733381598,name:peter]
```

```
g = traversal().with(graph).withComputer()
g.V().pageRank().with(PageRank.propertyName, 'friendRank').values('pageRank')
g.V().hasLabel('person').
  pageRank().
    with(PageRank.edges, __.outE('knows')).
    with(PageRank.propertyName, 'friendRank').
  order().by('friendRank',desc).
  elementMap('name','friendRank')
```

Note the use of the `with()` modulating step which provides configuration options to the algorithm. It takes
configuration keys from the `PageRank` and is automatically imported to the Gremlin Console.

The [`explain()`](06-steps/terminal-steps.md#explain-step)-step can be used to understand how the traversal is compiled into multiple
`GraphComputer` jobs.

console (groovy)

groovy

```
gremlin> g = traversal().with(graph).withComputer()
==>graphtraversalsource[tinkergraph[vertices:6 edges:6], graphcomputer]
gremlin> g.V().hasLabel('person').
           pageRank().
             with(PageRank.edges, __.outE('knows')).
             with(PageRank.propertyName, 'friendRank').
           order().by('friendRank',desc).
           elementMap('name','friendRank').explain()
==>Traversal Explanation
=============================================================================================================================================================================================================================================
Original Traversal                    [GraphStep(vertex,[]), HasStep([~label.eq(person)]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), OrderGlobalStep([[value(friendRank), desc]]), ElementMa
                                         pStep([name, friendRank])]

ConnectiveStrategy              [D]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), OrderGlobalStep([[value(friendRank), desc]]), ElementMa
                                         pStep([name, friendRank])]
VertexProgramStrategy           [D]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
IdentityRemovalStrategy         [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
MatchPredicateStrategy          [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
FilterRankingStrategy           [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
PathProcessorStrategy           [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
InlineFilterStrategy            [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
IncidentToAdjacentStrategy      [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
AdjacentToIncidentStrategy      [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
RepeatUnrollStrategy            [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
CountStrategy                   [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
PathRetractionStrategy          [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
EarlyLimitStrategy              [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
LazyBarrierStrategy             [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
ByModulatorOptimizationStrategy [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
OrderLimitStrategy              [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
MessagePassingReductionStrategy [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
GValueReductionStrategy         [O]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
TinkerGraphCountStrategy        [P]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
TinkerGraphStepStrategy         [P]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
ProfileStrategy                 [F]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
ComputerVerificationStrategy    [V]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
ComputerFinalizationStrategy    [T]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
StandardVerificationStrategy    [V]   [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]

Final Traversal                       [TraversalVertexProgramStep([GraphStep(vertex,[]), HasStep([~label.eq(person)])],graphfilter[none]), PageRankVertexProgramStep([VertexStep(OUT,[knows],edge)],friendRank,20,graphfilter[none]), Travers
                                         alVertexProgramStep([OrderGlobalStep([[value(friendRank), desc]]), ElementMapStep([name, friendRank])],graphfilter[none]), ComputerResultStep]
```

```
g = traversal().with(graph).withComputer()
g.V().hasLabel('person').
  pageRank().
    with(PageRank.edges, __.outE('knows')).
    with(PageRank.propertyName, 'friendRank').
  order().by('friendRank',desc).
  elementMap('name','friendRank').explain()
```

**Additional References**

[`pageRank()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#pageRank()),
[`pageRank(double)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#pageRank(double))

### Path Step

A traverser is transformed as it moves through a series of steps within a traversal. The history of the traverser is
realized by examining its path with `path()`-step (**map**).

![path step](../images/path-step.png)

console (groovy)

groovy

```
gremlin> g.V().out().out().values('name')
==>ripple
==>lop
gremlin> g.V().out().out().values('name').path()
==>[v[1],v[4],v[5],ripple]
==>[v[1],v[4],v[3],lop]
gremlin> g.V().both().path().by('age') //// (1)
==>[29,27]
==>[29,32]
==>[27,29]
==>[32,29]
```

```
g.V().out().out().values('name')
g.V().out().out().values('name').path()
g.V().both().path().by('age') //1
```

1. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are filtered.

If edges are required in the path, then be sure to traverse those edges explicitly.

console (groovy)

groovy

```
gremlin> g.V().outE().inV().outE().inV().path()
==>[v[1],e[8][1-knows->4],v[4],e[10][4-created->5],v[5]]
==>[v[1],e[8][1-knows->4],v[4],e[11][4-created->3],v[3]]
```

```
g.V().outE().inV().outE().inV().path()
```

It is possible to post-process the elements of the path in a round-robin fashion via `by()`.

console (groovy)

groovy

```
gremlin> g.V().out().out().path().by('name').by('age')
==>[marko,32,ripple]
==>[marko,32,lop]
```

```
g.V().out().out().path().by('name').by('age')
```

Finally, because `by()`-based post-processing, nothing prevents triggering yet another traversal. In the traversal
below, for each element of the path traversed thus far, if its a person (as determined by having an `age`-property),
then get all of their creations, else if its a creation, get all the people that created it.

console (groovy)

groovy

```
gremlin> g.V().out().out().path().by(
                            choose(hasLabel('person'),
                                          out('created').values('name'),
                                          __.in('created').values('name')).fold())
==>[[lop],[ripple,lop],[josh]]
==>[[lop],[ripple,lop],[marko,josh,peter]]
```

```
g.V().out().out().path().by(
                   choose(hasLabel('person'),
                                 out('created').values('name'),
                                 __.in('created').values('name')).fold())
```

It’s possible to limit the path using the [`to()`](06-steps/modulator-steps.md#to-step) or [`from()`](06-steps/modulator-steps.md#from-step) step modulators.

console (groovy)

groovy

```
gremlin> g.V().has('person','name','vadas').as('e').
               in('knows').
               out('knows').where(neq('e')).
               path().by('name') //// (1)
==>[vadas,marko,josh]
gremlin> g.V().has('person','name','vadas').as('e').
                in('knows').as('m').
                out('knows').where(neq('e')).
                path().to('m').by('name') //// (2)
==>[vadas,marko]
gremlin> g.V().has('person','name','vadas').as('e').
                in('knows').as('m').
                out('knows').where(neq('e')).
                path().from('m').by('name') //// (3)
==>[marko,josh]
```

```
g.V().has('person','name','vadas').as('e').
      in('knows').
      out('knows').where(neq('e')).
      path().by('name') //// (1)
g.V().has('person','name','vadas').as('e').
       in('knows').as('m').
       out('knows').where(neq('e')).
       path().to('m').by('name') //// (2)
g.V().has('person','name','vadas').as('e').
       in('knows').as('m').
       out('knows').where(neq('e')).
       path().from('m').by('name') //3
```

1. Obtain the full path from vadas to josh.
2. Save the middle node, marko, and use the `to()` modulator to show only the path from vadas to marko
3. Use the `from()` mdoulator to show only the path from marko to josh

|  |  |
| --- | --- |
| Warning | Generating path information is expensive as the history of the traverser is stored into a Java list. With numerous traversers, there are numerous lists. Moreover, in an OLAP [`GraphComputer`](09-graphcomputer.md#graphcomputer) environment this becomes exceedingly prohibitive as there are traversers emanating from all vertices in the graph in parallel. In OLAP there are optimizations provided for traverser populations, but when paths are calculated (and each traverser is unique due to its history), then these optimizations are no longer possible. |

#### Path Data Structure

The `Path` data structure is an ordered list of objects, where each object is associated to a `Set<String>` of
labels. An example is presented below to demonstrate both the `Path` API as well as how a traversal yields labeled paths.

![path data structure](../images/path-data-structure.png)

console (groovy)

groovy

```
gremlin> path = g.V(1).as('a').has('name').as('b').
                       out('knows').out('created').as('c').
                       has('name','ripple').values('name').as('d').
                       identity().as('e').path().next()
==>v[1]
==>v[4]
==>v[5]
==>ripple
gremlin> path.size()
==>4
gremlin> path.objects()
==>v[1]
==>v[4]
==>v[5]
==>ripple
gremlin> path.labels()
==>[b,a]
==>[]
==>[c]
==>[d,e]
gremlin> path.a
==>v[1]
gremlin> path.b
==>v[1]
gremlin> path.c
==>v[5]
gremlin> path.d == path.e
==>true
```

```
path = g.V(1).as('a').has('name').as('b').
              out('knows').out('created').as('c').
              has('name','ripple').values('name').as('d').
              identity().as('e').path().next()
path.size()
path.objects()
path.labels()
path.a
path.b
path.c
path.d == path.e
```

**Additional References**

[`path()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#path())

#### Path Data Structure

The `Path` data structure is an ordered list of objects, where each object is associated to a `Set<String>` of
labels. An example is presented below to demonstrate both the `Path` API as well as how a traversal yields labeled paths.

![path data structure](../images/path-data-structure.png)

console (groovy)

groovy

```
gremlin> path = g.V(1).as('a').has('name').as('b').
                       out('knows').out('created').as('c').
                       has('name','ripple').values('name').as('d').
                       identity().as('e').path().next()
==>v[1]
==>v[4]
==>v[5]
==>ripple
gremlin> path.size()
==>4
gremlin> path.objects()
==>v[1]
==>v[4]
==>v[5]
==>ripple
gremlin> path.labels()
==>[b,a]
==>[]
==>[c]
==>[d,e]
gremlin> path.a
==>v[1]
gremlin> path.b
==>v[1]
gremlin> path.c
==>v[5]
gremlin> path.d == path.e
==>true
```

```
path = g.V(1).as('a').has('name').as('b').
              out('knows').out('created').as('c').
              has('name','ripple').values('name').as('d').
              identity().as('e').path().next()
path.size()
path.objects()
path.labels()
path.a
path.b
path.c
path.d == path.e
```

**Additional References**

[`path()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#path())

### PeerPressure Step

The `peerPressure()`-step (**map**/**sideEffect**) clusters vertices using [`PeerPressureVertexProgram`](#peerpressurevertexprogram).

|  |  |
| --- | --- |
| Important | The `peerPressure()`-step is a `VertexComputing`-step and as such, can only be used against a graph that supports `GraphComputer` (OLAP). |

console (groovy)

groovy

```
gremlin> g = traversal().with(graph).withComputer()
==>graphtraversalsource[tinkergraph[vertices:6 edges:6], graphcomputer]
gremlin> g.V().peerPressure().with(PeerPressure.propertyName, 'cluster').values('cluster')
==>1
==>1
==>1
==>1
==>1
==>6
gremlin> g.V().hasLabel('person').
           peerPressure().
             with(PeerPressure.propertyName, 'cluster').
           group().
             by('cluster').
             by('name')
==>[1:[marko,vadas,josh],6:[peter]]
```

```
g = traversal().with(graph).withComputer()
g.V().peerPressure().with(PeerPressure.propertyName, 'cluster').values('cluster')
g.V().hasLabel('person').
  peerPressure().
    with(PeerPressure.propertyName, 'cluster').
  group().
    by('cluster').
    by('name')
```

Note the use of the `with()` modulating step which provides configuration options to the algorithm. It takes
configuration keys from the `PeerPressure` class and is automatically imported to the Gremlin Console.

**Additional References**

[`peerPressure()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#peerPressure())

### Product Step

The `product()`-step (**map**) calculates the cartesian product between the incoming list traverser and the provided list
argument. This step only expects list data (array or Iterable) and will throw an `IllegalArgumentException` if any
other type is encountered (including `null`).

console (groovy)

groovy

```
gremlin> g.V().values("name").fold().product(["james","jen"])
==>[[marko,james],[marko,jen],[vadas,james],[vadas,jen],[lop,james],[lop,jen],[josh,james],[josh,jen],[ripple,james],[ripple,jen],[peter,james],[peter,jen]]
gremlin> g.V().values("name").fold().product(__.V().has("age").limit(1).values("age").fold())
==>[[marko,29],[vadas,29],[lop,29],[josh,29],[ripple,29],[peter,29]]
```

```
g.V().values("name").fold().product(["james","jen"])
g.V().values("name").fold().product(__.V().has("age").limit(1).values("age").fold())
```

**Additional References**

[`product(Object)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#product(java.lang.Object))
[`Semantics`](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#product-step)

### Project Step

The `project()`-step (**map**) projects the current object into a `Map<String,Object>` keyed by provided labels. It is similar
to [`select()`](06-steps/map-steps.md#select-step)-step, save that instead of retrieving and modulating historic traverser state, it modulates
the current state of the traverser.

console (groovy)

groovy

```
gremlin> g.V().has('name','marko').
           project('id', 'name', 'out', 'in').
             by(id).
             by('name').
             by(outE().count()).
             by(inE().count())
==>[id:1,name:marko,out:3,in:0]
gremlin> g.V().has('name','marko').
           project('name', 'friendsNames').
             by('name').
             by(out('knows').values('name').fold())
==>[name:marko,friendsNames:[vadas,josh]]
gremlin> g.V().out('created').
           project('a','b').
             by('name').
             by(__.in('created').count()).
           order().by(select('b'),desc).
           select('a')
==>lop
==>lop
==>lop
==>ripple
gremlin> g.V().project('n','a').by('name').by('age') //// (1)
==>[n:marko,a:29]
==>[n:vadas,a:27]
==>[n:lop]
==>[n:josh,a:32]
==>[n:ripple]
==>[n:peter,a:35]
```

```
g.V().has('name','marko').
  project('id', 'name', 'out', 'in').
    by(id).
    by('name').
    by(outE().count()).
    by(inE().count())
g.V().has('name','marko').
  project('name', 'friendsNames').
    by('name').
    by(out('knows').values('name').fold())
g.V().out('created').
  project('a','b').
    by('name').
    by(__.in('created').count()).
  order().by(select('b'),desc).
  select('a')
g.V().project('n','a').by('name').by('age') //1
```

1. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are filtered and the key not present in the `Map`.

**Additional References**

[`project(String,String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#project(java.lang.String,java.lang.String...))

### Program Step

The `program()`-step (**map**/**sideEffect**) is the "lambda" step for `GraphComputer` jobs. The step takes a
[`VertexProgram`](#vertexprogram) as an argument and will process the incoming graph accordingly. Thus, the user
can create their own `VertexProgram` and have it execute within a traversal. The configuration provided to the
vertex program includes:

* `gremlin.vertexProgramStep.rootTraversal` is a serialization of a `PureTraversal` form of the root traversal.
* `gremlin.vertexProgramStep.stepId` is the step string id of the `program()`-step being executed.

The user supplied `VertexProgram` can leverage that information accordingly within their vertex program. Example uses
are provided below.

|  |  |
| --- | --- |
| Warning | Developing a `VertexProgram` is for expert users. Moreover, developing one that can be used effectively within a traversal requires yet more expertise. This information is recommended to advanced users with a deep understanding of the mechanics of Gremlin OLAP ([`GraphComputer`](09-graphcomputer.md#graphcomputer)). |

```
private TraverserSet<Object> haltedTraversers;

public void loadState(Graph graph, Configuration configuration) {
  VertexProgram.super.loadState(graph, configuration);
  this.traversal = PureTraversal.loadState(configuration, VertexProgramStep.ROOT_TRAVERSAL, graph);
  this.programStep = new TraversalMatrix<>(this.traversal.get()).getStepById(configuration.getString(ProgramVertexProgramStep.STEP_ID));
  // if the traversal sideEffects will be used in the computation, add them as memory compute keys
  this.memoryComputeKeys.addAll(MemoryTraversalSideEffects.getMemoryComputeKeys(this.traversal.get()));
  // if master-traversal traversers may be propagated, create a memory compute key
  this.memoryComputeKeys.add(MemoryComputeKey.of(TraversalVertexProgram.HALTED_TRAVERSERS, Operator.addAll, false, false));
  // returns an empty traverser set if there are no halted traversers
  this.haltedTraversers = TraversalVertexProgram.loadHaltedTraversers(configuration);
}

public void storeState(Configuration configuration) {
  VertexProgram.super.storeState(configuration);
  // if halted traversers is null or empty, it does nothing
  TraversalVertexProgram.storeHaltedTraversers(configuration, this.haltedTraversers);
}

public void setup(Memory memory) {
  if(!this.haltedTraversers.isEmpty()) {
    // do what you like with the halted master traversal traversers
  }
  // once used, no need to keep that information around (master)
  this.haltedTraversers = null;
}

public void execute(Vertex vertex, Messenger messenger, Memory memory) {
  // once used, no need to keep that information around (workers)
  if(null != this.haltedTraversers)
    this.haltedTraversers = null;
  if(vertex.property(TraversalVertexProgram.HALTED_TRAVERSERS).isPresent()) {
    // haltedTraversers in execute() represent worker-traversal traversers
    // for example, from a traversal of the form g.V().out().program(...)
    TraverserSet<Object> haltedTraversers = vertex.value(TraversalVertexProgram.HALTED_TRAVERSERS);
    // create a new halted traverser set that can be used by the next OLAP job in the chain
    // these are worker-traversers that are distributed throughout the graph
    TraverserSet<Object> newHaltedTraversers = new TraverserSet<>();
    haltedTraversers.forEach(traverser -> {
       newHaltedTraversers.add(traverser.split(traverser.get().toString(), this.programStep));
    });
    vertex.property(VertexProperty.Cardinality.single, TraversalVertexProgram.HALTED_TRAVERSERS, newHaltedTraversers);
    // it is possible to create master-traversers that are localized to the master traversal (this is how results are ultimately delivered back to the user)
    memory.add(TraversalVertexProgram.HALTED_TRAVERSERS,
               new TraverserSet<>(this.traversal().get().getTraverserGenerator().generate("an example", this.programStep, 1l)));
  }

public boolean terminate(Memory memory) {
  // the master-traversal will have halted traversers
  assert memory.exists(TraversalVertexProgram.HALTED_TRAVERSERS);
  TraverserSet<String> haltedTraversers = memory.get(TraversalVertexProgram.HALTED_TRAVERSERS);
  // it will only have the traversers sent to the master traversal via memory
  assert haltedTraversers.stream().map(Traverser::get).filter(s -> s.equals("an example")).findAny().isPresent();
  // it will not contain the worker traversers distributed throughout the vertices
  assert !haltedTraversers.stream().map(Traverser::get).filter(s -> !s.equals("an example")).findAny().isPresent();
  return true;
}
```

|  |  |
| --- | --- |
| Note | The test case `ProgramTest` in `gremlin-test` has an example vertex program called `TestProgram` that demonstrates all the various ways in which traversal and traverser information is propagated within a vertex program and ultimately usable by other vertex programs (including `TraversalVertexProgram`) down the line in an OLAP compute chain. |

Finally, an example is provided using `PageRankVertexProgram` which doesn’t use [`pageRank()`](#pagerank-step)-step.

console (groovy)

groovy

```
gremlin> g = traversal().with(graph).withComputer()
==>graphtraversalsource[tinkergraph[vertices:6 edges:6], graphcomputer]
gremlin> g.V().hasLabel('person').
           program(PageRankVertexProgram.build().property('rank').create(graph)).
             order().by('rank', asc).
           elementMap('name', 'rank')
==>[id:1,label:person,name:marko,rank:0.11375510357865537]
==>[id:2,label:person,name:vadas,rank:0.14598540152719103]
==>[id:4,label:person,name:josh,rank:0.14598540152719103]
==>[id:6,label:person,name:peter,rank:0.11375510357865537]
```

```
g = traversal().with(graph).withComputer()
g.V().hasLabel('person').
  program(PageRankVertexProgram.build().property('rank').create(graph)).
    order().by('rank', asc).
  elementMap('name', 'rank')
```

### Properties Step

The `properties()`-step (**map**) extracts properties from an `Element` in the traversal stream.

console (groovy)

groovy

```
gremlin> g.V(1).properties()
==>vp[name->marko]
==>vp[location->san diego]
==>vp[location->santa cruz]
==>vp[location->brussels]
==>vp[location->santa fe]
gremlin> g.V(1).properties('location').valueMap()
==>[startTime:1997,endTime:2001]
==>[startTime:2001,endTime:2004]
==>[startTime:2004,endTime:2005]
==>[startTime:2005]
gremlin> g.V(1).properties('location').has('endTime').valueMap()
==>[startTime:1997,endTime:2001]
==>[startTime:2001,endTime:2004]
==>[startTime:2004,endTime:2005]
```

```
g.V(1).properties()
g.V(1).properties('location').valueMap()
g.V(1).properties('location').has('endTime').valueMap()
```

**Additional References**

[`properties(String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#properties(java.lang.String...))

### PropertyMap Step

The `propertiesMap()`-step yields a Map representation of the properties of an element.

console (groovy)

groovy

```
gremlin> g.V().propertyMap()
==>[name:[vp[name->marko]],age:[vp[age->29]]]
==>[name:[vp[name->vadas]],age:[vp[age->27]]]
==>[name:[vp[name->lop]],lang:[vp[lang->java]]]
==>[name:[vp[name->josh]],age:[vp[age->32]]]
==>[name:[vp[name->ripple]],lang:[vp[lang->java]]]
==>[name:[vp[name->peter]],age:[vp[age->35]]]
gremlin> g.V().propertyMap('age')
==>[age:[vp[age->29]]]
==>[age:[vp[age->27]]]
==>[]
==>[age:[vp[age->32]]]
==>[]
==>[age:[vp[age->35]]]
gremlin> g.V().propertyMap('age','blah')
==>[age:[vp[age->29]]]
==>[age:[vp[age->27]]]
==>[]
==>[age:[vp[age->32]]]
==>[]
==>[age:[vp[age->35]]]
gremlin> g.E().propertyMap()
==>[weight:p[weight->0.5]]
==>[weight:p[weight->1.0]]
==>[weight:p[weight->0.4]]
==>[weight:p[weight->1.0]]
==>[weight:p[weight->0.4]]
==>[weight:p[weight->0.2]]
```

```
g.V().propertyMap()
g.V().propertyMap('age')
g.V().propertyMap('age','blah')
g.E().propertyMap()
```

**Additional References**

[`propertyMap(String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#propertyMap(java.lang.String...))

### Replace Step

The `replace()`-step (**map**) returns a string with the specified characters in the original string replaced with the new
characters. Any null arguments will be a no-op and the original string is returned. Null values from the incoming
traversers are not processed and remain as null when returned. If the incoming traverser is a non-String value then
an `IllegalArgumentException` will be thrown.

console (groovy)

groovy

```
gremlin> g.inject('that', 'this', 'test', null).replace('h', 'j') //// (1)
==>tjat
==>tjis
==>test
==>null
gremlin> g.inject('hello world').replace(null, 'j') //// (2)
==>hello world
gremlin> g.V().hasLabel("software").values("name").replace("p", "g") //// (3)
==>log
==>riggle
gremlin> g.V().hasLabel("software").values("name").fold().replace(local, "p", "g") //// (4)
==>[log,riggle]
```

```
g.inject('that', 'this', 'test', null).replace('h', 'j') //// (1)
g.inject('hello world').replace(null, 'j') //// (2)
g.V().hasLabel("software").values("name").replace("p", "g") //// (3)
g.V().hasLabel("software").values("name").fold().replace(local, "p", "g") //4
```

1. Replace "h" in the strings with "j".
2. Null inputs are ignored and the original string is returned.
3. Return software names with "p" replaced by "g".
4. Use `Scope.local` to operate on individual string elements inside incoming list, which will return a list.

**Additional References**
[`replace(String,String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#replace(java.lang.String,java.lang.String))
[`replace(Scope,String,String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#replace(org.apache.tinkerpop.gremlin.process.traversal.Scope,java.lang.String,java.lang.String))

### Reverse Step

The `reverse()`-step (**map**) returns the reverse of the incoming list traverser. Single values (including `null`) are not
processed and are added back to the Traversal Stream unchanged. If the incoming traverser is a String value then the
reversed String will be returned.

console (groovy)

groovy

```
gremlin> g.V().values("name").reverse() //// (1)
==>okram
==>sadav
==>pol
==>hsoj
==>elppir
==>retep
gremlin> g.V().values("name").order().fold().reverse() //// (2)
==>[vadas,ripple,peter,marko,lop,josh]
```

```
g.V().values("name").reverse() //// (1)
g.V().values("name").order().fold().reverse() //2
```

1. Reverse the order of the characters in each name.
2. Fold all the names into a list in ascending order and then reverse the list’s ordering (into descending).

[`reverse()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#reverse())

### RTrim Step

The `rTrim()`-step (**map**) returns a string with trailing whitespace removed. Null values are not processed and remain
as null when returned. If the incoming traverser is a non-String value then an `IllegalArgumentException` will be thrown.

console (groovy)

groovy

```
gremlin> g.inject("   hello   ", " world ", null).rTrim()
==>   hello
==> world
==>null
gremlin> g.inject(["   hello   ", " world ", null]).rTrim(local) //// (1)
==>[   hello, world,null]
```

```
g.inject("   hello   ", " world ", null).rTrim()
g.inject(["   hello   ", " world ", null]).rTrim(local) //1
```

1. Use `Scope.local` to operate on individual string elements inside incoming list, which will return a list.

[`rTrim()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#rTrim())
[`rTrim(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#rTrim(org.apache.tinkerpop.gremlin.process.traversal.Scope))

### Select Step

[Functional languages](http://en.wikipedia.org/wiki/Functional_programming) make use of function composition and
lazy evaluation to create complex computations from primitive operations. This is exactly what `Traversal` does. One
of the differentiating aspects of Gremlin’s data flow approach to graph processing is that the flow need not always go
"forward," but in fact, can go back to a previously seen area of computation. Examples include [`path()`](06-steps/map-steps.md#path-step)
as well as the `select()`-step (**map**). There are two general ways to use `select()`-step.

1. Select labeled steps within a path (as defined by `as()` in a traversal).
2. Select objects out of a `Map<String,Object>` flow (i.e. a sub-map).

The first use case is demonstrated via example below.

console (groovy)

groovy

```
gremlin> g.V().as('a').out().as('b').out().as('c') // no select
==>v[5]
==>v[3]
gremlin> g.V().as('a').out().as('b').out().as('c').select('a','b','c')
==>[a:v[1],b:v[4],c:v[5]]
==>[a:v[1],b:v[4],c:v[3]]
gremlin> g.V().as('a').out().as('b').out().as('c').select('a','b')
==>[a:v[1],b:v[4]]
==>[a:v[1],b:v[4]]
gremlin> g.V().as('a').out().as('b').out().as('c').select('a','b').by('name')
==>[a:marko,b:josh]
==>[a:marko,b:josh]
gremlin> g.V().as('a').out().as('b').out().as('c').select('a') //// (1)
==>v[1]
==>v[1]
gremlin> g.V(1).as('a').both().as('b').select('a','b').by('age')
==>[a:29,b:27]
==>[a:29,b:32]
```

```
g.V().as('a').out().as('b').out().as('c') // no select
g.V().as('a').out().as('b').out().as('c').select('a','b','c')
g.V().as('a').out().as('b').out().as('c').select('a','b')
g.V().as('a').out().as('b').out().as('c').select('a','b').by('name')
g.V().as('a').out().as('b').out().as('c').select('a') //// (1)
g.V(1).as('a').both().as('b').select('a','b').by('age')
```

1. If the selection is one step, no map is returned.
2. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are filtered.

When there is only one label selected, then a single object is returned. This is useful for stepping back in a
computation and easily moving forward again on the object reverted to.

console (groovy)

groovy

```
gremlin> g.V().out().out()
==>v[5]
==>v[3]
gremlin> g.V().out().out().path()
==>[v[1],v[4],v[5]]
==>[v[1],v[4],v[3]]
gremlin> g.V().as('x').out().out().select('x')
==>v[1]
==>v[1]
gremlin> g.V().out().as('x').out().select('x')
==>v[4]
==>v[4]
gremlin> g.V().out().out().as('x').select('x') // pointless
==>v[5]
==>v[3]
```

```
g.V().out().out()
g.V().out().out().path()
g.V().as('x').out().out().select('x')
g.V().out().as('x').out().select('x')
g.V().out().out().as('x').select('x') // pointless
```

|  |  |
| --- | --- |
| Note | When executing a traversal with `select()` on a standard traversal engine (i.e. OLTP), `select()` will do its best to avoid calculating the path history and instead, will rely on a global data structure for storing the currently selected object. As such, if only a subset of the path walked is required, `select()` should be used over the more resource intensive [`path()`](06-steps/map-steps.md#path-step)-step. |

When the set of keys or values (i.e. columns) of a path or map are needed, use `select(keys)` and `select(values)`,
respectively. This is especially useful when one is only interested in the top N elements in a `groupCount()`
ranking.

console (groovy)

groovy

```
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.io('data/grateful-dead.xml').read().iterate()
gremlin> g.V().hasLabel('song').out('followedBy').groupCount().by('name').
               order(local).by(values,desc).limit(local, 5)
==>[PLAYING IN THE BAND:107,JACK STRAW:99,TRUCKING:94,DRUMS:92,ME AND MY UNCLE:86]
gremlin> g.V().hasLabel('song').out('followedBy').groupCount().by('name').
               order(local).by(values,desc).limit(local, 5).select(keys)
==>[PLAYING IN THE BAND,JACK STRAW,TRUCKING,DRUMS,ME AND MY UNCLE]
gremlin> g.V().hasLabel('song').out('followedBy').groupCount().by('name').
               order(local).by(values,desc).limit(local, 5).select(keys).unfold()
==>PLAYING IN THE BAND
==>JACK STRAW
==>TRUCKING
==>DRUMS
==>ME AND MY UNCLE
```

```
g = traversal().with(graph)
g.io('data/grateful-dead.xml').read().iterate()
g.V().hasLabel('song').out('followedBy').groupCount().by('name').
      order(local).by(values,desc).limit(local, 5)
g.V().hasLabel('song').out('followedBy').groupCount().by('name').
      order(local).by(values,desc).limit(local, 5).select(keys)
g.V().hasLabel('song').out('followedBy').groupCount().by('name').
      order(local).by(values,desc).limit(local, 5).select(keys).unfold()
```

Similarly, for extracting the values from a path or map.

console (groovy)

groovy

```
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.io('data/grateful-dead.xml').read().iterate()
gremlin> g.V().hasLabel('song').out('sungBy').groupCount().by('name') //// (1)
==>[All:9,Weir_Garcia:1,Lesh:19,Weir_Kreutzmann:1,Pigpen_Garcia:1,Pigpen:36,Unknown:6,Weir_Bralove:1,Joan_Baez:10,Suzanne_Vega:2,Welnick:10,Lesh_Pigpen:1,Elvin_Bishop:4,Neil_Young:1,Garcia_Weir_Lesh:1,Hunter:3,Hornsby:4,Jon_Hendricks:2,Weir_Hart:3,Lesh_Mydland:1,Mydland_Lesh:1,instrumental:1,Garcia:146,Hart:2,Welnick_Bralove:1,Weir:99,Garcia_Dawson:1,Pigpen_Weir_Mydland:2,Jorma_Kaukonen:4,Joey_Covington:2,Allman_Brothers:1,Garcia_Lesh:3,Boz_Scaggs:1,Pigpen?:1,Keith_Godchaux:1,Etta_James:1,Weir_Wasserman:1,Hall_and_Oates:2,Grateful_Dead:17,Spencer_Davis:2,Pigpen_Mydland:3,Beach_Boys:3,Donna:4,Bo_Diddley:7,Bob_Dylan:22,Hart_Kreutzmann:2,Weir_Mydland:3,Lesh_Hart_Kreutzmann:1,Stephen_Stills:2,Mydland:18,Neville_Brothers:2,Weir_Hart_Welnick:1,Garcia_Lesh_Weir:1,Garcia_Weir:3,Neal_Cassady:1,John_Fogerty:5,Donna_Godchaux:2,Pigpen_Weir:8,Garcia_Kreutzmann:2,None:6]
gremlin> g.V().hasLabel('song').out('sungBy').groupCount().by('name').select(values) //// (2)
==>[9,1,19,1,1,36,6,1,10,2,10,1,4,1,1,3,4,2,3,1,1,1,146,2,1,99,1,2,4,2,1,3,1,1,1,1,1,2,17,2,3,3,4,7,22,2,3,1,2,18,2,1,1,3,1,5,2,8,2,6]
gremlin> g.V().hasLabel('song').out('sungBy').groupCount().by('name').select(values).unfold().
               groupCount().order(local).by(values,desc).limit(local, 5) //// (3)
==>[1:22,2:12,3:7,4:4,6:2]
```

```
g = traversal().with(graph)
g.io('data/grateful-dead.xml').read().iterate()
g.V().hasLabel('song').out('sungBy').groupCount().by('name') //// (1)
g.V().hasLabel('song').out('sungBy').groupCount().by('name').select(values) //// (2)
g.V().hasLabel('song').out('sungBy').groupCount().by('name').select(values).unfold().
      groupCount().order(local).by(values,desc).limit(local, 5) //3
```

1. Which artist sung how many songs?
2. Get an anonymized set of song repertoire sizes.
3. What are the 5 most common song repertoire sizes?

|  |  |
| --- | --- |
| Warning | Note that `by()`-modulation is not supported with `select(keys)` and `select(values)`. |

There is also an option to supply a `Pop` operation to `select()` to manipulate `List` objects in the `Traverser`:

console (groovy)

groovy

```
gremlin> g.V(1).as("a").repeat(out().as("a")).times(2).select(first, "a")
==>v[1]
==>v[1]
gremlin> g.V(1).as("a").repeat(out().as("a")).times(2).select(last, "a")
==>v[5]
==>v[3]
gremlin> g.V(1).as("a").repeat(out().as("a")).times(2).select(all, "a")
==>[v[1],v[4],v[5]]
==>[v[1],v[4],v[3]]
```

```
g.V(1).as("a").repeat(out().as("a")).times(2).select(first, "a")
g.V(1).as("a").repeat(out().as("a")).times(2).select(last, "a")
g.V(1).as("a").repeat(out().as("a")).times(2).select(all, "a")
```

In addition to the previously shown examples, where `select()` was used to select an element based on a static key, `select()` can also accept a traversal
that emits a key.

|  |  |
| --- | --- |
| Warning | Since the key used by `select(<traversal>)` cannot be determined at compile time, the `TraversalSelectStep` enables full path tracking. |

console (groovy)

groovy

```
gremlin> g.withSideEffect("alias", ["marko":"okram"]).V(). //// (1)
           values("name").sack(assign). //// (2)
           optional(select("alias").select(sack())) //// (3)
==>okram
==>vadas
==>lop
==>josh
==>ripple
==>peter
```

```
g.withSideEffect("alias", ["marko":"okram"]).V(). //// (1)
  values("name").sack(assign). //// (2)
  optional(select("alias").select(sack()))         //3
```

1. Inject a name alias map and start the traversal from all vertices.
2. Select all `name` values and store them as the current traverser’s sack value.
3. Optionally select the alias for the current name from the injected map.

#### Using Where with Select

Like [`match()`](06-steps/branch-steps.md#match-step)-step, it is possible to use `where()`, as where is a filter that processes
`Map<String,Object>` streams.

console (groovy)

groovy

```
gremlin> g.V().as('a').out('created').in('created').as('b').select('a','b').by('name') //// (1)
==>[a:marko,b:marko]
==>[a:marko,b:josh]
==>[a:marko,b:peter]
==>[a:josh,b:josh]
==>[a:josh,b:marko]
==>[a:josh,b:josh]
==>[a:josh,b:peter]
==>[a:peter,b:marko]
==>[a:peter,b:josh]
==>[a:peter,b:peter]
gremlin> g.V().as('a').out('created').in('created').as('b').
               select('a','b').by('name').where('a',neq('b')) //// (2)
==>[a:marko,b:josh]
==>[a:marko,b:peter]
==>[a:josh,b:marko]
==>[a:josh,b:peter]
==>[a:peter,b:marko]
==>[a:peter,b:josh]
gremlin> g.V().as('a').out('created').in('created').as('b').
               select('a','b'). //// (3)
               where('a',neq('b')).
               where(__.as('a').out('knows').as('b')).
               select('a','b').by('name')
==>[a:marko,b:josh]
```

```
g.V().as('a').out('created').in('created').as('b').select('a','b').by('name') //// (1)
g.V().as('a').out('created').in('created').as('b').
      select('a','b').by('name').where('a',neq('b')) //// (2)
g.V().as('a').out('created').in('created').as('b').
      select('a','b'). //// (3)
      where('a',neq('b')).
      where(__.as('a').out('knows').as('b')).
      select('a','b').by('name')
```

1. A standard `select()` that generates a `Map<String,Object>` of variables bindings in the path (i.e. `a` and `b`)
   for the sake of a running example.
2. The `select().by('name')` projects each binding vertex to their name property value and `where()` operates to
   ensure respective `a` and `b` strings are not the same.
3. The first `select()` projects a vertex binding set. A binding is filtered if `a` vertex equals `b` vertex. A
   binding is filtered if `a` doesn’t know `b`. The second and final `select()` projects the name of the vertices.

**Additional References**

[`select(Column)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#select(org.apache.tinkerpop.gremlin.structure.Column)),
[`select(Pop,String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#select(org.apache.tinkerpop.gremlin.process.traversal.Pop,java.lang.String)),
[`select(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#select(java.lang.String)),
[`select(String,String,String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#select(java.lang.String,java.lang.String,java.lang.String...)),
[`select(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#select(org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`select(Pop,Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#select(org.apache.tinkerpop.gremlin.process.traversal.Pop,org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`Column`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/structure/Column.html),
[`Pop`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Pop.html),
[A Note on Maps](../05a-traversal-concepts.md#a-note-on-maps)

#### Using Where with Select

Like [`match()`](06-steps/branch-steps.md#match-step)-step, it is possible to use `where()`, as where is a filter that processes
`Map<String,Object>` streams.

console (groovy)

groovy

```
gremlin> g.V().as('a').out('created').in('created').as('b').select('a','b').by('name') //// (1)
==>[a:marko,b:marko]
==>[a:marko,b:josh]
==>[a:marko,b:peter]
==>[a:josh,b:josh]
==>[a:josh,b:marko]
==>[a:josh,b:josh]
==>[a:josh,b:peter]
==>[a:peter,b:marko]
==>[a:peter,b:josh]
==>[a:peter,b:peter]
gremlin> g.V().as('a').out('created').in('created').as('b').
               select('a','b').by('name').where('a',neq('b')) //// (2)
==>[a:marko,b:josh]
==>[a:marko,b:peter]
==>[a:josh,b:marko]
==>[a:josh,b:peter]
==>[a:peter,b:marko]
==>[a:peter,b:josh]
gremlin> g.V().as('a').out('created').in('created').as('b').
               select('a','b'). //// (3)
               where('a',neq('b')).
               where(__.as('a').out('knows').as('b')).
               select('a','b').by('name')
==>[a:marko,b:josh]
```

```
g.V().as('a').out('created').in('created').as('b').select('a','b').by('name') //// (1)
g.V().as('a').out('created').in('created').as('b').
      select('a','b').by('name').where('a',neq('b')) //// (2)
g.V().as('a').out('created').in('created').as('b').
      select('a','b'). //// (3)
      where('a',neq('b')).
      where(__.as('a').out('knows').as('b')).
      select('a','b').by('name')
```

1. A standard `select()` that generates a `Map<String,Object>` of variables bindings in the path (i.e. `a` and `b`)
   for the sake of a running example.
2. The `select().by('name')` projects each binding vertex to their name property value and `where()` operates to
   ensure respective `a` and `b` strings are not the same.
3. The first `select()` projects a vertex binding set. A binding is filtered if `a` vertex equals `b` vertex. A
   binding is filtered if `a` doesn’t know `b`. The second and final `select()` projects the name of the vertices.

**Additional References**

[`select(Column)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#select(org.apache.tinkerpop.gremlin.structure.Column)),
[`select(Pop,String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#select(org.apache.tinkerpop.gremlin.process.traversal.Pop,java.lang.String)),
[`select(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#select(java.lang.String)),
[`select(String,String,String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#select(java.lang.String,java.lang.String,java.lang.String...)),
[`select(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#select(org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`select(Pop,Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#select(org.apache.tinkerpop.gremlin.process.traversal.Pop,org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`Column`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/structure/Column.html),
[`Pop`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Pop.html),
[A Note on Maps](../05a-traversal-concepts.md#a-note-on-maps)

### ShortestPath step

The `shortestPath()`-step provides an easy way to find shortest non-cyclic paths in a graph. It is configurable
using the `with()`-modulator with the options given below.

|  |  |
| --- | --- |
| Important | The `shortestPath()`-step is a `VertexComputing`-step and as such, can only be used against a graph that supports `GraphComputer` (OLAP). |

| Key | Type | Description | Default |
| --- | --- | --- | --- |
| `target` | `Traversal` | Sets a filter traversal for the end vertices (e.g. `__.has('name','marko')`). | all vertices (`__.identity()`) |
| `edges` | `Traversal` or `Direction` | Sets a `Traversal` that emits the edges to traverse from the current vertex or the `Direction` to traverse during the shortest path discovery. | `Direction.BOTH` |
| `distance` | `Traversal` or `String` | Sets the `Traversal` that calculates the distance for the current edge or the name of an edge property to use for the distance calculations. | `__.constant(1)` |
| `maxDistance` | `Number` | Sets the distance limit for all shortest paths. | none |
| `includeEdges` | `Boolean` | Whether to include edges in the result or not. | `false` |

console (groovy)

groovy

```
gremlin> g = g.withComputer()
==>graphtraversalsource[tinkergraph[vertices:6 edges:6], graphcomputer]
gremlin> g.V().shortestPath() //// (1)
==>[v[6],v[3],v[1],v[2]]
==>[v[6],v[3],v[1]]
==>[v[6],v[3]]
==>[v[6],v[3],v[4]]
==>[v[6]]
==>[v[6],v[3],v[4],v[5]]
==>[v[1],v[2]]
==>[v[1]]
==>[v[1],v[3]]
==>[v[1],v[4]]
==>[v[1],v[3],v[6]]
==>[v[1],v[4],v[5]]
==>[v[3],v[1],v[2]]
==>[v[3],v[1]]
==>[v[3]]
==>[v[3],v[4]]
==>[v[3],v[6]]
==>[v[3],v[4],v[5]]
==>[v[4],v[1],v[2]]
==>[v[4],v[1]]
==>[v[4],v[3]]
==>[v[4]]
==>[v[4],v[3],v[6]]
==>[v[4],v[5]]
==>[v[2]]
==>[v[2],v[1]]
==>[v[2],v[1],v[3]]
==>[v[2],v[1],v[4]]
==>[v[2],v[1],v[3],v[6]]
==>[v[2],v[1],v[4],v[5]]
==>[v[5],v[4],v[1],v[2]]
==>[v[5],v[4],v[1]]
==>[v[5],v[4],v[3]]
==>[v[5],v[4]]
==>[v[5],v[4],v[3],v[6]]
==>[v[5]]
gremlin> g.V().has('person','name','marko').shortestPath() //// (2)
==>[v[1]]
==>[v[1],v[2]]
==>[v[1],v[3]]
==>[v[1],v[4]]
==>[v[1],v[4],v[5]]
==>[v[1],v[3],v[6]]
gremlin> g.V().shortestPath().with(ShortestPath.target, __.has('name','peter')) //// (3)
==>[v[1],v[3],v[6]]
==>[v[2],v[1],v[3],v[6]]
==>[v[3],v[6]]
==>[v[4],v[3],v[6]]
==>[v[5],v[4],v[3],v[6]]
==>[v[6]]
gremlin> g.V().shortestPath().
                 with(ShortestPath.edges, Direction.IN).
                 with(ShortestPath.target, __.has('name','josh')) //// (4)
==>[v[3],v[4]]
==>[v[4]]
==>[v[5],v[4]]
gremlin> g.V().has('person','name','marko').
               shortestPath().
                 with(ShortestPath.target, __.has('name','josh')) //// (5)
==>[v[1],v[4]]
gremlin> g.V().has('person','name','marko').
               shortestPath().
                 with(ShortestPath.target, __.has('name','josh')).
                 with(ShortestPath.distance, 'weight') //// (6)
==>[v[1],v[3],v[4]]
gremlin> g.V().has('person','name','marko').
               shortestPath().
                 with(ShortestPath.target, __.has('name','josh')).
                 with(ShortestPath.includeEdges, true) //// (7)
==>[v[1],e[8][1-knows->4],v[4]]
```

```
g = g.withComputer()
g.V().shortestPath() //// (1)
g.V().has('person','name','marko').shortestPath() //// (2)
g.V().shortestPath().with(ShortestPath.target, __.has('name','peter')) //// (3)
g.V().shortestPath().
        with(ShortestPath.edges, Direction.IN).
        with(ShortestPath.target, __.has('name','josh')) //// (4)
g.V().has('person','name','marko').
      shortestPath().
        with(ShortestPath.target, __.has('name','josh')) //// (5)
g.V().has('person','name','marko').
      shortestPath().
        with(ShortestPath.target, __.has('name','josh')).
        with(ShortestPath.distance, 'weight') //// (6)
g.V().has('person','name','marko').
      shortestPath().
        with(ShortestPath.target, __.has('name','josh')).
        with(ShortestPath.includeEdges, true) //7
```

1. Find all shortest paths.
2. Find all shortest paths from `marko`.
3. Find all shortest paths to `peter`.
4. Find all in-directed paths to `josh`.
5. Find all shortest paths from `marko` to `josh`.
6. Find all shortest paths from `marko` to `josh` using a custom distance property.
7. Find all shortest paths from `marko` to `josh` and include edges in the result.

console (groovy)

groovy

```
gremlin> g.inject(g.withComputer().V().shortestPath().
                    with(ShortestPath.distance, 'weight').
                    with(ShortestPath.includeEdges, true).
                    with(ShortestPath.maxDistance, 1).toList().toArray()).
           map(unfold().values('name','weight').fold()) //// (1)
==>[marko]
==>[marko,0.5,vadas]
==>[marko,0.4,lop]
==>[marko,0.4,lop,0.4,josh]
==>[marko,0.4,lop,0.2,peter]
==>[vadas,0.5,marko]
==>[vadas]
==>[vadas,0.5,marko,0.4,lop]
==>[lop,0.4,marko]
==>[lop,0.4,marko,0.5,vadas]
==>[lop]
==>[lop,0.4,josh]
==>[lop,0.2,peter]
==>[ripple,1.0,josh]
==>[ripple]
==>[josh,0.4,lop,0.4,marko]
==>[josh,0.4,lop]
==>[josh]
==>[josh,1.0,ripple]
==>[josh,0.4,lop,0.2,peter]
==>[peter,0.2,lop,0.4,marko]
==>[peter,0.2,lop]
==>[peter,0.2,lop,0.4,josh]
==>[peter]
```

```
g.inject(g.withComputer().V().shortestPath().
           with(ShortestPath.distance, 'weight').
           with(ShortestPath.includeEdges, true).
           with(ShortestPath.maxDistance, 1).toList().toArray()).
  map(unfold().values('name','weight').fold()) //1
```

1. Find all shortest paths using a custom distance property and limit the distance to 1. Inject the result into a OLTP `GraphTraversal` in order to be able to select properties from all elements in all paths.

**Additional References**

[`shortestPath()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#shortestPath())

### Split Step

The `split()`-step (**map**) returns a list of strings created by splitting the incoming string traverser around the
matches of the given separator. A null separator will split the string by whitespaces. An empty string separator will split on each character.
Null values from the incoming traversers are not processed and remain as null when returned. If the incoming traverser is a non-String value then an
IllegalArgumentException will be thrown.

console (groovy)

groovy

```
gremlin> g.inject("that", "this", "test", null).split("h") //// (1)
==>[t,at]
==>[t,is]
==>[test]
==>null
gremlin> g.V().hasLabel("person").values("name").split("a") //// (2)
==>[m,rko]
==>[v,d,s]
==>[josh]
==>[peter]
gremlin> g.inject("helloworld", "hello world", "hello   world").split(null) //// (3)
==>[helloworld]
==>[hello,world]
==>[hello,world]
gremlin> g.inject("hello", "world", null).split("") //// (4)
==>[h,e,l,l,o]
==>[w,o,r,l,d]
==>null
gremlin> g.V().hasLabel("person").values("name").fold().split(local, "a") //// (5)
==>[[m,rko],[v,d,s],[josh],[peter]]
```

```
g.inject("that", "this", "test", null).split("h") //// (1)
g.V().hasLabel("person").values("name").split("a") //// (2)
g.inject("helloworld", "hello world", "hello   world").split(null) //// (3)
g.inject("hello", "world", null).split("") //// (4)
g.V().hasLabel("person").values("name").fold().split(local, "a") //5
```

1. Split the strings by "h".
2. Split person names by "a".
3. Splitting by null will split by whitespaces.
4. Splitting by "" will split by each character.
5. Use `Scope.local` to operate on individual string elements inside incoming list, which will return a list of results.

**Additional References**
[`split(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#split(java.lang.String))
[`split(Scope, String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#split(org.apache.tinkerpop.gremlin.process.traversal.Scope,java.lang.String))

### Substring Step

The `substring()`-step (**map**) returns a substring with a 0-based start index (inclusive) and optionally an end index (exclusive) specified.
If the start index is negative then it will begin at the specified index counted from the end of the string, or 0 if exceeding the string length.
Likewise, if the end index is negative then it will end at the specified index counted from the end of the string, or 0 if exceeding the string length.

End index is optional, if it is not specified or if it exceeds the length of the string then all remaining characters will
be returned. End index ≤ start index will return the empty string. Null values are not processed and remain as null when returned.
If the incoming traverser is a non-String value then an `IllegalArgumentException` will be thrown.

console (groovy)

groovy

```
gremlin> g.inject("test", "hello world", null).substring(1, 8)
==>est
==>ello wo
==>null
gremlin> g.inject("hello world").substring(-4) //// (1)
==>orld
gremlin> g.inject("hello world").substring(2, 0) //// (2)
==>
gremlin> g.V().hasLabel("software").values("name").substring(2)
==>p
==>pple
gremlin> g.V().hasLabel("software").values("name").fold().substring(local, 2) //// (3)
==>[p,pple]
```

```
g.inject("test", "hello world", null).substring(1, 8)
g.inject("hello world").substring(-4) //// (1)
g.inject("hello world").substring(2, 0) //// (2)
g.V().hasLabel("software").values("name").substring(2)
g.V().hasLabel("software").values("name").fold().substring(local, 2) //3
```

1. Negative start index, the first character is read by counting from the end of the string
2. Length of 0 specified will return the empty string
3. Use `Scope.local` to operate on individual string elements inside incoming list, which will return a list.

**Additional References**
[`substring(int)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#substring(int))
[`substring(Scope,int)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#substring(org.apache.tinkerpop.gremlin.process.traversal.Scope,int))
[`substring(int,int)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#substring(int,int))
[`substring(Scope,int,int)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#substring(org.apache.tinkerpop.gremlin.process.traversal.Scope,int,int))

### Sum Step

The `sum()`-step (**map**) operates on a stream of numbers and sums the numbers together to yield a result. Note that
the current traverser number is multiplied by the traverser bulk to determine how many such numbers are being
represented.

console (groovy)

groovy

```
gremlin> g.V().values('age').sum()
==>123
gremlin> g.V().repeat(both()).times(3).values('age').sum()
==>1471
```

```
g.V().values('age').sum()
g.V().repeat(both()).times(3).values('age').sum()
```

When called as `sum(local)` it determines the sum of the current, local object (not the objects in the traversal
stream). This works for `Collection`-type objects.

console (groovy)

groovy

```
gremlin> g.V().values('age').fold().sum(local)
==>123
```

```
g.V().values('age').fold().sum(local)
```

When there are `null` values being evaluated the `null` objects are ignored, but if all values are recognized as `null`
the return value is `null`.

console (groovy)

groovy

```
gremlin> g.inject(null,10, 9, null).sum()
==>19
gremlin> g.inject([null,null,null]).sum(local)
==>null
```

```
g.inject(null,10, 9, null).sum()
g.inject([null,null,null]).sum(local)
```

**Additional References**

[`sum()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#sum()),
[`sum(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#sum(org.apache.tinkerpop.gremlin.process.traversal.Scope)),
[`Scope`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Scope.html)

### ToLower Step

The `toLower()`-step (**map**) returns the lowercase representation of incoming string or list of string traverser. Null values are not processed and remain as null when returned.
If the incoming traverser is a non-String value then an `IllegalArgumentException` will be thrown.

console (groovy)

groovy

```
gremlin> g.inject("HELLO", "wORlD", null).toLower()
==>hello
==>world
==>null
gremlin> g.inject(["HELLO", "wORlD", null]).toLower(Scope.local) //// (1)
==>[hello,world,null]
```

```
g.inject("HELLO", "wORlD", null).toLower()
g.inject(["HELLO", "wORlD", null]).toLower(Scope.local) //1
```

1. Use `Scope.local` to operate on individual string elements inside incoming list, which will return a list.

**Additional References**

[`toLower()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#toLower())
[`toLower(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#toLower(org.apache.tinkerpop.gremlin.process.traversal.Scope))

### ToUpper Step

The `toUpper()`-step (**map**) returns the uppercase representation of incoming string or list of string traverser. Null values are not processed and remain as null when returned.
If the incoming traverser is a non-String value then an `IllegalArgumentException` will be thrown.

console (groovy)

groovy

```
gremlin> g.inject("hello", "wORlD", null).toUpper()
==>HELLO
==>WORLD
==>null
gremlin> g.V().values("name").toUpper() //// (1)
==>MARKO
==>VADAS
==>LOP
==>JOSH
==>RIPPLE
==>PETER
gremlin> g.V().values("name").fold().toUpper(local) //// (2)
==>[MARKO,VADAS,LOP,JOSH,RIPPLE,PETER]
```

```
g.inject("hello", "wORlD", null).toUpper()
g.V().values("name").toUpper() //// (1)
g.V().values("name").fold().toUpper(local) //2
```

1. Returns the upper case representation of all vertex names.
2. Use `Scope.local` to operate on individual string elements inside incoming list, which will return a list.

**Additional References**

[`toUpper()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#toUpper())
[`toUpper(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#toUpper(org.apache.tinkerpop.gremlin.process.traversal.Scope))

### Trim Step

The `trim()`-step (**map**) returns a string with leading and leading whitespace removed. Null values are not processed and remain
as null when returned. If the incoming traverser is a non-String value then an `IllegalArgumentException` will be thrown.

console (groovy)

groovy

```
gremlin> g.inject("   hello   ", " world ", null).trim()
==>hello
==>world
==>null
gremlin> g.inject(["   hello   ", " world ", null]).trim(Scope.local) //// (1)
==>[hello,world,null]
```

```
g.inject("   hello   ", " world ", null).trim()
g.inject(["   hello   ", " world ", null]).trim(Scope.local) //1
```

1. Use `Scope.local` to operate on individual string elements inside incoming list, which will return a list.

[`trim()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#trim())
[`trim(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#trim(org.apache.tinkerpop.gremlin.process.traversal.Scope))

### Unfold Step

If the object reaching `unfold()` (**flatMap**) is an iterator, iterable, or map, then it is unrolled into a linear
form. If not, then the object is simply emitted. Please see [`fold()`](06-steps/map-steps.md#fold-step) step for the inverse behavior.

console (groovy)

groovy

```
gremlin> g.V(1).out().fold().inject('gremlin',[1.23,2.34])
==>gremlin
==>[1.23,2.34]
==>[v[3],v[2],v[4]]
gremlin> g.V(1).out().fold().inject('gremlin',[1.23,2.34]).unfold()
==>gremlin
==>1.23
==>2.34
==>v[3]
==>v[2]
==>v[4]
```

```
g.V(1).out().fold().inject('gremlin',[1.23,2.34])
g.V(1).out().fold().inject('gremlin',[1.23,2.34]).unfold()
```

Note that `unfold()` does not recursively unroll iterators. Instead, `repeat()` can be used to for recursive unrolling.

console (groovy)

groovy

```
gremlin> inject(1,[2,3,[4,5,[6]]])
==>1
==>[2,3,[4,5,[6]]]
gremlin> inject(1,[2,3,[4,5,[6]]]).unfold()
==>1
==>2
==>3
==>[4,5,[6]]
gremlin> inject(1,[2,3,[4,5,[6]]]).repeat(unfold()).until(count(local).is(1)).unfold()
==>1
==>2
==>3
==>4
==>5
==>6
```

```
inject(1,[2,3,[4,5,[6]]])
inject(1,[2,3,[4,5,[6]]]).unfold()
inject(1,[2,3,[4,5,[6]]]).repeat(unfold()).until(count(local).is(1)).unfold()
```

**Additional References**

[`unfold()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#unfold())

### Value Step

The `value()`-step (**map**) takes a `Property` and extracts the value from it.

console (groovy)

groovy

```
gremlin> g.V(1).properties().value()
==>marko
==>san diego
==>santa cruz
==>brussels
==>santa fe
gremlin> g.V(1).properties().properties().value()
==>1997
==>2001
==>2001
==>2004
==>2004
==>2005
==>2005
```

```
g.V(1).properties().value()
g.V(1).properties().properties().value()
```

**Additional References**

[`value()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#value())

### ValueMap Step

The `valueMap()`-step yields a `Map` representation of the properties of an element.

|  |  |
| --- | --- |
| Important | This step is the precursor to the [elementMap()-step](06-steps/map-steps.md#elementmap-step). Users should typically choose `elementMap()` unless they utilize multi-properties. `elementMap()` effectively mimics the functionality of `valueMap(true).by(unfold())` as a single step. |

console (groovy)

groovy

```
gremlin> g.V().valueMap()
==>[name:[marko],age:[29]]
==>[name:[vadas],age:[27]]
==>[name:[lop],lang:[java]]
==>[name:[josh],age:[32]]
==>[name:[ripple],lang:[java]]
==>[name:[peter],age:[35]]
gremlin> g.V().valueMap('age')
==>[age:[29]]
==>[age:[27]]
==>[]
==>[age:[32]]
==>[]
==>[age:[35]]
gremlin> g.V().valueMap('age','blah')
==>[age:[29]]
==>[age:[27]]
==>[]
==>[age:[32]]
==>[]
==>[age:[35]]
gremlin> g.E().valueMap()
==>[weight:0.5]
==>[weight:1.0]
==>[weight:0.4]
==>[weight:1.0]
==>[weight:0.4]
==>[weight:0.2]
```

```
g.V().valueMap()
g.V().valueMap('age')
g.V().valueMap('age','blah')
g.E().valueMap()
```

It is important to note that the map of a vertex maintains a list of values for each key. The map of an edge or
vertex-property represents a single property (not a list). The reason is that vertices in TinkerPop leverage
[vertex properties](#vertex-properties) which support multiple values per key. Using the ["The Crew"](#the-crew-toy-graph) toy graph, the point is made explicit.

console (groovy)

groovy

```
gremlin> g.V().valueMap()
==>[name:[marko],location:[san diego,santa cruz,brussels,santa fe]]
==>[name:[stephen],location:[centreville,dulles,purcellville]]
==>[name:[matthias],location:[bremen,baltimore,oakland,seattle]]
==>[name:[daniel],location:[spremberg,kaiserslautern,aachen]]
==>[name:[gremlin]]
==>[name:[tinkergraph]]
gremlin> g.V().has('name','marko').properties('location')
==>vp[location->san diego]
==>vp[location->santa cruz]
==>vp[location->brussels]
==>vp[location->santa fe]
gremlin> g.V().has('name','marko').properties('location').valueMap()
==>[startTime:1997,endTime:2001]
==>[startTime:2001,endTime:2004]
==>[startTime:2004,endTime:2005]
==>[startTime:2005]
```

```
g.V().valueMap()
g.V().has('name','marko').properties('location')
g.V().has('name','marko').properties('location').valueMap()
```

To turn list of values into single items, the `by()` modulator can be used as shown below.

console (groovy)

groovy

```
gremlin> g.V().valueMap().by(unfold())
==>[name:marko,location:san diego]
==>[name:stephen,location:centreville]
==>[name:matthias,location:bremen]
==>[name:daniel,location:spremberg]
==>[name:gremlin]
==>[name:tinkergraph]
gremlin> g.V().valueMap('name','location').by(unfold())
==>[name:marko,location:san diego]
==>[name:stephen,location:centreville]
==>[name:matthias,location:bremen]
==>[name:daniel,location:spremberg]
==>[name:gremlin]
==>[name:tinkergraph]
```

```
g.V().valueMap().by(unfold())
g.V().valueMap('name','location').by(unfold())
```

If the `id`, `label`, `key`, and `value` of the `Element` is desired, then the `with()` modulator can be used to
trigger its insertion into the returned map.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person').valueMap().with(WithOptions.tokens)
==>[id:1,label:person,name:[marko],location:[san diego,santa cruz,brussels,santa fe]]
==>[id:7,label:person,name:[stephen],location:[centreville,dulles,purcellville]]
==>[id:8,label:person,name:[matthias],location:[bremen,baltimore,oakland,seattle]]
==>[id:9,label:person,name:[daniel],location:[spremberg,kaiserslautern,aachen]]
gremlin> g.V().hasLabel('person').valueMap('name').with(WithOptions.tokens, WithOptions.labels)
==>[label:person,name:[marko]]
==>[label:person,name:[stephen]]
==>[label:person,name:[matthias]]
==>[label:person,name:[daniel]]
gremlin> g.V().hasLabel('person').properties('location').valueMap().with(WithOptions.tokens, WithOptions.values)
==>[value:san diego,startTime:1997,endTime:2001]
==>[value:santa cruz,startTime:2001,endTime:2004]
==>[value:brussels,startTime:2004,endTime:2005]
==>[value:santa fe,startTime:2005]
==>[value:centreville,startTime:1990,endTime:2000]
==>[value:dulles,startTime:2000,endTime:2006]
==>[value:purcellville,startTime:2006]
==>[value:bremen,startTime:2004,endTime:2007]
==>[value:baltimore,startTime:2007,endTime:2011]
==>[value:oakland,startTime:2011,endTime:2014]
==>[value:seattle,startTime:2014]
==>[value:spremberg,startTime:1982,endTime:2005]
==>[value:kaiserslautern,startTime:2005,endTime:2009]
==>[value:aachen,startTime:2009]
```

```
g.V().hasLabel('person').valueMap().with(WithOptions.tokens)
g.V().hasLabel('person').valueMap('name').with(WithOptions.tokens, WithOptions.labels)
g.V().hasLabel('person').properties('location').valueMap().with(WithOptions.tokens, WithOptions.values)
```

**Additional References**

[`valueMap(String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#valueMap(java.lang.String...))

### Values Step

The `values()`-step (**map**) extracts the values of properties from an `Element` in the traversal stream.

console (groovy)

groovy

```
gremlin> g.V(1).values()
==>marko
==>san diego
==>santa cruz
==>brussels
==>santa fe
gremlin> g.V(1).values('location')
==>san diego
==>santa cruz
==>brussels
==>santa fe
gremlin> g.V(1).properties('location').values()
==>1997
==>2001
==>2001
==>2004
==>2004
==>2005
==>2005
```

```
g.V(1).values()
g.V(1).values('location')
g.V(1).properties('location').values()
```

**Additional References**

[`values(String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#values(java.lang.String...))

