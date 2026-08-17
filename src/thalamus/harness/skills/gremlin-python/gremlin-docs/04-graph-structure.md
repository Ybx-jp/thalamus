### The Graph Structure

![gremlin standing](../images/gremlin-standing.png) A graph’s structure is the topology formed by the explicit references
between its vertices, edges, and properties. A vertex has incident edges. A vertex is adjacent to another vertex if
they share an incident edge. A property is attached to an element and an element has a set of properties. A property
is a key/value pair, where the key is always a character `String`. Conceptual knowledge of how a graph is composed is
essential to end-users working with graphs, however, as mentioned earlier, the structure API is not the appropriate
way for users to think when building applications with TinkerPop. The structure API is reserved for usage by graph
providers. Those interested in implementing the structure API to make their graph system TinkerPop enabled can learn
more about it in the [Graph Provider](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/) documentation.

# The Graph

![gremlin standing](../images/gremlin-standing.png)

The [Introduction](01-introduction.md#intro) discussed the diversity of TinkerPop-enabled graphs, with special attention paid to the
different [connection models](02-connecting.md#connecting-gremlin), and how TinkerPop makes it possible to bridge that diversity in
an [agnostic](#staying-agnostic) manner. This particular section deals with elements of the Graph API which was noted
as an API to avoid when trying to build an agnostic system. The Graph API refers to the core elements of what composes
the [structure of a graph](01-introduction.md#graph-computing) within the Gremlin Traversal Machine (GTM), such as the `Graph`, `Vertex`
and `Edge` Java interfaces.

To maintain the most portable code, users should only reference these interfaces. To "reference", simply means to
utilize it as a pointer. For `Graph`, that means holding a pointer to the location of graph data and then using it to
spawn `GraphTraversalSource` instances so as to write Gremlin:

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.addV('person')
==>v[0]
```

```
graph = TinkerGraph.open()
g = traversal().with(graph)
g.addV('person')
```

In the above example, "graph" is the `Graph` interface produced by calling `open()` on `TinkerGraph` which creates the
instance. Note that while the end intent of the code is to create a "person" vertex, it does not use the APIs on
`Graph` to do that - e.g. `graph.addVertex(T.label,'person')`.

Even if the developer desired to use the `graph.addVertex()` method there are only a handful of scenarios where it is
possible:

* The application is being developed on the JVM and the developer is using [embedded](#connecting-embedded) mode
* The architecture includes Gremlin Server and the user is sending Gremlin scripts to the server
* The graph system chosen is a [Remote Gremlin Provider](#connecting-rgp) and they expose the Graph API via scripts

Note that Gremlin Language Variants force developers to use the Graph API by reference. There is no `addVertex()`
method available to GLVs on their respective `Graph` instances, nor are their graph elements filled with data at the
call of `properties()`. Developing applications to meet this lowest common denominator in API usage will go a long
way to making that application portable across TinkerPop-enabled systems.

When considering the remaining sub-sections that follow, recall that they are all generally bound to the Graph API.
They are described here for reference and in some sense backward compatibility with older recommended models of
development. In the future, the contents of this section will become less and less relevant.

## Features

A `Feature` implementation describes the capabilities of a `Graph` instance. This interface is implemented by graph
system providers for two purposes:

1. It tells users the capabilities of their `Graph` instance.
2. It allows the features they do comply with to be tested against the Gremlin Test Suite - tests that do not comply are "ignored").

The following example in the Gremlin Console shows how to print all the features of a `Graph`:

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> graph.features()
==>FEATURES
> GraphFeatures
>-- Computer: true
>-- Persistence: true
>-- ConcurrentAccess: false
>-- IoRead: true
>-- IoWrite: true
>-- ServiceCall: true
>-- Transactions: false
>-- ThreadedTransactions: false
>-- OrderabilitySemantics: true
> VariableFeatures
>-- Variables: true
>-- BooleanValues: true
>-- ByteValues: true
>-- DoubleValues: true
>-- FloatValues: true
>-- IntegerValues: true
>-- LongValues: true
>-- MapValues: true
>-- MixedListValues: true
>-- SerializableValues: true
>-- StringValues: true
>-- UniformListValues: true
>-- BooleanArrayValues: true
>-- ByteArrayValues: true
>-- DoubleArrayValues: true
>-- FloatArrayValues: true
>-- IntegerArrayValues: true
>-- LongArrayValues: true
>-- StringArrayValues: true
> VertexFeatures
>-- MetaProperties: true
>-- Upsert: false
>-- AddVertices: true
>-- RemoveVertices: true
>-- MultiProperties: true
>-- DuplicateMultiProperties: true
>-- AddProperty: true
>-- RemoveProperty: true
>-- NumericIds: true
>-- StringIds: true
>-- UuidIds: true
>-- CustomIds: false
>-- AnyIds: true
>-- UserSuppliedIds: true
>-- NullPropertyValues: false
> VertexPropertyFeatures
>-- RemoveProperty: true
>-- NumericIds: true
>-- StringIds: true
>-- UuidIds: true
>-- CustomIds: false
>-- AnyIds: true
>-- UserSuppliedIds: true
>-- NullPropertyValues: false
>-- Properties: true
>-- BooleanValues: true
>-- ByteValues: true
>-- DoubleValues: true
>-- FloatValues: true
>-- IntegerValues: true
>-- LongValues: true
>-- MapValues: true
>-- MixedListValues: true
>-- SerializableValues: true
>-- StringValues: true
>-- UniformListValues: true
>-- BooleanArrayValues: true
>-- ByteArrayValues: true
>-- DoubleArrayValues: true
>-- FloatArrayValues: true
>-- IntegerArrayValues: true
>-- LongArrayValues: true
>-- StringArrayValues: true
> EdgeFeatures
>-- AddEdges: true
>-- RemoveEdges: true
>-- Upsert: false
>-- AddProperty: true
>-- RemoveProperty: true
>-- NumericIds: true
>-- StringIds: true
>-- UuidIds: true
>-- CustomIds: false
>-- AnyIds: true
>-- UserSuppliedIds: true
>-- NullPropertyValues: false
> EdgePropertyFeatures
>-- Properties: true
>-- BooleanValues: true
>-- ByteValues: true
>-- DoubleValues: true
>-- FloatValues: true
>-- IntegerValues: true
>-- LongValues: true
>-- MapValues: true
>-- MixedListValues: true
>-- SerializableValues: true
>-- StringValues: true
>-- UniformListValues: true
>-- BooleanArrayValues: true
>-- ByteArrayValues: true
>-- DoubleArrayValues: true
>-- FloatArrayValues: true
>-- IntegerArrayValues: true
>-- LongArrayValues: true
>-- StringArrayValues: true
```

```
graph = TinkerGraph.open()
graph.features()
```

A common pattern for using features is to check their support prior to performing an operation:

console (groovy)

groovy

```
gremlin> graph.features().graph().supportsTransactions()
==>false
gremlin> graph.features().graph().supportsTransactions() ? g.tx().commit() : "no tx"
==>no tx
```

```
graph.features().graph().supportsTransactions()
graph.features().graph().supportsTransactions() ? g.tx().commit() : "no tx"
```

|  |  |
| --- | --- |
| Tip | To ensure provider agnostic code, always check feature support prior to usage of a particular function. In that way, the application can behave gracefully in case a particular implementation is provided at runtime that does not support a function being accessed. |

|  |  |
| --- | --- |
| Warning | Features of reference graphs which are used to connect to remote graphs do not reflect the features of the graph to which it connects. It reflects the features of instantiated graph itself, which will likely be quite different considering that reference graphs will typically be immutable. |

## Vertex Properties

![vertex properties](../images/vertex-properties.png) TinkerPop introduces the concept of a `VertexProperty<V>`. All the
properties of a `Vertex` are a `VertexProperty`. A `VertexProperty` implements `Property` and as such, it has a
key/value pair. However, `VertexProperty` also implements `Element` and thus, can have a collection of key/value
pairs. Moreover, while an `Edge` can only have one property of key "name" (for example), a `Vertex` can have multiple
"name" properties. With the inclusion of vertex properties, two features are introduced which ultimately advance the
graph modelers toolkit:

1. Multiple properties (**multi-properties**): a vertex property key can have multiple values. For example, a vertex can
   have multiple "name" properties.
2. Properties on properties (**meta-properties**): a vertex property can have properties (i.e. a vertex property can
   have key/value data associated with it).

Possible use cases for meta-properties:

1. **Permissions**: Vertex properties can have key/value ACL-type permission information associated with them.
2. **Auditing**: When a vertex property is manipulated, it can have key/value information attached to it saying who the
   creator, deletor, etc. are.
3. **Provenance**: The "name" of a vertex can be declared by multiple users. For example, there may be multiple spellings
   of a name from different sources.

A running example using vertex properties is provided below to demonstrate and explain the API.

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> v = g.addV().property('name','marko').property('name','marko a. rodriguez').next()
==>v[0]
gremlin> g.V(v).properties('name').count() //// (1)
==>2
gremlin> v.property(list, 'name', 'm. a. rodriguez') //// (2)
==>vp[name->m. a. rodriguez]
gremlin> g.V(v).properties('name').count()
==>3
gremlin> g.V(v).properties()
==>vp[name->marko]
==>vp[name->marko a. rodriguez]
==>vp[name->m. a. rodriguez]
gremlin> g.V(v).properties('name')
==>vp[name->marko]
==>vp[name->marko a. rodriguez]
==>vp[name->m. a. rodriguez]
gremlin> g.V(v).properties('name').hasValue('marko')
==>vp[name->marko]
gremlin> g.V(v).properties('name').hasValue('marko').property('acl','private') //// (3)
==>vp[name->marko]
gremlin> g.V(v).properties('name').hasValue('marko a. rodriguez')
==>vp[name->marko a. rodriguez]
gremlin> g.V(v).properties('name').hasValue('marko a. rodriguez').property('acl','public')
==>vp[name->marko a. rodriguez]
gremlin> g.V(v).properties('name').has('acl','public').value()
==>marko a. rodriguez
gremlin> g.V(v).properties('name').has('acl','public').drop() //// (4)
gremlin> g.V(v).properties('name').has('acl','public').value()
gremlin> g.V(v).properties('name').has('acl','private').value()
==>marko
gremlin> g.V(v).properties()
==>vp[name->marko]
==>vp[name->m. a. rodriguez]
gremlin> g.V(v).properties().properties() //// (5)
==>p[acl->private]
gremlin> g.V(v).properties().property('date',2014) //// (6)
==>vp[name->marko]
==>vp[name->m. a. rodriguez]
gremlin> g.V(v).properties().property('creator','stephen')
==>vp[name->marko]
==>vp[name->m. a. rodriguez]
gremlin> g.V(v).properties().properties()
==>p[date->2014]
==>p[creator->stephen]
==>p[acl->private]
==>p[date->2014]
==>p[creator->stephen]
gremlin> g.V(v).properties('name').valueMap()
==>[date:2014,creator:stephen,acl:private]
==>[date:2014,creator:stephen]
gremlin> g.V(v).property('name','okram') //// (7)
==>v[0]
gremlin> g.V(v).properties('name')
==>vp[name->okram]
gremlin> g.V(v).values('name') //// (8)
==>okram
```

```
graph = TinkerGraph.open()
g = traversal().with(graph)
v = g.addV().property('name','marko').property('name','marko a. rodriguez').next()
g.V(v).properties('name').count() //// (1)
v.property(list, 'name', 'm. a. rodriguez') //// (2)
g.V(v).properties('name').count()
g.V(v).properties()
g.V(v).properties('name')
g.V(v).properties('name').hasValue('marko')
g.V(v).properties('name').hasValue('marko').property('acl','private') //// (3)
g.V(v).properties('name').hasValue('marko a. rodriguez')
g.V(v).properties('name').hasValue('marko a. rodriguez').property('acl','public')
g.V(v).properties('name').has('acl','public').value()
g.V(v).properties('name').has('acl','public').drop() //// (4)
g.V(v).properties('name').has('acl','public').value()
g.V(v).properties('name').has('acl','private').value()
g.V(v).properties()
g.V(v).properties().properties() //// (5)
g.V(v).properties().property('date',2014) //// (6)
g.V(v).properties().property('creator','stephen')
g.V(v).properties().properties()
g.V(v).properties('name').valueMap()
g.V(v).property('name','okram') //// (7)
g.V(v).properties('name')
g.V(v).values('name') //8
```

1. A vertex can have zero or more properties with the same key associated with it.
2. If a property is added with a cardinality of `Cardinality.list`, an additional property with the provided key will be added.
3. A vertex property can have standard key/value properties attached to it.
4. Vertex property removal is identical to property removal.
5. Gets the meta-properties of each vertex property.
6. A vertex property can have any number of key/value properties attached to it.
7. `property(…​)` will remove all existing key’d properties before adding the new single property (see `VertexProperty.Cardinality`).
8. If only the value of a property is needed, then `values()` can be used.

If the concept of vertex properties is difficult to grasp, then it may be best to think of vertex properties in terms
of "literal vertices." A vertex can have an edge to a "literal vertex" that has a single value key/value — e.g.
"value=okram." The edge that points to that literal vertex has an edge-label of "name." The properties on the edge
represent the literal vertex’s properties. The "literal vertex" can not have any other edges to it (only one from the
associated vertex).

|  |  |
| --- | --- |
| Tip | A toy graph demonstrating all of the new TinkerPop graph structure features is available at `TinkerFactory.createTheCrew()` and `data/tinkerpop-crew*`. This graph demonstrates multi-properties and meta-properties. |

![the crew graph](../images/the-crew-graph.png)

Figure 3. TinkerPop Crew

console (groovy)

groovy

```
gremlin> g.V().as('a').
               properties('location').as('b').
               hasNot('endTime').as('c').
               select('a','b','c').by('name').by(value).by('startTime') // determine the current location of each person
==>[a:marko,b:santa fe,c:2005]
==>[a:stephen,b:purcellville,c:2006]
==>[a:matthias,b:seattle,c:2014]
==>[a:daniel,b:aachen,c:2009]
gremlin> g.V().has('name','gremlin').inE('uses').
               order().by('skill',asc).as('a').
               outV().as('b').
               select('a','b').by('skill').by('name') // rank the users of gremlin by their skill level
==>[a:3,b:matthias]
==>[a:4,b:marko]
==>[a:5,b:stephen]
==>[a:5,b:daniel]
```

```
g.V().as('a').
      properties('location').as('b').
      hasNot('endTime').as('c').
      select('a','b','c').by('name').by(value).by('startTime') // determine the current location of each person
g.V().has('name','gremlin').inE('uses').
      order().by('skill',asc).as('a').
      outV().as('b').
      select('a','b').by('skill').by('name') // rank the users of gremlin by their skill level
```

## Graph Variables

`Graph.Variables` are key/value pairs associated with the graph itself — in essence, a `Map<String,Object>`. These
variables are intended to store metadata about the graph. Example use cases include:

* **Schema information**: What do the namespace prefixes resolve to and when was the schema last modified?
* **Global permissions**: What are the access rights for particular groups?
* **System user information**: Who are the admins of the system?

An example of graph variables in use is presented below:

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> graph.variables()
==>variables[size:0]
gremlin> graph.variables().set('systemAdmins',['stephen','peter','pavel'])
==>null
gremlin> graph.variables().set('systemUsers',['matthias','marko','josh'])
==>null
gremlin> graph.variables().keys()
==>systemAdmins
==>systemUsers
gremlin> graph.variables().get('systemUsers')
==>Optional[[matthias, marko, josh]]
gremlin> graph.variables().get('systemUsers').get()
==>matthias
==>marko
==>josh
gremlin> graph.variables().remove('systemAdmins')
==>null
gremlin> graph.variables().keys()
==>systemUsers
```

```
graph = TinkerGraph.open()
graph.variables()
graph.variables().set('systemAdmins',['stephen','peter','pavel'])
graph.variables().set('systemUsers',['matthias','marko','josh'])
graph.variables().keys()
graph.variables().get('systemUsers')
graph.variables().get('systemUsers').get()
graph.variables().remove('systemAdmins')
graph.variables().keys()
```

|  |  |
| --- | --- |
| Important | Graph variables are not intended to be subject to heavy, concurrent mutation nor to be used in complex computations. The intention is to have a location to store data about the graph for administrative purposes. |

|  |  |
| --- | --- |
| Warning | Attempting to set graph variables in a reference graph will not promote them to the remote graph. Typically, a reference graph has immutable features and will not support this features. |

## Namespace Conventions

End users, [graph system providers](13-tinkergraph.md#implementations), [`GraphComputer`](09-graphcomputer.md#graphcomputer) algorithm designers,
[GremlinPlugin](11-gremlin-server.md#gremlin-plugins) creators, etc. all leverage properties on elements to store information. There are
a few conventions that should be respected when naming property keys to ensure that conflicts between these
stakeholders do not conflict.

* End users are granted the *flat namespace* (e.g. `name`, `age`, `location`) to key their properties and label their elements.
* Graph system providers are granted the *hidden namespace* (e.g. `~metadata`) to key their properties and labels.
  Data keyed as such is only accessible via the graph system implementation and no other stakeholders are granted read
  nor write access to data prefixed with "~" (see `Graph.Hidden`). Test coverage and exceptions exist to ensure that
  graph systems respect this hard boundary.
* [`VertexProgram`](#vertexprogram) and [`MapReduce`](#mapreduce) developers should leverage *qualified namespaces*
  particular to their domain (e.g. `mydomain.myvertexprogram.computedata`).
* `GremlinPlugin` creators should prefix their plugin name with their domain (e.g. `mydomain.myplugin`).

|  |  |
| --- | --- |
| Important | TinkerPop uses `tinkerpop.` and `gremlin.` as the prefixes for provided strategies, vertex programs, map reduce implementations, and plugins. |

The only truly protected namespace is the *hidden namespace* provided to graph systems. From there, it’s up to
engineers to respect the namespacing conventions presented.

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

## Graph Filter

Most OLAP jobs do not require the entire source graph to faithfully execute their `VertexProgram`. For instance, if
`PageRankVertexProgram` is only going to compute the centrality of people in the friendship-graph, then the following
`GraphFilter` can be applied.

```
graph.computer().
  vertices(hasLabel("person")).
  vertexProperties(__.properties("name")).
  edges(bothE("knows")).
  program(PageRankVertexProgram...)
```

There are three methods for constructing a `GraphFilter`.

* `vertices(Traversal<Vertex,Vertex>)`: A traversal that will be used that can only analyze a vertex and its properties.
  If the traversal `hasNext()`, the input `Vertex` is passed to the `GraphComputer`.
* `vertexProperties(Traversal<Vertex, ? extends Property<?>)`: A traversal that will either let the vertex property pass or not.
* `edges(Traversal<Vertex,Edge>)`: A traversal that will iterate all legal edges for the source vertex.

`GraphFilter` is a "push-down predicate" that providers can reason on to determine the most efficient way to provide
graph data to the `GraphComputer`.

|  |  |
| --- | --- |
| Important | Apache TinkerPop provides `GraphFilterStrategy` [traversal strategy](07-traversal-strategies.md#traversalstrategy) which analyzes a submitted OLAP traversal and, if possible, creates an appropriate `GraphFilter` automatically. For instance, `g.V().count()` would yield a `GraphFilter.edges(limit(0))`. Thus, for traversal submissions, users typically do not need to be aware of creating graph filters explicitly. Users can use the [`explain()`](06-steps/terminal-steps.md#explain-step)-step to see the `GraphFilter` generated by `GraphFilterStrategy`. |

### Graph Plugins

This section does not refer to a specific Gremlin Plugin, but a class of them. Graph Plugins are typically created by
graph providers to make it easy to integrate their graph systems into Gremlin Console and Gremlin Server. As TinkerPop
provides two reference `Graph` implementations in [TinkerGraph](13-tinkergraph.md#tinkergraph-gremlin) and [Neo4j](#neo4j-gremlin),
there is also one Gremlin Plugin for each of them.

The TinkerGraph plugin is installed and activated in the Gremlin Console by default and the sample configurations that
are supplied with the Gremlin Server distribution include the `TinkerGraphGremlinPlugin` as part of the default setup.
If using Neo4j, however, the plugin must be installed manually. Instructions for doing so can be found in the
[Neo4j](#neo4j-gremlin) section.

#### GraphSON I/O Format

* **InputFormat**: `org.apache.tinkerpop.gremlin.hadoop.structure.io.graphson.GraphSONInputFormat`
* **OutputFormat**: `org.apache.tinkerpop.gremlin.hadoop.structure.io.graphson.GraphSONOutputFormat`

[GraphSON](04-graph-structure.md#graphson) is a JSON based graph format. GraphSON is a space-expensive graph format in that
it is a text-based markup language. However, it is convenient for many developers to work with as its structure is
simple (easy to create and parse).

The data below represents an adjacency list representation of the classic TinkerGraph toy graph in GraphSON format.

```
{"id":1,"label":"person","outE":{"created":[{"id":9,"inV":3,"properties":{"weight":0.4}}],"knows":[{"id":7,"inV":2,"properties":{"weight":0.5}},{"id":8,"inV":4,"properties":{"weight":1.0}}]},"properties":{"name":[{"id":0,"value":"marko"}],"age":[{"id":1,"value":29}]}}
{"id":2,"label":"person","inE":{"knows":[{"id":7,"outV":1,"properties":{"weight":0.5}}]},"properties":{"name":[{"id":2,"value":"vadas"}],"age":[{"id":3,"value":27}]}}
{"id":3,"label":"software","inE":{"created":[{"id":9,"outV":1,"properties":{"weight":0.4}},{"id":11,"outV":4,"properties":{"weight":0.4}},{"id":12,"outV":6,"properties":{"weight":0.2}}]},"properties":{"name":[{"id":4,"value":"lop"}],"lang":[{"id":5,"value":"java"}]}}
{"id":4,"label":"person","inE":{"knows":[{"id":8,"outV":1,"properties":{"weight":1.0}}]},"outE":{"created":[{"id":10,"inV":5,"properties":{"weight":1.0}},{"id":11,"inV":3,"properties":{"weight":0.4}}]},"properties":{"name":[{"id":6,"value":"josh"}],"age":[{"id":7,"value":32}]}}
{"id":5,"label":"software","inE":{"created":[{"id":10,"outV":4,"properties":{"weight":1.0}}]},"properties":{"name":[{"id":8,"value":"ripple"}],"lang":[{"id":9,"value":"java"}]}}
{"id":6,"label":"person","outE":{"created":[{"id":12,"inV":3,"properties":{"weight":0.2}}]},"properties":{"name":[{"id":10,"value":"peter"}],"age":[{"id":11,"value":35}]}}
```

