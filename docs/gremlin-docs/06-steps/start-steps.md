### AddE Step

[Reasoning](http://en.wikipedia.org/wiki/Automated_reasoning) is the process of making explicit what is implicit
in the data. What is explicit in a graph are the objects of the graph — i.e. vertices and edges. What is implicit
in the graph is the traversal. In other words, traversals expose meaning where the meaning is determined by the
traversal definition. For example, take the concept of a "co-developer." Two people are co-developers if they have
worked on the same project together. This concept can be represented as a traversal and thus, the concept of
"co-developers" can be derived. Moreover, what was once implicit can be made explicit via the `addE()`-step
(**map**/**sideEffect**).

![addedge step](../images/addedge-step.png)

console (groovy)

groovy

```
gremlin> g.V(1).as('a').out('created').in('created').where(neq('a')).
           addE('co-developer').from('a').property('year',2009) //// (1)
==>e[0][1-co-developer->4]
==>e[13][1-co-developer->6]
gremlin> g.V(3,4,5).aggregate('x').has('name','josh').as('a').
           select('x').unfold().hasLabel('software').addE('createdBy').to('a') //// (2)
==>e[14][3-createdBy->4]
==>e[15][5-createdBy->4]
gremlin> g.V().as('a').out('created').addE('createdBy').to('a').property('acl','public') //// (3)
==>e[16][3-createdBy->1]
==>e[17][5-createdBy->4]
==>e[18][3-createdBy->4]
==>e[19][3-createdBy->6]
gremlin> g.V(1).as('a').out('knows').
           addE('livesNear').from('a').property('year',2009).
           inV().inE('livesNear').values('year') //// (4)
==>2009
==>2009
gremlin> g.V().match(
                 __.as('a').out('knows').as('b'),
                 __.as('a').out('created').as('c'),
                 __.as('b').out('created').as('c')).
               addE('friendlyCollaborator').from('a').to('b').
                 property(id,23).property('project',select('c').values('name')) //// (5)
==>e[23][1-friendlyCollaborator->4]
gremlin> g.E(23).valueMap()
==>[project:lop]
gremlin> vMarko = g.V().has('name','marko').next()
==>v[1]
gremlin> vPeter = g.V().has('name','peter').next()
==>v[6]
gremlin> g.V(vMarko).addE('knows').to(vPeter) //// (6)
==>e[22][1-knows->6]
gremlin> g.addE('knows').from(vMarko).to(vPeter) //// (7)
==>e[24][1-knows->6]
gremlin> g.addE('knows').from(__.V(1)).to(__.constant(6)) //// (8)
==>e[25][1-knows->6]
```

```
g.V(1).as('a').out('created').in('created').where(neq('a')).
  addE('co-developer').from('a').property('year',2009) //// (1)
g.V(3,4,5).aggregate('x').has('name','josh').as('a').
  select('x').unfold().hasLabel('software').addE('createdBy').to('a') //// (2)
g.V().as('a').out('created').addE('createdBy').to('a').property('acl','public') //// (3)
g.V(1).as('a').out('knows').
  addE('livesNear').from('a').property('year',2009).
  inV().inE('livesNear').values('year') //// (4)
g.V().match(
        __.as('a').out('knows').as('b'),
        __.as('a').out('created').as('c'),
        __.as('b').out('created').as('c')).
      addE('friendlyCollaborator').from('a').to('b').
        property(id,23).property('project',select('c').values('name')) //// (5)
g.E(23).valueMap()
vMarko = g.V().has('name','marko').next()
vPeter = g.V().has('name','peter').next()
g.V(vMarko).addE('knows').to(vPeter) //// (6)
g.addE('knows').from(vMarko).to(vPeter) //// (7)
g.addE('knows').from(__.V(1)).to(__.constant(6)) //8
```

1. Add a co-developer edge with a year-property between marko and his collaborators.
2. Add incoming createdBy edges from the josh-vertex to the lop- and ripple-vertices.
3. Add an inverse createdBy edge for all created edges.
4. The newly created edge is a traversable object.
5. Two arbitrary bindings in a traversal can be joined `from()`→`to()`, where `id` can be provided for graphs that
   supports user provided ids.
6. Add an edge between marko and peter given the directed (detached) vertex references.
7. Add an edge between marko and peter given the directed (detached) vertex references.
8. Use child traversals producing either a vertex, or vertex id to add an edge between marko and peter.

**Additional References**

[`addE(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#addE(java.lang.String)),
[`addE(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#addE(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### AddV Step

The `addV()`-step is used to add vertices to the graph (**map**/**sideEffect**). For every incoming object, a vertex is
created. Moreover, `GraphTraversalSource` maintains an `addV()` method.

console (groovy)

groovy

```
gremlin> g.addV('person').property('name','stephen')
==>v[0]
gremlin> g.V().values('name')
==>stephen
==>marko
==>vadas
==>lop
==>josh
==>ripple
==>peter
gremlin> g.V().outE('knows').addV().property('name','nothing')
==>v[13]
==>v[15]
gremlin> g.V().has('name','nothing')
==>v[13]
==>v[15]
gremlin> g.V().has('name','nothing').bothE()
```

```
g.addV('person').property('name','stephen')
g.V().values('name')
g.V().outE('knows').addV().property('name','nothing')
g.V().has('name','nothing')
g.V().has('name','nothing').bothE()
```

**Additional References**

[`addV()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#addV()),
[`addV(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#addV(java.lang.String)),
[`addV(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#addV(org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### Call Step

The `call()` step allows for custom, provider-specific service calls either at the start of a traversal or mid-traversal.
This allows Graph providers to expose operations not natively built into the Gremlin language, such as full text search,
custom analytics, notification triggers, etc.

When called with no arguments, `call()` will produce a list of callable services available for the graph in use. This
no-argument version is equivalent to `call('--list')`. This "directory service" is also capable of producing more
verbose output describing all the services or an individual service:

console (groovy)

groovy

```
gremlin> g.call() //// (1)
gremlin> g.call('--list') //// (1)
gremlin> g.call().with('verbose') //// (2)
gremlin> g.call().with('verbose').with('service', 'xyz-service') //// (3)
```

```
g.call() //// (1)
g.call('--list') //// (1)
g.call().with('verbose') //// (2)
g.call().with('verbose').with('service', 'xyz-service') //3
```

1. List available services by name
2. Produce a Map of detailed service information by name
3. Produce the detailed service information for the 'xyz-service'

The first argument to `call()` is always the name of the service call. Additionally, service calls can accept both
static and dynamically produced parameters. Static parameters can be passed as a `Map` to the `call()` as the second
argument. Individual static parameters can also be added using the `.with()` modulator. Dynamic parameters can be
passed as a `Map`-producing `Traversal` as the second argument (no static parameters) or third argument (static + dynamic
parameters). Additional individual dynamic parameters can be added using the `.with()` modulator.

```
g.call('xyz-service') //1
g.call('xyz-service', ['a':'b']) //2
g.call('xyz-service').with('a', 'b') //2
g.call('xyz-service', __.inject(['a':'b'])) //3
g.call('xyz-service').with('a', __.inject('b')) //3
g.call('xyz-service', ['a':'b'], __.inject(['c':'d'])) //4
```

1. Call the 'xyz-service' with no parameters
2. Examples of static parameters (constants known before execution)
3. Examples of dynamic parameters (these will be computed at execution time)
4. Example of static + dynamic parameters (these will be computed and merged into one set of parameters at execution time)

**Additional References**

GraphTraversalSource:

[`call()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversalSource.html#call())
[`call(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversalSource.html#call(java.lang.String))
[`call(String, Map)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversalSource.html#call(java.lang.String,java.util.Map))
[`call(String, Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversalSource.html#call(java.lang.String,org.apache.tinkerpop.gremlin.process.traversal.Traversal))
[`call(String, Map, Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversalSource.html#call(java.lang.String,java.util.Map,org.apache.tinkerpop.gremlin.process.traversal.Traversal))

GraphTraversal:

[`call(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#call(java.lang.String))
[`call(String, Map)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#call(java.lang.String,java.util.Map))
[`call(String, Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#call(java.lang.String,org.apache.tinkerpop.gremlin.process.traversal.Traversal))
[`call(String, Map, Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#call(java.lang.String,java.util.Map,org.apache.tinkerpop.gremlin.process.traversal.Traversal))

### E Step

The `E()`-step is meant to read edges from the graph and is usually used to start a `GraphTraversal`, but can also
be used mid-traversal.

console (groovy)

groovy

```
gremlin> g.E(11) //// (1)
==>e[11][4-created->3]
gremlin> g.E().hasLabel('knows').has('weight', gt(0.75))
==>e[8][1-knows->4]
gremlin> g.inject(1).coalesce(E().hasLabel("knows"), addE("knows").from(V().has("name","josh")).to(V().has("name","vadas"))) //// (2)
==>e[7][1-knows->2]
==>e[8][1-knows->4]
```

```
g.E(11) //// (1)
g.E().hasLabel('knows').has('weight', gt(0.75))
g.inject(1).coalesce(E().hasLabel("knows"), addE("knows").from(V().has("name","josh")).to(V().has("name","vadas"))) //2
```

1. Find the edge by its unique identifier (i.e. `T.id`) - not all graphs will use a numeric value for their identifier.
2. Get edges with label `knows`, if there is none then add new one between `josh` and `vadas`.

**Additional References**

[`E(Object…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#E(java.lang.Object...))

### Inject Step

![inject step](../images/inject-step.png)

The concept of "injectable steps" makes it possible to insert objects arbitrarily into a traversal stream. In general,
`inject()`-step (**sideEffect**) exists and a few examples are provided below.

console (groovy)

groovy

```
gremlin> g.V(4).out().values('name').inject('daniel')
==>daniel
==>ripple
==>lop
gremlin> g.V(4).out().values('name').inject('daniel').map {it.get().length()}
==>6
==>6
==>3
gremlin> g.V(4).out().values('name').inject('daniel').map {it.get().length()}.path()
==>[daniel,6]
==>[v[4],v[5],ripple,6]
==>[v[4],v[3],lop,3]
```

```
g.V(4).out().values('name').inject('daniel')
g.V(4).out().values('name').inject('daniel').map {it.get().length()}
g.V(4).out().values('name').inject('daniel').map {it.get().length()}.path()
```

In the last example above, note that the path starting with `daniel` is only of length 2. This is because the
`daniel` string was inserted half-way in the traversal. Finally, a typical use case is provided below — when the
start of the traversal is not a graph object.

console (groovy)

groovy

```
gremlin> inject(1,2)
==>1
==>2
gremlin> inject(1,2).map {it.get() + 1}
==>2
==>3
gremlin> inject(1,2).map {it.get() + 1}.map {g.V(it.get()).next()}.values('name')
==>vadas
==>lop
```

```
inject(1,2)
inject(1,2).map {it.get() + 1}
inject(1,2).map {it.get() + 1}.map {g.V(it.get()).next()}.values('name')
```

**Additional References**

[`inject(Object)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#inject(E...))

### IO Step

![gremlin io](../images/gremlin-io.png) The task of importing and exporting the data of `Graph` instances is the
job of the `io()`-step. By default, TinkerPop supports three formats for importing and exporting graph data in
[GraphML](04-graph-structure.md#graphml), [GraphSON](04-graph-structure.md#graphson), and [Gryo](#gryo).

|  |  |
| --- | --- |
| Note | Additional documentation for TinkerPop IO formats can be found in the [IO Reference](https://tinkerpop.apache.org/docs/3.8.0/dev/io/). |

By itself the `io()`-step merely configures the kind of importing and exporting that is going
to occur and it is the follow-on call to the `read()` or `write()` step that determines which of those actions will
execute. Therefore, a typical usage of the `io()`-step would look like this:

```
g.io(someInputFile).read().iterate()
g.io(someOutputFile).write().iterate()
```

|  |  |
| --- | --- |
| Important | The commands above are still traversals and therefore require iteration to be executed, hence the use of `iterate()` as a termination step. |

By default, the `io()`-step will try to detect the right file format using the file name extension. To gain greater
control of the format use the `with()` step modulator to provide further information to `io()`. For example:

```
g.io(someInputFile).
    with(IO.reader, IO.graphson).
  read().iterate()
g.io(someOutputFile).
    with(IO.writer,IO.graphml).
  write().iterate()
```

The `IO` class is a helper for the `io()`-step that provides expressions that can be used to help configure it
and in this case it allows direct specification of the "reader" or "writer" to use. The "reader" actually refers to
a `GraphReader` implementation and the "writer" refers to a `GraphWriter` implementation. The implementations of
those interfaces provided by default are the standard TinkerPop implementations.

That default is an important point to consider for users. The default TinkerPop implementations are not designed with
massive, complex, parallel bulk loading in mind. They are designed to do single-threaded, OLTP-style loading of data
in the most generic way possible so as to accommodate the greatest number of graph databases out there. As such, from
a reading perspective, they work best for small datasets (or perhaps medium datasets where memory is plentiful and
time is not critical) that are loading to an empty graph - incremental loading is not supported. The story from the
writing perspective is not that different in there are no parallel operations in play, however streaming the output
to disk requires a single pass of the data without high memory requirements for larger datasets.

|  |  |
| --- | --- |
| Important | Default graph formats don’t contain information about property cardinality, so it is up to the graph provider to choose the appropriate one. You will see a warning message if the chosen cardinality is SINGLE while your graph input contains multiple values for that property. |

In general, TinkerPop recommends that users examine the native bulk import/export tools of the graph implementation
that they choose. Those tools will often outperform the `io()`-step and perhaps be easier to use with a greater
feature set. That said, graph providers do have the option to optimize `io()` to back it with their own
import/export utilities and therefore the default behavior provided by TinkerPop described above might be overridden
by the graph.

An excellent example of this lies in [HadoopGraph](14-hadoop.md#hadoop-gremlin) with [SparkGraphComputer](10-spark.md#sparkgraphcomputer)
which replaces the default single-threaded implementation with a more advanced OLAP style bulk import/export
functionality internally using [CloneVertexProgram](#clonevertexprogram). With this model, graphs of arbitrary size
can be imported/exported assuming that there is a Hadoop `InputFormat` or `OutputFormat` to support it.

|  |  |
| --- | --- |
| Important | Remote Gremlin Console users or Gremlin Language Variant (GLV) users (e.g. gremlin-python) who utilize the `io()`-step should recall that their `read()` or `write()` operation will occur on the server and not locally and therefore the file specified for import/export must be something accessible by the server. |

GraphSON and Gryo formats are extensible allowing users and graph providers to extend supported serialization options.
These extensions are exposed through `IoRegistry` implementations. To apply an `IoRegistry` use the `with()` option
and the `IO.registry` key, where the value is either an actual `IoRegistry` instance or the fully qualified class
name of one.

```
g.io(someInputFile).
    with(IO.reader, IO.gryo).
    with(IO.registry, TinkerIoRegistryV3d0.instance())
  read().iterate()
g.io(someOutputFile).
    with(IO.writer,IO.graphson).
    with(IO.registry, "org.apache.tinkerpop.gremlin.tinkergraph.structure.TinkerIoRegistryV3d0")
  write().iterate()
```

GLVs will obviously always be forced to use the latter form as they can’t explicitly create an instance of an
`IoRegistry` to pass to the server (nor are `IoRegistry` instances necessarily serializable).

The version of the formats (e.g. GraphSON 2.0 or 3.0) utilized by `io()` is determined entirely by the `IO.reader` and
`IO.writer` configurations or their defaults. The defaults will always be the latest version for the current release
of TinkerPop. It is also possible for graph providers to override these defaults, so consult the documentation of the
underlying graph database in use for any details on that.

|  |  |
| --- | --- |
| Note | The `io()` step will try to automatically detect the appropriate `GraphReader` or `GraphWriter` to use based on the file extension. If the file has a different extension than the ones expected, use `with()` as shown above to set the `reader` or `writer` explicitly. |

For more advanced configuration of `GraphReader` and `GraphWriter` operations (e.g. normalized output for GraphSON,
disabling class registrations for Gryo, etc.) then construct the appropriate `GraphReader` and `GraphWriter` using
the `build()` method on their implementations and use it directly. It can be passed directly to the `IO.reader` or
`IO.writer` options. Obviously, these are JVM based operations and thus not available to GLVs as portable features.

#### GraphML

![gremlin graphml](../images/gremlin-graphml.png) The [GraphML](http://graphml.graphdrawing.org/) file format is a
common XML-based representation of a graph. It is widely supported by graph-related tools and libraries making it a
solid interchange format for TinkerPop. In other words, if the intent is to work with graph data in conjunction with
applications outside of TinkerPop, GraphML may be the best choice to do that. Common use cases might be:

* Generate a graph using [NetworkX](https://networkx.github.io/), export it with GraphML and import it to TinkerPop.
* Produce a subgraph and export it to GraphML to be consumed by and visualized in [Gephi](https://gephi.org/).
* Migrate the data of an entire graph to a different graph database not supported by TinkerPop.

|  |  |
| --- | --- |
| Warning | GraphML is a "lossy" format in that it only supports primitive values for properties and does not have support for `Graph` variables. It will use `toString` to serialize property values outside of those primitives. |

|  |  |
| --- | --- |
| Warning | GraphML as a specification allows for `<edge>` and `<node>` elements to appear in any order. Most software that writes GraphML (including as TinkerPop’s `GraphMLWriter`) write `<node>` elements before `<edge>` elements. However it is important to note that `GraphMLReader` will read this data in order and order can matter. This is because TinkerPop does not allow the vertex label to be changed after the vertex has been created. Therefore, if an `<edge>` element comes before the `<node>`, the label on the vertex will be ignored. It is thus better to order `<node>` elements in the GraphML to appear before all `<edge>` elements if vertex labels are important to the graph. |

```
// expects a file extension of .xml or .graphml to determine that
// a GraphML reader/writer should be used.
g.io("graph.xml").read().iterate();
g.io("graph.xml").write().iterate();
```

|  |  |
| --- | --- |
| Note | If using GraphML generated from TinkerPop 2.x, read more about its incompatibilities in the [Upgrade Documentation](https://tinkerpop.apache.org/docs/3.8.0/upgrade/#graphml-format). |

#### GraphSON

![gremlin graphson](../images/gremlin-graphson.png) GraphSON is a [JSON](http://json.org/)-based format extended
from earlier versions of TinkerPop. It is important to note that TinkerPop’s GraphSON is not backwards compatible
with prior TinkerPop GraphSON versions. GraphSON has some support from graph-related application outside of TinkerPop,
but it is generally best used in two cases:

* A text format of the graph or its elements is desired (e.g. debugging, usage in source control, etc.)
* The graph or its elements need to be consumed by code that is not JVM-based (e.g. JavaScript, Python, .NET, etc.)

```
// expects a file extension of .json to interpret that
// a GraphSON reader/writer should be used
g.io("graph.json").read().iterate();
g.io("graph.json").write().iterate();
```

|  |  |
| --- | --- |
| Note | Additional documentation for GraphSON can be found in the [IO Reference](https://tinkerpop.apache.org/docs/3.8.0/dev/io/#graphson). |

#### Gryo

![gremlin kryo](../images/gremlin-kryo.png) [Kryo](https://github.com/EsotericSoftware/kryo) is a popular
serialization package for the JVM. Gremlin-Kryo is a binary `Graph` serialization format for use on the JVM by JVM
languages. It is designed to be space efficient, non-lossy and is promoted as the standard format to use when working
with graph data inside of the TinkerPop stack. A list of common use cases is presented below:

* Migration from one Gremlin Structure implementation to another (e.g. `TinkerGraph` to `Neo4jGraph`)
* Serialization of individual graph elements to be sent over the network to another JVM.
* Backups of in-memory graphs or subgraphs.

|  |  |
| --- | --- |
| Warning | When migrating between Gremlin Structure implementations, Kryo may not lose data, but it is important to consider the features of each `Graph` and whether or not the data types supported in one will be supported in the other. Failure to do so, may result in errors. |

```
// expects a file extension of .kryo to interpret that
// a GraphSON reader/writer should be used
g.io("graph.kryo").read().iterate()
g.io("graph.kryo").write().iterate()
```

**Additional References**

[`io(String)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversalSource.html#io(java.lang.String))

### MergeEdge Step

The `mergeE()` step is used to add edges and their properties to a graph in a "create
if not exist" fashion. The `mergeE()` step can also be used to find edges matching a given
pattern. The input passed to `mergeE()` can be either a `Map`, or a child traversal that
produces a `Map`.

|  |  |
| --- | --- |
| Note | There is a corresponding `mergeV()` step that can be used when creating vertices. |

Additionally, `option()` modulators may be combined with `mergeE()` to take action depending on
whether a vertex was created, or already existed. There are various ways that `mergeE()` can
be used. The simplest being to provide a single `Map` of keys and values, along with the
source and target vertex IDs, as a parameter. A `T.id` and a `T.label` may also be provided but
this is optional. The `mergeE()` step can be used directly from the `GraphTraversalSource` - `g`,
or in the middle of a traversal. For a match with an existing vertex to occur, all values
in the `Map` must exist on a vertex; otherwise, a new vertex will be created. The examples
that follow show how `mergeE()` can be used to add relationships between dogs in the graph.

console (groovy)

groovy

```
gremlin> g.mergeV([(T.id):1,(T.label):'Dog',name:'Toby'])
==>v[1]
gremlin> g.mergeV([(T.id):2,(T.label):'Dog',name:'Brandy']) //// (1)
==>v[2]
gremlin> g.mergeE([(T.label):'Sibling',created:'2022-02-07',(Direction.from):1,(Direction.to):2]) //// (2)
==>e[2][1-Sibling->2]
gremlin> g.E().elementMap()
==>[id:2,label:Sibling,IN:[id:2,label:Dog],OUT:[id:1,label:Dog],created:2022-02-07]
```

```
g.mergeV([(T.id):1,(T.label):'Dog',name:'Toby'])
g.mergeV([(T.id):2,(T.label):'Dog',name:'Brandy']) //// (1)
g.mergeE([(T.label):'Sibling',created:'2022-02-07',(Direction.from):1,(Direction.to):2]) //// (2)
g.E().elementMap()
```

1. Create two vertices with ID values of 1 and 2.
2. Create a "Sibling" relationship between the vertices.

|  |  |
| --- | --- |
| Note | The example above is written with `gremlin-groovy` and evaluated in Gremlin Console as a Groovy script thus allowing [Groovy syntax](https://groovy-lang.org/syntax.html#_maps) for initializing a `Map`. |

For a `mergeE()` step to succeed, both the `from` and `to` vertices must already exist. It
is not possible to create new vertices directly using `mergeE()`, but `mergeV()` and `mergeE()`
steps can be combined, in a single query, to achieve that goal.

|  |  |
| --- | --- |
| Note | The `mergeE()` step will not create vertices that do not exist. In those cases an error will be returned. |

If the `Direction` enum has been statically included, its explicit use can be omitted from
the query.

console (groovy)

groovy

```
gremlin> g.mergeV([(T.id):1,(T.label):'Dog',name:'Toby'])
==>v[1]
gremlin> g.mergeV([(T.id):2,(T.label):'Dog',name:'Brandy'])
==>v[2]
gremlin> g.mergeE([(T.label):'Sibling',created:'2022-02-07',(from):1,(to):2])
==>e[2][1-Sibling->2]
gremlin> g.E().elementMap()
==>[id:2,label:Sibling,IN:[id:2,label:Dog],OUT:[id:1,label:Dog],created:2022-02-07]
```

```
g.mergeV([(T.id):1,(T.label):'Dog',name:'Toby'])
g.mergeV([(T.id):2,(T.label):'Dog',name:'Brandy'])
g.mergeE([(T.label):'Sibling',created:'2022-02-07',(from):1,(to):2])
g.E().elementMap()
```

One or more `option()` steps can be used to control the behavior when an edge is created or
updated. Similar to `mergeV()`, the onCreate `Map` inherits from the main merge argument - any
existence criteria in the main merge argument (`T.id`, `T.label`, `Direction.OUT`, `Direction.IN`)
will be automatically carried over to the onCreate action, and these existence criteria cannot be overriden
in the onCreate `Map`.

console (groovy)

groovy

```
gremlin> g.mergeV([(T.id):1,(T.label):'Dog',name:'Toby'])
==>v[1]
gremlin> g.mergeV([(T.id):2,(T.label):'Dog',name:'Brandy'])
==>v[2]
gremlin> g.withSideEffect('map',[(T.label):'Sibling',(from):1,(to):2]).
           mergeE(select('map')).
             option(Merge.onCreate,[created:'2022-02-07']). //// (1)
             option(Merge.onMatch,[updated:'2022-02-07'])
==>e[2][1-Sibling->2]
gremlin> g.E().elementMap()
==>[id:2,label:Sibling,IN:[id:2,label:Dog],OUT:[id:1,label:Dog],created:2022-02-07]
gremlin> g.withSideEffect('map',[(T.label):'Sibling',(from):1,(to):2]).
           mergeE(select('map')).
             option(Merge.onCreate,[created:'2022-02-07']).
             option(Merge.onMatch,[updated:'2022-02-07']) //// (2)
==>e[2][1-Sibling->2]
gremlin> g.E().elementMap()
==>[id:2,label:Sibling,IN:[id:2,label:Dog],OUT:[id:1,label:Dog],created:2022-02-07,updated:2022-02-07]
```

```
g.mergeV([(T.id):1,(T.label):'Dog',name:'Toby'])
g.mergeV([(T.id):2,(T.label):'Dog',name:'Brandy'])
g.withSideEffect('map',[(T.label):'Sibling',(from):1,(to):2]).
  mergeE(select('map')).
    option(Merge.onCreate,[created:'2022-02-07']). //// (1)
    option(Merge.onMatch,[updated:'2022-02-07'])
g.E().elementMap()
g.withSideEffect('map',[(T.label):'Sibling',(from):1,(to):2]).
  mergeE(select('map')).
    option(Merge.onCreate,[created:'2022-02-07']).
    option(Merge.onMatch,[updated:'2022-02-07']) //// (2)
g.E().elementMap()
```

1. The edge did not exist - set the created date.
2. The edge did exist - set the updated date.

More than one edge can be created by a single `mergeE()` operation. This is done by
injecting a list of maps into the traversal and letting them stream into the `mergeE()`
step.

console (groovy)

groovy

```
gremlin> maps = [[(T.label):'Siblings',(from):1,(to):2],
                 [(T.label):'Siblings',(from):1,(to):3]]
==>[label:Siblings,OUT:1,IN:2]
==>[label:Siblings,OUT:1,IN:3]
gremlin> g.mergeV([(T.id):1,(T.label):'Dog',name:'Toby']) //// (1)
==>v[1]
gremlin> g.mergeV([(T.id):2,(T.label):'Dog',name:'Brandy'])
==>v[2]
gremlin> g.mergeV([(T.id):3,(T.label):'Dog',name:'Dax'])
==>v[3]
gremlin> g.inject(maps).unfold().mergeE() //// (2)
==>e[3][1-Siblings->2]
==>e[4][1-Siblings->3]
gremlin> g.E().elementMap()
==>[id:3,label:Siblings,IN:[id:2,label:Dog],OUT:[id:1,label:Dog]]
==>[id:4,label:Siblings,IN:[id:3,label:Dog],OUT:[id:1,label:Dog]]
```

```
maps = [[(T.label):'Siblings',(from):1,(to):2],
        [(T.label):'Siblings',(from):1,(to):3]]
g.mergeV([(T.id):1,(T.label):'Dog',name:'Toby']) //// (1)
g.mergeV([(T.id):2,(T.label):'Dog',name:'Brandy'])
g.mergeV([(T.id):3,(T.label):'Dog',name:'Dax'])
g.inject(maps).unfold().mergeE() //// (2)
g.E().elementMap()
```

1. Create three dogs.
2. Stream the edge maps into `mergeE()` steps.

The `mergeE` step can be combined with the `mergeV` step (or any other step producing a `Vertex`) using the
`Merge.outV` and `Merge.inV` option modulators. These options can be used to "late-bind" the `OUT` and `IN`
vertices in the main merge argument and in the `onCreate` argument:

console (groovy)

groovy

```
gremlin> g.mergeV([(T.id):1,(T.label):'Dog',name:'Toby']).as('Toby').
           mergeV([(T.id):2,(T.label):'Dog',name:'Brandy']).as('Brandy').
           mergeE([(T.label):'Sibling',created:'2022-02-07',(from):Merge.outV,(to):Merge.inV]).
             option(Merge.outV, select('Toby')).
             option(Merge.inV, select('Brandy'))
==>e[2][1-Sibling->2]
gremlin> g.E().elementMap()
==>[id:2,label:Sibling,IN:[id:2,label:Dog],OUT:[id:1,label:Dog],created:2022-02-07]
```

```
g.mergeV([(T.id):1,(T.label):'Dog',name:'Toby']).as('Toby').
  mergeV([(T.id):2,(T.label):'Dog',name:'Brandy']).as('Brandy').
  mergeE([(T.label):'Sibling',created:'2022-02-07',(from):Merge.outV,(to):Merge.inV]).
    option(Merge.outV, select('Toby')).
    option(Merge.inV, select('Brandy'))
g.E().elementMap()
```

The `Merge.outV` and `Merge.inV` tokens can be used as placeholders for values for `Direction.OUT` and `Direction.IN`
respectively in the `mergeE` arguments. These options can produce `Vertices`, as in the example above, or they can
specify `Maps`, which will be used to search for `Vertices` in the graph. This is useful when the exact `T.id` of
the from/to vertices is not known in advance:

console (groovy)

groovy

```
gremlin> g.mergeV([(T.label):'Dog',name:'Toby'])
==>v[0]
gremlin> g.mergeV([(T.label):'Dog',name:'Brandy'])
==>v[2]
gremlin> g.mergeE([(T.label):'Sibling',created:'2022-02-07',(from):Merge.outV,(to):Merge.inV]).
           option(Merge.outV, [(T.label):'Dog',name:'Toby']).
           option(Merge.inV, [(T.label):'Dog',name:'Brandy'])
==>e[4][0-Sibling->2]
gremlin> g.E().elementMap()
==>[id:4,label:Sibling,IN:[id:2,label:Dog],OUT:[id:0,label:Dog],created:2022-02-07]
```

```
g.mergeV([(T.label):'Dog',name:'Toby'])
g.mergeV([(T.label):'Dog',name:'Brandy'])
g.mergeE([(T.label):'Sibling',created:'2022-02-07',(from):Merge.outV,(to):Merge.inV]).
  option(Merge.outV, [(T.label):'Dog',name:'Toby']).
  option(Merge.inV, [(T.label):'Dog',name:'Brandy'])
g.E().elementMap()
```

**Additional References**

[`mergeE()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#mergeE()),
[`mergeE(Map)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#mergeE(java.util.Map)),
[`mergeE(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#mergeE(org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`Merge`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Merge.html),
[Semantics](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#_mergee)

### MergeVertex Step

The `mergeV()` -step is used to add vertices and their properties to a graph in a "create
if not exist" fashion. The `mergeV()` step can also be used to find vertices matching a given
pattern. The input passed to `mergeV()` can be either a `Map`, or a child `Traversal` that
produces a `Map`.

|  |  |
| --- | --- |
| Note | There is a corresponding [`mergeE()`](06-steps/start-steps.md#mergeedge-step) step that can be used when creating edges. |

Additionally, `option()` modulators may be combined with `mergeV()` to take action depending on
whether a vertex was created, or already existed. There are various ways `mergeV()` can
be used. The simplest being to provide a single `Map` of keys and values as a parameter. A `T.id`
and a `T.label` may also be provided but this is optional. The `mergeV()` step can be used directly
from the `GraphTraversalSource` - `g`, or in the middle of a traversal. For a match with an
existing vertex to occur, all values in the `Map` must exist on a vertex; otherwise, a new
vertex will be created. The examples that follow show how `mergeV()` can be used to add some
dogs to the graph.

console (groovy)

groovy

```
gremlin> g.mergeV([name: 'Brandy']) //// (1)
==>v[0]
gremlin> g.V().has('name','Brandy')
==>v[0]
gremlin> g.mergeV([(T.label):'Dog',name:'Scamp', age:12]) //// (2)
==>v[2]
gremlin> g.V().hasLabel('Dog').valueMap()
==>[name:[Scamp],age:[12]]
gremlin> g.mergeV([(T.id):300, (T.label):'Dog', name:'Toby', age:10]) //// (3)
==>v[300]
gremlin> g.V().hasLabel('Dog').valueMap().with(WithOptions.tokens)
==>[id:2,label:Dog,name:[Scamp],age:[12]]
==>[id:300,label:Dog,name:[Toby],age:[10]]
```

```
g.mergeV([name: 'Brandy']) //// (1)
g.V().has('name','Brandy')
g.mergeV([(T.label):'Dog',name:'Scamp', age:12]) //// (2)
g.V().hasLabel('Dog').valueMap()
g.mergeV([(T.id):300, (T.label):'Dog', name:'Toby', age:10]) //// (3)
g.V().hasLabel('Dog').valueMap().with(WithOptions.tokens)
```

1. Create a vertex for Brandy as no other matching ones exist yet.
2. Create a vertex for Scamp and also add a Dog label his age.
3. Create a vertex for Toby with an `T.id` of 300.

|  |  |
| --- | --- |
| Note | The example above is written with `gremlin-groovy` and evaluated in Gremlin Console as a Groovy script thus allowing [Groovy syntax](https://groovy-lang.org/syntax.html#_maps) for initializing a `Map`. |

If a vertex already exists that matches the map passed to `mergeV()`, the existing
vertex will be returned, otherwise a new one will be created. In this way, `mergeV()`
provides "get or create" semantics.

console (groovy)

groovy

```
gremlin> g.mergeV([name: 'Brandy']) //// (1)
==>v[0]
```

```
g.mergeV([name: 'Brandy']) //1
```

1. A vertex for Brandy already exists so return it. A new one is not created.

It’s important to note that every key/value pair passed to `mergeV()` must already exist on
one or more vertices for there to be a match. If a match is found, the vertex, or
vertices, representing that match will be returned. If a vertex representing a dog called
Brandy already exists, but it does not have an "age" property, the `mergeV()` below will not
find a match and a new vertex will be created.

console (groovy)

groovy

```
gremlin> g.addV('Dog').property('name','Brandy') //// (1)
==>v[0]
gremlin> g.mergeV([(T.label):'Dog',name:'Brandy',age:13]) //// (2)
==>v[2]
```

```
g.addV('Dog').property('name','Brandy') //// (1)
g.mergeV([(T.label):'Dog',name:'Brandy',age:13]) //2
```

1. Create a vertex for Brandy with no age property.
2. A new vertex is created as there is no exact match to any existing vertices.

A common scenario is to search for a vertex with a known `T.id` and if it exists return that
vertex. If it does not exist, create it. As we have seen, one way to do this is to pass
the `T.id` and all properties directly to `mergeV()`. Another is to use `Merge.onCreate`. Note
that the `Map` specified for `Match.onCreate` does not need to include the `T.id` already present
in the original search. The values provided to the `mergeV()` `Map` are inherited by the onCreate
action and combined with the `Map` provided to `Merge.onCreate`. Overrides of the `T.id` or `T.label`
in the onCreate `Map` are prohibited.

console (groovy)

groovy

```
gremlin> g.mergeV([(T.id):300]).
           option(Merge.onCreate,[(T.label):'Dog', name:'Toby', age:10])
==>v[300]
```

```
g.mergeV([(T.id):300]).
  option(Merge.onCreate,[(T.label):'Dog', name:'Toby', age:10])
```

To take specific action when the vertex already exists, `Merge.onMatch` can be used. The
second parameter to the `option` step can be either a `Map` whose values are used to update
the vertex or another Gremlin traversal that generates a `Map`.

|  |  |
| --- | --- |
| Note | If `mergeV()` is given an empty `Map`; such as `mergeV([:])`, it will match, and return, every vertex in the graph. This is the same behavior seen with `V([])`. |

console (groovy)

groovy

```
gremlin> g.mergeV([(T.id):300]).
           option(Merge.onCreate,[(T.label):'Dog', name:'Toby', age:10]). //// (1)
           option(Merge.onMatch,[age:11]) //// (2)
==>v[300]
gremlin> g.withSideEffect('new-data',[age:11]).
           mergeV([(T.id):300]).
           option(Merge.onCreate,[(T.label):'Dog', name:'Toby', age:10]).
           option(Merge.onMatch,select('new-data')) //// (3)
==>v[300]
gremlin> g.V(300).valueMap().with(WithOptions.tokens)
==>[id:300,label:Dog,name:[Toby],age:[11]]
```

```
g.mergeV([(T.id):300]).
  option(Merge.onCreate,[(T.label):'Dog', name:'Toby', age:10]). //// (1)
  option(Merge.onMatch,[age:11]) //// (2)
g.withSideEffect('new-data',[age:11]).
  mergeV([(T.id):300]).
  option(Merge.onCreate,[(T.label):'Dog', name:'Toby', age:10]).
  option(Merge.onMatch,select('new-data')) //// (3)
g.V(300).valueMap().with(WithOptions.tokens)
```

1. If no match found create the vertex using these values.
2. If a match is found, change the age property value.
3. Change the age property by selecting from the `new-data` map.

It is sometimes helpful to incorporate `fail()` step into scenarios where there is a need to stop the traversal
for one event or the other:

```
gremlin> g.mergeV([(T.id): 1]).
......1>     option(onCreate, fail("vertex did not exist")).
......2>     option(onMatch, [modified: 2022])
fail() Step Triggered
======================================================================================================================================================================
Message  > vertex did not exist
Traverser> false
  Bulk   > 1
Traversal> fail("vertex did not exist")
Parent   > TinkerMergeVertexStep [mergeV([(T.id):((int) 1)]).option(Merge.onCreate,__.fail("vertex did not exist")).option(Merge.onMatch,[("modified"):((int) 2022)])]
Metadata > {}
======================================================================================================================================================================
```

When working with multi-properties, there are two ways to specify them for `mergeV()`. First, you can specify them
individually using a `CardinalityValue` as the value in the `Map`. The `CardinalityValue` allows you to specify the
value as well as the `Cardinality` for that value. Note that it is only possible to specify one value with this syntax
even if you are using `set` or `list`.

console (groovy)

groovy

```
gremlin> g.mergeV([(T.label):'Dog', name:'Max']). //// (1)
             option(onCreate, [alias: set('Maximus')]). //// (2)
           property(set,'alias','Maxamillion') //// (3)
==>v[0]
gremlin> g.V().has('name','Max').valueMap().with(WithOptions.tokens)
==>[id:0,label:Dog,name:[Max],alias:[Maximus,Maxamillion]]
```

```
g.mergeV([(T.label):'Dog', name:'Max']). //// (1)
    option(onCreate, [alias: set('Maximus')]). //// (2)
  property(set,'alias','Maxamillion') //// (3)
g.V().has('name','Max').valueMap().with(WithOptions.tokens)
```

1. Find or create a vertex for Max.
2. If Max is not found then add an alias of `set` cardinality.
3. Whether Max was found or created, add another alias with `set` cardinality.

The second option is to specify `Cardinality` for the entire range of values as follows:

console (groovy)

groovy

```
gremlin> g.mergeV([(T.label):'Dog', name:'Max']).
             option(onCreate, [alias: 'Maximus', city: 'Boston'], set) //// (1)
==>v[0]
gremlin> g.mergeV([(T.label):'Dog', name:'Max']).
             option(onCreate, [alias: 'Maximus', city: single('Boston')], set) //// (2)
==>v[0]
```

```
g.mergeV([(T.label):'Dog', name:'Max']).
    option(onCreate, [alias: 'Maximus', city: 'Boston'], set) //// (1)
g.mergeV([(T.label):'Dog', name:'Max']).
    option(onCreate, [alias: 'Maximus', city: single('Boston')], set) //2
```

1. If Max is created then set the alias and city with cardinality of `set`.
2. If Max is created then set the alias with cardinality of `set` and city with cardinality `single`.

More than one vertex can be created by a single `mergeV()` operation. This is done by
injecting a `List` of `Map` objects into the traversal and letting them stream into the `mergeV()`
step.

console (groovy)

groovy

```
gremlin> maps = [[(T.label) : 'Dog', name: 'Toby'  , breed: 'Golden Retriever'],
                 [(T.label) : 'Dog', name: 'Brandy', breed: 'Golden Retriever'],
                 [(T.label) : 'Dog', name: 'Scamp' , breed: 'King Charles Spaniel'],
                 [(T.label) : 'Dog', name: 'Shadow', breed: 'Mixed'],
                 [(T.label) : 'Dog', name: 'Rocket', breed: 'Golden Retriever'],
                 [(T.label) : 'Dog', name: 'Dax'   , breed: 'Mixed'],
                 [(T.label) : 'Dog', name: 'Baxter', breed: 'Mixed'],
                 [(T.label) : 'Dog', name: 'Zoe'   , breed: 'Corgi'],
                 [(T.label) : 'Dog', name: 'Pixel' , breed: 'Mixed']]
==>[label:Dog,name:Toby,breed:Golden Retriever]
==>[label:Dog,name:Brandy,breed:Golden Retriever]
==>[label:Dog,name:Scamp,breed:King Charles Spaniel]
==>[label:Dog,name:Shadow,breed:Mixed]
==>[label:Dog,name:Rocket,breed:Golden Retriever]
==>[label:Dog,name:Dax,breed:Mixed]
==>[label:Dog,name:Baxter,breed:Mixed]
==>[label:Dog,name:Zoe,breed:Corgi]
==>[label:Dog,name:Pixel,breed:Mixed]
gremlin> g.inject(maps).unfold().mergeV()
==>v[0]
==>v[3]
==>v[6]
==>v[9]
==>v[12]
==>v[15]
==>v[18]
==>v[21]
==>v[24]
gremlin> g.V().hasLabel('Dog').valueMap().with(WithOptions.tokens)
==>[id:0,label:Dog,name:[Toby],breed:[Golden Retriever]]
==>[id:18,label:Dog,name:[Baxter],breed:[Mixed]]
==>[id:3,label:Dog,name:[Brandy],breed:[Golden Retriever]]
==>[id:21,label:Dog,name:[Zoe],breed:[Corgi]]
==>[id:6,label:Dog,name:[Scamp],breed:[King Charles Spaniel]]
==>[id:24,label:Dog,name:[Pixel],breed:[Mixed]]
==>[id:9,label:Dog,name:[Shadow],breed:[Mixed]]
==>[id:12,label:Dog,name:[Rocket],breed:[Golden Retriever]]
==>[id:15,label:Dog,name:[Dax],breed:[Mixed]]
```

```
maps = [[(T.label) : 'Dog', name: 'Toby'  , breed: 'Golden Retriever'],
        [(T.label) : 'Dog', name: 'Brandy', breed: 'Golden Retriever'],
        [(T.label) : 'Dog', name: 'Scamp' , breed: 'King Charles Spaniel'],
        [(T.label) : 'Dog', name: 'Shadow', breed: 'Mixed'],
        [(T.label) : 'Dog', name: 'Rocket', breed: 'Golden Retriever'],
        [(T.label) : 'Dog', name: 'Dax'   , breed: 'Mixed'],
        [(T.label) : 'Dog', name: 'Baxter', breed: 'Mixed'],
        [(T.label) : 'Dog', name: 'Zoe'   , breed: 'Corgi'],
        [(T.label) : 'Dog', name: 'Pixel' , breed: 'Mixed']]
g.inject(maps).unfold().mergeV()
g.V().hasLabel('Dog').valueMap().with(WithOptions.tokens)
```

Another useful pattern that can be used with `mergeV()` involves putting multiple maps in a
list and selecting different maps based on the action being taken. The examples below use
a list containing three maps. The first containing just the ID to be searched for. The
second map contains all the information to use when the vertex is created. The third map
contains additional information that will be applied if an existing vertex is found.

console (groovy)

groovy

```
gremlin> g.inject([[(T.id):400],[(T.label):'Dog',name:'Pixel',age:1],[updated:'2022-02-1']]).as('m').
           mergeV(select('m').limit(local,1).unfold()). //// (1)
           option(Merge.onCreate, select('m').range(local,1,2).unfold()). //// (2)
           option(Merge.onMatch, select('m').tail(local).unfold()) //// (3)
==>v[400]
gremlin> g.V(400).valueMap().with(WithOptions.tokens)
==>[id:400,label:Dog,name:[Pixel],age:[1]]
gremlin> g.inject([[(T.id):400],[(T.label):'Dog',name:'Pixel',age:1],[updated:'2022-02-1']]).as('m').
           mergeV(select('m').limit(local,1).unfold()).
           option(Merge.onCreate, select('m').range(local,1,2).unfold()).
           option(Merge.onMatch, select('m').tail(local).unfold()) //// (4)
==>v[400]
gremlin> g.V(400).valueMap().with(WithOptions.tokens) //// (5)
==>[id:400,label:Dog,name:[Pixel],updated:[2022-02-1],age:[1]]
```

```
g.inject([[(T.id):400],[(T.label):'Dog',name:'Pixel',age:1],[updated:'2022-02-1']]).as('m').
  mergeV(select('m').limit(local,1).unfold()). //// (1)
  option(Merge.onCreate, select('m').range(local,1,2).unfold()). //// (2)
  option(Merge.onMatch, select('m').tail(local).unfold()) //// (3)
g.V(400).valueMap().with(WithOptions.tokens)
g.inject([[(T.id):400],[(T.label):'Dog',name:'Pixel',age:1],[updated:'2022-02-1']]).as('m').
  mergeV(select('m').limit(local,1).unfold()).
  option(Merge.onCreate, select('m').range(local,1,2).unfold()).
  option(Merge.onMatch, select('m').tail(local).unfold()) //// (4)
g.V(400).valueMap().with(WithOptions.tokens)  //5
```

1. Use the first map to search for a vertex with an ID of 400.
2. If the vertex was not found, use the second map to create it.
3. If the vertex was found, add an `updated` property.
4. Pixel exists now, so we will take this option.
5. The `updated` property has now been added.

**Additional References**

[`mergeV()`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#mergeV()),
[`mergeV(Map)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#mergeV(java.util.Map)),
[`mergeV(Traversal)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#mergeV(org.apache.tinkerpop.gremlin.process.traversal.Traversal)),
[`Merge`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/Merge.html),
[Semantics](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#_mergee)

### Read Step

The `read()`-step is not really a "step" but a step modulator in that it modifies the functionality of the `io()`-step.
More specifically, it tells the `io()`-step that it is expected to use its configuration to read data from some
location. Please see the [documentation](06-steps/start-steps.md#io-step) for `io()`-step for more complete details on usage.

**Additional References**

[`read()`](https://tinkerpop.apache.org/javadocs/3.8.0/full/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#read())

### V Step

The `V()`-step is meant to read vertices from the graph and is usually used to start a `GraphTraversal`, but can also
be used mid-traversal.

console (groovy)

groovy

```
gremlin> g.V(1) //// (1)
==>v[1]
gremlin> g.V().has('name', within('marko', 'vadas', 'josh')).as('person').
           V().has('name', within('lop', 'ripple')).addE('uses').from('person') //// (2)
==>e[0][1-uses->3]
==>e[13][1-uses->5]
==>e[14][2-uses->3]
==>e[15][2-uses->5]
==>e[16][4-uses->3]
==>e[17][4-uses->5]
```

```
g.V(1) //// (1)
g.V().has('name', within('marko', 'vadas', 'josh')).as('person').
  V().has('name', within('lop', 'ripple')).addE('uses').from('person') //2
```

1. Find the vertex by its unique identifier (i.e. `T.id`) - not all graphs will use a numeric value for their identifier.
2. An example where `V()` is used both as a start step and in the middle of a traversal.

|  |  |
| --- | --- |
| Note | Whether a mid-traversal `V()` uses an index or not, depends on a) whether suitable index exists and b) if the particular graph system provider implemented this functionality. |

console (groovy)

groovy

```
gremlin> g.V().has('name', within('marko', 'vadas', 'josh')).as('person').
           V().has('name', within('lop', 'ripple')).addE('uses').from('person').toString() //// (1)
==>[GraphStep(vertex,[]), HasStep([name.within([marko, vadas, josh])])@[person], GraphStep(vertex,[]), HasStep([name.within([lop, ripple])]), AddEdgeStepPlaceholder]
gremlin> g.V().has('name', within('marko', 'vadas', 'josh')).as('person').
           V().has('name', within('lop', 'ripple')).addE('uses').from('person').iterate().toString() //// (2)
==>[TinkerGraphStep(vertex,[name.within([marko, vadas, josh])])@[person], TinkerGraphStep(vertex,[name.within([lop, ripple])]), AddEdgeStep({~from=[[SelectOneStep(last,person,null)]], label=[uses]}), DiscardStep]
```

```
g.V().has('name', within('marko', 'vadas', 'josh')).as('person').
  V().has('name', within('lop', 'ripple')).addE('uses').from('person').toString() //// (1)
g.V().has('name', within('marko', 'vadas', 'josh')).as('person').
  V().has('name', within('lop', 'ripple')).addE('uses').from('person').iterate().toString() //2
```

1. Normally the `V()`-step will iterate over all vertices. However, graph strategies can fold `HasContainer`'s into a `GraphStep` to allow index lookups.
2. Whether the graph system provider supports mid-traversal `V()` index lookups or not can easily be determined by inspecting the `toString()` output of the iterated traversal. If `has` conditions were folded into the `V()`-step, an index - if one exists - will be used.

**Additional References**

[`V(Object…​)`](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#V(java.lang.Object...))

### Write Step

The `write()`-step is not really a "step" but a step modulator in that it modifies the functionality of the `io()`-step.
More specifically, it tells the `io()`-step that it is expected to use its configuration to write data to some
location. Please see the [documentation](06-steps/start-steps.md#io-step) for `io()`-step for more complete details on usage.

**Additional References**

[`write()`](https://tinkerpop.apache.org/javadocs/3.8.0/full/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html#write())

