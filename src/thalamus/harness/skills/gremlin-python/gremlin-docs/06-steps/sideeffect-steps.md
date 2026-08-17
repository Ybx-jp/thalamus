### Aggregate Step

![aggregate step](../images/aggregate-step.png)

The `aggregate()`-step (**sideEffect**) is used to aggregate all the objects at a particular point of traversal into a
`Collection`. By default, the step will use [eager evaluation](http://en.wikipedia.org/wiki/Eager_evaluation) in that
no objects continue on until all previous objects have been fully aggregated. The eager evaluation model is crucial in situations
where everything at a particular point is required for future computation.

console (groovy)

groovy

```
gremlin> g.V(1).out('created') //// (1)
==>v[3]
gremlin> g.V(1).out('created').aggregate('x') //// (2)
==>v[3]
gremlin> g.V(1).out('created').aggregate('x').in('created') //// (3)
==>v[1]
==>v[4]
==>v[6]
gremlin> g.V(1).out('created').aggregate('x').in('created').out('created') //// (4)
==>v[3]
==>v[5]
==>v[3]
==>v[3]
gremlin> g.V(1).out('created').aggregate('x').in('created').out('created').
                where(without('x')).values('name') //// (5)
==>ripple
```

```
g.V(1).out('created') //// (1)
g.V(1).out('created').aggregate('x') //// (2)
g.V(1).out('created').aggregate('x').in('created') //// (3)
g.V(1).out('created').aggregate('x').in('created').out('created') //// (4)
g.V(1).out('created').aggregate('x').in('created').out('created').
       where(without('x')).values('name') //5
```

1. What has marko created?
2. Aggregate all his creations.
3. Who are marko’s collaborators?
4. What have marko’s collaborators created?
5. What have marko’s collaborators created that he hasn’t created?

In [recommendation systems](http://en.wikipedia.org/wiki/Recommender_system), the above pattern is used:

```
"What has userA liked? Who else has liked those things? What have they liked that userA hasn't already liked?"
```

Finally, `aggregate()`-step can be modulated via `by()`-projection.

console (groovy)

groovy

```
gremlin> g.V().out('knows').aggregate('x').cap('x')
==>[v[2],v[4]]
gremlin> g.V().out('knows').aggregate('x').by('name').cap('x')
==>[vadas,josh]
gremlin> g.V().out('knows').aggregate('x').by('age').cap('x') //// (1)
==>[27,32]
```

```
g.V().out('knows').aggregate('x').cap('x')
g.V().out('knows').aggregate('x').by('name').cap('x')
g.V().out('knows').aggregate('x').by('age').cap('x')  //1
```

1. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are not included in the aggregation.

Aggregation can be controlled to occur in a [lazy](http://en.wikipedia.org/wiki/Lazy_evaluation) fashion by using
the step inside `local()`.

console (groovy)

groovy

groovy

```
gremlin> g.V().aggregate('x').limit(1).cap('x')
==>[v[1],v[2],v[3],v[4],v[5],v[6]]
gremlin> g.V().local(aggregate('x')).limit(1).cap('x')
==>[v[1],v[2]]
```

```
g.V().aggregate('x').limit(1).cap('x')
g.V().local(aggregate('x')).limit(1).cap('x')
```

```
g.E().local(aggregate('x')).by('weight').cap('x')
```

**Additional References**

[`aggregate(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#aggregate(java.lang.String)),

### Cap Step

The `cap()`-step (**barrier**) iterates the traversal up to itself and emits the sideEffect referenced by the provided
key. If multiple keys are provided, then a `Map<String,Object>` of sideEffects is emitted.

console (groovy)

groovy

```
gremlin> g.V().groupCount('a').by(label).cap('a') //// (1)
==>[software:2,person:4]
gremlin> g.V().groupCount('a').by(label).groupCount('b').by(outE().count()).cap('a','b') //// (2)
==>[a:[software:2,person:4],b:[0:3,1:1,2:1,3:1]]
```

```
g.V().groupCount('a').by(label).cap('a') //// (1)
g.V().groupCount('a').by(label).groupCount('b').by(outE().count()).cap('a','b')   //2
```

1. Group and count vertices by their label. Emit the side effect labeled 'a', which is the group count by label.
2. Same as statement 1, but also emit the side effect labeled 'b' which groups vertices by the number of out edges.

**Additional References**

[`cap(String,String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#cap(java.lang.String,java.lang.String...))

### Discard Step

The `discard()`-step (**filter**) filters all objects from a traversal stream. It is helpful with [Branch Step](06-steps/branch-steps.md#branch-step) types
of steps where a particular branch of code should "throw away" traversers. In the following example, traversers that
don’t match are filtered out of the traversal stream.

console (groovy)

groovy

```
gremlin> g.V().choose(T.label).
                 option("person", __.out("knows").values("name")).
                 option("bleep", __.out("created").values("name")).
                 option(none, discard())
==>vadas
==>josh
```

```
g.V().choose(T.label).
        option("person", __.out("knows").values("name")).
        option("bleep", __.out("created").values("name")).
        option(none, discard())
```

It is also useful for traversals that are executed remotely where returning results is not useful and the traversal is
only meant to generate side-effects. Choosing not to return results saves in serialization and network costs as the
objects are filtered on the remote end and not returned to the client side. Typically, this step does not need to be
used directly and is quietly used by the `iterate()` terminal step which appends `discard()` to the traversal before
actually cycling through results.

**Additional References**

[`discard()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Traversal.html#discard())
[`iterate()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Traversal.html#iterate())

### Drop Step

The `drop()`-step (**filter**/**sideEffect**) is used to remove element and properties from the graph (i.e. remove). It
is a filter step because the traversal yields no outgoing objects.

console (groovy)

groovy

```
gremlin> g.V().outE().drop()
gremlin> g.E()
gremlin> g.V().properties('name').drop()
gremlin> g.V().elementMap()
==>[id:1,label:person,age:29]
==>[id:2,label:person,age:27]
==>[id:3,label:software,lang:java]
==>[id:4,label:person,age:32]
==>[id:5,label:software,lang:java]
==>[id:6,label:person,age:35]
gremlin> g.V().drop()
gremlin> g.V()
```

```
g.V().outE().drop()
g.E()
g.V().properties('name').drop()
g.V().elementMap()
g.V().drop()
g.V()
```

**Additional References**

* [`drop()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#drop())

### Fail Step

The `fail()`-step provides a way to force a traversal to immediately fail with an exception. This feature is often
helpful during debugging purposes and for validating certain conditions prior to continuing with traversal execution.

```
gremlin> g.V().has('person','name','peter').fold().
......1>   coalesce(unfold(),
......2>            fail('peter should exist')).
......3>   property('k',100)
==>v[6]
gremlin> g.V().has('person','name','stephen').fold().
......1>   coalesce(unfold(),
......2>            fail('stephen should exist')).
......3>   property('k',100)
fail() Step Triggered
===========================================================================================================================
Message > stephen should exist
Traverser> []
  Bulk   > 1
Traversal> fail()
Parent   > CoalesceStep [V().has("person","name","stephen").fold().coalesce(__.unfold(),__.fail()).property("k",(int) 100)]
Metadata > {}
===========================================================================================================================
```

The code example above exemplifies the latter use case where there is essentially an assertion that there is a vertex
with a particular "name" value prior to updating the property "k" and explicitly failing when that vertex is not found.

The `fail()` step does not guarantee that mutations are not partially applied. Triggering `fail()` produces an
exception, but it’s effect on any open transactions or the underlying graph’s behavior ends there. Generally speaking,
mutations made to the point of `fail()` being triggered are applied and `fail()` itself has no influence on rolling back
those changes. It is up to the application catching that exception to act in a fashion that will allow for that
rollback. Moreover, the ability to rollback at all is graph provider dependent. For example, a basic TinkerGraph,
configured without transaction support, will simply be left in a partially mutated state whether the action to rollback
on `fail()` was implemented or not.

**Additional References**

[`fail()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#fail()),
[`fail(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#fail(java.lang.String))

### Group Step

As traversers propagate across a graph as defined by a traversal, sideEffect computations are sometimes required.
That is, the actual path taken or the current location of a traverser is not the ultimate output of the computation,
but some other representation of the traversal. The `group()`-step (**map**/**sideEffect**) is one such sideEffect that
organizes the objects according to some function of the object. Then, if required, that organization (a list) is
reduced. An example is provided below.

console (groovy)

groovy

```
gremlin> g.V().group().by(label) //// (1)
==>[software:[v[3],v[5]],person:[v[1],v[2],v[4],v[6]]]
gremlin> g.V().group().by(label).by('name') //// (2)
==>[software:[lop,ripple],person:[marko,vadas,josh,peter]]
gremlin> g.V().group().by(label).by(count()) //// (3)
==>[software:2,person:4]
```

```
g.V().group().by(label) //// (1)
g.V().group().by(label).by('name') //// (2)
g.V().group().by(label).by(count()) //3
```

1. Group the vertices by their label.
2. For each vertex in the group, get their name.
3. For each grouping, what is its size?

The two projection parameters available to `group()` via `by()` are:

1. Key-projection: What feature of the object to group on (a function that yields the map key)?
2. Value-projection: What feature of the group to store in the key-list?

console (groovy)

groovy

```
gremlin> g.V().group().by('age').by('name') //// (1)
==>[32:[josh],35:[peter],27:[vadas],29:[marko]]
gremlin> g.V().group().by('name').by('age') //// (2)
==>[ripple:[],peter:[35],vadas:[27],josh:[32],lop:[],marko:[29]]
```

```
g.V().group().by('age').by('name') //// (1)
g.V().group().by('name').by('age') //2
```

1. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those keys are filtered.
2. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are filtered.

**Additional References**

[`group()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#group()),
[`group(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#group(java.lang.String))

### GroupCount Step

When it is important to know how many times a particular object has been at a particular part of a traversal,
`groupCount()`-step (**map**/**sideEffect**) is used.

```
"What is the distribution of ages in the graph?"
```

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person').values('age').groupCount()
==>[32:1,35:1,27:1,29:1]
gremlin> g.V().hasLabel('person').groupCount().by('age') //// (1)
==>[32:1,35:1,27:1,29:1]
gremlin> g.V().groupCount().by('age') //// (2)
==>[32:1,35:1,27:1,29:1]
```

```
g.V().hasLabel('person').values('age').groupCount()
g.V().hasLabel('person').groupCount().by('age') //// (1)
g.V().groupCount().by('age') //2
```

1. You can also supply a pre-group projection, where the provided [`by()`](06-steps/modulator-steps.md#by-step)-modulation determines what to
   group the incoming object by.
2. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are filtered.

There is one person that is 32, one person that is 35, one person that is 27, and one person that is 29.

```
"Iteratively walk the graph and count the number of times you see the second letter of each name."
```

![groupcount step](../images/groupcount-step.png)

console (groovy)

groovy

```
gremlin> g.V().repeat(both().groupCount('m').by(label)).times(10).cap('m')
==>[software:19598,person:39196]
```

```
g.V().repeat(both().groupCount('m').by(label)).times(10).cap('m')
```

The above is interesting in that it demonstrates the use of referencing the internal `Map<Object,Long>` of
`groupCount()` with a string variable. Given that `groupCount()` is a sideEffect-step, it simply passes the object
it received to its output. Internal to `groupCount()`, the object’s count is incremented.

**Additional References**

[`groupCount()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#groupCount()),
[`groupCount(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#groupCount(java.lang.String))

### Property Step

The `property()`-step is used to add properties to the elements of the graph (**sideEffect**). Unlike `addV()` and
`addE()`, `property()` is a full sideEffect step in that it does not return the property it created, but the element
that streamed into it. Moreover, if `property()` follows an `addV()` or `addE()`, then it is "folded" into the
previous step to enable vertex and edge creation with all its properties in one creation operation.

console (groovy)

groovy

```
gremlin> g.V(1).property('country','usa')
==>v[1]
gremlin> g.V(1).property('city','santa fe').property('state','new mexico').valueMap()
==>[country:[usa],city:[santa fe],name:[marko],state:[new mexico],age:[29]]
gremlin> g.V(1).property(['city': 'santa fe', 'state': 'new mexico']) //// (1)
==>v[1]
gremlin> g.V(1).property(list,'age',35) //// (2)
==>v[1]
gremlin> g.V(1).property(list, ['city': 'santa fe', 'state': 'new mexico']) //// (3)
==>v[1]
gremlin> g.V(1).valueMap()
==>[country:[usa],city:[santa fe,santa fe],name:[marko],state:[new mexico,new mexico],age:[29,35]]
gremlin> g.V(1).property(list, ['age': single(36), 'city': 'wilmington', 'state': 'delaware']) //// (4)
==>v[1]
gremlin> g.V(1).valueMap()
==>[country:[usa],city:[santa fe,santa fe,wilmington],name:[marko],state:[new mexico,new mexico,delaware],age:[36]]
gremlin> g.V(1).property('friendWeight',outE('knows').values('weight').sum(),'acl','private') //// (5)
==>v[1]
gremlin> g.V(1).properties('friendWeight').valueMap() //// (6)
==>[acl:private]
gremlin> g.addV().property(T.label,'person').valueMap().with(WithOptions.tokens) //// (7)
==>[id:13,label:person]
gremlin> g.addV().property(null) //// (8)
==>v[14]
gremlin> g.addV().property(set, null)
==>v[15]
```

```
g.V(1).property('country','usa')
g.V(1).property('city','santa fe').property('state','new mexico').valueMap()
g.V(1).property(['city': 'santa fe', 'state': 'new mexico']) //// (1)
g.V(1).property(list,'age',35) //// (2)
g.V(1).property(list, ['city': 'santa fe', 'state': 'new mexico']) //// (3)
g.V(1).valueMap()
g.V(1).property(list, ['age': single(36), 'city': 'wilmington', 'state': 'delaware']) //// (4)
g.V(1).valueMap()
g.V(1).property('friendWeight',outE('knows').values('weight').sum(),'acl','private') //// (5)
g.V(1).properties('friendWeight').valueMap() //// (6)
g.addV().property(T.label,'person').valueMap().with(WithOptions.tokens) //// (7)
g.addV().property(null) //// (8)
g.addV().property(set, null)
```

1. Properties can also take a `Map` as an argument.
2. For vertices, a cardinality can be provided for [vertex properties](#vertex-properties).
3. If a cardinality is specified for a `Map` then that cardinality will be used for all properties in the map.
4. Assign the `Cardinality` individually to override the specified `list` or the default cardinality if not specified.
5. It is possible to select the property value (as well as key) via a traversal.
6. For vertices, the `property()`-step can add meta-properties.
7. The label value can be specified as a property only at the time a vertex is added and if one is not specified in the addV()
8. If you pass a `null` value for the Map this will be treated as a no-op and the input will be returned

**Additional References**

[`property(Object, Object, Object…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#property(java.lang.Object,java.lang.Object,java.lang.Object...)),
[`property(Cardinality, Object, Object, Object…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#property(org.apache.tinkerpop.gremlin.structure.VertexProperty.Cardinality,java.lang.Object,java.lang.Object,java.lang.Object...)),
[`Cardinality`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/structure/VertexProperty.Cardinality.html)

### Sack Step

![gremlin sacks running](../images/gremlin-sacks-running.png) A traverser can contain a local data structure called a "sack".
The `sack()`-step is used to read and write sacks (**sideEffect** or **map**). Each sack of each traverser is created
when using `GraphTraversal.withSack(initialValueSupplier,splitOperator?,mergeOperator?)`.

* **Initial value supplier**: A `Supplier` providing the initial value of each traverser’s sack.
* **Split operator**: a `UnaryOperator` that clones the traverser’s sack when the traverser splits. If no split operator
  is provided, then `UnaryOperator.identity()` is assumed.
* **Merge operator**: A `BinaryOperator` that unites two traverser’s sack when they are merged. If no merge operator is
  provided, then traversers with sacks can not be merged.

Two trivial examples are presented below to demonstrate the **initial value supplier**. In the first example below, a
traverser is created at each vertex in the graph (`g.V()`), with a 1.0 sack (`withSack(1.0f)`), and then the sack
value is accessed (`sack()`). In the second example, a random float supplier is used to generate sack values.

console (groovy)

groovy

```
gremlin> g.withSack(1.0f).V().sack()
==>1.0
==>1.0
==>1.0
==>1.0
==>1.0
==>1.0
gremlin> rand = new Random()
==>java.util.Random@7d575d24
gremlin> g.withSack {rand.nextFloat()}.V().sack()
==>0.07906163
==>0.31745565
==>0.9005943
==>0.8956969
==>0.4104929
==>0.93647516
```

```
g.withSack(1.0f).V().sack()
rand = new Random()
g.withSack {rand.nextFloat()}.V().sack()
```

A more complicated initial value supplier example is presented below where the sack values are used in a running
computation and then emitted at the end of the traversal. When an edge is traversed, the edge weight is multiplied
by the sack value (`sack(mult).by('weight')`). Note that the [`by()`](06-steps/modulator-steps.md#by-step)-modulator can be any arbitrary traversal.

console (groovy)

groovy

```
gremlin> g.withSack(1.0f).V().repeat(outE().sack(mult).by('weight').inV()).times(2)
==>v[5]
==>v[3]
gremlin> g.withSack(1.0f).V().repeat(outE().sack(mult).by('weight').inV()).times(2).sack()
==>1.0
==>0.4
gremlin> g.withSack(1.0f).V().repeat(outE().sack(mult).by('weight').inV()).times(2).path().
               by().by('weight')
==>[v[1],1.0,v[4],1.0,v[5]]
==>[v[1],1.0,v[4],0.4,v[3]]
gremlin> g.V().sack(assign).by('age').sack() //// (1)
==>29
==>27
==>32
==>35
```

```
g.withSack(1.0f).V().repeat(outE().sack(mult).by('weight').inV()).times(2)
g.withSack(1.0f).V().repeat(outE().sack(mult).by('weight').inV()).times(2).sack()
g.withSack(1.0f).V().repeat(outE().sack(mult).by('weight').inV()).times(2).path().
      by().by('weight')
g.V().sack(assign).by('age').sack() //1
```

1. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are filtered during the assignment.

![gremlin sacks standing](../images/gremlin-sacks-standing.png) When complex objects are used (i.e. non-primitives), then a
**split operator** should be defined to ensure that each traverser gets a clone of its parent’s sack. The first example
does not use a split operator and as such, the same map is propagated to all traversers (a global data structure). The
second example, demonstrates how `Map.clone()` ensures that each traverser’s sack contains a unique, local sack.

console (groovy)

groovy

```
gremlin> g.withSack {[:]}.V().out().out().
               sack {m,v -> m[v.value('name')] = v.value('lang'); m}.sack() // BAD: single map
==>[ripple:java]
==>[ripple:java,lop:java]
gremlin> g.withSack {[:]}{it.clone()}.V().out().out().
               sack {m,v -> m[v.value('name')] = v.value('lang'); m}.sack() // GOOD: cloned map
==>[ripple:java]
==>[lop:java]
```

```
g.withSack {[:]}.V().out().out().
      sack {m,v -> m[v.value('name')] = v.value('lang'); m}.sack() // BAD: single map
g.withSack {[:]}{it.clone()}.V().out().out().
      sack {m,v -> m[v.value('name')] = v.value('lang'); m}.sack() // GOOD: cloned map
```

|  |  |
| --- | --- |
| Note | For primitives (i.e. integers, longs, floats, etc.), a split operator is not required as a primitives are encoded in the memory address of the sack, not as a reference to an object. |

If a **merge operator** is not provided, then traversers with sacks can not be bulked. However, in many situations,
merging the sacks of two traversers at the same location is algorithmically sound and good to provide so as to gain
the bulking optimization. In the examples below, the binary merge operator is `Operator.sum`. Thus, when two traverser
merge, their respective sacks are added together.

console (groovy)

groovy

```
gremlin> g.withSack(1.0d).V(1).out('knows').in('knows') //// (1)
==>v[1]
==>v[1]
gremlin> g.withSack(1.0d).V(1).out('knows').in('knows').sack() //// (2)
==>1.0
==>1.0
gremlin> g.withSack(1.0d, sum).V(1).out('knows').in('knows').sack() //// (3)
==>2.0
==>2.0
gremlin> g.withSack(1.0d).V(1).local(outE('knows').barrier(normSack).inV()).in('knows').barrier() //// (4)
==>v[1]
==>v[1]
gremlin> g.withSack(1.0d).V(1).local(outE('knows').barrier(normSack).inV()).in('knows').barrier().sack() //// (5)
==>0.5
==>0.5
gremlin> g.withSack(1.0d,sum).V(1).local(outE('knows').barrier(normSack).inV()).in('knows').barrier().sack() //// (6)
==>1.0
==>1.0
gremlin> g.withBulk(false).withSack(1.0f,sum).V(1).local(outE('knows').barrier(normSack).inV()).in('knows').barrier().sack() //// (7)
==>1.0
gremlin> g.withBulk(false).withSack(1.0f).V(1).local(outE('knows').barrier(normSack).inV()).in('knows').barrier().sack() //// (8)
==>0.5
==>0.5
gremlin>
```

```
g.withSack(1.0d).V(1).out('knows').in('knows') //// (1)
g.withSack(1.0d).V(1).out('knows').in('knows').sack() //// (2)
g.withSack(1.0d, sum).V(1).out('knows').in('knows').sack() //// (3)
g.withSack(1.0d).V(1).local(outE('knows').barrier(normSack).inV()).in('knows').barrier() //// (4)
g.withSack(1.0d).V(1).local(outE('knows').barrier(normSack).inV()).in('knows').barrier().sack() //// (5)
g.withSack(1.0d,sum).V(1).local(outE('knows').barrier(normSack).inV()).in('knows').barrier().sack() //// (6)
g.withBulk(false).withSack(1.0f,sum).V(1).local(outE('knows').barrier(normSack).inV()).in('knows').barrier().sack() //// (7)
g.withBulk(false).withSack(1.0f).V(1).local(outE('knows').barrier(normSack).inV()).in('knows').barrier().sack() //// (8)
```

1. We find vertex 1 twice because he knows two other people
2. Without a merge operation the sack values are 1.0.
3. When specifying `sum` as the merge operation, the sack values are 2.0 because of bulking
4. Like 1, but using barrier internally
5. The `local(…​barrier(normSack)…​)` ensures that all traversers leaving vertex 1 have an evenly distributed amount of the initial 1.0 "energy" (50-50), i.e. the sack is 0.5 on each result
6. Like 3, but using `sum` as merge operator leads to the expected 1.0
7. There is now a single traverser with bulk of 2 and sack of 1.0 and thus, setting `` withBulk(false)` `` yields the expected 1.0
8. Like 7, but without the `sum` operator

**Additional References**

[`sack()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#sack()),
[`sack(BiFunction)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#sack(java.util.function.BiFunction))

### SideEffect Step

The `sideEffect()` step performs some operation on the traverser and passes it to the next step in the process. Please
see the [Steps Reference](index.md) for more information.

**Additional References**

[`map(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#sideEffect(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### Subgraph Step

![subgraph logo](../images/subgraph-logo.png)

Extracting a portion of a graph from a larger one for analysis, visualization or other purposes is a fairly common
use case for graph analysts and developers. The `subgraph()`-step (**sideEffect**) provides a way to produce an
[edge-induced subgraph](http://mathworld.wolfram.com/Edge-InducedSubgraph.html) from virtually any traversal.
The following example demonstrates how to produce the "knows" subgraph:

console (groovy)

groovy

```
gremlin> subGraph = g.E().hasLabel('knows').subgraph('subGraph').cap('subGraph').next() //// (1)
==>tinkergraph[vertices:3 edges:2]
gremlin> sg = traversal().with(subGraph)
==>graphtraversalsource[tinkergraph[vertices:3 edges:2], standard]
gremlin> sg.E() //// (2)
==>e[7][1-knows->2]
==>e[8][1-knows->4]
```

```
subGraph = g.E().hasLabel('knows').subgraph('subGraph').cap('subGraph').next() //// (1)
sg = traversal().with(subGraph)
sg.E() //2
```

1. As this function produces "edge-induced" subgraphs, `subgraph()` must be called at edge steps.
2. The subgraph contains only "knows" edges.

A more common subgraphing use case is to get all of the graph structure surrounding a single vertex:

console (groovy)

groovy

```
gremlin> subGraph = g.V(3).repeat(__.inE().subgraph('subGraph').outV()).times(3).cap('subGraph').next() //// (1)
==>tinkergraph[vertices:4 edges:4]
gremlin> sg = traversal().with(subGraph)
==>graphtraversalsource[tinkergraph[vertices:4 edges:4], standard]
gremlin> sg.E()
==>e[8][1-knows->4]
==>e[9][1-created->3]
==>e[11][4-created->3]
==>e[12][6-created->3]
```

```
subGraph = g.V(3).repeat(__.inE().subgraph('subGraph').outV()).times(3).cap('subGraph').next() //// (1)
sg = traversal().with(subGraph)
sg.E()
```

1. Starting at vertex `3`, traverse 3 steps away on in-edges, outputting all of that into the subgraph.

The above example is purposely brief so as to focus on `subgraph()` usage, however, it may not be the most optimal
method for constructing the subgraph. For instance, if the graph had cycles, it would attempt to reconstruct parts
of the subgraph which are already present. The duplicates would not be created, but it would involve some unnecessary
processing. If the only interest of the traversal was to populate the subgraph, it would be better to include
`simplePath()` to filter out those cycles, as in `.inE().subgraph('subGraph').outV().simplePath()`. From another
perspective, it might also make some sense to use `dedup()` to avoid traversing the same vertices repeatedly where
two vertices shared the multiple edges between them, as in `.inE().dedup().subgraph('subGraph').outV().dedup()`.

There can be multiple `subgraph()` calls within the same traversal. Each operating against either the same graph
(i.e. same side-effect key) or different graphs (i.e. different side-effect keys).

console (groovy)

groovy

```
gremlin> t = g.V().outE('knows').subgraph('knowsG').inV().outE('created').subgraph('createdG').
                   inV().inE('created').subgraph('createdG').iterate()
gremlin> traversal().with(t.sideEffects.get('knowsG')).E()
==>e[7][1-knows->2]
==>e[8][1-knows->4]
gremlin> traversal().with(t.sideEffects.get('createdG')).E()
==>e[9][1-created->3]
==>e[10][4-created->5]
==>e[11][4-created->3]
==>e[12][6-created->3]
```

```
t = g.V().outE('knows').subgraph('knowsG').inV().outE('created').subgraph('createdG').
          inV().inE('created').subgraph('createdG').iterate()
traversal().with(t.sideEffects.get('knowsG')).E()
traversal().with(t.sideEffects.get('createdG')).E()
```

TinkerGraph is the ideal (and default) `Graph` into which a subgraph is extracted as it’s fast, in-memory, and supports
user-supplied identifiers which can be any Java object. It is this last feature that needs some focus as many
TinkerPop-enabled graphs have complex identifier types and TinkerGraph’s ability to consume those makes it a perfect
host for an incoming subgraph. However care needs to be taken when using the elements of the TinkerGraph subgraph.
The original graph’s identifiers may be preserved, but the elements of the graph are now TinkerGraph objects like,
`TinkerVertex` and `TinkerEdge`. As a result, they can not be used directly in Gremlin running against the original
graph. For example, the following traversal would likely return an error:

```
Vertex v = sg.V().has('name','marko').next();  //1
List<Vertex> vertices = g.V(v).out().toList(); //2
```

1. Here "sg" is a reference to a TinkerGraph subgraph and "v" is a `TinkerVertex`.
2. The `g.V(v)` has the potential to fail as "g" is the original `Graph` instance and not a TinkerGraph - it could
   reject the `TinkerVertex` instance as it will not recognize it.

It is safer to wrap the `TinkerVertex` in a `ReferenceVertex` or simply reference the `id()` as follows:

```
Vertex v = sg.V().has('name','marko').next();
List<Vertex> vertices = g.V(v.id()).out().toList();

// OR

Vertex v = new ReferenceVertex(sg.V().has('name','marko').next());
List<Vertex> vertices = g.V(v).out().toList();
```

**Additional References**

[`subgraph(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#subgraph(java.lang.String))

### Tree Step

From any one element (i.e. vertex or edge), the emanating paths from that element can be aggregated to form a
[tree](http://en.wikipedia.org/wiki/Tree_(data_structure)). Gremlin provides `tree()`-step (**sideEffect**) for such
this situation.

![tree step](../images/tree-step.png)

console (groovy)

groovy

```
gremlin> tree = g.V().out().out().tree().next()
==>v[1]={v[4]={v[3]={}, v[5]={}}}
```

```
tree = g.V().out().out().tree().next()
```

It is important to see how the paths of all the emanating traversers are united to form the tree.

![tree step2](../images/tree-step2.png)

The resultant tree data structure can then be manipulated (see `Tree` JavaDoc).

console (groovy)

groovy

```
gremlin> tree = g.V().out().out().tree().by('name').next()
==>marko={josh={ripple={}, lop={}}}
gremlin> tree['marko']
==>josh={ripple={}, lop={}}
gremlin> tree['marko']['josh']
==>ripple={}
==>lop={}
gremlin> tree.getObjectsAtDepth(3)
==>ripple
==>lop
```

```
tree = g.V().out().out().tree().by('name').next()
tree['marko']
tree['marko']['josh']
tree.getObjectsAtDepth(3)
```

Note that when using `by()`-modulation, tree nodes are combined based on projection uniqueness, not on the
uniqueness of the original objects being projected. For instance:

console (groovy)

groovy

```
gremlin> g.V().has('name','josh').out('created').values('name').tree() //// (1)
==>[v[4]:[v[3]:[lop:[]],v[5]:[ripple:[]]]]
gremlin> g.V().has('name','josh').out('created').values('name').
           tree().by('name').by(label).by() //// (2)
==>[josh:[software:[ripple:[],lop:[]]]]
```

```
g.V().has('name','josh').out('created').values('name').tree() //// (1)
g.V().has('name','josh').out('created').values('name').
  tree().by('name').by(label).by() //2
```

1. When the `tree()` is created, vertex 3 and 5 are unique and thus, form unique branches in the tree structure.
2. When the `tree()` is `by()`-modulated by `label`, then vertex 3 and 5 are both "software" and thus are merged to a single node in the tree.

The `tree()` step can also take a side-effect key as an argument. When using this form, the `Tree` is is built up in a
side-effect as each traverser passes through. The `Tree` can later be accessed by either `select()` or `cap()`.

console (groovy)

groovy

```
gremlin> g.V().has('name','josh').out('created').values('name').tree('x').select('x')
==>[v[4]:[v[3]:[lop:[]],v[5]:[ripple:[]]]]
==>[v[4]:[v[3]:[lop:[]],v[5]:[ripple:[]]]]
```

```
g.V().has('name','josh').out('created').values('name').tree('x').select('x')
```

It is possible to force lazy construction of the tree by embedding inside a `local()` step.

console (groovy)

groovy

```
gremlin> g.V().has('name','josh').out('created').values('name').local(tree('x')).select('x')
==>[v[4]:[v[5]:[ripple:[]]]]
==>[v[4]:[v[3]:[lop:[]],v[5]:[ripple:[]]]]
```

```
g.V().has('name','josh').out('created').values('name').local(tree('x')).select('x')
```

**Additional References**

[`tree()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#tree()),
[`tree(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#tree(java.lang.String))

