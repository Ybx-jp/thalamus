### Branch Step

The `branch()` step splits the traverser to all the child traversals provided to it. Please see the
[Steps Reference](index.md) for more information, but also consider that `branch()` is the basis for more
robust steps like [choose()](06-steps/branch-steps.md#choose-step) and [union()](06-steps/branch-steps.md#union-step).

**Additional References**

[`map(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#branch(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### Choose Step

![choose step](../images/choose-step.png)

The `choose()`-step (**branch**) routes the current traverser to a particular traversal branch option. With `choose()`,
it is possible to implement two different types of semantics: if-then-else (conditional branching) and switch
(value-based selection).

#### If-Then-Else

The if-the-else semantics of `choose()` evaluate a predicate traversal and route the traverser to either the "true"
branch or the "false" branch based on the result.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person').
               choose(values('age').is(lte(30)),
                      __.in(),
                      __.out()).values('name') //// (1)
==>marko
==>ripple
==>lop
==>lop
gremlin> g.V().hasLabel('person').
               choose(outE('knows').count().is(gt(0)),
                      __.out('knows'),
                      __.identity()).values('name') //// (2)
==>vadas
==>josh
==>vadas
==>josh
==>peter
```

```
g.V().hasLabel('person').
      choose(values('age').is(lte(30)),
             __.in(),
             __.out()).values('name') //// (1)
g.V().hasLabel('person').
      choose(outE('knows').count().is(gt(0)),
             __.out('knows'),
             __.identity()).values('name') //2
```

1. If the person’s age is less than or equal to 30, then traverse to incoming vertices, else traverse to outgoing
   vertices.
2. If the person has outgoing "knows" edges, then traverse to those known vertices, else return the person vertex
   itself.

If the "false"-branch is not provided, then simple if-then-semantics are implemented, where traversers that don’t match
the condition are passed through unchanged.

console (groovy)

groovy

```
gremlin> g.V().choose(hasLabel('person'), out('created')).values('name') //// (1)
==>lop
==>lop
==>ripple
==>lop
==>ripple
==>lop
gremlin> g.V().choose(hasLabel('person'), out('created'), identity()).values('name') //// (2)
==>lop
==>lop
==>ripple
==>lop
==>ripple
==>lop
```

```
g.V().choose(hasLabel('person'), out('created')).values('name') //// (1)
g.V().choose(hasLabel('person'), out('created'), identity()).values('name') //2
```

1. If the vertex is a person, emit the vertices they created, else emit the vertex.
2. if-the-else with an `identity()` on the false-branch is equivalent to if-then with no false-branch.

#### Switch

The switch semantics of `choose()` use the result of a traversal as a key to select from multiple traversal options.
This allows for more complex branching logic beyond simple true/false conditions.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person').
               choose(values('name')).
                 option('marko', values('age')).
                 option('josh', values('name')).
                 option('vadas', elementMap()).
                 option('peter', label()) //// (1)
==>29
==>[id:2,label:person,name:vadas,age:27]
==>josh
==>person
gremlin> g.V().hasLabel('person').
               choose(values('age')).
                 option(27, __.in().values('name')).
                 option(32, __.out().values('name')) //// (2)
==>v[1]
==>marko
==>ripple
==>lop
==>v[6]
```

```
g.V().hasLabel('person').
      choose(values('name')).
        option('marko', values('age')).
        option('josh', values('name')).
        option('vadas', elementMap()).
        option('peter', label()) //// (1)
g.V().hasLabel('person').
      choose(values('age')).
        option(27, __.in().values('name')).
        option(32, __.out().values('name')) //2
```

1. Use the person’s name to select which property or operation to return.
2. Use the person’s age value to select which traversal to apply, noting that traversers matching no age values simply
   pass through.

The `choose()`-step can use predicates with options to match ranges of values or other conditions.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person').
               choose(values('age')).
                 option(P.between(26, 30), constant('younger')).
                 option(P.gt(30), constant('older')).
                 option(Pick.none, constant('unknown')) //// (1)
==>younger
==>younger
==>older
==>older
```

```
g.V().hasLabel('person').
      choose(values('age')).
        option(P.between(26, 30), constant('younger')).
        option(P.gt(30), constant('older')).
        option(Pick.none, constant('unknown')) //1
```

1. If the person’s age is between 26 and 30, classify them as 'younger', if greater than 30, classify as 'older',
   otherwise 'unknown'.

The token `T.label` can be used as shorthand for `__.label()` when selecting options based on element labels.

console (groovy)

groovy

```
gremlin> g.V().choose(T.label).
                 option('person', out('created')).
                 option('software', in('created')).
                 values('name') //// (1)
==>lop
==>marko
==>josh
==>peter
==>ripple
==>lop
==>josh
==>lop
```

```
g.V().choose(T.label).
        option('person', out('created')).
        option('software', in('created')).
        values('name') //1
```

1. For person vertices, traverse to the software they created; for software vertices, traverse to the people who
   created them.

The `Pick` enum was introduced in an example earlier to handle non-matching scenarios. The following `Pick` options may
be used with `choose()`:

* `Pick.none` - Matches when no other options match
* `Pick.unproductive` - Matches when the choice in `choose()` produces no results

console (groovy)

groovy

```
gremlin> g.V().choose(values('age')).
                 option(P.between(26, 30), values('name')).
                 option(Pick.none, values('name')).
                 option(Pick.unproductive, label()) //// (1)
==>marko
==>vadas
==>software
==>josh
==>software
==>peter
gremlin> g.V().hasLabel('person').
               choose(out('knows').count()).
                 option(0, constant('noFriends')).
                 option(Pick.none, constant('hasFriends')) //// (2)
==>hasFriends
==>noFriends
==>noFriends
==>noFriends
gremlin> g.V().choose(values('age')).
                 option(27, __.in().values('name')).
                 option(32, __.out().values('name')).
                 option(Pick.unproductive, discard()).
                 option(Pick.none, discard()) //// (3)
==>marko
==>ripple
==>lop
```

```
g.V().choose(values('age')).
        option(P.between(26, 30), values('name')).
        option(Pick.none, values('name')).
        option(Pick.unproductive, label()) //// (1)
g.V().hasLabel('person').
      choose(out('knows').count()).
        option(0, constant('noFriends')).
        option(Pick.none, constant('hasFriends')) //// (2)
g.V().choose(values('age')).
        option(27, __.in().values('name')).
        option(32, __.out().values('name')).
        option(Pick.unproductive, discard()).
        option(Pick.none, discard()) //3
```

1. For vertices with age between 26-30, return the name. For vertices with age outside that range, return the name.
   For vertices without an age property, return the label.
2. For people with no outgoing "knows" edges, return 'noFriends', otherwise return 'hasFriends'.
3. Use `none()` step in combination with `Pick.none` and `Pick.unproductive` to filter unproductive traversals and
   unmatched values.

|  |  |
| --- | --- |
| Important | It is important to think of `choose()` as a branching step and not a filter. The if-then semantics can intuitively lead to thinking the latter, where no match would mean to remove the traverser from the stream. As shown in the examples, this is not what happens. |

The `choose()`-step can be used within a `map()` step to apply the branching logic to each element in a collection.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person').
               map(choose(values('age')).
                     option(P.between(26, 30), values('name').fold()).
                     option(Pick.none, values('name').fold())) //// (1)
==>[marko]
==>[vadas]
==>[josh]
==>[peter]
```

```
g.V().hasLabel('person').
      map(choose(values('age')).
            option(P.between(26, 30), values('name').fold()).
            option(Pick.none, values('name').fold())) //1
```

1. For each person, create a list containing their name, using the same traversal regardless of age.

**Additional References**

[`choose(Function)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#choose(java.util.function.Function)),
[`choose(Predicate,Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#choose(java.util.function.Predicate,org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`choose(Predicate,Traversal,Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#choose(java.util.function.Predicate,org.apache.tinkerpop.gremlin.process.traversal.Traversal,org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`choose(Traversal,Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#choose(org.apache.tinkerpop.gremlin.process.traversal.Traversal,org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`choose(Traversal,Traversal,Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#choose(org.apache.tinkerpop.gremlin.process.traversal.Traversal,org.apache.tinkerpop.gremlin.process.traversal.Traversal,org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`choose(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#choose(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### Coalesce Step

The `coalesce()`-step evaluates the provided traversals in order and returns the first traversal that emits at
least one element.

console (groovy)

groovy

```
gremlin> g.V(1).coalesce(outE('knows'), outE('created')).inV().path().by('name').by(label)
==>[marko,knows,vadas]
==>[marko,knows,josh]
gremlin> g.V(1).coalesce(outE('created'), outE('knows')).inV().path().by('name').by(label)
==>[marko,created,lop]
gremlin> g.V(1).property('nickname', 'okram')
==>v[1]
gremlin> g.V().hasLabel('person').coalesce(values('nickname'), values('name'))
==>okram
==>vadas
==>josh
==>peter
```

```
g.V(1).coalesce(outE('knows'), outE('created')).inV().path().by('name').by(label)
g.V(1).coalesce(outE('created'), outE('knows')).inV().path().by('name').by(label)
g.V(1).property('nickname', 'okram')
g.V().hasLabel('person').coalesce(values('nickname'), values('name'))
```

Be aware that the current traverser behavior where the traverser appears to be unaffected by state modifying steps or
account as a single bulk to side effects inside the `coalesce()` traversal is subject to change. The following are
examples of some traversals on the "modern" graph whose output may change:

```
gremlin> g.V(1, 1).barrier().coalesce(aggregate("x"), groupCount("x")).cap("x")
==>[v[1]]

gremlin> g.withSack(1.0f).V(1).barrier().coalesce(sack(mult).by("age"), constant(2)).sack()
==>1.0
```

**Additional References**

[`coalesce(Traversal…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#coalesce(org.apache.tinkerpop.gremlin.process.traversal.Traversal...))

### Local Step

![local step](../images/local-step.png)

A `GraphTraversal` operates on a continuous stream of objects. In many situations, it is important to operate on a
single element within that stream. To do such object-local traversal computations, `local()`-step exists (**branch**).
Note that the examples below use the [The Crew](#the-crew-toy-graph) toy data set.

console (groovy)

groovy

```
gremlin> g.V().as('person').
               properties('location').order().by('startTime',asc).limit(2).value().as('location').
               select('person','location').by('name').by() //// (1)
==>[person:daniel,location:spremberg]
==>[person:stephen,location:centreville]
gremlin> g.V().as('person').
               local(properties('location').order().by('startTime',asc).limit(2)).value().as('location').
               select('person','location').by('name').by() //// (2)
==>[person:marko,location:san diego]
==>[person:marko,location:santa cruz]
==>[person:stephen,location:centreville]
==>[person:stephen,location:dulles]
==>[person:matthias,location:bremen]
==>[person:matthias,location:baltimore]
==>[person:daniel,location:spremberg]
==>[person:daniel,location:kaiserslautern]
```

```
g.V().as('person').
      properties('location').order().by('startTime',asc).limit(2).value().as('location').
      select('person','location').by('name').by() //// (1)
g.V().as('person').
      local(properties('location').order().by('startTime',asc).limit(2)).value().as('location').
      select('person','location').by('name').by() //2
```

1. Get the first two people and their respective location according to the most historic location start time.
2. For every person, get their two most historic locations.

The two traversals above look nearly identical save the inclusion of `local()` which wraps a section of the traversal
in an object-local traversal. As such, the `order().by()` and the `limit()` refer to a particular object, not to the
stream as a whole.

Local Step is quite similar in functionality to Flat Map Step where it can often be confused.
The primary distinction between these steps is that while `local()` preserves the path history of traversers as they
pass through its child traversal, `flatMap()` does not. As another example consider:

console (groovy)

groovy

```
gremlin> g.V().local(outE().inV()).path()
==>[v[1],e[9][1-created->3],v[3]]
==>[v[1],e[7][1-knows->2],v[2]]
==>[v[1],e[8][1-knows->4],v[4]]
==>[v[4],e[10][4-created->5],v[5]]
==>[v[4],e[11][4-created->3],v[3]]
==>[v[6],e[12][6-created->3],v[3]]
gremlin> g.V().flatMap(outE().inV()).path()
==>[v[1],v[3]]
==>[v[1],v[2]]
==>[v[1],v[4]]
==>[v[4],v[5]]
==>[v[4],v[3]]
==>[v[6],v[3]]
```

```
g.V().local(outE().inV()).path()
g.V().flatMap(outE().inV()).path()
```

|  |  |
| --- | --- |
| Warning | The anonymous traversal of `local()` processes the current object "locally." In OLAP, where the atomic unit of computing is the vertex and its local "star graph," it is important that the anonymous traversal does not leave the confines of the vertex’s star graph. In other words, it can not traverse to an adjacent vertex’s properties or edges. |

**Additional References**

[`local(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#local(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### Match Step

The `match()`-step (**map**) provides a more [declarative](http://en.wikipedia.org/wiki/Declarative_programming)
form of graph querying based on the notion of [pattern matching](http://en.wikipedia.org/wiki/Pattern_matching).
With `match()`, the user provides a collection of "traversal fragments," called patterns, that have variables defined
that must hold true throughout the duration of the `match()`. When a traverser is in `match()`, a registered
`MatchAlgorithm` analyzes the current state of the traverser (i.e. its history based on its
[path data](06-steps/map-steps.md#path-data-structure)), the runtime statistics of the traversal patterns, and returns a traversal-pattern
that the traverser should try next. The default `MatchAlgorithm` provided is called `CountMatchAlgorithm` and it
dynamically revises the pattern execution plan by sorting the patterns according to their filtering capabilities
(i.e. largest set reduction patterns execute first). For very large graphs, where the developer is uncertain of the
statistics of the graph (e.g. how many `knows`-edges vs. `worksFor`-edges exist in the graph), it is advantageous to
use `match()`, as an optimal plan will be determined automatically. Furthermore, some queries are much easier to
express via `match()` than with single-path traversals.

```
"Who created a project named 'lop' that was also created by someone who is 29 years old? Return the two creators."
```

![match step](../images/match-step.png)

console (groovy)

groovy

```
gremlin> g.V().match(
                 __.as('a').out('created').as('b'),
                 __.as('b').has('name', 'lop'),
                 __.as('b').in('created').as('c'),
                 __.as('c').has('age', 29)).
               select('a','c').by('name')
==>[a:marko,c:marko]
==>[a:josh,c:marko]
==>[a:peter,c:marko]
```

```
g.V().match(
        __.as('a').out('created').as('b'),
        __.as('b').has('name', 'lop'),
        __.as('b').in('created').as('c'),
        __.as('c').has('age', 29)).
      select('a','c').by('name')
```

Note that the above can also be more concisely written as below which demonstrates that standard inner-traversals can
be arbitrarily defined.

console (groovy)

groovy

```
gremlin> g.V().match(
                 __.as('a').out('created').has('name', 'lop').as('b'),
                 __.as('b').in('created').has('age', 29).as('c')).
               select('a','c').by('name')
==>[a:marko,c:marko]
==>[a:josh,c:marko]
==>[a:peter,c:marko]
```

```
g.V().match(
        __.as('a').out('created').has('name', 'lop').as('b'),
        __.as('b').in('created').has('age', 29).as('c')).
      select('a','c').by('name')
```

In order to improve readability, `as()`-steps can be given meaningful labels which better reflect your domain. The
previous query can thus be written in a more expressive way as shown below.

console (groovy)

groovy

```
gremlin> g.V().match(
                 __.as('creators').out('created').has('name', 'lop').as('projects'), //// (1)
                 __.as('projects').in('created').has('age', 29).as('cocreators')). //// (2)
               select('creators','cocreators').by('name') //// (3)
==>[creators:marko,cocreators:marko]
==>[creators:josh,cocreators:marko]
==>[creators:peter,cocreators:marko]
```

```
g.V().match(
        __.as('creators').out('created').has('name', 'lop').as('projects'), //// (1)
        __.as('projects').in('created').has('age', 29).as('cocreators')). //// (2)
      select('creators','cocreators').by('name') //3
```

1. Find vertices that created something and match them as 'creators', then find out what they created which is
   named 'lop' and match these vertices as 'projects'.
2. Using these 'projects' vertices, find out their creators aged 29 and remember these as 'cocreators'.
3. Return the name of both 'creators' and 'cocreators'.

![grateful dead schema](../images/grateful-dead-schema.png)

Figure 4. Grateful Dead

`MatchStep` brings functionality similar to [SPARQL](http://en.wikipedia.org/wiki/SPARQL) to Gremlin. Like SPARQL,
MatchStep conjoins a set of patterns applied to a graph. For example, the following traversal finds exactly those
songs which Jerry Garcia has both sung and written (using the Grateful Dead graph distributed in the `data/` directory):

console (groovy)

groovy

```
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.io('data/grateful-dead.xml').read().iterate()
gremlin> g.V().match(
                 __.as('a').has('name', 'Garcia'),
                 __.as('a').in('writtenBy').as('b'),
                 __.as('a').in('sungBy').as('b')).
               select('b').values('name')
==>CREAM PUFF WAR
==>CRYPTICAL ENVELOPMENT
```

```
g = traversal().with(graph)
g.io('data/grateful-dead.xml').read().iterate()
g.V().match(
        __.as('a').has('name', 'Garcia'),
        __.as('a').in('writtenBy').as('b'),
        __.as('a').in('sungBy').as('b')).
      select('b').values('name')
```

Among the features which differentiate `match()` from SPARQL are:

console (groovy)

groovy

```
gremlin> g.V().match(
                 __.as('a').out('created').has('name','lop').as('b'), //// (1)
                 __.as('b').in('created').has('age', 29).as('c'),
                 __.as('c').repeat(out()).times(2)). //// (2)
               select('c').out('knows').dedup().values('name') //// (3)
==>vadas
==>josh
```

```
g.V().match(
        __.as('a').out('created').has('name','lop').as('b'), //// (1)
        __.as('b').in('created').has('age', 29).as('c'),
        __.as('c').repeat(out()).times(2)). //// (2)
      select('c').out('knows').dedup().values('name') //3
```

1. **Patterns of arbitrary complexity**: `match()` is not restricted to triple patterns or property paths.
2. **Recursion support**: `match()` supports the branch-based steps within a pattern, including `repeat()`.
3. **Imperative/declarative hybrid**: Before and after a `match()`, it is possible to leverage classic Gremlin traversals.

To extend point #3, it is possible to support going from imperative, to declarative, to imperative, ad infinitum.

console (groovy)

groovy

```
gremlin> g.V().match(
                 __.as('a').out('knows').as('b'),
                 __.as('b').out('created').has('name','lop')).
               select('b').out('created').
                 match(
                   __.as('x').in('created').as('y'),
                   __.as('y').out('knows').as('z')).
               select('z').values('name')
==>vadas
==>josh
```

```
g.V().match(
        __.as('a').out('knows').as('b'),
        __.as('b').out('created').has('name','lop')).
      select('b').out('created').
        match(
          __.as('x').in('created').as('y'),
          __.as('y').out('knows').as('z')).
      select('z').values('name')
```

|  |  |
| --- | --- |
| Important | The `match()`-step is stateless. The variable bindings of the traversal patterns are stored in the path history of the traverser. As such, the variables used over all `match()`-steps within a traversal are globally unique. A benefit of this is that subsequent `where()`, `select()`, `match()`, etc. steps can leverage the same variables in their analysis. |

Like all other steps in Gremlin, `match()` is a function and thus, `match()` within `match()` is a natural consequence
of Gremlin’s functional foundation (i.e. recursive matching).

console (groovy)

groovy

```
gremlin> g.V().match(
                 __.as('a').out('knows').as('b'),
                 __.as('b').out('created').has('name','lop'),
                 __.as('b').match(
                              __.as('b').out('created').as('c'),
                              __.as('c').has('name','ripple')).
                            select('c').as('c')).
               select('a','c').by('name')
==>[a:marko,c:ripple]
```

```
g.V().match(
        __.as('a').out('knows').as('b'),
        __.as('b').out('created').has('name','lop'),
        __.as('b').match(
                     __.as('b').out('created').as('c'),
                     __.as('c').has('name','ripple')).
                   select('c').as('c')).
      select('a','c').by('name')
```

If a step-labeled traversal proceeds the `match()`-step and the traverser entering the `match()` is destined to bind
to a particular variable, then the previous step should be labeled accordingly.

console (groovy)

groovy

```
gremlin> g.V().as('a').out('knows').as('b').
           match(
             __.as('b').out('created').as('c'),
             __.not(__.as('c').in('created').as('a'))).
           select('a','b','c').by('name')
==>[a:marko,b:josh,c:ripple]
```

```
g.V().as('a').out('knows').as('b').
  match(
    __.as('b').out('created').as('c'),
    __.not(__.as('c').in('created').as('a'))).
  select('a','b','c').by('name')
```

There are three types of `match()` traversal patterns.

1. `as('a')…​as('b')`: both the start and end of the traversal have a declared variable.
2. `as('a')…​`: only the start of the traversal has a declared variable.
3. `…​`: there are no declared variables.

If a variable is at the start of a traversal pattern it **must** exist as a label in the path history of the traverser
else the traverser can not go down that path. If a variable is at the end of a traversal pattern then if the variable
exists in the path history of the traverser, the traverser’s current location **must** match (i.e. equal) its historic
location at that same label. However, if the variable does not exist in the path history of the traverser, then the
current location is labeled as the variable and thus, becomes a bound variable for subsequent traversal patterns. If a
traversal pattern does not have an end label, then the traverser must simply "survive" the pattern (i.e. not be
filtered) to continue to the next pattern. If a traversal pattern does not have a start label, then the traverser
can go down that path at any point, but will only go down that pattern once as a traversal pattern is executed once
and only once for the history of the traverser. Typically, traversal patterns that do not have a start and end label
are used in conjunction with `and()`, `or()`, and `where()`. Once the traverser has "survived" all the patterns (or at
least one for `or()`), `match()`-step analyzes the traverser’s path history and emits a `Map<String,Object>` of the
variable bindings to the next step in the traversal.

console (groovy)

groovy

```
gremlin> g.V().as('a').out().as('b'). //// (1)
             match( //// (2)
               __.as('a').out().count().as('c'), //// (3)
               __.not(__.as('a').in().as('b')), //// (4)
               or( //// (5)
                 __.as('a').out('knows').as('b'),
                 __.as('b').in().count().as('c').and().as('c').is(gt(2)))). //// (6)
             dedup('a','c'). //// (7)
             select('a','b','c').by('name').by('name').by() //// (8)
==>[a:marko,b:lop,c:3]
```

```
g.V().as('a').out().as('b'). //// (1)
    match( //// (2)
      __.as('a').out().count().as('c'), //// (3)
      __.not(__.as('a').in().as('b')), //// (4)
      or( //// (5)
        __.as('a').out('knows').as('b'),
        __.as('b').in().count().as('c').and().as('c').is(gt(2)))). //// (6)
    dedup('a','c'). //// (7)
    select('a','b','c').by('name').by('name').by() //8
```

1. A standard, step-labeled traversal can come prior to `match()`.
2. If the traverser’s path prior to entering `match()` has requisite label values, then those historic values are bound.
3. It is possible to use [barrier steps](../05a-traversal-concepts.md#a-note-on-barrier-steps) though they are computed locally to the pattern (as one would expect).
4. It is possible to `not()` a pattern.
5. It is possible to nest `and()`- and `or()`-steps for conjunction matching.
6. Both infix and prefix conjunction notation is supported.
7. It is possible to "distinct" the specified label combination.
8. The bound values are of different types — vertex ("a"), vertex ("b"), long ("c").

#### Using Where with Match

Match is typically used in conjunction with both `select()` (demonstrated previously) and `where()` (presented here).
A `where()`-step allows the user to further constrain the result set provided by `match()`.

console (groovy)

groovy

```
gremlin> g.V().match(
                 __.as('a').out('created').as('b'),
                 __.as('b').in('created').as('c')).
                 where('a', neq('c')).
               select('a','c').by('name')
==>[a:marko,c:josh]
==>[a:marko,c:peter]
==>[a:josh,c:marko]
==>[a:josh,c:peter]
==>[a:peter,c:marko]
==>[a:peter,c:josh]
```

```
g.V().match(
        __.as('a').out('created').as('b'),
        __.as('b').in('created').as('c')).
        where('a', neq('c')).
      select('a','c').by('name')
```

The `where()`-step can take either a `P`-predicate (example above) or a `Traversal` (example below). Using
`MatchPredicateStrategy`, `where()`-clauses are automatically folded into `match()` and thus, subject to the query
optimizer within `match()`-step.

console (groovy)

groovy

```
gremlin> traversal = g.V().match(
                             __.as('a').has(label,'person'), //// (1)
                             __.as('a').out('created').as('b'),
                             __.as('b').in('created').as('c')).
                             where(__.as('a').out('knows').as('c')). //// (2)
                           select('a','c').by('name'); null //// (3)
==>null
gremlin> traversal.toString() //// (4)
==>[GraphStep(vertex,[]), MatchStep(null,AND,[[MatchStartStep(a), HasStep([~label.eq(person)]), MatchEndStep(null)], [MatchStartStep(a), VertexStep(OUT,[created],vertex), MatchEndStep(b)], [MatchStartStep(b), VertexStep(IN,[created],vertex), MatchEndStep(c)]]), WhereTraversalStep([WhereStartStep(a), VertexStep(OUT,[knows],vertex), WhereEndStep(c)]), SelectStep(last,[a, c],[value(name)])]
gremlin> traversal // // (5) (6)
==>[a:marko,c:josh]
gremlin> traversal.toString() //// (7)
==>[TinkerGraphStep(vertex,[~label.eq(person)])@[a], MatchStep(null,AND,[[MatchStartStep(a), VertexStep(OUT,[created],vertex), MatchEndStep(b)], [MatchStartStep(b), VertexStep(IN,[created],vertex), MatchEndStep(c)], [MatchStartStep(a), WhereTraversalStep([WhereStartStep(null), VertexStep(OUT,[knows],vertex), WhereEndStep(c)]), MatchEndStep(null)]]), SelectStep(last,[a, c],[value(name)])]
```

```
traversal = g.V().match(
                    __.as('a').has(label,'person'), //// (1)
                    __.as('a').out('created').as('b'),
                    __.as('b').in('created').as('c')).
                    where(__.as('a').out('knows').as('c')). //// (2)
                  select('a','c').by('name'); null //// (3)
traversal.toString() //// (4)
traversal // // (5) (6) (5)
traversal.toString() //7
```

1. Any `has()`-step traversal patterns that start with the match-key are pulled out of `match()` to enable the graph
   system to leverage the filter for index lookups.
2. A `where()`-step with a traversal containing variable bindings declared in `match()`.
3. A useful trick to ensure that the traversal is not iterated by Gremlin Console.
4. The string representation of the traversal prior to its strategies being applied.
5. The Gremlin Console will automatically iterate anything that is an iterator or is iterable.
6. Both marko and josh are co-developers and marko knows josh.
7. The string representation of the traversal after the strategies have been applied (and thus, `where()` is folded into `match()`)

|  |  |
| --- | --- |
| Important | A `where()`-step is a filter and thus, variables within a `where()` clause are not globally bound to the path of the traverser in `match()`. As such, `where()`-steps in `match()` are used for filtering, not binding. |

**Additional References**

[`match(Traversal…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#match(org.apache.tinkerpop.gremlin.process.traversal.Traversal...))

#### Using Where with Match

Match is typically used in conjunction with both `select()` (demonstrated previously) and `where()` (presented here).
A `where()`-step allows the user to further constrain the result set provided by `match()`.

console (groovy)

groovy

```
gremlin> g.V().match(
                 __.as('a').out('created').as('b'),
                 __.as('b').in('created').as('c')).
                 where('a', neq('c')).
               select('a','c').by('name')
==>[a:marko,c:josh]
==>[a:marko,c:peter]
==>[a:josh,c:marko]
==>[a:josh,c:peter]
==>[a:peter,c:marko]
==>[a:peter,c:josh]
```

```
g.V().match(
        __.as('a').out('created').as('b'),
        __.as('b').in('created').as('c')).
        where('a', neq('c')).
      select('a','c').by('name')
```

The `where()`-step can take either a `P`-predicate (example above) or a `Traversal` (example below). Using
`MatchPredicateStrategy`, `where()`-clauses are automatically folded into `match()` and thus, subject to the query
optimizer within `match()`-step.

console (groovy)

groovy

```
gremlin> traversal = g.V().match(
                             __.as('a').has(label,'person'), //// (1)
                             __.as('a').out('created').as('b'),
                             __.as('b').in('created').as('c')).
                             where(__.as('a').out('knows').as('c')). //// (2)
                           select('a','c').by('name'); null //// (3)
==>null
gremlin> traversal.toString() //// (4)
==>[GraphStep(vertex,[]), MatchStep(null,AND,[[MatchStartStep(a), HasStep([~label.eq(person)]), MatchEndStep(null)], [MatchStartStep(a), VertexStep(OUT,[created],vertex), MatchEndStep(b)], [MatchStartStep(b), VertexStep(IN,[created],vertex), MatchEndStep(c)]]), WhereTraversalStep([WhereStartStep(a), VertexStep(OUT,[knows],vertex), WhereEndStep(c)]), SelectStep(last,[a, c],[value(name)])]
gremlin> traversal // // (5) (6)
==>[a:marko,c:josh]
gremlin> traversal.toString() //// (7)
==>[TinkerGraphStep(vertex,[~label.eq(person)])@[a], MatchStep(null,AND,[[MatchStartStep(a), VertexStep(OUT,[created],vertex), MatchEndStep(b)], [MatchStartStep(b), VertexStep(IN,[created],vertex), MatchEndStep(c)], [MatchStartStep(a), WhereTraversalStep([WhereStartStep(null), VertexStep(OUT,[knows],vertex), WhereEndStep(c)]), MatchEndStep(null)]]), SelectStep(last,[a, c],[value(name)])]
```

```
traversal = g.V().match(
                    __.as('a').has(label,'person'), //// (1)
                    __.as('a').out('created').as('b'),
                    __.as('b').in('created').as('c')).
                    where(__.as('a').out('knows').as('c')). //// (2)
                  select('a','c').by('name'); null //// (3)
traversal.toString() //// (4)
traversal // // (5) (6) (5)
traversal.toString() //7
```

1. Any `has()`-step traversal patterns that start with the match-key are pulled out of `match()` to enable the graph
   system to leverage the filter for index lookups.
2. A `where()`-step with a traversal containing variable bindings declared in `match()`.
3. A useful trick to ensure that the traversal is not iterated by Gremlin Console.
4. The string representation of the traversal prior to its strategies being applied.
5. The Gremlin Console will automatically iterate anything that is an iterator or is iterable.
6. Both marko and josh are co-developers and marko knows josh.
7. The string representation of the traversal after the strategies have been applied (and thus, `where()` is folded into `match()`)

|  |  |
| --- | --- |
| Important | A `where()`-step is a filter and thus, variables within a `where()` clause are not globally bound to the path of the traverser in `match()`. As such, `where()`-steps in `match()` are used for filtering, not binding. |

**Additional References**

[`match(Traversal…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#match(org.apache.tinkerpop.gremlin.process.traversal.Traversal...))

### Optional Step

The `optional()`-step (**branch/flatMap**) returns the result of the specified traversal if it yields a result else it returns the calling
element, i.e. the `identity()`.

console (groovy)

groovy

```
gremlin> g.V(2).optional(out('knows')) //// (1)
==>v[2]
gremlin> g.V(2).optional(__.in('knows')) //// (2)
==>v[1]
```

```
g.V(2).optional(out('knows')) //// (1)
g.V(2).optional(__.in('knows')) //2
```

1. vadas does not have an outgoing knows-edge so vadas is returned.
2. vadas does have an incoming knows-edge so marko is returned.

`optional` is particularly useful for lifting entire graphs when used in conjunction with `path` or `tree`.

console (groovy)

groovy

```
gremlin> g.V().hasLabel('person').optional(out('knows').optional(out('created'))).path() //// (1)
==>[v[1],v[2]]
==>[v[1],v[4],v[5]]
==>[v[1],v[4],v[3]]
==>[v[2]]
==>[v[4]]
==>[v[6]]
```

```
g.V().hasLabel('person').optional(out('knows').optional(out('created'))).path() //1
```

1. Returns the paths of everybody followed by who they know followed by what they created.

**Additional References**

[`optional(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#optional(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### Repeat Step

![gremlin fade](../images/gremlin-fade.png)

The `repeat()`-step (**branch**) is used for looping over a traversal given some break predicate. Below are some
examples of `repeat()`-step in action.

console (groovy)

groovy

```
gremlin> g.V(1).repeat(out()).times(2).path().by('name') //// (1)
==>[marko,josh,ripple]
==>[marko,josh,lop]
gremlin> g.V().until(has('name','ripple')).
               repeat(out()).path().by('name') //// (2)
==>[marko,josh,ripple]
==>[josh,ripple]
==>[ripple]
```

```
g.V(1).repeat(out()).times(2).path().by('name') //// (1)
g.V().until(has('name','ripple')).
      repeat(out()).path().by('name') //2
```

1. do-while semantics stating to do `out()` 2 times.
2. while-do semantics stating to break if the traverser is at a vertex named "ripple".

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.io('data/grateful-dead.xml').read().iterate()
gremlin> g.V().has('name','JAM').repeat(out('followedBy').limit(2)).times(3) //// (1)
==>v[15]
==>v[215]
gremlin> g.V().has('name','DRUMS').repeat(__.in('followedBy').range(1,3)).until(loops().is(2)) //// (2)
==>v[49]
==>v[175]
gremlin> g.V().has('name','HEY BO DIDDLEY').repeat(out('followedBy').skip(5)).times(2) //// (3)
```

```
graph = TinkerGraph.open()
g = traversal().with(graph)
g.io('data/grateful-dead.xml').read().iterate()
g.V().has('name','JAM').repeat(out('followedBy').limit(2)).times(3) //// (1)
g.V().has('name','DRUMS').repeat(__.in('followedBy').range(1,3)).until(loops().is(2)) //// (2)
g.V().has('name','HEY BO DIDDLEY').repeat(out('followedBy').skip(5)).times(2) //3
```

1. Starting from the song 'JAM' get 2 songs that have followed, looping 3 times.
2. Starting from the song 'DRUMS' get the 2nd and 3rd songs that have preceded, looping twice.
3. Starting from the song 'HEY BO DIDDLEY' get the songs that have followed, skipping the first 5 and looping twice.

|  |  |
| --- | --- |
| Important | There are three modulators for `repeat()`: `times()`, `until()`, and `emit()`. The most straightforward is `times()`, which indicates the number of times to execute the loop. Conditional loops can be executed using `until()`. If `until()` comes after `repeat()` it is do/while looping. If `until()` comes before `repeat()` it is while/do looping. Emission of traversers from the loop are controlled with `emit()`. If `emit()` is placed after `repeat()`, it is evaluated on the traversers leaving the repeat-traversal. If `emit()` is placed before `repeat()`, it is evaluated on the traversers prior to entering the repeat-traversal. |

The `repeat()`-step also supports an "emit predicate", where the predicate for an empty argument `emit()` is
`true` (i.e. `emit() == emit{true}`). With `emit()`, the traverser is split in two — the traverser exits the code
block as well as continues back within the code block (assuming `until()` holds true).

console (groovy)

groovy

```
gremlin> g.V(1).repeat(out()).times(2).emit().path().by('name') //// (1)
==>[marko,lop]
==>[marko,vadas]
==>[marko,josh]
==>[marko,josh,ripple]
==>[marko,josh,lop]
gremlin> g.V(1).emit().repeat(out()).times(2).path().by('name') //// (2)
==>[marko]
==>[marko,lop]
==>[marko,vadas]
==>[marko,josh]
==>[marko,josh,ripple]
==>[marko,josh,lop]
```

```
g.V(1).repeat(out()).times(2).emit().path().by('name') //// (1)
g.V(1).emit().repeat(out()).times(2).path().by('name') //2
```

1. The `emit()` comes after `repeat()` and thus, emission happens after the `repeat()` traversal is executed. Thus,
   no one vertex paths exist.
2. The `emit()` comes before `repeat()` and thus, emission happens prior to the `repeat()` traversal being executed.
   Thus, one vertex paths exist.

The `emit()`-modulator can take an arbitrary predicate.

console (groovy)

groovy

```
gremlin> g.V(1).repeat(out()).times(2).emit(has('lang')).path().by('name')
==>[marko,lop]
==>[marko,josh,ripple]
==>[marko,josh,lop]
```

```
g.V(1).repeat(out()).times(2).emit(has('lang')).path().by('name')
```

![repeat step](../images/repeat-step.png)

console (groovy)

groovy

```
gremlin> g.V(1).repeat(out()).times(2).emit().path().by('name')
==>[marko,lop]
==>[marko,vadas]
==>[marko,josh]
==>[marko,josh,ripple]
==>[marko,josh,lop]
```

```
g.V(1).repeat(out()).times(2).emit().path().by('name')
```

The first time through the `repeat()`, the vertices lop, vadas, and josh are seen. Given that `loops==1`, the
traverser repeats. However, because the emit-predicate is declared true, those vertices are emitted. The next time through
`repeat()`, the vertices traversed are ripple and lop (Josh’s created projects, as lop and vadas have no out edges).
Given that `loops==2`, the until-predicate fails and ripple and lop are emitted.
Therefore, the traverser has seen the vertices: lop, vadas, josh, ripple, and lop.

`repeat()`-steps may be nested inside each other or inside the `emit()` or `until()` predicates and they can also be 'named' by passing a string as the first parameter to `repeat()`. The loop counter of a named repeat step can be accessed within the looped context with `loops(loopName)` where `loopName` is the name set whe creating the `repeat()`-step.

console (groovy)

groovy

```
gremlin> g.V(1).
           repeat(out("knows")).
             until(repeat(out("created")).emit(has("name", "lop"))) //// (1)
==>v[4]
gremlin> g.V(6).
           repeat('a', both('created').simplePath()).
             emit(repeat('b', both('knows')).
                    until(loops('b').as('b').where(loops('a').as('b'))).
           hasId(2)).dedup() //// (2)
==>v[4]
```

```
g.V(1).
  repeat(out("knows")).
    until(repeat(out("created")).emit(has("name", "lop"))) //// (1)
g.V(6).
  repeat('a', both('created').simplePath()).
    emit(repeat('b', both('knows')).
           until(loops('b').as('b').where(loops('a').as('b'))).
  hasId(2)).dedup() //2
```

1. Starting from vertex 1, keep going taking outgoing 'knows' edges until the vertex was created by 'lop'.
2. Starting from vertex 6, keep taking created edges in either direction until the vertex is same distance from vertex 2 over knows edges as it is from vertex 6 over created edges.

Finally, note that both `emit()` and `until()` can take a traversal and in such, situations, the predicate is
determined by `traversal.hasNext()`. A few examples are provided below.

console (groovy)

groovy

```
gremlin> g.V(1).repeat(out()).until(hasLabel('software')).path().by('name') //// (1)
==>[marko,lop]
==>[marko,josh,ripple]
==>[marko,josh,lop]
gremlin> g.V(1).emit(hasLabel('person')).repeat(out()).path().by('name') //// (2)
==>[marko]
==>[marko,vadas]
==>[marko,josh]
gremlin> g.V(1).repeat(out()).until(outE().count().is(0)).path().by('name') //// (3)
==>[marko,lop]
==>[marko,vadas]
==>[marko,josh,ripple]
==>[marko,josh,lop]
```

```
g.V(1).repeat(out()).until(hasLabel('software')).path().by('name') //// (1)
g.V(1).emit(hasLabel('person')).repeat(out()).path().by('name') //// (2)
g.V(1).repeat(out()).until(outE().count().is(0)).path().by('name') //3
```

1. Starting from vertex 1, keep taking outgoing edges until a software vertex is reached.
2. Starting from vertex 1, and in an infinite loop, emit the vertex if it is a person and then traverser the outgoing edges.
3. Starting from vertex 1, keep taking outgoing edges until a vertex is reached that has no more outgoing edges.

|  |  |
| --- | --- |
| Warning | The anonymous traversal of `emit()` and `until()` (not `repeat()`) process their current objects "locally." In OLAP, where the atomic unit of computing is the vertex and its local "star graph," it is important that the anonymous traversals do not leave the confines of the vertex’s star graph. In other words, they can not traverse to an adjacent vertex’s properties or edges. |

**Additional References**

[`repeat(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#repeat(org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[emit](06-steps/modulator-steps.md#emit-step), [times()](06-steps/modulator-steps.md#times-step), [until()](06-steps/modulator-steps.md#until-step),
[`Looping Recipes`](https://tinkerpop.apache.org/docs/3.8.0/recipes/#looping)

### Union Step

![union step](../images/union-step.png)

The `union()`-step (**branch**) supports the merging of the results of an arbitrary number of traversals. When a
traverser reaches a `union()`-step, it is copied to each of its internal steps. The traversers emitted from `union()`
are the outputs of the respective internal traversals.

console (groovy)

groovy

```
gremlin> g.V(4).union(
                  __.in().values('age'),
                  out().values('lang'))
==>29
==>java
==>java
gremlin> g.V(4).union(
                  __.in().values('age'),
                  out().values('lang')).path()
==>[v[4],v[1],29]
==>[v[4],v[5],java]
==>[v[4],v[3],java]
gremlin> g.union(V().has('person','name','vadas'),
                 V().has('software','name','lop').in('created'))
==>v[2]
==>v[1]
==>v[4]
==>v[6]
```

```
g.V(4).union(
         __.in().values('age'),
         out().values('lang'))
g.V(4).union(
         __.in().values('age'),
         out().values('lang')).path()
g.union(V().has('person','name','vadas'),
        V().has('software','name','lop').in('created'))
```

**Additional References**

[`union(Traversal…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#union(org.apache.tinkerpop.gremlin.process.traversal.Traversal...))

