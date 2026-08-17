### All Step

It is possible to filter list traversers using `all()`-step (**filter**). Every item in the list will be tested against
the supplied predicate and if all of the items pass then the traverser is passed along the stream, otherwise it is
filtered. Empty lists are passed along but null or non-iterable traversers are filtered out.

|  |  |
| --- | --- |
| Python | The term `all` is a reserved word in Python, and therefore must be referred to in Gremlin with `all_()`. |

console (groovy)

groovy

```
gremlin> g.V().values('age').fold().all(gt(25)) //// (1)
==>[29,27,32,35]
```

```
g.V().values('age').fold().all(gt(25)) //1
```

1. Return the list of ages only if everyone’s age is greater than 25.

**Additional References**

[`all(P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#all(org.apache.tinkerpop.gremlin.process.traversal.P)),
[`P`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/P.html)

### And Step

The `and()`-step ensures that all provided traversals yield a result (**filter**). Please see [`or()`](06-steps/filter-steps.md#or-step) for or-semantics.

|  |  |
| --- | --- |
| Python | The term `and` is a reserved word in Python, and therefore must be referred to in Gremlin with `and_()`. |

console (groovy)

groovy

```
gremlin> g.V().and(
            outE('knows'),
            values('age').is(lt(30))).
              values('name')
==>marko
```

```
g.V().and(
   outE('knows'),
   values('age').is(lt(30))).
     values('name')
```

The `and()`-step can take an arbitrary number of traversals. All traversals must produce at least one output for the
original traverser to pass to the next step.

An [infix notation](http://en.wikipedia.org/wiki/Infix_notation) can be used as well.

console (groovy)

groovy

```
gremlin> g.V().where(outE('created').and().outE('knows')).values('name')
==>marko
```

```
g.V().where(outE('created').and().outE('knows')).values('name')
```

**Additional References**

[`and(Traversal…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#and(org.apache.tinkerpop.gremlin.process.traversal.Traversal...))

### Any Step

It is possible to filter list traversers using `any()`-step (**filter**). All items in the list will be tested against
the supplied predicate and if any of the items pass then the traverser is passed along the stream, otherwise it is
filtered. Empty lists, null traversers, and non-iterable traversers are filtered out as well.

|  |  |
| --- | --- |
| Python | The term `any` is a reserved word in Python, and therefore must be referred to in Gremlin with `any_()`. |

console (groovy)

groovy

```
gremlin> g.V().values('age').fold().any(gt(25)) //// (1)
==>[29,27,32,35]
```

```
g.V().values('age').fold().any(gt(25)) //1
```

1. Return the list of ages if anyone’s age is greater than 25.

**Additional References**

[`any(P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#any(org.apache.tinkerpop.gremlin.process.traversal.P)),
[`P`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/P.html)

### Coin Step

To randomly filter out a traverser, use the `coin()`-step (**filter**). The provided double argument biases the "coin toss."

console (groovy)

groovy

```
gremlin> g.V().coin(0.5)
==>v[1]
==>v[3]
==>v[5]
==>v[6]
gremlin> g.V().coin(0.0)
gremlin> g.V().coin(1.0)
==>v[1]
==>v[2]
==>v[3]
==>v[4]
==>v[5]
==>v[6]
```

```
g.V().coin(0.5)
g.V().coin(0.0)
g.V().coin(1.0)
```

**Additional References**

[`coin(double)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#coin(double))

### CyclicPath Step

![cyclicpath step](../images/cyclicpath-step.png)

Each traverser maintains its history through the traversal over the graph — i.e. its [path](06-steps/map-steps.md#path-data-structure).
If it is important that the traverser repeat its course, then `cyclic()`-path should be used (**filter**). The step
analyzes the path of the traverser thus far and if there are any repeats, the traverser is filtered out over the
traversal computation. If non-cyclic behavior is desired, see [`simplePath()`](06-steps/filter-steps.md#simplepath-step).

console (groovy)

groovy

```
gremlin> g.V(1).both().both()
==>v[1]
==>v[4]
==>v[6]
==>v[1]
==>v[5]
==>v[3]
==>v[1]
gremlin> g.V(1).both().both().cyclicPath()
==>v[1]
==>v[1]
==>v[1]
gremlin> g.V(1).both().both().cyclicPath().path()
==>[v[1],v[3],v[1]]
==>[v[1],v[2],v[1]]
==>[v[1],v[4],v[1]]
gremlin> g.V(1).both().both().cyclicPath().by('age').path() //// (1)
==>[v[1],v[2],v[1]]
==>[v[1],v[4],v[1]]
gremlin> g.V(1).as('a').out('created').as('b').
           in('created').as('c').
           cyclicPath().
           path()
==>[v[1],v[3],v[1]]
gremlin> g.V(1).as('a').out('created').as('b').
           in('created').as('c').
           cyclicPath().from('a').to('b').
           path()
```

```
g.V(1).both().both()
g.V(1).both().both().cyclicPath()
g.V(1).both().both().cyclicPath().path()
g.V(1).both().both().cyclicPath().by('age').path() //// (1)
g.V(1).as('a').out('created').as('b').
  in('created').as('c').
  cyclicPath().
  path()
g.V(1).as('a').out('created').as('b').
  in('created').as('c').
  cyclicPath().from('a').to('b').
  path()
```

1. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those traversers are filtered.

**Additional References**

[`cyclicPath()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#cyclicPath())

### Dedup Step

With `dedup()`-step (**filter**), repeatedly seen objects are removed from the traversal stream. Note that if a
traverser’s bulk is greater than 1, then it is set to 1 before being emitted.

console (groovy)

groovy

```
gremlin> g.V().values('lang')
==>java
==>java
gremlin> g.V().values('lang').dedup()
==>java
gremlin> g.V(1).repeat(bothE('created').dedup().otherV()).emit().path() //// (1)
==>[v[1],e[9][1-created->3],v[3]]
==>[v[1],e[9][1-created->3],v[3],e[11][4-created->3],v[4]]
==>[v[1],e[9][1-created->3],v[3],e[12][6-created->3],v[6]]
==>[v[1],e[9][1-created->3],v[3],e[11][4-created->3],v[4],e[10][4-created->5],v[5]]
gremlin> g.V().bothE().properties().dedup() //// (2)
==>p[weight->0.4]
==>p[weight->0.5]
==>p[weight->1.0]
==>p[weight->0.2]
```

```
g.V().values('lang')
g.V().values('lang').dedup()
g.V(1).repeat(bothE('created').dedup().otherV()).emit().path() //// (1)
g.V().bothE().properties().dedup() //2
```

1. Traverse all `created` edges, but don’t touch any edge twice.
2. Note that `Property` instances will compare on key and value, whereas a `VertexProperty` will also include its
   element as it is a first-class citizen.

If a by-step modulation is provided to `dedup()`, then the object is processed accordingly prior to determining if it
has been seen or not.

console (groovy)

groovy

```
gremlin> g.V().elementMap('name')
==>[id:1,label:person,name:marko]
==>[id:2,label:person,name:vadas]
==>[id:3,label:software,name:lop]
==>[id:4,label:person,name:josh]
==>[id:5,label:software,name:ripple]
==>[id:6,label:person,name:peter]
gremlin> g.V().dedup().by(label).values('name')
==>marko
==>lop
```

```
g.V().elementMap('name')
g.V().dedup().by(label).values('name')
```

If `dedup()` is provided an array of strings, then it will ensure that the de-duplication is not with respect to the
current traverser object, but to the path history of the traverser.

console (groovy)

groovy

```
gremlin> g.V().as('a').out('created').as('b').in('created').as('c').select('a','b','c')
==>[a:v[1],b:v[3],c:v[1]]
==>[a:v[1],b:v[3],c:v[4]]
==>[a:v[1],b:v[3],c:v[6]]
==>[a:v[4],b:v[5],c:v[4]]
==>[a:v[4],b:v[3],c:v[1]]
==>[a:v[4],b:v[3],c:v[4]]
==>[a:v[4],b:v[3],c:v[6]]
==>[a:v[6],b:v[3],c:v[1]]
==>[a:v[6],b:v[3],c:v[4]]
==>[a:v[6],b:v[3],c:v[6]]
gremlin> g.V().as('a').out('created').as('b').in('created').as('c').dedup('a','b').select('a','b','c') //// (1)
==>[a:v[1],b:v[3],c:v[1]]
==>[a:v[4],b:v[5],c:v[4]]
==>[a:v[4],b:v[3],c:v[1]]
==>[a:v[6],b:v[3],c:v[1]]
gremlin> g.V().as('a').both().as('b').both().as('c').
           dedup('a','b').by('age'). //// (2)
           select('a','b','c').by('name')
==>[a:marko,b:vadas,c:marko]
==>[a:marko,b:josh,c:ripple]
==>[a:vadas,b:marko,c:lop]
==>[a:josh,b:marko,c:lop]
```

```
g.V().as('a').out('created').as('b').in('created').as('c').select('a','b','c')
g.V().as('a').out('created').as('b').in('created').as('c').dedup('a','b').select('a','b','c') //// (1)
g.V().as('a').both().as('b').both().as('c').
  dedup('a','b').by('age'). //// (2)
  select('a','b','c').by('name')
```

1. If the current `a` and `b` combination has been seen previously, then filter the traverser.
2. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are filtered.

The `dedup()` step can work on many different types of objects. One object in particular can need a bit of explanation.
If you use `dedup()` on a `Path` object there is a chance that you may get some unexpected results. Consider the
following example which forcibly generates duplicate path results in the first traversal and in the second applies
`dedup()` to remove them:

console (groovy)

groovy

```
gremlin> g.V().union(out().path(), out().path())
==>[v[1],v[3]]
==>[v[1],v[2]]
==>[v[1],v[4]]
==>[v[1],v[3]]
==>[v[1],v[2]]
==>[v[1],v[4]]
==>[v[4],v[5]]
==>[v[4],v[3]]
==>[v[4],v[5]]
==>[v[4],v[3]]
==>[v[6],v[3]]
==>[v[6],v[3]]
gremlin> g.V().union(out().path(), out().path()).dedup()
==>[v[1],v[3]]
==>[v[1],v[2]]
==>[v[1],v[4]]
==>[v[4],v[5]]
==>[v[4],v[3]]
==>[v[6],v[3]]
```

```
g.V().union(out().path(), out().path())
g.V().union(out().path(), out().path()).dedup()
```

The `dedup()` step checks the equality of the paths by examining the equality of the objects on the `Path` (in this case
vertices), but also on any path labels. In the prior example, there weren’t any path labels so `dedup()` behaved as
expected. In the next example, note the difference in the results if a label is added for one `Path` but not the other:

console (groovy)

groovy

```
gremlin> g.V().union(out().as('x').path(), out().path())
==>[v[1],v[3]]
==>[v[1],v[2]]
==>[v[1],v[4]]
==>[v[1],v[3]]
==>[v[1],v[2]]
==>[v[1],v[4]]
==>[v[4],v[5]]
==>[v[4],v[3]]
==>[v[4],v[5]]
==>[v[4],v[3]]
==>[v[6],v[3]]
==>[v[6],v[3]]
gremlin> g.V().union(out().as('x').path(), out().path()).dedup()
==>[v[1],v[3]]
==>[v[1],v[2]]
==>[v[1],v[4]]
==>[v[1],v[3]]
==>[v[1],v[2]]
==>[v[1],v[4]]
==>[v[4],v[5]]
==>[v[4],v[3]]
==>[v[4],v[5]]
==>[v[4],v[3]]
==>[v[6],v[3]]
==>[v[6],v[3]]
```

```
g.V().union(out().as('x').path(), out().path())
g.V().union(out().as('x').path(), out().path()).dedup()
```

The prior example shows how `dedup()` does not have the same effect when a path label is in place. In this contrived
example the answer is simple: remove the `as('x')`. If in the real world, it is not possible to remove the label, the
workaround is to deconstruct the `Path` into a `List` to drop the label. In this way, `dedup()` is just comparing `List`
objects and the objects in the `Path`.

console (groovy)

groovy

```
gremlin> g.V().union(out().as('x').path(), out().path()).map(unfold().fold()).dedup()
==>[v[1],v[3]]
==>[v[1],v[2]]
==>[v[1],v[4]]
==>[v[4],v[5]]
==>[v[4],v[3]]
==>[v[6],v[3]]
```

```
g.V().union(out().as('x').path(), out().path()).map(unfold().fold()).dedup()
```

**Additional References**

[`dedup(Scope,String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#dedup(org.apache.tinkerpop.gremlin.process.traversal.Scope,java.lang.String...)),
[`dedup(String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#dedup(java.lang.String...)),
[`Scope`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Scope.html),
[`Semantics`](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#dedup-step)

### Filter Step

The `filter()` step maps the traverser from the current object to either `true` or `false` where the latter will not
pass the traverser to the next step in the process. Please see the [Steps Reference](index.md) for more
information.

**Additional References**

[`map(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#filter(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### Has Step

![has step](../images/has-step.png)

It is possible to filter vertices, edges, and vertex properties based on their properties using `has()`-step
(**filter**). There are numerous variations on `has()` including:

* `has(key,value)`: Remove the traverser if its element does not have the provided key/value property.
* `has(label, key, value)`: Remove the traverser if its element does not have the specified label and provided key/value property.
* `has(key,predicate)`: Remove the traverser if its element does not have a key value that satisfies the bi-predicate. For more information on predicates, please read [A Note on Predicates](../05a-traversal-concepts.md#a-note-on-predicates).
* `hasLabel(labels…​)`: Remove the traverser if its element does not have any of the labels.
* `hasId(ids…​)`: Remove the traverser if its element does not have any of the ids.
* `hasKey(keys…​)`: Remove the `Property` traverser if it does not match one of the provided keys.
* `hasValue(values…​)`: Remove the `Property` traverser if it does not match one of the provided values.
* `has(key)`: Remove the traverser if its element does not have a value for the key.
* `hasNot(key)`: Remove the traverser if its element has a value for the key.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person')
==>v[1]
==>v[2]
==>v[4]
==>v[6]
gremlin> g.V().hasLabel('person','name','marko')
==>v[1]
==>v[2]
==>v[4]
==>v[6]
gremlin> g.V().hasLabel('person').out().has('name',within('vadas','josh'))
==>v[2]
==>v[4]
gremlin> g.V().hasLabel('person').out().has('name',within('vadas','josh')).
               outE().hasLabel('created')
==>e[10][4-created->5]
==>e[11][4-created->3]
gremlin> g.V().has('age',inside(20,30)).values('age') //// (1)
==>29
==>27
gremlin> g.V().has('age',outside(20,30)).values('age') //// (2)
==>32
==>35
gremlin> g.V().has('name',within('josh','marko')).elementMap() //// (3)
==>[id:1,label:person,name:marko,age:29]
==>[id:4,label:person,name:josh,age:32]
gremlin> g.V().has('name',without('josh','marko')).elementMap() //// (4)
==>[id:2,label:person,name:vadas,age:27]
==>[id:3,label:software,name:lop,lang:java]
==>[id:5,label:software,name:ripple,lang:java]
==>[id:6,label:person,name:peter,age:35]
gremlin> g.V().has('name',not(within('josh','marko'))).elementMap() //// (5)
==>[id:2,label:person,name:vadas,age:27]
==>[id:3,label:software,name:lop,lang:java]
==>[id:5,label:software,name:ripple,lang:java]
==>[id:6,label:person,name:peter,age:35]
gremlin> g.V().properties().hasKey('age').value() //// (6)
==>29
==>27
==>32
==>35
gremlin> g.V().hasNot('age').values('name') //// (7)
==>lop
==>ripple
gremlin> g.V().has('person','name', startingWith('m')) //// (8)
==>v[1]
gremlin> g.V().has(null, 'vadas') //// (9)
gremlin> g.V().has('person', 'name', regex('r')).values('name') //// (10)
==>marko
==>peter
```

```
g.V().hasLabel('person')
g.V().hasLabel('person','name','marko')
g.V().hasLabel('person').out().has('name',within('vadas','josh'))
g.V().hasLabel('person').out().has('name',within('vadas','josh')).
      outE().hasLabel('created')
g.V().has('age',inside(20,30)).values('age') //// (1)
g.V().has('age',outside(20,30)).values('age') //// (2)
g.V().has('name',within('josh','marko')).elementMap() //// (3)
g.V().has('name',without('josh','marko')).elementMap() //// (4)
g.V().has('name',not(within('josh','marko'))).elementMap() //// (5)
g.V().properties().hasKey('age').value() //// (6)
g.V().hasNot('age').values('name') //// (7)
g.V().has('person','name', startingWith('m')) //// (8)
g.V().has(null, 'vadas') //// (9)
g.V().has('person', 'name', regex('r')).values('name') //10
```

1. Find all vertices whose ages are between 20 (exclusive) and 30 (exclusive). In other words, the age must be greater than 20 and less than 30.
2. Find all vertices whose ages are not between 20 (inclusive) and 30 (inclusive). In other words, the age must be less than 20 or greater than 30.
3. Find all vertices whose names are exact matches to any names in the collection `[josh,marko]`, display all
   the key,value pairs for those vertices.
4. Find all vertices whose names are not in the collection `[josh,marko]`, display all the key,value pairs for those vertices.
5. Same as the prior example save using `not` on `within` to yield `without`.
6. Find all age-properties and emit their value.
7. Find all vertices that do not have an age-property and emit their name.
8. Find all "person" vertices that have a name property that starts with the letter "m".
9. Property key is always stored as `String` and therefore an equality check with `null` will produce no result.
10. An example of using `has()` with regular expression predicate.

**Additional References**

[`has(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#has(java.lang.String)),
[`has(String,Object)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#has(java.lang.String,java.lang.Object)),
[`has(String,P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#has(java.lang.String,org.apache.tinkerpop.gremlin.process.traversal.P)),
[`has(String,String,Object)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#has(java.lang.String,java.lang.String,java.lang.Object)),
[`has(String,String,P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#has(java.lang.String,java.lang.String,org.apache.tinkerpop.gremlin.process.traversal.P)),
[`has(String,Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#has(java.lang.String,org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`has(T,Object)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#has(org.apache.tinkerpop.gremlin.structure.T,java.lang.Object)),
[`has(T,P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#has(org.apache.tinkerpop.gremlin.structure.T,org.apache.tinkerpop.gremlin.process.traversal.P)),
[`has(T,Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#has(org.apache.tinkerpop.gremlin.structure.T,org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`hasId(Object,Object…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#hasId(java.lang.Object,java.lang.Object...)),
[`hasId(P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#hasId(org.apache.tinkerpop.gremlin.process.traversal.P)),
[`hasKey(P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#hasKey(org.apache.tinkerpop.gremlin.process.traversal.P)),
[`hasKey(String,String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#hasKey(java.lang.String,java.lang.String...)),
[`hasLabel(P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#hasLabel(org.apache.tinkerpop.gremlin.process.traversal.P)),
[`hasLabel(String,String…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#hasLabel(java.lang.String,java.lang.String...)),
[`hasNot(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#hasNot(java.lang.String)),
[`hasValue(Object,Object…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#hasValue(java.lang.Object,java.lang.Object...)),
[`hasValue(P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#hasValue(org.apache.tinkerpop.gremlin.process.traversal.P)),
[`P`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/P.html),
[`TextP`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/TextP.html),
[`T`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/structure/T.html),
[Recipes - Anti-pattern](https://tinkerpop.apache.org/docs/3.8.0/recipes/#has-traversal)

### Is Step

It is possible to filter scalar values using `is()`-step (**filter**).

|  |  |
| --- | --- |
| Python | The term `is` is a reserved word in Python, and therefore must be referred to in Gremlin with `is_()`. |

console (groovy)

groovy

```
gremlin> g.V().values('age').is(32)
==>32
gremlin> g.V().values('age').is(lte(30))
==>29
==>27
gremlin> g.V().values('age').is(inside(30, 40))
==>32
==>35
gremlin> g.V().where(__.in('created').count().is(1)).values('name') //// (1)
==>ripple
gremlin> g.V().where(__.in('created').count().is(gte(2))).values('name') //// (2)
==>lop
gremlin> g.V().where(__.in('created').values('age').
                                    mean().is(inside(30d, 35d))).values('name') //// (3)
==>lop
==>ripple
```

```
g.V().values('age').is(32)
g.V().values('age').is(lte(30))
g.V().values('age').is(inside(30, 40))
g.V().where(__.in('created').count().is(1)).values('name') //// (1)
g.V().where(__.in('created').count().is(gte(2))).values('name') //// (2)
g.V().where(__.in('created').values('age').
                           mean().is(inside(30d, 35d))).values('name') //3
```

1. Find projects having exactly one contributor.
2. Find projects having two or more contributors.
3. Find projects whose contributors average age is between 30 and 35.

**Additional References**

[`is(Object)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#is(java.lang.Object)),
[`is(P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#is(org.apache.tinkerpop.gremlin.process.traversal.P)),
[`P`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/P.html)

### Limit Step

The `limit()`-step is analogous to [`range()`-step](06-steps/filter-steps.md#range-step) save that the lower end range is set to 0.

console (groovy)

groovy

```
gremlin> g.V().limit(2)
==>v[1]
==>v[2]
gremlin> g.V().range(0, 2)
==>v[1]
==>v[2]
```

```
g.V().limit(2)
g.V().range(0, 2)
```

The `limit()`-step can also be applied with `Scope.local`, in which case it operates on the incoming collection.
The examples below use the [The Crew](#the-crew-toy-graph) toy data set.

console (groovy)

groovy

```
gremlin> g.V().valueMap().select('location').limit(local,2) //// (1)
==>[san diego,santa cruz]
==>[centreville,dulles]
==>[bremen,baltimore]
==>[spremberg,kaiserslautern]
gremlin> g.V().valueMap().limit(local, 1) //// (2)
==>[name:[marko]]
==>[name:[stephen]]
==>[name:[matthias]]
==>[name:[daniel]]
==>[name:[gremlin]]
==>[name:[tinkergraph]]
gremlin> g.V().valueMap().select('location').limit(local, 1) //// (3)
==>[san diego]
==>[centreville]
==>[bremen]
==>[spremberg]
gremlin> g.V().valueMap().select('location').limit(local, 1).unfold() //// (4)
==>san diego
==>centreville
==>bremen
==>spremberg
```

```
g.V().valueMap().select('location').limit(local,2) //// (1)
g.V().valueMap().limit(local, 1) //// (2)
g.V().valueMap().select('location').limit(local, 1) //// (3)
g.V().valueMap().select('location').limit(local, 1).unfold() //4
```

1. `List<String>` for each vertex containing the first two locations.
2. `Map<String, Object>` for each vertex, but containing only the first property value.
3. `List<String>` for each vertex containing the first location.
4. `String` for each vertex containing the first location (use `unfold()` to extract single elements from singleton collections).

**Additional References**

[`limit(long)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#limit(long)),
[`limit(Scope,long)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#limit(org.apache.tinkerpop.gremlin.process.traversal.Scope,long))
[`Scope`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Scope.html)

### None Step

It is possible to filter list traversers using `none()`-step (**filter**). Every item in the list will be tested against
the supplied predicate and if none of the items pass then the traverser is passed along the stream, otherwise it is
filtered. Empty lists are passed along but null or non-iterable traversers are filtered out.

|  |  |
| --- | --- |
| Note | Prior to release 3.8.0, `none()` was a traversal discarding step primarily used by [`iterate()`](#iterate-step). This step has since been renamed to [`discard()`](06-steps/sideeffect-steps.md#discard-step) |

console (groovy)

groovy

```
gremlin> g.V().values('age').fold().none(gt(25)) //// (1)
```

```
g.V().values('age').fold().none(gt(25)) //1
```

1. Return the list of ages only if no one’s age is greater than 25.

**Additional References**

[`none(P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#none(org.apache.tinkerpop.gremlin.process.traversal.P)),
[`P`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/P.html)

### Not Step

The `not()`-step (**filter**) removes objects from the traversal stream when the traversal provided as an argument
returns an object.

|  |  |
| --- | --- |
| Groovy | The term `not` is a reserved word in Groovy, and when therefore used as part of an anonymous traversal must be referred to in Gremlin with the double underscore `__.not()`. |

|  |  |
| --- | --- |
| Python | The term `not` is a reserved word in Python, and therefore must be referred to in Gremlin with `not_()`. |

console (groovy)

groovy

```
gremlin> g.V().not(hasLabel('person')).elementMap()
==>[id:3,label:software,name:lop,lang:java]
==>[id:5,label:software,name:ripple,lang:java]
gremlin> g.V().hasLabel('person').
           not(out('created').count().is(gt(1))).values('name') //// (1)
==>marko
==>vadas
==>peter
```

```
g.V().not(hasLabel('person')).elementMap()
g.V().hasLabel('person').
  not(out('created').count().is(gt(1))).values('name')   //1
```

1. josh created two projects and vadas none

**Additional References**

[`not(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#not(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### Or Step

The `or()`-step ensures that at least one of the provided traversals yield a result (**filter**). Please see
[`and()`](06-steps/filter-steps.md#and-step) for and-semantics.

|  |  |
| --- | --- |
| Python | The term `or` is a reserved word in Python, and therefore must be referred to in Gremlin with `or_()`. |

console (groovy)

groovy

```
gremlin> g.V().or(
            __.outE('created'),
            __.inE('created').count().is(gt(1))).
              values('name')
==>marko
==>lop
==>josh
==>peter
```

```
g.V().or(
   __.outE('created'),
   __.inE('created').count().is(gt(1))).
     values('name')
```

The `or()`-step can take an arbitrary number of traversals. At least one of the traversals must produce at least one
output for the original traverser to pass to the next step.

An [infix notation](http://en.wikipedia.org/wiki/Infix_notation) can be used as well.

console (groovy)

groovy

```
gremlin> g.V().where(outE('created').or().outE('knows')).values('name')
==>marko
==>josh
==>peter
```

```
g.V().where(outE('created').or().outE('knows')).values('name')
```

**Additional References**

[`or(Traversal…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#or(org.apache.tinkerpop.gremlin.process.traversal.Traversal...))

### Range Step

As traversers propagate through the traversal, it is possible to only allow a certain number of them to pass through
with `range()`-step (**filter**). When the low-end of the range is not met, objects are continued to be iterated. When
within the low (inclusive) and high (exclusive) range, traversers are emitted. When above the high range, the traversal
breaks out of iteration. Finally, the use of `-1` on the high range will emit remaining traversers after the low range
begins.

console (groovy)

groovy

```
gremlin> g.V().range(0,3)
==>v[1]
==>v[2]
==>v[3]
gremlin> g.V().range(1,3)
==>v[2]
==>v[3]
gremlin> g.V().range(1, -1)
==>v[2]
==>v[3]
==>v[4]
==>v[5]
==>v[6]
gremlin> g.V().repeat(both()).times(1000000).emit().range(6,10)
==>v[1]
==>v[5]
==>v[3]
==>v[1]
```

```
g.V().range(0,3)
g.V().range(1,3)
g.V().range(1, -1)
g.V().repeat(both()).times(1000000).emit().range(6,10)
```

The `range()`-step can also be applied with `Scope.local`, in which case it operates on the incoming collection.
For example, it is possible to produce a `Map<String, String>` for each traversed path, but containing only the second
property value (the "b" step).

console (groovy)

groovy

```
gremlin> g.V().as('a').out().as('b').in().as('c').select('a','b','c').by('name').range(local,1,2)
==>[b:lop]
==>[b:lop]
==>[b:lop]
==>[b:vadas]
==>[b:josh]
==>[b:ripple]
==>[b:lop]
==>[b:lop]
==>[b:lop]
==>[b:lop]
==>[b:lop]
==>[b:lop]
```

```
g.V().as('a').out().as('b').in().as('c').select('a','b','c').by('name').range(local,1,2)
```

The next example uses the [The Crew](#the-crew-toy-graph) toy data set. It produces a `List<String>` containing the
second and third location for each vertex.

console (groovy)

groovy

```
gremlin> g.V().valueMap().select('location').range(local, 1, 3) //// (1)
==>[santa cruz,brussels]
==>[dulles,purcellville]
==>[baltimore,oakland]
==>[kaiserslautern,aachen]
gremlin> g.V().valueMap().select('location').range(local, 1, 2) //// (2)
==>[santa cruz]
==>[dulles]
==>[baltimore]
==>[kaiserslautern]
gremlin> g.V().valueMap().select('location').range(local, 1, 2).unfold() //// (3)
==>santa cruz
==>dulles
==>baltimore
==>kaiserslautern
```

```
g.V().valueMap().select('location').range(local, 1, 3) //// (1)
g.V().valueMap().select('location').range(local, 1, 2) //// (2)
g.V().valueMap().select('location').range(local, 1, 2).unfold() //3
```

1. `List<String>` for each vertex containing the second and third locations.
2. `List<String>` for each vertex containing the second location.
3. `String` for each vertex containing the second location (use `unfold()` to extract single elements from singleton collections).

**Additional References**

[`range(long,long)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#range(long,long)),
[`range(Scope,long,long)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#range(org.apache.tinkerpop.gremlin.process.traversal.Scope,long,long)),
[`Scope`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Scope.html)

### Sample Step

The `sample()`-step is useful for sampling some number of traversers previous in the traversal.

console (groovy)

groovy

```
gremlin> g.V().outE().sample(1).values('weight')
==>0.5
gremlin> g.V().outE().sample(1).by('weight').values('weight')
==>1.0
gremlin> g.V().outE().sample(2).by('weight').values('weight')
==>1.0
==>0.4
gremlin> g.V().both().sample(2).by('age') //// (1)
==>v[6]
==>v[4]
```

```
g.V().outE().sample(1).values('weight')
g.V().outE().sample(1).by('weight').values('weight')
g.V().outE().sample(2).by('weight').values('weight')
g.V().both().sample(2).by('age') //1
```

1. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are not considered when sampling.

One of the more interesting use cases for `sample()` is when it is used in conjunction with [`local()`](06-steps/branch-steps.md#local-step).
The combination of the two steps supports the execution of [random walks](http://en.wikipedia.org/wiki/Random_walk).
In the example below, the traversal starts are vertex 1 and selects one edge to traverse based on a probability
distribution generated by the weights of the edges. The output is always a single path as by selecting a single edge,
the traverser never splits and continues down a single path in the graph.

console (groovy)

groovy

```
gremlin> g.V(1).
           repeat(local(bothE().sample(1).by('weight').otherV())).
             times(5)
==>v[1]
gremlin> g.V(1).
           repeat(local(bothE().sample(1).by('weight').otherV())).
             times(5).
           path()
==>[v[1],e[9][1-created->3],v[3],e[9][1-created->3],v[1],e[9][1-created->3],v[3],e[11][4-created->3],v[4],e[10][4-created->5],v[5]]
gremlin> g.V(1).
           repeat(local(bothE().sample(1).by('weight').otherV())).
             times(10).
           path()
==>[v[1],e[9][1-created->3],v[3],e[11][4-created->3],v[4],e[11][4-created->3],v[3],e[11][4-created->3],v[4],e[10][4-created->5],v[5],e[10][4-created->5],v[4],e[8][1-knows->4],v[1],e[9][1-created->3],v[3],e[9][1-created->3],v[1],e[8][1-knows->4],v[4]]
```

```
g.V(1).
  repeat(local(bothE().sample(1).by('weight').otherV())).
    times(5)
g.V(1).
  repeat(local(bothE().sample(1).by('weight').otherV())).
    times(5).
  path()
g.V(1).
  repeat(local(bothE().sample(1).by('weight').otherV())).
    times(10).
  path()
```

As a clarification, note that in the above example `local()` is not strictly required as it only does the random walk
over a single vertex, but note what happens without it if multiple vertices are traversed:

console (groovy)

groovy

```
gremlin> g.V().repeat(bothE().sample(1).by('weight').otherV()).times(5).path()
==>[v[1],e[8][1-knows->4],v[4],e[8][1-knows->4],v[1],e[8][1-knows->4],v[4],e[8][1-knows->4],v[1],e[8][1-knows->4],v[4]]
```

```
g.V().repeat(bothE().sample(1).by('weight').otherV()).times(5).path()
```

The use of `local()` ensures that the traversal over `bothE()` occurs once per vertex traverser that passes through,
thus allowing one random walk per vertex.

console (groovy)

groovy

```
gremlin> g.V().repeat(local(bothE().sample(1).by('weight').otherV())).times(5).path()
==>[v[1],e[9][1-created->3],v[3],e[9][1-created->3],v[1],e[8][1-knows->4],v[4],e[8][1-knows->4],v[1],e[8][1-knows->4],v[4]]
==>[v[2],e[7][1-knows->2],v[1],e[7][1-knows->2],v[2],e[7][1-knows->2],v[1],e[9][1-created->3],v[3],e[12][6-created->3],v[6]]
==>[v[3],e[9][1-created->3],v[1],e[9][1-created->3],v[3],e[12][6-created->3],v[6],e[12][6-created->3],v[3],e[11][4-created->3],v[4]]
==>[v[4],e[8][1-knows->4],v[1],e[8][1-knows->4],v[4],e[8][1-knows->4],v[1],e[9][1-created->3],v[3],e[9][1-created->3],v[1]]
==>[v[5],e[10][4-created->5],v[4],e[10][4-created->5],v[5],e[10][4-created->5],v[4],e[11][4-created->3],v[3],e[11][4-created->3],v[4]]
==>[v[6],e[12][6-created->3],v[3],e[11][4-created->3],v[4],e[8][1-knows->4],v[1],e[7][1-knows->2],v[2],e[7][1-knows->2],v[1]]
```

```
g.V().repeat(local(bothE().sample(1).by('weight').otherV())).times(5).path()
```

So, while not strictly required, it is likely better to be explicit with the use of `local()` so that the proper intent
of the traversal is expressed.

**Additional References**

[`sample(int)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#sample(int)),
[`sample(Scope,int)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#sample(org.apache.tinkerpop.gremlin.process.traversal.Scope,int)),
[`Scope`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Scope.html)

### SimplePath Step

![simplepath step](../images/simplepath-step.png)

When it is important that a traverser not repeat its path through the graph, `simplePath()`-step should be used
(**filter**). The [path](06-steps/map-steps.md#path-data-structure) information of the traverser is analyzed and if the path has repeated
objects in it, the traverser is filtered. If cyclic behavior is desired, see [`cyclicPath()`](06-steps/filter-steps.md#cyclicpath-step).

console (groovy)

groovy

```
gremlin> g.V(1).both().both()
==>v[1]
==>v[4]
==>v[6]
==>v[1]
==>v[5]
==>v[3]
==>v[1]
gremlin> g.V(1).both().both().simplePath()
==>v[4]
==>v[6]
==>v[5]
==>v[3]
gremlin> g.V(1).both().both().simplePath().path()
==>[v[1],v[3],v[4]]
==>[v[1],v[3],v[6]]
==>[v[1],v[4],v[5]]
==>[v[1],v[4],v[3]]
gremlin> g.V(1).both().both().simplePath().by('age') //// (1)
gremlin> g.V().out().as('a').out().as('b').out().as('c').
           simplePath().by(label).
           path()
gremlin> g.V().out().as('a').out().as('b').out().as('c').
           simplePath().
             by(label).
             from('b').
             to('c').
           path().
             by('name')
```

```
g.V(1).both().both()
g.V(1).both().both().simplePath()
g.V(1).both().both().simplePath().path()
g.V(1).both().both().simplePath().by('age') //// (1)
g.V().out().as('a').out().as('b').out().as('c').
  simplePath().by(label).
  path()
g.V().out().as('a').out().as('b').out().as('c').
  simplePath().
    by(label).
    from('b').
    to('c').
  path().
    by('name')
```

1. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are filtered.

By using the `from()` and `to()` modulators traversers can ensure that only certain sections of the path are acyclic.

console (groovy)

groovy

```
gremlin> g.addV().property(id, 'A').as('a').
           addV().property(id, 'B').as('b').
           addV().property(id, 'C').as('c').
           addV().property(id, 'D').as('d').
           addE('link').from('a').to('b').
           addE('link').from('b').to('c').
           addE('link').from('c').to('d').iterate()
gremlin> g.V('A').repeat(both().simplePath()).times(3).path() //// (1)
==>[v[A],v[B],v[C],v[D]]
gremlin> g.V('D').repeat(both().simplePath()).times(3).path() //// (2)
==>[v[D],v[C],v[B],v[A]]
gremlin> g.V('A').as('a').
           repeat(both().simplePath().from('a')).times(3).as('b').
           repeat(both().simplePath().from('b')).times(3).path() //// (3)
==>[v[A],v[B],v[C],v[D],v[C],v[B],v[A]]
```

```
g.addV().property(id, 'A').as('a').
  addV().property(id, 'B').as('b').
  addV().property(id, 'C').as('c').
  addV().property(id, 'D').as('d').
  addE('link').from('a').to('b').
  addE('link').from('b').to('c').
  addE('link').from('c').to('d').iterate()
g.V('A').repeat(both().simplePath()).times(3).path() //// (1)
g.V('D').repeat(both().simplePath()).times(3).path() //// (2)
g.V('A').as('a').
  repeat(both().simplePath().from('a')).times(3).as('b').
  repeat(both().simplePath().from('b')).times(3).path()  //3
```

1. Traverse all acyclic 3-hop paths starting from vertex `A`
2. Traverse all acyclic 3-hop paths starting from vertex `D`
3. Traverse all acyclic 3-hop paths starting from vertex `A` and from there again all 3-hop paths. The second path may
   cross the vertices from the first path.

**Additional References**

[`simplePath()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#simplePath())

### Skip Step

The `skip()`-step is analogous to [`range()`-step](06-steps/filter-steps.md#range-step) save that the higher end range is set to -1.

console (groovy)

groovy

```
gremlin> g.V().values('age').order()
==>27
==>29
==>32
==>35
gremlin> g.V().values('age').order().skip(2)
==>32
==>35
gremlin> g.V().values('age').order().range(2, -1)
==>32
==>35
```

```
g.V().values('age').order()
g.V().values('age').order().skip(2)
g.V().values('age').order().range(2, -1)
```

The `skip()`-step can also be applied with `Scope.local`, in which case it operates on the incoming collection.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person').filter(outE('created')).as('p'). //// (1)
           map(out('created').values('name').fold()).
           project('person','primary','other').
             by(select('p').by('name')).
             by(limit(local, 1).unfold()). //// (2)
             by(skip(local, 1)) //// (3)
==>[person:marko,primary:lop,other:[]]
==>[person:josh,primary:ripple,other:[lop]]
==>[person:peter,primary:lop,other:[]]
```

```
g.V().hasLabel('person').filter(outE('created')).as('p'). //// (1)
  map(out('created').values('name').fold()).
  project('person','primary','other').
    by(select('p').by('name')).
    by(limit(local, 1).unfold()). //// (2)
    by(skip(local, 1)) //3
```

1. For each person who created something…​
2. …​select the first project (random order) as `primary` and…​
3. …​select all other projects as `other`.

**Additional References**

[`skip(long)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#skip(long)),
[`skip(Scope,long)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#skip(org.apache.tinkerpop.gremlin.process.traversal.Scope,long)),
[`Scope`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Scope.html)

### Tail Step

![tail step](../images/tail-step.png)

The `tail()`-step is analogous to [`limit()`](06-steps/filter-steps.md#limit-step)-step, except that it emits the last `n`-objects instead of
the first `n`-objects.

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
gremlin> g.V().values('name').order().tail() //// (1)
==>vadas
gremlin> g.V().values('name').order().tail(1) //// (2)
==>vadas
gremlin> g.V().values('name').order().tail(3) //// (3)
==>peter
==>ripple
==>vadas
```

```
g.V().values('name').order()
g.V().values('name').order().tail() //// (1)
g.V().values('name').order().tail(1) //// (2)
g.V().values('name').order().tail(3) //3
```

1. Last name (alphabetically).
2. Same as statement 1.
3. Last three names.

The `tail()`-step can also be applied with `Scope.local`, in which case it operates on the incoming collection.

console (groovy)

groovy

```
gremlin> g.V().as('a').out().as('a').out().as('a').select('a').by(tail(local)).values('name') //// (1)
==>ripple
==>lop
gremlin> g.V().as('a').out().as('a').out().as('a').select('a').by(unfold().values('name').fold()).tail(local) //// (2)
==>[ripple]
==>[lop]
gremlin> g.V().as('a').out().as('a').out().as('a').select('a').by(unfold().values('name').fold()).tail(local, 1) //// (3)
==>[ripple]
==>[lop]
gremlin> g.V().as('a').out().as('a').out().as('a').select('a').by(unfold().values('name').fold()).tail(local, 1).unfold() //// (4)
==>ripple
==>lop
gremlin> g.V().as('a').out().as('a').out().as('a').select('a').by(unfold().values('name').fold()).tail(local, 2) //// (5)
==>[ripple]
==>[lop]
gremlin> g.V().elementMap().tail(local) //// (6)
==>[age:29]
==>[age:27]
==>[lang:java]
==>[age:32]
==>[lang:java]
==>[age:35]
```

```
g.V().as('a').out().as('a').out().as('a').select('a').by(tail(local)).values('name') //// (1)
g.V().as('a').out().as('a').out().as('a').select('a').by(unfold().values('name').fold()).tail(local) //// (2)
g.V().as('a').out().as('a').out().as('a').select('a').by(unfold().values('name').fold()).tail(local, 1) //// (3)
g.V().as('a').out().as('a').out().as('a').select('a').by(unfold().values('name').fold()).tail(local, 1).unfold() //// (4)
g.V().as('a').out().as('a').out().as('a').select('a').by(unfold().values('name').fold()).tail(local, 2) //// (5)
g.V().elementMap().tail(local) //6
```

1. Only the most recent name from the "a" step (`List<Vertex>` becomes `Vertex`).
2. `List<String>` for each path containing the last name from the 'a' step.
3. Same as statement 2 (`List<String>` for each path containing the last name).
4. `String` for each path containing the last name (use `unfold()` to extract single elements from singleton collections).
5. `List<String>` for each path containing the last two names from the 'a' step.
6. `Map<String, Object>` for each vertex, containing only the last property value.

**Additional References**

[`tail()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#tail()),
[`tail(long)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#tail(long)),
[`tail(Scope)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#tail(org.apache.tinkerpop.gremlin.process.traversal.Scope))
[`tail(Scope,long)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#tail(org.apache.tinkerpop.gremlin.process.traversal.Scope,long))
[`Scope`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Scope.html)

### TimeLimit Step

In many situations, a graph traversal is not about getting an exact answer as its about getting a relative ranking.
A classic example is [recommendation](http://en.wikipedia.org/wiki/Recommender_system). What is desired is a
relative ranking of vertices, not their absolute rank. Next, it may be desirable to have the traversal execute for
no more than 2 milliseconds. In such situations, `timeLimit()`-step (**filter**) can be used.

![timelimit step](../images/timelimit-step.png)

|  |  |
| --- | --- |
| Note | The method `clock(int runs, Closure code)` is a utility preloaded in the [Gremlin Console](#gremlin-console) that can be used to time execution of a body of code. |

console (groovy)

groovy

```
gremlin> g.V().repeat(both().groupCount('m')).times(16).cap('m').order(local).by(values,desc).next()
==>v[1]=2744208
==>v[3]=2744208
==>v[4]=2744208
==>v[2]=1136688
==>v[5]=1136688
==>v[6]=1136688
gremlin> clock(1) {g.V().repeat(both().groupCount('m')).times(16).cap('m').order(local).by(values,desc).next()}
==>0.440584
gremlin> g.V().repeat(timeLimit(2).both().groupCount('m')).times(16).cap('m').order(local).by(values,desc).next()
==>v[1]=2744208
==>v[3]=2744208
==>v[4]=2744208
==>v[2]=1136688
==>v[5]=1136688
==>v[6]=1136688
gremlin> clock(1) {g.V().repeat(timeLimit(2).both().groupCount('m')).times(16).cap('m').order(local).by(values,desc).next()}
==>0.36966699999999997
```

```
g.V().repeat(both().groupCount('m')).times(16).cap('m').order(local).by(values,desc).next()
clock(1) {g.V().repeat(both().groupCount('m')).times(16).cap('m').order(local).by(values,desc).next()}
g.V().repeat(timeLimit(2).both().groupCount('m')).times(16).cap('m').order(local).by(values,desc).next()
clock(1) {g.V().repeat(timeLimit(2).both().groupCount('m')).times(16).cap('m').order(local).by(values,desc).next()}
```

In essence, the relative order is respected, even through the number of traversers at each vertex is not. The primary
benefit being that the calculation is guaranteed to complete at the specified time limit (in milliseconds). Finally,
note that the internal clock of `timeLimit()`-step starts when the first traverser enters it. When the time limit is
reached, any `next()` evaluation of the step will yield a `NoSuchElementException` and any `hasNext()` evaluation will
yield `false`.

**Additional References**

[`timeLimit(long)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#timeLimit(long))

### Where Step

The `where()`-step filters the current object based on either the object itself (`Scope.local`) or the path history
of the object (`Scope.global`) (**filter**). This step is typically used in conjunction with either
[`match()`](06-steps/branch-steps.md#match-step)-step or [`select()`](06-steps/map-steps.md#select-step)-step, but can be used in isolation.

console (groovy)

groovy

```
gremlin> g.V(1).as('a').out('created').in('created').where(neq('a')) //// (1)
==>v[4]
==>v[6]
gremlin> g.withSideEffect('a',['josh','peter']).V(1).out('created').in('created').values('name').where(within('a')) //// (2)
==>josh
==>peter
gremlin> g.V(1).out('created').in('created').where(out('created').count().is(gt(1))).values('name') //// (3)
==>josh
```

```
g.V(1).as('a').out('created').in('created').where(neq('a')) //// (1)
g.withSideEffect('a',['josh','peter']).V(1).out('created').in('created').values('name').where(within('a')) //// (2)
g.V(1).out('created').in('created').where(out('created').count().is(gt(1))).values('name') //3
```

1. Who are marko’s collaborators, where marko can not be his own collaborator? (predicate)
2. Of the co-creators of marko, only keep those whose name is josh or peter. (using a sideEffect)
3. Which of marko’s collaborators have worked on more than 1 project? (using a traversal)

|  |  |
| --- | --- |
| Important | Please see [`match().where()`](06-steps/branch-steps.md#using-where-with-match) and [`select().where()`](#using-where-with-select) for how `where()` can be used in conjunction with `Map<String,Object>` projecting steps — i.e. `Scope.local`. |

A few more examples of filtering an arbitrary object based on a anonymous traversal is provided below.

console (groovy)

groovy

```
gremlin> g.V().where(out('created')).values('name') //// (1)
==>marko
==>josh
==>peter
gremlin> g.V().out('knows').where(out('created')).values('name') //// (2)
==>josh
gremlin> g.V().where(out('created').count().is(gte(2))).values('name') //// (3)
==>josh
gremlin> g.V().where(out('knows').where(out('created'))).values('name') //// (4)
==>marko
gremlin> g.V().where(__.not(out('created'))).where(__.in('knows')).values('name') //// (5)
==>vadas
gremlin> g.V().where(__.not(out('created')).and().in('knows')).values('name') //// (6)
==>vadas
gremlin> g.V().as('a').out('knows').as('b').
           where('a',gt('b')).
             by('age').
           select('a','b').
             by('name') //// (7)
==>[a:marko,b:vadas]
gremlin> g.V().as('a').out('knows').as('b').
           where('a',gt('b').or(eq('b'))).
             by('age').
             by('age').
             by(__.in('knows').values('age')).
           select('a','b').
             by('name') //// (8)
==>[a:marko,b:vadas]
==>[a:marko,b:josh]
gremlin> g.V().as('a').both().both().as('b').
           where('a',eq('b')).by('age') //// (9)
==>v[1]
==>v[1]
==>v[1]
==>v[2]
==>v[4]
==>v[4]
==>v[4]
==>v[6]
```

```
g.V().where(out('created')).values('name') //// (1)
g.V().out('knows').where(out('created')).values('name') //// (2)
g.V().where(out('created').count().is(gte(2))).values('name') //// (3)
g.V().where(out('knows').where(out('created'))).values('name') //// (4)
g.V().where(__.not(out('created'))).where(__.in('knows')).values('name') //// (5)
g.V().where(__.not(out('created')).and().in('knows')).values('name') //// (6)
g.V().as('a').out('knows').as('b').
  where('a',gt('b')).
    by('age').
  select('a','b').
    by('name') //// (7)
g.V().as('a').out('knows').as('b').
  where('a',gt('b').or(eq('b'))).
    by('age').
    by('age').
    by(__.in('knows').values('age')).
  select('a','b').
    by('name') //// (8)
g.V().as('a').both().both().as('b').
  where('a',eq('b')).by('age') //9
```

1. What are the names of the people who have created a project?
2. What are the names of the people that are known by someone one and have created a project?
3. What are the names of the people how have created two or more projects?
4. What are the names of the people who know someone that has created a project? (This only works in OLTP — see the `WARNING` below)
5. What are the names of the people who have not created anything, but are known by someone?
6. The concatenation of `where()`-steps is the same as a single `where()`-step with an and’d clause.
7. Marko knows josh and vadas but is only older than vadas.
8. Marko is younger than josh, but josh knows someone equal in age to marko (which is marko).
9. The "age" property is not [productive](06-steps/modulator-steps.md#by-step) for all vertices and therefore those values are filtered.

|  |  |
| --- | --- |
| Warning | The anonymous traversal of `where()` processes the current object "locally". In OLAP, where the atomic unit of computing is the vertex and its local "star graph," it is important that the anonymous traversal does not leave the confines of the vertex’s star graph. In other words, it can not traverse to an adjacent vertex’s properties or edges. |

**Additional References**

[`where(P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#where(org.apache.tinkerpop.gremlin.process.traversal.P)),
[`where(String,P)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#where(java.lang.String,org.apache.tinkerpop.gremlin.process.traversal.P)),
[`where(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#where(org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`P`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/P.html)

