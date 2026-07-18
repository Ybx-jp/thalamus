## Basic Gremlin

![language variants](../images/language-variants.png) The `GraphTraversalSource` is basically the connection to a graph
instance. That graph instance might be [embedded](#connecting-embedded), hosted in
[Gremlin Server](02-connecting.md#connecting-gremlin-server) or hosted in a [RGP](#connecting-rgp), but the `GraphTraversalSource` is
agnostic to that. Assuming "g" is the `GraphTraversalSource`, getting data into the graph regardless of programming
language or mode of operation is just some basic Gremlin:

console (groovy)

groovy

csharp

java

javascript

python

go

```
gremlin> v1 = g.add_v('person').property('name','marko').next()
==>v[0]
gremlin> v2 = g.add_v('person').property('name','stephen').next()
==>v[2]
gremlin> g.V(v1).addE('knows').to(v2).property('weight',0.75).iterate()
```

```
v1 = g.add_v('person').property('name','marko').next()
v2 = g.add_v('person').property('name','stephen').next()
g.V(v1).addE('knows').to(v2).property('weight',0.75).iterate()
```

```
var v1 = g.add_v("person").Property("name", "marko").Next();
var v2 = g.add_v("person").Property("name", "stephen").Next();
g.V(v1).AddE("knows").To(v2).Property("weight", 0.75).Iterate();
```

```
Vertex v1 = g.add_v("person").property("name","marko").next();
Vertex v2 = g.add_v("person").property("name","stephen").next();
g.V(v1).addE("knows").to(v2).property("weight",0.75).iterate();
```

```
const v1 = g.add_v('person').property('name','marko').next();
const v2 = g.add_v('person').property('name','stephen').next();
g.V(v1).addE('knows').to(v2).property('weight',0.75).iterate();
```

```
v1 = g.add_v('person').property('name','marko').next()
v2 = g.add_v('person').property('name','stephen').next()
g.V(v1).add_e('knows').to(v2).property('weight',0.75).iterate()
```

```
v1, err := g.add_v("person").Property("name", "marko").Next()
v2, err := g.add_v("person").Property("name", "stephen").Next()
g.V(v1).AddE("knows").To(v2).Property("weight", 0.75).Iterate()
```

The first two lines add a vertex each with the vertex label of "person" and the associated "name" property. The third
line adds an edge with the "knows" label between them and an associated "weight" property. Note the use of `next()`
and `iterate()` at the end of the lines - their effect as [terminal steps](06-steps/terminal-steps.md#terminal-steps) is described in
[The Gremlin Console Tutorial](https://tinkerpop.apache.org/docs/3.8.0/tutorials/the-gremlin-console/#result-iteration).

|  |  |
| --- | --- |
| Important | Writing Gremlin is just one way to load data into the graph. Some graphs may have special data loaders which could be more efficient and make the task easier and faster. It is worth looking into those tools especially if there is a large one-time load to do. |

Retrieving this data is also a just writing a Gremlin statement:

console (groovy)

groovy

csharp

java

javascript

python

go

```
gremlin> marko = g.V().has('person','name','marko').next()
==>v[0]
gremlin> peopleMarkoKnows = g.V().has('person','name','marko').out('knows').to_list()
==>v[2]
```

```
marko = g.V().has('person','name','marko').next()
peopleMarkoKnows = g.V().has('person','name','marko').out('knows').to_list()
```

```
var marko = g.V().Has("person", "name", "marko").Next();
var peopleMarkoKnows = g.V().Has("person", "name", "marko").Out("knows").to_list();
```

```
Vertex marko = g.V().has("person","name","marko").next()
List<Vertex> peopleMarkoKnows = g.V().has("person","name","marko").out("knows").to_list()
```

```
const marko = g.V().has('person','name','marko').next()
const peopleMarkoKnows = g.V().has('person','name','marko').out('knows').to_list()
```

```
marko = g.V().has('person','name','marko').next()
people_marko_knows = g.V().has('person','name','marko').out('knows').to_list()
```

```
marko, err := g.V().Has("person", "name", "marko").Next()
peopleMarkoKnows, err := g.V().Has("person", "name", "marko").Out("knows").to_list()
```

In all these examples presented so far there really isn’t a lot of difference in how the Gremlin itself looks. There
are a few language syntax specific odds and ends, but for the most part Gremlin looks like Gremlin in all of the
different languages.

The library of Gremlin steps with examples for each can be found in [The Traversal Section](05-traversal-overview.md). This section
is meant as a reference guide and will not necessarily provide methods for applying Gremlin to solve particular
problems. Please see the aforementioned [Tutorials](https://tinkerpop.apache.org/docs/3.8.0/#tutorials)
[Recipes](https://tinkerpop.apache.org/docs/3.8.0/recipes/) and the
[Practical Gremlin](http://kelvinlawrence.net/book/Gremlin-Graph-Guide.html) book for that sort of information.

|  |  |
| --- | --- |
| Note | A full list of helpful Gremlin resources can be found on the [TinkerPop Compendium](https://tinkerpop.apache.org/docs/3.8.0/) page. |

