# Implementations

![gremlin racecar](../images/gremlin-racecar.png)

TinkerPop offers several reference implementations of its interfaces that are not only meant for production usage,
but also represent models by which different graph providers can build their systems. More specific documentation
on how to build systems at this level of the API can be found in the
[Provider Documentation](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/). The following sections
describe the various reference implementations and their usage.

## TinkerGraph-Gremlin

```
<dependency>
   <groupId>org.apache.tinkerpop</groupId>
   <artifactId>tinkergraph-gremlin</artifactId>
   <version>3.8.0</version>
</dependency>

<!--
  For a minimal version without sample datasets where TinkerFactory will not load the
  Air Routes or Grateful Dead dataset.
-->
<dependency>
   <groupId>org.apache.tinkerpop</groupId>
   <artifactId>tinkergraph-gremlin</artifactId>
   <version>3.8.0</version>
   <classifier>min</classifier>
</dependency>
```

![tinkerpop character](../images/tinkerpop-character.png) TinkerGraph is a single machine, in-memory (with optional
persistence), graph engine that provides both OLTP and OLAP functionality. It is non-transactional by default but does
have a lightweight transactional form that can be instantiated offering simple `ThreadLocal` transactions supporting
`read committed` transaction isolation. TinkerGraph is deployed with TinkerPop and serves as the reference
implementation for other providers to study in order to understand the semantics of the various methods of the
TinkerPop API. Its status as a reference implementation does not however imply that it is not suitable for production.
TinkerGraph has many practical use cases in production applications and their development. Some examples of TinkerGraph
use cases include:

* Ad-hoc analysis of large immutable graphs that fit in memory.
* Extract subgraphs, from larger graphs that don’t fit in memory, into TinkerGraph for further analysis or other
  purposes.
* Use TinkerGraph as a sandbox to develop and debug complex traversals by simulating data from a larger graph inside
  a TinkerGraph.
* Configure it to match the semantics of a production graph database for unit testing purpose to simplify development
  setup and automated builds.

Constructing a simple graph using TinkerGraph in Java is presented below:

```
Graph graph = TinkerGraph.open();
GraphTraversalSource g = traversal().with(graph);
Vertex marko = g.addV("person").property("name","marko").property("age",29).next();
Vertex lop = g.addV("software").property("name","lop").property("lang","java").next();
g.addE("created").from(marko).to(lop).property("weight",0.6d).iterate();
```

The above Gremlin creates two vertices named "marko" and "lop" and connects them via a created-edge with a weight=0.6
property. The addition of these two vertices and the edge between them could also be done in a single Gremlin statement
as follows:

```
g.addV("person").property("name","marko").property("age",29).as("m").
  addV("software").property("name","lop").property("lang","java").as("l").
  addE("created").from("m").to("l").property("weight",0.6d).iterate();
```

|  |  |
| --- | --- |
| Important | Pay attention to the fact that traversals end with `next()` or `iterate()`. These methods advance the objects in the traversal stream and without those methods, the traversal does nothing. Review the [Result Iteration Section](https://tinkerpop.apache.org/docs/3.8.0/tutorials/the-gremlin-console/#result-iteration) of The Gremlin Console tutorial for more information. |

Next, the graph can be queried as such.

```
g.V().has("name","marko").out("created").values("name")
```

The `g.V().has("name","marko")` part of the query can be executed in two ways.

* A linear scan of all vertices filtering out those vertices that don’t have the name "marko"
* A `O(log(|V|))` index lookup for all vertices with the name "marko"

Given the initial graph construction in the first code block, no index was defined and thus, a linear scan is executed.
However, if the graph was constructed as such, then an index lookup would be used.

```
Graph g = TinkerGraph.open();
g.createIndex("name",Vertex.class)
```

The execution times for a vertex lookup by property is provided below for both no-index and indexed version of
TinkerGraph over the Grateful Dead graph.

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.io('data/grateful-dead.xml').read().iterate()
gremlin> clock(1000) {g.V().has('name','Garcia').iterate()} //// (1)
==>0.12759067
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> graph.createIndex('name',Vertex.class)
==>null
gremlin> g.io('data/grateful-dead.xml').read().iterate()
gremlin> clock(1000){g.V().has('name','Garcia').iterate()} //// (2)
==>0.027926219999999998
```

```
graph = TinkerGraph.open()
g = traversal().with(graph)
g.io('data/grateful-dead.xml').read().iterate()
clock(1000) {g.V().has('name','Garcia').iterate()} //// (1)
graph = TinkerGraph.open()
g = traversal().with(graph)
graph.createIndex('name',Vertex.class)
g.io('data/grateful-dead.xml').read().iterate()
clock(1000){g.V().has('name','Garcia').iterate()} //2
```

1. Determine the average runtime of 1000 vertex lookups when no `name`-index is defined.
2. Determine the average runtime of 1000 vertex lookups when a `name`-index is defined.

|  |  |
| --- | --- |
| Important | Each graph system will have different mechanism by which indices and schemas are defined. TinkerPop does not require any conformance in this area. In TinkerGraph, the only definitions are around indices. With other graph systems, property value types, indices, edge labels, etc. may be required to be defined *a priori* to adding data to the graph. |

|  |  |
| --- | --- |
| Note | TinkerGraph is distributed with Gremlin Server and is therefore automatically available to it for configuration. |

### Data Types

TinkerGraph can store any Java `Object` for a property value. It is therefore important to take note of the types of
the values that are being used and it is often best to be explicit in terms of exactly what type is being used,
especially in the case of numbers.

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.addV().property('vp2',0.65780294)
==>v[0]
gremlin> g.addV().property('vp2',0.65780294f)
==>v[2]
gremlin> g.addV().property('vp2',0.65780294d)
==>v[4]
gremlin> g.V().has('vp2',0.65780294) //// (1)
==>v[0]
==>v[2]
==>v[4]
gremlin> g.V().has('vp2',0.65780294f) //// (2)
==>v[0]
==>v[2]
gremlin> g.V().has('vp2',0.65780294d) //// (3)
==>v[0]
==>v[4]
```

```
graph = TinkerGraph.open()
g = traversal().with(graph)
g.addV().property('vp2',0.65780294)
g.addV().property('vp2',0.65780294f)
g.addV().property('vp2',0.65780294d)
g.V().has('vp2',0.65780294) //// (1)
g.V().has('vp2',0.65780294f) //// (2)
g.V().has('vp2',0.65780294d)    //3
```

1. In Gremlin Console, `0.65780294` actually evaluates to a `BigDecimal`, which won’t match the specifically typed
   `float` property value.
2. The explicit `float` will only match the `float` property value.
3. The explicit `double` will only match the `double` and `BigDecimal` values.

Unlike other graphs, the above demonstration shows that TinkerGraph does not do any form of type coercion (except for
type coercion related to element identifiers as described in the [tinkergraph-configuration](#next section)).

### Configuration

TinkerGraph has several settings that can be provided on creation via `Configuration` object:

| Property | Description |
| --- | --- |
| gremlin.graph | `org.apache.tinkerpop.gremlin.tinkergraph.structure.TinkerGraph` |
| gremlin.tinkergraph.vertexIdManager | The `IdManager` implementation to use for vertices. |
| gremlin.tinkergraph.edgeIdManager | The `IdManager` implementation to use for edges. |
| gremlin.tinkergraph.vertexPropertyIdManager | The `IdManager` implementation to use for vertex properties. |
| gremlin.tinkergraph.defaultVertexPropertyCardinality | The default `VertexProperty.Cardinality` to use when `Vertex.property(k,v)` is called. |
| gremlin.tinkergraph.allowNullPropertyValues | A boolean value that determines whether or not `null` property values are allowed and defaults to `false`. |
| gremlin.tinkergraph.graphLocation | The path and file name for where TinkerGraph should persist the graph data. If a value is specified here, the `gremlin.tinkergraph.graphFormat` should also be specified. If this value is not included (default), then the graph will stay in-memory and not be loaded/persisted to disk. |
| gremlin.tinkergraph.graphFormat | The format to use to serialize the graph which may be one of the following: `graphml`, `graphson`, `gryo`, or a fully qualified class name that implements Io.Builder interface (which allows for external third party graph reader/writer formats to be used for persistence). If a value is specified here, then the `gremlin.tinkergraph.graphLocation` should also be specified. If this value is not included (default), then the graph will stay in-memory and not be loaded/persisted to disk. |

|  |  |
| --- | --- |
| Note | To use [transactions](13-tinkergraph.md#tinkergraph-gremlin-tx), configure `gremlin.graph` as `org.apache.tinkerpop.gremlin.tinkergraph.structure.TinkerTransactionGraph`. |

The `IdManager` settings above refer to how TinkerGraph will control identifiers for vertices, edges and vertex
properties. There are several options for each of these settings: `ANY`, `LONG`, `INTEGER`, `UUID`, `STRING` or the
fully qualified class name of an `IdManager` implementation on the classpath. When not specified, the default values
for all settings is `ANY`, meaning that the graph will work with any object on the JVM as the identifier and will
generate new identifiers from `Long` when the identifier is not user supplied. TinkerGraph will also expect the
user to understand the types used for identifiers when querying, meaning that `g.V(1)` and `g.V(1L)` could return
two different vertices. `LONG`, `INTEGER` and `UUID` settings will try to coerce identifier values to the expected
type as well as generate new identifiers with that specified type.

|  |  |
| --- | --- |
| Tip | Setting the `IdManager` to `ANY` also allows `String` type ID values to be used. |

If the TinkerGraph is configured for persistence with `gremlin.tinkergraph.graphLocation` and
`gremlin.tinkergraph.graphFormat`, then the graph will be written to the specified location with the specified
format when `Graph.close()` is called. In addition, if these settings are present, TinkerGraph will attempt to
load the graph from the specified location.

|  |  |
| --- | --- |
| Important | If choosing `graphson` as the `gremlin.tinkergraph.graphFormat`, be sure to also establish the various `IdManager` settings as well to ensure that identifiers are properly coerced to the appropriate types as GraphSON can lose the identifier’s type during serialization (i.e. it will assume `Integer` when the default for TinkerGraph is `Long`, which could lead to load errors that result in a message like, "Vertex with id already exists"). |

It is important to consider the data being imported to TinkerGraph with respect to `defaultVertexPropertyCardinality`
setting. For example, if a `.gryo` file is known to contain multi-property data, be sure to set the default
cardinality to `list` or else the data will import as `single`. Consider the following:

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.io("data/tinkerpop-crew.kryo").read().iterate()
[WARN] o.a.t.g.s.u.Attachable$Method - location has SINGLE cardinality but with more than one value: [vp[location->san diego], vp[location->santa cruz], vp[location->brussels], vp[location->santa fe]]. Only last value will be retained.
[WARN] o.a.t.g.s.u.Attachable$Method - location has SINGLE cardinality but with more than one value: [vp[location->centreville], vp[location->dulles], vp[location->purcellville]]. Only last value will be retained.
[WARN] o.a.t.g.s.u.Attachable$Method - location has SINGLE cardinality but with more than one value: [vp[location->bremen], vp[location->baltimore], vp[location->oakland], vp[location->seattle]]. Only last value will be retained.
[WARN] o.a.t.g.s.u.Attachable$Method - location has SINGLE cardinality but with more than one value: [vp[location->spremberg], vp[location->kaiserslautern], vp[location->aachen]]. Only last value will be retained.
gremlin> g.V().properties()
==>vp[name->marko]
==>vp[location->santa fe]
==>vp[name->stephen]
==>vp[location->purcellville]
==>vp[name->matthias]
==>vp[location->seattle]
==>vp[name->daniel]
==>vp[location->aachen]
==>vp[name->gremlin]
==>vp[name->tinkergraph]
gremlin> conf = new BaseConfiguration()
==>org.apache.commons.configuration2.BaseConfiguration@7d8a5ec7
gremlin> conf.setProperty("gremlin.tinkergraph.defaultVertexPropertyCardinality","list")
==>null
gremlin> graph = TinkerGraph.open(conf)
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.io("data/tinkerpop-crew.kryo").read().iterate()
gremlin> g.V().properties()
==>vp[name->marko]
==>vp[location->san diego]
==>vp[location->santa cruz]
==>vp[location->brussels]
==>vp[location->santa fe]
==>vp[name->stephen]
==>vp[location->centreville]
==>vp[location->dulles]
==>vp[location->purcellville]
==>vp[name->matthias]
==>vp[location->bremen]
==>vp[location->baltimore]
==>vp[location->oakland]
==>vp[location->seattle]
==>vp[name->daniel]
==>vp[location->spremberg]
==>vp[location->kaiserslautern]
==>vp[location->aachen]
==>vp[name->gremlin]
==>vp[name->tinkergraph]
```

```
graph = TinkerGraph.open()
g = traversal().with(graph)
g.io("data/tinkerpop-crew.kryo").read().iterate()
g.V().properties()
conf = new BaseConfiguration()
conf.setProperty("gremlin.tinkergraph.defaultVertexPropertyCardinality","list")
graph = TinkerGraph.open(conf)
g = traversal().with(graph)
g.io("data/tinkerpop-crew.kryo").read().iterate()
g.V().properties()
```

### Transactions

`TinkerGraph` includes optional transaction support and thread-safety through the `TinkerTransactionGraph` class.
The default configuration of TinkerGraph remains non-transactional.

|  |  |
| --- | --- |
| Note | This feature was first made available in TinkerPop 3.7.0. |

#### Transaction Semantics

`TinkerTransactionGraph` only has support for `ThreadLocal` transactions, so embedded graph transactions may not be fully
supported. You can think of the transaction as belonging to a thread, any traversals executed within the same thread
will share the same transaction even if you attempt to start a new transaction.

`TinkerTransactionGraph` provides the `read committed` transaction isolation level. This means that it will always try to
guard against dirty reads but will not prevent non-repeatable reads or phantom reads. While you may notice stricter
isolation semantics in some cases, you should not depend on this behavior as it may change in the future.

`TinkerTransactionGraph` employs optimistic locking as its locking strategy. This reduces complexity in the design as
there are fewer timeouts that the user needs to manage. However, a consequence of this approach is that a transaction
will throw a `TransactionException` if two different transactions attempt to lock the same element (see "Best Practices"
below).

#### Testing Remote Providers

These transaction semantics described above may not fit use cases for some production scenarios that require strict
ACID-like transactions. Therefore, it is recommended that `TinkerTransactionGraph` be used as a `Graph` for test
environments where you still require access to a `Graph` that supports transactions. `TinkerTransactionGraph` does fully
support TinkerPop’s `Transaction` interface which still makes it a useful `Graph` for exploring the
[Transaction API](#transactions).

A common scenario where this sort of testing is helpful is with [Remote Graph Providers](#connecting-rgp), where
developing unit tests might be hard against a graph service. Instead, configure `TinkerTransactionGraph`, either in an
embedded style if using Java or with Gremlin Server for other cases.

```
// consider this class that returns the results of some Gremlin. by constructing the
// GraphService in a way that takes a GraphTraversalSource it becomes possible to
// execute getPersons() under any graph system.
public class GraphService {
    private final GraphTraversalSource g;

    public GraphService(GraphTraversalSource g) {
        this.g = g;
    }

    public List<Vertex> getPersons() {
        return g.V().hasLabel("person").toList();
    }
}

// when writing tests for the GraphService it becomes possible to configure the test
// to run in a variety of scenarios. here we decide that TinkerTransactionGraph is a
// suitable test graph replacement for our actual production graph.
public class GraphServiceTest {
    private static final TinkerTransactionGraph graph = TinkerTransactionGraph.open();
    private static final GraphTraversalSource g = traversal.with(graph);
    private static final GraphService service = new GraphService(g);

    @Test
    public void shouldGetPersons() {
        final List<Vertex> persons = service.getPersons();
        assertEquals(6, persons.size());
    }
}

// or perhaps, since we're using a remote graph provider, we feel it would be better to
// start Gremlin Server with a TinkerTransactionGraph configured using a docker container,
// embedding it directly in our tests or running it as a separate process like:
//
// bin/gremlin-server.sh conf/gremlin-server-transaction.yaml
//
// and then connect to it with a driver in more of an integration test style. obviously,
// with this approach you could also configure your production graph directly or use custom
// build options to trigger different test configurations for a more dynamic approach
public class GraphServiceTest {
    private static final GraphTraversalSource g = traversal.with(
            new DriverRemoteConnection('ws://localhost:8182/gremlin'));
    private static final GraphService service = new GraphService(g);

    @Test
    public void shouldGetPersons() {
        final List<Vertex> persons = service.getPersons();
        assertEquals(6, persons.size());
    }
}
```

|  |  |
| --- | --- |
| Warning | There can be subtle behavioral differences between TinkerGraph and the graph ultimately intended for use. Be aware of the differences when writing tests to ensure that you are testing behaviors of your applications appropriately. |

#### Best Practices

Errors can occur before a transaction gets committed. Specifically for `TinkerTransactionGraph`, you may encounter many
`TransactionException` errors in a highly concurrent environment due its optimistic approach to locking. Users should
follow the try-catch-rollback pattern described in the
[transactions](https://tinkerpop.apache.org/docs/3.8.0/reference/#transactions) section in combination with
exponential backoff based retries to mitigate this issue.

#### Performance Considerations

While transactions impose minimal impact for mutating workloads, users should expect performance degradation for
read-only work relative to the non-transactional configuration. However, its approach to locking
(write-only, optimistic) and its in-memory nature, TinkerTransactionGraph is likely faster than other `Graph`
implementations that support transactions.

#### Examples

Constructing a simple graph using `TinkerTransactionGraph` in Java is presented below:

```
Graph graph = TinkerTransactionGraph.open();
g = traversal().with(graph)
GraphTraversalSource gtx = g.tx().begin();

try {
  Vertex marko = gtx.addV("person").property("name","marko").property("age",29).next();
  Vertex lop = gtx.addV("software").property("name","lop").property("lang","java").next();
  gtx.addE("created").from(marko).to(lop).property("weight",0.6d).iterate();

  gtx.tx().commit();
} catch (Exception ex) {
  gtx.tx().rollback();
}
```

The above Gremlin creates two vertices named "marko" and "lop" and connects them via a created-edge with a weight=0.6
property. In case of any errors `rollback()` will be called and no changes will be performed.

To use the embedded TinkerTransactionGraph in Gremlin Console:

console (groovy)

groovy

```
gremlin> graph = TinkerTransactionGraph.open() //// (1)
==>tinkertransactiongraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph) //// (2)
==>graphtraversalsource[tinkertransactiongraph[vertices:0 edges:0], standard]
gremlin> g.addV('test').property('name','one')
==>v[0]
gremlin> g.tx().commit() //// (3)
==>null
gremlin> g.V().valueMap()
==>[name:[one]]
gremlin> g.addV('test').property('name','two') //// (4)
==>v[2]
gremlin> g.V().valueMap()
==>[name:[one]]
==>[name:[two]]
gremlin> g.tx().rollback() //// (5)
==>null
gremlin> g.V().valueMap()
==>[name:[one]]
```

```
graph = TinkerTransactionGraph.open() //// (1)
g = traversal().with(graph) //// (2)
g.addV('test').property('name','one')
g.tx().commit() //// (3)
g.V().valueMap()
g.addV('test').property('name','two') //// (4)
g.V().valueMap()
g.tx().rollback() //// (5)
g.V().valueMap()
```

1. Open transactional graph.
2. Spawn a GraphTraversalSource with transactional graph.
3. Commit the add vertex operation
4. Add a second vertex without committing
5. Rollback the change

## Neo4j-Gremlin (Deprecated)

|  |  |
| --- | --- |
| Warning | Deprecated: Neo4j-Gremlin is not compatible with versions of Neo4j beyond 3.4 (Reached End of Life March 31, 2020). For this reason, use of Neo4j-Gremlin is not recommended for production environments. Neo4j-Gremlin is expected to remain compatible with upcoming releases of TinkerPop, however long term support is not guaranteed. Neo4j-Gremlin may be dropped from future versions of TinkerPop if compatibility cannot reasonably be maintained. Alternative TinkerPop enabled graph providers can be found on the [TinkerPop site](https://tinkerpop.apache.org/providers.html). |

|  |  |
| --- | --- |
| Warning | Neo4j-Gremlin can work with JDK17, but requires the use of the `--add-opens` flag to be provided to the JVM as follows: `--add-opens=java.base/sun.nio.ch=ALL-UNNAMED`. |

```
<dependency>
   <groupId>org.apache.tinkerpop</groupId>
   <artifactId>neo4j-gremlin</artifactId>
   <version>3.8.0</version>
</dependency>
<!-- neo4j-tinkerpop-api-impl is NOT Apache 2 licensed - more information below -->
<!-- supports Neo4j 3.4.11 -->
<dependency>
  <groupId>org.neo4j</groupId>
  <artifactId>neo4j-tinkerpop-api-impl</artifactId>
  <version>0.9-3.4.0</version>
</dependency>
```

[Neo4j, Inc.](http://neo4j.com) are the developers of the OLTP-based [Neo4j graph database](http://neo4j.com).

|  |  |
| --- | --- |
| Warning | Unless under a commercial agreement with Neo4j, Inc., Neo4j is licensed [AGPL](http://en.wikipedia.org/wiki/Affero_General_Public_License). The `neo4j-gremlin` module is licensed Apache2 because it only references the Apache2-licensed Neo4j API (not its implementation). Note that neither the [Gremlin Console](#gremlin-console) nor [Gremlin Server](11-gremlin-server.md#gremlin-server) distribute with the Neo4j implementation binaries. To access the binaries, use the `:install` command to download binaries from [Maven Central Repository](http://search.maven.org/). |

|  |  |
| --- | --- |
| Important | When connecting to existing Neo4j databases, ensure that this database is compatible with the version of Neo4j that TinkerPop currently supports in the `neo4j-tinkerpop-api-impl`. |

|  |  |
| --- | --- |
| Tip | For configuring Grape, the dependency resolver of Groovy, please refer to the [Gremlin Applications](11-gremlin-server.md#gremlin-applications) section. |

```
gremlin> :install org.apache.tinkerpop neo4j-gremlin 3.8.0
==>Loaded: [org.apache.tinkerpop, neo4j-gremlin, 3.8.0] - restart the console to use [tinkerpop.neo4j]
gremlin> :q
...
gremlin> :plugin use tinkerpop.neo4j
==>tinkerpop.neo4j activated
gremlin> graph = Neo4jGraph.open('/tmp/neo4j')
==>neo4jgraph[EmbeddedGraphDatabase [/tmp/neo4j]]
```

|  |  |
| --- | --- |
| Tip | To host Neo4j in [Gremlin Server](11-gremlin-server.md#gremlin-server), the dependencies must first be "installed" or otherwise copied to the Gremlin Server path. The automated method for doing this would be to execute `bin/gremlin-server.sh install org.apache.tinkerpop neo4j-gremlin 3.8.0`. Once installed, the Gremlin Server configuration file must be edited to include the `Neo4jGremlinPlugin` as shown in `conf/gremlin-server-neo4j.yaml`. |

### Indices

Neo4j 2.x indices leverage vertex labels to partition the index space. TinkerPop does not provide method interfaces
for defining schemas/indices for the underlying graph system. Thus, in order to create indices, it is important to
call the Neo4j API directly.

|  |  |
| --- | --- |
| Note | `Neo4jGraphStep` will attempt to discern which indices to use when executing a traversal of the form `g.V().has()`. |

The Gremlin-Console session below demonstrates Neo4j indices. For more information, please refer to the Neo4j documentation:

* Manipulating indices with [Cypher](http://neo4j.com/docs/developer-manual/current/#query-schema-index).
* Manipulating indices with the Neo4j [Java API](http://neo4j.com/docs/stable/tutorials-java-embedded-new-index.html).

console (groovy)

groovy

```
gremlin> graph = Neo4jGraph.open('/tmp/neo4j')
==>neo4jgraph[community single [/tmp/neo4j]]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[neo4jgraph[community single [/tmp/neo4j]], standard]
gremlin> graph.cypher("CREATE INDEX ON :person(name)")
gremlin> graph.tx().commit() //// (1)
==>null
gremlin> g.addV('person').property('name','marko')
==>v[0]
gremlin> g.addV('dog').property('name','puppy')
==>v[1]
gremlin> g.V().hasLabel('person').has('name','marko').values('name')
==>marko
gremlin> graph.close()
==>null
```

```
graph = Neo4jGraph.open('/tmp/neo4j')
g = traversal().with(graph)
graph.cypher("CREATE INDEX ON :person(name)")
graph.tx().commit() //// (1)
g.addV('person').property('name','marko')
g.addV('dog').property('name','puppy')
g.V().hasLabel('person').has('name','marko').values('name')
graph.close()
```

1. Schema mutations must happen in a different transaction than graph mutations

Below demonstrates the runtime benefits of indices and demonstrates how if there is no defined index (only vertex
labels), a linear scan of the vertex-label partition is still faster than a linear scan of all vertices.

console (groovy)

groovy

```
gremlin> graph = Neo4jGraph.open('/tmp/neo4j')
==>neo4jgraph[community single [/tmp/neo4j]]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[neo4jgraph[community single [/tmp/neo4j]], standard]
gremlin> g.io('data/grateful-dead.xml').read().iterate()
gremlin> g.tx().commit()
==>null
gremlin> clock(1000) {g.V().hasLabel('artist').has('name','Garcia').iterate()} //// (1)
==>0.35700886299999995
gremlin> graph.cypher("CREATE INDEX ON :artist(name)") //// (2)
gremlin> g.tx().commit()
==>null
gremlin> Thread.sleep(5000) //// (3)
==>null
gremlin> clock(1000) {g.V().hasLabel('artist').has('name','Garcia').iterate()} //// (4)
==>0.060893195
gremlin> clock(1000) {g.V().has('name','Garcia').iterate()} //// (5)
==>0.618721043
gremlin> graph.cypher("DROP INDEX ON :artist(name)") //// (6)
gremlin> g.tx().commit()
==>null
gremlin> graph.close()
==>null
```

```
graph = Neo4jGraph.open('/tmp/neo4j')
g = traversal().with(graph)
g.io('data/grateful-dead.xml').read().iterate()
g.tx().commit()
clock(1000) {g.V().hasLabel('artist').has('name','Garcia').iterate()} //// (1)
graph.cypher("CREATE INDEX ON :artist(name)") //// (2)
g.tx().commit()
Thread.sleep(5000) //// (3)
clock(1000) {g.V().hasLabel('artist').has('name','Garcia').iterate()} //// (4)
clock(1000) {g.V().has('name','Garcia').iterate()} //// (5)
graph.cypher("DROP INDEX ON :artist(name)") //// (6)
g.tx().commit()
graph.close()
```

1. Find all artists whose name is Garcia which does a linear scan of the artist vertex-label partition.
2. Create an index for all artist vertices on their name property.
3. Neo4j indices are eventually consistent so this stalls to give the index time to populate itself.
4. Find all artists whose name is Garcia which uses the pre-defined schema index.
5. Find all vertices whose name is Garcia which requires a linear scan of all the data in the graph.
6. Drop the created index.

### Cypher

![gremlin loves cypher](../images/gremlin-loves-cypher.png)

NeoTechnology are the creators of the graph pattern-match query language [Cypher](https://neo4j.com/developer/cypher-query-language/).
It is possible to leverage Cypher from within Gremlin by using the `Neo4jGraph.cypher()` graph traversal method.

console (groovy)

groovy

```
gremlin> graph = Neo4jGraph.open('/tmp/neo4j')
==>neo4jgraph[community single [/tmp/neo4j]]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[neo4jgraph[community single [/tmp/neo4j]], standard]
gremlin> g.io('data/tinkerpop-modern.kryo').read().iterate()
gremlin> graph.cypher('MATCH (a {name:"marko"}) RETURN a')
==>[a:v[0]]
gremlin> graph.cypher('MATCH (a {name:"marko"}) RETURN a').select('a').out('knows').values('name')
==>josh
==>vadas
gremlin> graph.close()
==>null
```

```
graph = Neo4jGraph.open('/tmp/neo4j')
g = traversal().with(graph)
g.io('data/tinkerpop-modern.kryo').read().iterate()
graph.cypher('MATCH (a {name:"marko"}) RETURN a')
graph.cypher('MATCH (a {name:"marko"}) RETURN a').select('a').out('knows').values('name')
graph.close()
```

Thus, like [`match()`](06-steps/branch-steps.md#match-step)-step in Gremlin, it is possible to do a declarative pattern match and then move
back into imperative Gremlin.

|  |  |
| --- | --- |
| Tip | For those developers using [Gremlin Server](11-gremlin-server.md#gremlin-server) against Neo4j, it is possible to do Cypher queries by simply placing the Cypher string in `graph.cypher(…​)` before submission to the server. |

### Multi-Label

TinkerPop requires every `Element` to have a single, immutable string label (i.e. a `Vertex`, `Edge`, and
`VertexProperty`). In Neo4j, a `Node` (vertex) can have an
[arbitrary number of labels](http://neo4j.com/docs/developer-manual/current/#graphdb-neo4j-labels) while a `Relationship`
(edge) can have one and only one. Furthermore, in Neo4j, `Node` labels are mutable while `Relationship` labels are
not. In order to handle this mismatch, three `Neo4jVertex` specific methods exist in Neo4j-Gremlin.

```
public Set<String> labels() // get all the labels of the vertex
public void addLabel(String label) // add a label to the vertex
public void removeLabel(String label) // remove a label from the vertex
```

An example use case is presented below.

console (groovy)

groovy

```
gremlin> graph = Neo4jGraph.open('/tmp/neo4j')
==>neo4jgraph[community single [/tmp/neo4j]]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[neo4jgraph[community single [/tmp/neo4j]], standard]
gremlin> vertex = (Neo4jVertex) g.addV('human::animal').next() //// (1)
==>v[0]
gremlin> vertex.label() //// (2)
==>animal::human
gremlin> vertex.labels() //// (3)
==>animal
==>human
gremlin> vertex.addLabel('organism') //// (4)
==>null
gremlin> vertex.label()
==>animal::human::organism
gremlin> vertex.removeLabel('human') //// (5)
==>null
gremlin> vertex.labels()
==>animal
==>organism
gremlin> vertex.addLabel('organism') //// (6)
==>null
gremlin> vertex.labels()
==>animal
==>organism
gremlin> vertex.removeLabel('human') //// (7)
==>null
gremlin> vertex.label()
==>animal::organism
gremlin> g.V().has(label,'organism') //// (8)
gremlin> g.V().has(label,of('organism')) //// (9)
==>v[0]
gremlin> g.V().has(label,of('organism')).has(label,of('animal'))
==>v[0]
gremlin> g.V().has(label,of('organism').and(of('animal')))
==>v[0]
gremlin> graph.close()
==>null
```

```
graph = Neo4jGraph.open('/tmp/neo4j')
g = traversal().with(graph)
vertex = (Neo4jVertex) g.addV('human::animal').next() //// (1)
vertex.label() //// (2)
vertex.labels() //// (3)
vertex.addLabel('organism') //// (4)
vertex.label()
vertex.removeLabel('human') //// (5)
vertex.labels()
vertex.addLabel('organism') //// (6)
vertex.labels()
vertex.removeLabel('human') //// (7)
vertex.label()
g.V().has(label,'organism') //// (8)
g.V().has(label,of('organism')) //// (9)
g.V().has(label,of('organism')).has(label,of('animal'))
g.V().has(label,of('organism').and(of('animal')))
graph.close()
```

1. Typecasting to a `Neo4jVertex` is only required in Java.
2. The standard `Vertex.label()` method returns all the labels in alphabetical order concatenated using `::`.
3. `Neo4jVertex.labels()` method returns the individual labels as a set.
4. `Neo4jVertex.addLabel()` method adds a single label.
5. `Neo4jVertex.removeLabel()` method removes a single label.
6. Labels are unique and thus duplicate labels don’t exist.
7. If a label that does not exist is removed, nothing happens.
8. `P.eq()` does a full string match and should only be used if multi-labels are not leveraged.
9. `LabelP.of()` is specific to `Neo4jGraph` and used for multi-label matching.

|  |  |
| --- | --- |
| Important | `LabelP.of()` is only required if multi-labels are leveraged. `LabelP.of()` is used when filtering/looking-up vertices by their label(s) as the standard `P.eq()` does a direct match on the `::`-representation of `vertex.label()` |

### Configuration

The previous examples showed how to create a `Neo4jGraph` with the default configuration, but Neo4j has many other
options to initialize it that are native to Neo4j. In order to expose those, `Neo4jGraph` has an `open(Configuration)`
method which takes a standard Apache Configuration object. The same can be said of the standard method for creating
`Graph` instances with `GraphFactory`. Each configuration key that Neo4j has must simply be prefixed with
`gremlin.neo4j.conf.` and the suffix configuration key will be passed through to Neo4j.

|  |  |
| --- | --- |
| Note | Gremlin Server uses `GraphFactory` to instantiate the `Graph` instances it manages, so the example below is also relevant for that purpose as well. |

For example, a standard configuration file called `neo4j.properties` that sets the Neo4j
`dbms.index_sampling.background_enabled` setting might look like:

```
gremlin.graph=org.apache.tinkerpop.gremlin.neo4j.structure.Neo4jGraph
gremlin.neo4j.directory=/tmp/neo4j
gremlin.neo4j.conf.dbms.index_sampling.background_enabled=true
```

which can then be used as follows:

```
gremlin> graph = GraphFactory.open('neo4j.properties')
==>neo4jgraph[community single [/tmp/neo4j]]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[neo4jgraph[community single [/tmp/neo4j]], standard]
```

Having this ability to set standard Neo4j configurations makes it possible to better control the initialization of
Neo4j itself and provides the ability to enable certain features that would not otherwise be accessible.

### Bolt Configuration

While `Neo4jGraph` enables Gremlin based queries, users may find it helpful to also be able to connect to that graph
with native Neo4j drivers and other tools from that space. It is possible to enable the
[Bolt Protocol](https://boltprotocol.org/) as a way to do this:

```
gremlin.graph=org.apache.tinkerpop.gremlin.neo4j.structure.Neo4jGraph
gremlin.neo4j.directory=/tmp/neo4j
gremlin.neo4j.conf.dbms.connector.0.type=BOLT
gremlin.neo4j.conf.dbms.connector.0.enabled=true
gremlin.neo4j.conf.dbms.connector.0.address=localhost:7687
```

This configuration is especially relevant to Gremlin Server where one might want to connect to the same graph instance
with both Gremlin and Cypher.

```
gremlin> :install org.neo4j.driver neo4j-java-driver 1.7.2
==>Loaded: [org.neo4j.driver, neo4j-java-driver, 1.7.2]
... // restart Gremlin Console
gremlin> import org.neo4j.driver.v1.*
==>org.apache.tinkerpop.gremlin.structure.*, org.apache.tinkerpop.gremlin.structure.util.*, ... org.neo4j.driver.v1.*
gremlin> driver = GraphDatabase.driver( "bolt://localhost:7687", AuthTokens.basic("neo4j", "neo4j"))
Oct 28, 2019 3:28:20 PM org.neo4j.driver.internal.logging.JULogger info
INFO: Direct driver instance 1385140107 created for server address localhost:7687
==>org.neo4j.driver.internal.InternalDriver@528f8f8b
gremlin> session = driver.session()
==>org.neo4j.driver.internal.NetworkSession@f3fcd59
gremlin> session.run( "CREATE (a:person {name: {name}, age: {age}})",
......1>                 Values.parameters("name", "stephen", "age", 29))
gremlin> :remote connect tinkerpop.server conf/remote.yaml
==>Configured localhost/127.0.0.1:8182
gremlin> :remote console
==>All scripts will now be sent to Gremlin Server - [localhost/127.0.0.1:8182] - type ':remote console' to return to local mode
gremlin> g.V().elementMap()
==>{id=0, label=person, name=stephen, age=29}
```

### High Availability Configuration

![neo4j ha](../images/neo4j-ha.png) TinkerPop supports running Neo4j with its fault tolerant master-slave
replication configuration, referred to as its
[High Availability (HA) cluster](http://neo4j.com/docs/operations-manual/current/#_neo4j_cluster_install). From the
TinkerPop perspective, configuring for HA is not that different than configuring for embedded mode as shown above. The
main difference is the usage of HA configuration options that enable the cluster. Once connected to a cluster, usage
from the TinkerPop perspective is largely the same.

In configuring for HA the most important thing to realize is that all Neo4j HA settings are simply passed through the
TinkerPop configuration settings given to the `GraphFactory.open()` or `Neo4j.open()` methods. For example, to
provide the all-important `ha.server_id` configuration option through TinkerPop, simply prefix that key with the
TinkerPop Neo4j key of `gremlin.neo4j.conf`.

The following properties demonstrates one of the three configuration files required to setup a simple three node HA
cluster on the same machine instance:

```
gremlin.graph=org.apache.tinkerpop.gremlin.neo4j.structure.Neo4jGraph
gremlin.neo4j.directory=/tmp/neo4j.server1
gremlin.neo4j.conf.ha.server_id=1
gremlin.neo4j.conf.ha.initial_hosts=localhost:5001\,localhost:5002\,localhost:5003
gremlin.neo4j.conf.ha.host.coordination=localhost:5001
gremlin.neo4j.conf.ha.host.data=localhost:6001
```

Assuming the intent is to configure this cluster completely within TinkerPop (perhaps within three separate Gremlin
Server instances), the other two configuration files will be quite similar. The second will be:

```
gremlin.graph=org.apache.tinkerpop.gremlin.neo4j.structure.Neo4jGraph
gremlin.neo4j.directory=/tmp/neo4j.server2
gremlin.neo4j.conf.ha.server_id=2
gremlin.neo4j.conf.ha.initial_hosts=localhost:5001\,localhost:5002\,localhost:5003
gremlin.neo4j.conf.ha.host.coordination=localhost:5002
gremlin.neo4j.conf.ha.host.data=localhost:6002
```

and the third will be:

```
gremlin.graph=org.apache.tinkerpop.gremlin.neo4j.structure.Neo4jGraph
gremlin.neo4j.directory=/tmp/neo4j.server3
gremlin.neo4j.conf.ha.server_id=3
gremlin.neo4j.conf.ha.initial_hosts=localhost:5001\,localhost:5002\,localhost:5003
gremlin.neo4j.conf.ha.host.coordination=localhost:5003
gremlin.neo4j.conf.ha.host.data=localhost:6003
```

|  |  |
| --- | --- |
| Important | The backslashes in the values provided to `gremlin.neo4j.conf.ha.initial_hosts` prevent that configuration setting as being interpreted as a `List`. |

Create three separate Gremlin Server configuration files and point each at one of these Neo4j files. Since these Gremlin
Server instances will be running on the same machine, ensure that each Gremlin Server instance has a unique `port`
setting in that Gremlin Server configuration file. Start each Gremlin Server instance to bring the HA cluster online.

|  |  |
| --- | --- |
| Note | `Neo4jGraph` instances will block until all nodes join the cluster. |

Neither Gremlin Server nor Neo4j will share transactions across the cluster. Be sure to either use Gremlin Server
managed transactions or, if using a session without that option, ensure that all requests are being routed to the
same server.

This example discussed use of Gremlin Server to demonstrate the HA configuration, but it is also easy to setup with
three Gremlin Console instances. Simply start three Gremlin Console instances and use `GraphFactory` to read those
configuration files to form the cluster. Furthermore, keep in mind that it is possible to have a Gremlin Console join
a cluster handled by two Gremlin Servers or Neo4j Enterprise. The only limits as to how the configuration can be
utilized are prescribed by Neo4j itself. Please refer to their
[documentation](http://neo4j.com/docs/operations-manual/current/#ha-setup-tutorial) for more information on how
this feature works.

## Hadoop-Gremlin

```
<dependency>
   <groupId>org.apache.tinkerpop</groupId>
   <artifactId>hadoop-gremlin</artifactId>
   <version>3.8.0</version>
</dependency>
```

![hadoop logo notext](../images/hadoop-logo-notext.png) [Hadoop](http://hadoop.apache.org/) is a distributed
computing framework that is used to process data represented across a multi-machine compute cluster. When the
data in the Hadoop cluster represents a TinkerPop graph, then Hadoop-Gremlin can be used to process the graph
using both TinkerPop’s OLTP and OLAP graph computing models.

|  |  |
| --- | --- |
| Important | This section assumes that the user has a Hadoop 3.x cluster functioning. For more information on getting started with Hadoop, please see the [Single Node Setup](http://hadoop.apache.org/docs/r3.3.1/hadoop-project-dist/hadoop-common/SingleCluster.html) tutorial. Moreover, if using `SparkGraphComputer` it is advisable that the reader also familiarize their self with and Spark ([Quick Start](http://spark.apache.org/docs/latest/quick-start.html)). |

### Installing Hadoop-Gremlin

If using [Gremlin Console](#gremlin-console), it is important to install the Hadoop-Gremlin plugin. Note that
Hadoop-Gremlin requires a Gremlin Console restart after installing.

```
$ bin/gremlin.sh

         \,,,/
         (o o)
-----oOOo-(3)-oOOo-----
plugin activated: tinkerpop.server
plugin activated: tinkerpop.utilities
plugin activated: tinkerpop.tinkergraph
gremlin> :install org.apache.tinkerpop hadoop-gremlin 3.8.0
==>loaded: [org.apache.tinkerpop, hadoop-gremlin, 3.8.0] - restart the console to use [tinkerpop.hadoop]
gremlin> :q
$ bin/gremlin.sh

         \,,,/
         (o o)
-----oOOo-(3)-oOOo-----
plugin activated: tinkerpop.server
plugin activated: tinkerpop.utilities
plugin activated: tinkerpop.tinkergraph
gremlin> :plugin use tinkerpop.hadoop
==>tinkerpop.hadoop activated
gremlin>
```

It is important that the `CLASSPATH` environmental variable references `HADOOP_CONF_DIR` and that the configuration
files in `HADOOP_CONF_DIR` contain references to a live Hadoop cluster. It is easy to verify a proper configuration
from within the Gremlin Console. If `hdfs` references the local file system, then there is a configuration issue.

```
gremlin> hdfs
==>storage[org.apache.hadoop.fs.LocalFileSystem@65bb9029] // BAD

gremlin> hdfs
==>storage[DFS[DFSClient[clientName=DFSClient_NONMAPREDUCE_1229457199_1, ugi=user (auth:SIMPLE)]]] // GOOD
```

The `HADOOP_GREMLIN_LIBS` references locations that contain jars that should be uploaded to a respective
distributed cache ([YARN](http://hadoop.apache.org/docs/3.8.0/hadoop-yarn/hadoop-yarn-site/YARN.html) or SparkServer).
Note that the locations in `HADOOP_GREMLIN_LIBS` can be colon-separated (`:`) and all jars from all locations will
be loaded into the cluster. Locations can be local paths (e.g. `/path/to/libs`), but may also be prefixed with a file
scheme to reference files or directories in different file systems (e.g. `hdfs:///path/to/distributed/libs`).
Typically, only the jars of the respective `GraphComputer` are required to be loaded.

### Properties Files

`HadoopGraph` makes use of properties files which ultimately get turned into Apache configurations and/or
Hadoop configurations.

```
gremlin.graph=org.apache.tinkerpop.gremlin.hadoop.structure.HadoopGraph
gremlin.hadoop.inputLocation=tinkerpop-modern.kryo
gremlin.hadoop.graphReader=org.apache.tinkerpop.gremlin.hadoop.structure.io.gryo.GryoInputFormat
gremlin.hadoop.outputLocation=output
gremlin.hadoop.graphWriter=org.apache.tinkerpop.gremlin.hadoop.structure.io.gryo.GryoOutputFormat
gremlin.hadoop.jarsInDistributedCache=true
gremlin.hadoop.defaultGraphComputer=org.apache.tinkerpop.gremlin.spark.process.computer.SparkGraphComputer
####################################
# Spark Configuration              #
####################################
spark.master=local[4]
spark.executor.memory=1g
spark.serializer=org.apache.tinkerpop.gremlin.spark.structure.io.gryo.GryoSerializer
gremlin.spark.persistContext=true
```

A review of the Hadoop-Gremlin specific properties are provided in the table below. For the respective OLAP
engines ([`SparkGraphComputer`](10-spark.md#sparkgraphcomputer) refer to their respective documentation for configuration options.

| Property | Description |
| --- | --- |
| gremlin.graph | The class of the graph to construct using GraphFactory. |
| gremlin.hadoop.inputLocation | The location of the input file(s) for Hadoop-Gremlin to read the graph from. |
| gremlin.hadoop.graphReader | The class that the graph input file(s) are read with (e.g. an `InputFormat`). |
| gremlin.hadoop.outputLocation | The location to write the computed HadoopGraph to. |
| gremlin.hadoop.graphWriter | The class that the graph output file(s) are written with (e.g. an `OutputFormat`). |
| gremlin.hadoop.jarsInDistributedCache | Whether to upload the Hadoop-Gremlin jars to a distributed cache (necessary if jars are not on the machines' classpaths). |
| gremlin.hadoop.defaultGraphComputer | The default `GraphComputer` to use when `graph.compute()` is called. This is optional. |

Along with the properties above, the numerous [Hadoop specific properties](http://hadoop.apache.org/docs/stable/hadoop-project-dist/hadoop-common/core-default.xml)
can be added as needed to tune and parameterize the executed Hadoop-Gremlin job on the respective Hadoop cluster.

|  |  |
| --- | --- |
| Important | As the size of the graphs being processed becomes large, it is important to fully understand how the underlying OLAP engine (e.g. Spark, etc.) works and understand the numerous parameterizations offered by these systems. Such knowledge can help alleviate out of memory exceptions, slow load times, slow processing times, garbage collection issues, etc. |

### OLTP Hadoop-Gremlin

![hadoop pipes](../images/hadoop-pipes.png) It is possible to execute OLTP operations over a `HadoopGraph`.
However, realize that the underlying HDFS files are not random access and thus, to retrieve a vertex, a linear scan
is required. OLTP operations are useful for peeking into the graph prior to executing a long running OLAP job — e.g.
`g.V().valueMap().limit(10)`.

|  |  |
| --- | --- |
| Warning | OLTP operations on `HadoopGraph` are not efficient. They require linear scans to execute and are unreasonable for large graphs. In such large graph situations, make use of [TraversalVertexProgram](09-graphcomputer.md#traversalvertexprogram) which is the OLAP Gremlin machine. |

console (groovy)

groovy

```
gremlin> hdfs.copyFromLocal('data/tinkerpop-modern.kryo', 'tinkerpop-modern.kryo')
==>null
gremlin> hdfs.ls()
==>rwxr-xr-x coleg supergroup 0 (D) .sparkStaging
==>rw-r--r-- coleg supergroup 781 tinkerpop-modern.kryo
gremlin> graph = GraphFactory.open('conf/hadoop/hadoop-gryo.properties')
==>hadoopgraph[gryoinputformat->gryooutputformat]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[hadoopgraph[gryoinputformat->gryooutputformat], standard]
gremlin> g.V().count()
==>6
gremlin> g.V().out().out().values('name')
==>ripple
==>lop
gremlin> g.V().group().by{it.value('name')[1]}.by('name').next()
==>a=[marko, vadas]
==>e=[peter]
==>i=[ripple]
==>o=[lop, josh]
```

```
hdfs.copyFromLocal('data/tinkerpop-modern.kryo', 'tinkerpop-modern.kryo')
hdfs.ls()
graph = GraphFactory.open('conf/hadoop/hadoop-gryo.properties')
g = traversal().with(graph)
g.V().count()
g.V().out().out().values('name')
g.V().group().by{it.value('name')[1]}.by('name').next()
```

### OLAP Hadoop-Gremlin

![hadoop furnace](../images/hadoop-furnace.png) Hadoop-Gremlin was designed to execute OLAP operations via
`GraphComputer`. The OLTP examples presented previously are reproduced below, but using `TraversalVertexProgram`
for the execution of the Gremlin traversal.

A `Graph` in TinkerPop can support any number of `GraphComputer` implementations. Out of the box, Hadoop-Gremlin
supports the following two implementations.

* [`SparkGraphComputer`](10-spark.md#sparkgraphcomputer): Leverages Apache Spark to execute TinkerPop OLAP computations.

  + The graph may fit within the total RAM of the cluster (supports larger graphs). Message passing is coordinated via
    Spark map/reduce/join operations on in-memory and disk-cached data (average speed traversals).

|  |  |
| --- | --- |
| Tip | gremlin sugar For those wanting to use the [SugarPlugin](#sugar-plugin) with their submitted traversal, do `:remote config useSugar true` as well as `:plugin use tinkerpop.sugar` at the start of the Gremlin Console session if it is not already activated. |

```
$ bin/gremlin.sh

         \,,,/
         (o o)
-----oOOo-(3)-oOOo-----
plugin activated: tinkerpop.server
plugin activated: tinkerpop.utilities
plugin activated: tinkerpop.tinkergraph
plugin activated: tinkerpop.hadoop
gremlin> :install org.apache.tinkerpop spark-gremlin 3.8.0
==>loaded: [org.apache.tinkerpop, spark-gremlin, 3.8.0] - restart the console to use [tinkerpop.spark]
gremlin> :q
$ bin/gremlin.sh

         \,,,/
         (o o)
-----oOOo-(3)-oOOo-----
plugin activated: tinkerpop.server
plugin activated: tinkerpop.utilities
plugin activated: tinkerpop.tinkergraph
plugin activated: tinkerpop.hadoop
gremlin> :plugin use tinkerpop.spark
==>tinkerpop.spark activated
```

|  |  |
| --- | --- |
| Warning | Hadoop and Spark all depend on many of the same libraries (e.g. ZooKeeper, Snappy, Netty, Guava, etc.). Unfortunately, typically these dependencies are not to the same versions of the respective libraries. As such, it is may be necessary to manually cleanup dependency conflicts among different plugins. |

#### SparkGraphComputer

```
<dependency>
   <groupId>org.apache.tinkerpop</groupId>
   <artifactId>spark-gremlin</artifactId>
   <version>3.8.0</version>
</dependency>
```

![spark logo](../images/spark-logo.png) [Spark](http://spark.apache.org) is an Apache Software Foundation
project focused on general-purpose OLAP data processing. Spark provides a hybrid in-memory/disk-based distributed
computing model that is similar to Hadoop’s MapReduce model. Spark maintains a fluent function chaining DSL that is
arguably easier for developers to work with than native Hadoop MapReduce. Spark-Gremlin provides an implementation of
the bulk-synchronous parallel, distributed message passing algorithm within Spark and thus, any `VertexProgram` can be
executed over `SparkGraphComputer`.

Furthermore the `lib/` directory should be distributed across all machines in the SparkServer cluster. For this purpose
TinkerPop provides a helper script, which takes the Spark installation directory and the Spark machines as input:

```
bin/hadoop/init-tp-spark.sh /usr/local/spark spark@10.0.0.1 spark@10.0.0.2 spark@10.0.0.3
```

Once the `lib/` directory is distributed, `SparkGraphComputer` can be used as follows.

console (groovy)

groovy

```
gremlin> graph = GraphFactory.open('conf/hadoop/hadoop-gryo.properties')
==>hadoopgraph[gryoinputformat->gryooutputformat]
gremlin> g = traversal().with(graph).withComputer(SparkGraphComputer)
==>graphtraversalsource[hadoopgraph[gryoinputformat->gryooutputformat], sparkgraphcomputer]
gremlin> g.V().count()
==>6
gremlin> g.V().out().out().values('name')
==>lop
==>ripple
```

```
graph = GraphFactory.open('conf/hadoop/hadoop-gryo.properties')
g = traversal().with(graph).withComputer(SparkGraphComputer)
g.V().count()
g.V().out().out().values('name')
```

For using lambdas in Gremlin-Groovy, simply provide `:remote connect` a `TraversalSource` which leverages SparkGraphComputer.

console (groovy)

groovy

```
gremlin> graph = GraphFactory.open('conf/hadoop/hadoop-gryo.properties')
==>hadoopgraph[gryoinputformat->gryooutputformat]
gremlin> g = traversal().with(graph).withComputer(SparkGraphComputer)
==>graphtraversalsource[hadoopgraph[gryoinputformat->gryooutputformat], sparkgraphcomputer]
gremlin> :remote connect tinkerpop.hadoop graph g
[INFO] o.a.t.g.h.j.HadoopGremlinPlugin - HADOOP_GREMLIN_LIBS is set to: /Users/coleg/apacheTinkerpop/tinkerpop/gremlin-console/target/apache-tinkerpop-gremlin-console-3.8.0-standalone/ext/tinkergraph-gremlin/lib
[INFO] o.a.t.g.h.j.HadoopGremlinPlugin - HADOOP_GREMLIN_LIBS is set to: /Users/coleg/apacheTinkerpop/tinkerpop/gremlin-console/target/apache-tinkerpop-gremlin-console-3.8.0-standalone/ext/tinkergraph-gremlin/lib
[INFO] o.a.t.g.h.j.HadoopGremlinPlugin - HADOOP_GREMLIN_LIBS is set to: /Users/coleg/apacheTinkerpop/tinkerpop/gremlin-console/target/apache-tinkerpop-gremlin-console-3.8.0-standalone/ext/tinkergraph-gremlin/lib
==>useTraversalSource=graphtraversalsource[hadoopgraph[gryoinputformat->gryooutputformat], sparkgraphcomputer]
==>useSugar=false
gremlin> :> g.V().group().by{it.value('name')[1]}.by('name')
==>[a:[marko,vadas],i:[ripple],e:[peter],o:[lop,josh]]
```

```
graph = GraphFactory.open('conf/hadoop/hadoop-gryo.properties')
g = traversal().with(graph).withComputer(SparkGraphComputer)
:remote connect tinkerpop.hadoop graph g
:> g.V().group().by{it.value('name')[1]}.by('name')
```

The `SparkGraphComputer` algorithm leverages Spark’s caching abilities to reduce the amount of data shuffled across
the wire on each iteration of the [`VertexProgram`](#vertexprogram). When the graph is loaded as a Spark RDD
(Resilient Distributed Dataset) it is immediately cached as `graphRDD`. The `graphRDD` is a distributed adjacency
list which encodes the vertex, its properties, and all its incident edges. On the first iteration, each vertex
(in parallel) is passed through `VertexProgram.execute()`. This yields an output of the vertex’s mutated state
(i.e. updated compute keys — `propertyX`) and its outgoing messages. This `viewOutgoingRDD` is then reduced to
`viewIncomingRDD` where the outgoing messages are sent to their respective vertices. If a `MessageCombiner` exists
for the vertex program, then messages are aggregated locally and globally to ultimately yield one incoming message
for the vertex. This reduce sequence is the "message pass." If the vertex program does not terminate on this
iteration, then the `viewIncomingRDD` is joined with the cached `graphRDD` and the process continues. When there
are no more iterations, there is a final join and the resultant RDD is stripped of its edges and messages. This
`mapReduceRDD` is cached and is processed by each [`MapReduce`](#mapreduce) job in the
[`GraphComputer`](09-graphcomputer.md#graphcomputer) computation.

![spark algorithm](../images/spark-algorithm.png)

| Property | Description |
| --- | --- |
| gremlin.hadoop.graphReader | A class for reading a graph-based RDD (e.g. an `InputRDD` or `InputFormat`). |
| gremlin.hadoop.graphWriter | A class for writing a graph-based RDD (e.g. an `OutputRDD` or `OutputFormat`). |
| gremlin.spark.graphStorageLevel | What `StorageLevel` to use for the cached graph during job execution (default `MEMORY_ONLY`). |
| gremlin.spark.persistContext | Whether to create a new `SparkContext` for every `SparkGraphComputer` or to reuse an existing one. |
| gremlin.spark.persistStorageLevel | What `StorageLevel` to use when persisted RDDs via `PersistedOutputRDD` (default `MEMORY_ONLY`). |

##### InputRDD and OutputRDD

If the provider/user does not want to use Hadoop `InputFormats`, it is possible to leverage Spark’s RDD
constructs directly. An `InputRDD` provides a read method that takes a `SparkContext` and returns a graphRDD. Likewise,
and `OutputRDD` is used for writing a graphRDD.

If the graph system provider uses an `InputRDD`, the RDD should maintain an associated `org.apache.spark.Partitioner`. By doing so,
`SparkGraphComputer` will not partition the loaded graph across the cluster as it has already been partitioned by the graph system provider.
This can save a significant amount of time and space resources. If the `InputRDD` does not have a registered partitioner,
`SparkGraphComputer` will partition the graph using a `org.apache.spark.HashPartitioner` with the number of partitions
being either the number of existing partitions in the input (i.e. input splits) or the user specified number of `GraphComputer.workers()`.

If the provider/user finds there are many small HDFS files generated by `OutputRDD`. The option `gremlin.spark.outputRepartition`
can help to repartition the output according to the specified number. The option is disabled by default.

##### Storage Levels

The `SparkGraphComputer` uses `MEMORY_ONLY` to cache the input graph and the output graph by default. Users should be aware of the impact of
different storage levels, since the default settings can quickly lead to memory issues on larger graphs. An overview of Spark’s persistence
settings is provided in [Spark’s programming guide](http://spark.apache.org/docs/latest/rdd-programming-guide.html#rdd-persistence).

##### Using a Persisted Context

It is possible to persist the graph RDD between jobs within the `SparkContext` (e.g. SparkServer) by leveraging `PersistedOutputRDD`.
Note that `gremlin.spark.persistContext` should be set to `true` or else the persisted RDD will be destroyed when the `SparkContext` closes.
The persisted RDD is named by the `gremlin.hadoop.outputLocation` configuration. Similarly, `PersistedInputRDD` is used with respective
`gremlin.hadoop.inputLocation` to retrieve the persisted RDD from the `SparkContext`.

When using a persistent `SparkContext` the configuration used by the original Spark Configuration will be inherited by all threaded
references to that Spark Context. The exception to this rule are those properties which have a specific thread local effect.

Thread Local Properties

1. spark.jobGroup.id
2. spark.job.description
3. spark.job.interruptOnCancel
4. spark.scheduler.pool

Finally, there is a `spark` object that can be used to manage persisted RDDs (see [Interacting with Spark](#interacting-with-spark)).

##### Using CloneVertexProgram

The [CloneVertexProgram](#clonevertexprogram) copies a whole graph from any graph `InputFormat` to any graph
`OutputFormat`. TinkerPop provides formats such as `GraphSONOutputFormat`, `GryoOutputFormat` or `ScriptOutputFormat`.
The example below takes a Hadoop graph as the input (in `GryoInputFormat`) and exports it as a GraphSON file
(`GraphSONOutputFormat`).

console (groovy)

groovy

```
gremlin> hdfs.copyFromLocal('data/tinkerpop-modern.kryo', 'tinkerpop-modern.kryo')
==>null
gremlin> graph = GraphFactory.open('conf/hadoop/hadoop-gryo.properties')
==>hadoopgraph[gryoinputformat->gryooutputformat]
gremlin> graph.configuration().setProperty('gremlin.hadoop.graphWriter', 'org.apache.tinkerpop.gremlin.hadoop.structure.io.graphson.GraphSONOutputFormat')
==>null
gremlin> graph.compute(SparkGraphComputer).program(CloneVertexProgram.build().create()).submit().get()
==>result[hadoopgraph[graphsoninputformat->graphsonoutputformat],memory[size:0]]
gremlin> hdfs.ls('output')
==>rwxr-xr-x coleg supergroup 0 (D) ~g
gremlin> hdfs.head('output/~g')
==>{"id":{"@type":"g:Int32","@value":1},"label":"person","outE":{"created":[{"id":{"@type":"g:Int32","@value":9},"inV":{"@type":"g:Int32","@value":3},"properties":{"weight":{"@type":"g:Double","@value":0.4}}}],"knows":[{"id":{"@type":"g:Int32","@value":7},"inV":{"@type":"g:Int32","@value":2},"properties":{"weight":{"@type":"g:Double","@value":0.5}}},{"id":{"@type":"g:Int32","@value":8},"inV":{"@type":"g:Int32","@value":4},"properties":{"weight":{"@type":"g:Double","@value":1.0}}}]},"properties":{"name":[{"id":{"@type":"g:Int64","@value":0},"value":"marko"}],"age":[{"id":{"@type":"g:Int64","@value":1},"value":{"@type":"g:Int32","@value":29}}]}}
==>{"id":{"@type":"g:Int32","@value":2},"label":"person","inE":{"knows":[{"id":{"@type":"g:Int32","@value":7},"outV":{"@type":"g:Int32","@value":1},"properties":{"weight":{"@type":"g:Double","@value":0.5}}}]},"properties":{"name":[{"id":{"@type":"g:Int64","@value":2},"value":"vadas"}],"age":[{"id":{"@type":"g:Int64","@value":3},"value":{"@type":"g:Int32","@value":27}}]}}
==>{"id":{"@type":"g:Int32","@value":3},"label":"software","inE":{"created":[{"id":{"@type":"g:Int32","@value":9},"outV":{"@type":"g:Int32","@value":1},"properties":{"weight":{"@type":"g:Double","@value":0.4}}},{"id":{"@type":"g:Int32","@value":11},"outV":{"@type":"g:Int32","@value":4},"properties":{"weight":{"@type":"g:Double","@value":0.4}}},{"id":{"@type":"g:Int32","@value":12},"outV":{"@type":"g:Int32","@value":6},"properties":{"weight":{"@type":"g:Double","@value":0.2}}}]},"properties":{"name":[{"id":{"@type":"g:Int64","@value":4},"value":"lop"}],"lang":[{"id":{"@type":"g:Int64","@value":5},"value":"java"}]}}
==>{"id":{"@type":"g:Int32","@value":4},"label":"person","inE":{"knows":[{"id":{"@type":"g:Int32","@value":8},"outV":{"@type":"g:Int32","@value":1},"properties":{"weight":{"@type":"g:Double","@value":1.0}}}]},"outE":{"created":[{"id":{"@type":"g:Int32","@value":10},"inV":{"@type":"g:Int32","@value":5},"properties":{"weight":{"@type":"g:Double","@value":1.0}}},{"id":{"@type":"g:Int32","@value":11},"inV":{"@type":"g:Int32","@value":3},"properties":{"weight":{"@type":"g:Double","@value":0.4}}}]},"properties":{"name":[{"id":{"@type":"g:Int64","@value":6},"value":"josh"}],"age":[{"id":{"@type":"g:Int64","@value":7},"value":{"@type":"g:Int32","@value":32}}]}}
==>{"id":{"@type":"g:Int32","@value":5},"label":"software","inE":{"created":[{"id":{"@type":"g:Int32","@value":10},"outV":{"@type":"g:Int32","@value":4},"properties":{"weight":{"@type":"g:Double","@value":1.0}}}]},"properties":{"name":[{"id":{"@type":"g:Int64","@value":8},"value":"ripple"}],"lang":[{"id":{"@type":"g:Int64","@value":9},"value":"java"}]}}
==>{"id":{"@type":"g:Int32","@value":6},"label":"person","outE":{"created":[{"id":{"@type":"g:Int32","@value":12},"inV":{"@type":"g:Int32","@value":3},"properties":{"weight":{"@type":"g:Double","@value":0.2}}}]},"properties":{"name":[{"id":{"@type":"g:Int64","@value":10},"value":"peter"}],"age":[{"id":{"@type":"g:Int64","@value":11},"value":{"@type":"g:Int32","@value":35}}]}}
```

```
hdfs.copyFromLocal('data/tinkerpop-modern.kryo', 'tinkerpop-modern.kryo')
graph = GraphFactory.open('conf/hadoop/hadoop-gryo.properties')
graph.configuration().setProperty('gremlin.hadoop.graphWriter', 'org.apache.tinkerpop.gremlin.hadoop.structure.io.graphson.GraphSONOutputFormat')
graph.compute(SparkGraphComputer).program(CloneVertexProgram.build().create()).submit().get()
hdfs.ls('output')
hdfs.head('output/~g')
```

### Input/Output Formats

![adjacency list](../images/adjacency-list.png) Hadoop-Gremlin provides various I/O formats — i.e. Hadoop
`InputFormat` and `OutputFormat`. All of the formats make use of an [adjacency list](http://en.wikipedia.org/wiki/Adjacency_list)
representation of the graph where each "row" represents a single vertex, its properties, and its incoming and
outgoing edges.

#### Gryo I/O Format

* **InputFormat**: `org.apache.tinkerpop.gremlin.hadoop.structure.io.gryo.GryoInputFormat`
* **OutputFormat**: `org.apache.tinkerpop.gremlin.hadoop.structure.io.gryo.GryoOutputFormat`

[Gryo](#gryo) is a binary graph format that leverages [Kryo](https://github.com/EsotericSoftware/kryo)
to make a compact, binary representation of a vertex. It is recommended that users leverage Gryo given its space/time
savings over text-based representations.

|  |  |
| --- | --- |
| Note | The `GryoInputFormat` is splittable. |

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

#### Script I/O Format

* **InputFormat**: `org.apache.tinkerpop.gremlin.hadoop.structure.io.script.ScriptInputFormat`
* **OutputFormat**: `org.apache.tinkerpop.gremlin.hadoop.structure.io.script.ScriptOutputFormat`

`ScriptInputFormat` and `ScriptOutputFormat` take an arbitrary script and use that script to either read or write
`Vertex` objects, respectively. This can be considered the most general `InputFormat`/`OutputFormat` possible in that
Hadoop-Gremlin uses the user provided script for all reading/writing.

##### ScriptInputFormat

The data below represents an adjacency list representation of the classic TinkerGraph toy graph. First line reads,
"vertex `1`, labeled `person` having 2 property values (`marko` and `29`) has 3 outgoing edges; the first edge is
labeled `knows`, connects the current vertex `1` with vertex `2` and has a property value `0.4`, and so on."

```
1:person:marko:29 knows:2:0.5,knows:4:1.0,created:3:0.4
2:person:vadas:27
3:project:lop:java
4:person:josh:32 created:3:0.4,created:5:1.0
5:project:ripple:java
6:person:peter:35 created:3:0.2
```

There is no corresponding `InputFormat` that can parse this particular file (or some adjacency list variant of it).
As such, `ScriptInputFormat` can be used. With `ScriptInputFormat` a script is stored in HDFS and leveraged by each
mapper in the Hadoop job. The script must have the following method defined:

```
def parse(String line) { ... }
```

In order to create vertices and edges, the `parse()` method gets access to a global variable named `graph`, which holds
the local `StarGraph` for the current line/vertex.

An appropriate `parse()` for the above adjacency list file is:

```
def parse(line) {
    def parts = line.split(/ /)
    def (id, label, name, x) = parts[0].split(/:/).toList()
    def v1 = graph.addVertex(T.id, id, T.label, label)
    if (name != null) v1.property('name', name) // first value is always the name
    if (x != null) {
        // second value depends on the vertex label; it's either
        // the age of a person or the language of a project
        if (label.equals('project')) v1.property('lang', x)
        else v1.property('age', Integer.valueOf(x))
    }
    if (parts.length == 2) {
        parts[1].split(/,/).grep { !it.isEmpty() }.each {
            def (eLabel, refId, weight) = it.split(/:/).toList()
            def v2 = graph.addVertex(T.id, refId)
            v1.addOutEdge(eLabel, v2, 'weight', Double.valueOf(weight))
        }
    }
    return v1
}
```

The resultant `Vertex` denotes whether the line parsed yielded a valid Vertex. As such, if the line is not valid
(e.g. a comment line, a skip line, etc.), then simply return `null`.

##### ScriptOutputFormat Support

The principle above can also be used to convert a vertex to an arbitrary `String` representation that is ultimately
streamed back to a file in HDFS. This is the role of `ScriptOutputFormat`. `ScriptOutputFormat` requires that the
provided script maintains a method with the following signature:

```
def stringify(Vertex vertex) { ... }
```

An appropriate `stringify()` to produce output in the same format that was shown in the `ScriptInputFormat` sample is:

```
def stringify(vertex) {
    def v = vertex.values('name', 'age', 'lang').inject(vertex.id(), vertex.label()).join(':')
    def outE = vertex.outE().map {
        def e = it.get()
        e.values('weight').inject(e.label(), e.inV().next().id()).join(':')
    }.join(',')
    return [v, outE].join('\t')
}
```

### Storage Systems

Hadoop-Gremlin provides two implementations of the `Storage` API:

* `FileSystemStorage`: Access HDFS and local file system data.
* `SparkContextStorage`: Access Spark persisted RDD data.

#### Interacting with HDFS

The distributed file system of Hadoop is called [HDFS](http://en.wikipedia.org/wiki/Apache_Hadoop#Hadoop_distributed_file_system).
The results of any OLAP operation are stored in HDFS accessible via `hdfs`. For local file system access, there is `fs`.

console (groovy)

groovy

```
gremlin> graph = GraphFactory.open('conf/hadoop/hadoop-gryo.properties')
==>hadoopgraph[gryoinputformat->gryooutputformat]
gremlin> graph.compute(SparkGraphComputer).program(PeerPressureVertexProgram.build().create(graph)).mapReduce(ClusterCountMapReduce.build().memoryKey('clusterCount').create()).submit().get();
==>result[hadoopgraph[gryoinputformat->gryooutputformat],memory[size:1]]
gremlin> hdfs.ls()
==>rwxr-xr-x coleg supergroup 0 (D) .sparkStaging
==>rwxr-xr-x coleg supergroup 0 (D) output
==>rw-r--r-- coleg supergroup 781 tinkerpop-modern.kryo
gremlin> hdfs.ls('output')
==>rwxr-xr-x coleg supergroup 0 (D) clusterCount
==>rwxr-xr-x coleg supergroup 0 (D) ~g
gremlin> hdfs.head('output', GryoInputFormat)
==>v[4]
==>v[1]
==>v[6]
==>v[3]
==>v[5]
==>v[2]
gremlin> hdfs.head('output', 'clusterCount', SequenceFileInputFormat)
==>2
gremlin> hdfs.rm('output')
==>true
gremlin> hdfs.ls()
==>rwxr-xr-x coleg supergroup 0 (D) .sparkStaging
==>rw-r--r-- coleg supergroup 781 tinkerpop-modern.kryo
```

```
graph = GraphFactory.open('conf/hadoop/hadoop-gryo.properties')
graph.compute(SparkGraphComputer).program(PeerPressureVertexProgram.build().create(graph)).mapReduce(ClusterCountMapReduce.build().memoryKey('clusterCount').create()).submit().get();
hdfs.ls()
hdfs.ls('output')
hdfs.head('output', GryoInputFormat)
hdfs.head('output', 'clusterCount', SequenceFileInputFormat)
hdfs.rm('output')
hdfs.ls()
```

#### Interacting with Spark

If a Spark context is persisted, then Spark RDDs will remain the Spark cache and accessible over subsequent jobs.
RDDs are retrieved and saved to the `SparkContext` via `PersistedInputRDD` and `PersistedOutputRDD` respectively.
Persisted RDDs can be accessed using `spark`.

console (groovy)

groovy

```
gremlin> Spark.create('local[4]')
==>org.apache.spark.SparkContext@1f7853af
gremlin> graph = GraphFactory.open('conf/hadoop/hadoop-gryo.properties')
==>hadoopgraph[gryoinputformat->gryooutputformat]
gremlin> graph.configuration().setProperty('gremlin.hadoop.graphWriter', PersistedOutputRDD.class.getCanonicalName())
==>null
gremlin> graph.configuration().setProperty('gremlin.spark.persistContext',true)
==>null
gremlin> graph.compute(SparkGraphComputer).program(PeerPressureVertexProgram.build().create(graph)).mapReduce(ClusterCountMapReduce.build().memoryKey('clusterCount').create()).submit().get();
==>result[hadoopgraph[persistedinputrdd->persistedoutputrdd],memory[size:1]]
gremlin> spark.ls()
gremlin> spark.ls('output')
==>output/clusterCount [Memory Deserialized 1x Replicated]
==>output/~g [Memory Deserialized 1x Replicated]
gremlin> spark.head('output', PersistedInputRDD)
==>v[4]
==>v[1]
==>v[6]
==>v[3]
==>v[5]
==>v[2]
gremlin> spark.head('output', 'clusterCount', PersistedInputRDD)
==>2
gremlin> spark.rm('output')
==>true
gremlin> spark.ls()
```

```
Spark.create('local[4]')
graph = GraphFactory.open('conf/hadoop/hadoop-gryo.properties')
graph.configuration().setProperty('gremlin.hadoop.graphWriter', PersistedOutputRDD.class.getCanonicalName())
graph.configuration().setProperty('gremlin.spark.persistContext',true)
graph.compute(SparkGraphComputer).program(PeerPressureVertexProgram.build().create(graph)).mapReduce(ClusterCountMapReduce.build().memoryKey('clusterCount').create()).submit().get();
spark.ls()
spark.ls('output')
spark.head('output', PersistedInputRDD)
spark.head('output', 'clusterCount', PersistedInputRDD)
spark.rm('output')
spark.ls()
```

## TinkerGraph-Gremlin

```
<dependency>
   <groupId>org.apache.tinkerpop</groupId>
   <artifactId>tinkergraph-gremlin</artifactId>
   <version>3.8.0</version>
</dependency>

<!--
  For a minimal version without sample datasets where TinkerFactory will not load the
  Air Routes or Grateful Dead dataset.
-->
<dependency>
   <groupId>org.apache.tinkerpop</groupId>
   <artifactId>tinkergraph-gremlin</artifactId>
   <version>3.8.0</version>
   <classifier>min</classifier>
</dependency>
```

![tinkerpop character](../images/tinkerpop-character.png) TinkerGraph is a single machine, in-memory (with optional
persistence), graph engine that provides both OLTP and OLAP functionality. It is non-transactional by default but does
have a lightweight transactional form that can be instantiated offering simple `ThreadLocal` transactions supporting
`read committed` transaction isolation. TinkerGraph is deployed with TinkerPop and serves as the reference
implementation for other providers to study in order to understand the semantics of the various methods of the
TinkerPop API. Its status as a reference implementation does not however imply that it is not suitable for production.
TinkerGraph has many practical use cases in production applications and their development. Some examples of TinkerGraph
use cases include:

* Ad-hoc analysis of large immutable graphs that fit in memory.
* Extract subgraphs, from larger graphs that don’t fit in memory, into TinkerGraph for further analysis or other
  purposes.
* Use TinkerGraph as a sandbox to develop and debug complex traversals by simulating data from a larger graph inside
  a TinkerGraph.
* Configure it to match the semantics of a production graph database for unit testing purpose to simplify development
  setup and automated builds.

Constructing a simple graph using TinkerGraph in Java is presented below:

```
Graph graph = TinkerGraph.open();
GraphTraversalSource g = traversal().with(graph);
Vertex marko = g.addV("person").property("name","marko").property("age",29).next();
Vertex lop = g.addV("software").property("name","lop").property("lang","java").next();
g.addE("created").from(marko).to(lop).property("weight",0.6d).iterate();
```

The above Gremlin creates two vertices named "marko" and "lop" and connects them via a created-edge with a weight=0.6
property. The addition of these two vertices and the edge between them could also be done in a single Gremlin statement
as follows:

```
g.addV("person").property("name","marko").property("age",29).as("m").
  addV("software").property("name","lop").property("lang","java").as("l").
  addE("created").from("m").to("l").property("weight",0.6d).iterate();
```

|  |  |
| --- | --- |
| Important | Pay attention to the fact that traversals end with `next()` or `iterate()`. These methods advance the objects in the traversal stream and without those methods, the traversal does nothing. Review the [Result Iteration Section](https://tinkerpop.apache.org/docs/3.8.0/tutorials/the-gremlin-console/#result-iteration) of The Gremlin Console tutorial for more information. |

Next, the graph can be queried as such.

```
g.V().has("name","marko").out("created").values("name")
```

The `g.V().has("name","marko")` part of the query can be executed in two ways.

* A linear scan of all vertices filtering out those vertices that don’t have the name "marko"
* A `O(log(|V|))` index lookup for all vertices with the name "marko"

Given the initial graph construction in the first code block, no index was defined and thus, a linear scan is executed.
However, if the graph was constructed as such, then an index lookup would be used.

```
Graph g = TinkerGraph.open();
g.createIndex("name",Vertex.class)
```

The execution times for a vertex lookup by property is provided below for both no-index and indexed version of
TinkerGraph over the Grateful Dead graph.

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.io('data/grateful-dead.xml').read().iterate()
gremlin> clock(1000) {g.V().has('name','Garcia').iterate()} //// (1)
==>0.12759067
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> graph.createIndex('name',Vertex.class)
==>null
gremlin> g.io('data/grateful-dead.xml').read().iterate()
gremlin> clock(1000){g.V().has('name','Garcia').iterate()} //// (2)
==>0.027926219999999998
```

```
graph = TinkerGraph.open()
g = traversal().with(graph)
g.io('data/grateful-dead.xml').read().iterate()
clock(1000) {g.V().has('name','Garcia').iterate()} //// (1)
graph = TinkerGraph.open()
g = traversal().with(graph)
graph.createIndex('name',Vertex.class)
g.io('data/grateful-dead.xml').read().iterate()
clock(1000){g.V().has('name','Garcia').iterate()} //2
```

1. Determine the average runtime of 1000 vertex lookups when no `name`-index is defined.
2. Determine the average runtime of 1000 vertex lookups when a `name`-index is defined.

|  |  |
| --- | --- |
| Important | Each graph system will have different mechanism by which indices and schemas are defined. TinkerPop does not require any conformance in this area. In TinkerGraph, the only definitions are around indices. With other graph systems, property value types, indices, edge labels, etc. may be required to be defined *a priori* to adding data to the graph. |

|  |  |
| --- | --- |
| Note | TinkerGraph is distributed with Gremlin Server and is therefore automatically available to it for configuration. |

### Data Types

TinkerGraph can store any Java `Object` for a property value. It is therefore important to take note of the types of
the values that are being used and it is often best to be explicit in terms of exactly what type is being used,
especially in the case of numbers.

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.addV().property('vp2',0.65780294)
==>v[0]
gremlin> g.addV().property('vp2',0.65780294f)
==>v[2]
gremlin> g.addV().property('vp2',0.65780294d)
==>v[4]
gremlin> g.V().has('vp2',0.65780294) //// (1)
==>v[0]
==>v[2]
==>v[4]
gremlin> g.V().has('vp2',0.65780294f) //// (2)
==>v[0]
==>v[2]
gremlin> g.V().has('vp2',0.65780294d) //// (3)
==>v[0]
==>v[4]
```

```
graph = TinkerGraph.open()
g = traversal().with(graph)
g.addV().property('vp2',0.65780294)
g.addV().property('vp2',0.65780294f)
g.addV().property('vp2',0.65780294d)
g.V().has('vp2',0.65780294) //// (1)
g.V().has('vp2',0.65780294f) //// (2)
g.V().has('vp2',0.65780294d)    //3
```

1. In Gremlin Console, `0.65780294` actually evaluates to a `BigDecimal`, which won’t match the specifically typed
   `float` property value.
2. The explicit `float` will only match the `float` property value.
3. The explicit `double` will only match the `double` and `BigDecimal` values.

Unlike other graphs, the above demonstration shows that TinkerGraph does not do any form of type coercion (except for
type coercion related to element identifiers as described in the [tinkergraph-configuration](#next section)).

### Configuration

TinkerGraph has several settings that can be provided on creation via `Configuration` object:

| Property | Description |
| --- | --- |
| gremlin.graph | `org.apache.tinkerpop.gremlin.tinkergraph.structure.TinkerGraph` |
| gremlin.tinkergraph.vertexIdManager | The `IdManager` implementation to use for vertices. |
| gremlin.tinkergraph.edgeIdManager | The `IdManager` implementation to use for edges. |
| gremlin.tinkergraph.vertexPropertyIdManager | The `IdManager` implementation to use for vertex properties. |
| gremlin.tinkergraph.defaultVertexPropertyCardinality | The default `VertexProperty.Cardinality` to use when `Vertex.property(k,v)` is called. |
| gremlin.tinkergraph.allowNullPropertyValues | A boolean value that determines whether or not `null` property values are allowed and defaults to `false`. |
| gremlin.tinkergraph.graphLocation | The path and file name for where TinkerGraph should persist the graph data. If a value is specified here, the `gremlin.tinkergraph.graphFormat` should also be specified. If this value is not included (default), then the graph will stay in-memory and not be loaded/persisted to disk. |
| gremlin.tinkergraph.graphFormat | The format to use to serialize the graph which may be one of the following: `graphml`, `graphson`, `gryo`, or a fully qualified class name that implements Io.Builder interface (which allows for external third party graph reader/writer formats to be used for persistence). If a value is specified here, then the `gremlin.tinkergraph.graphLocation` should also be specified. If this value is not included (default), then the graph will stay in-memory and not be loaded/persisted to disk. |

|  |  |
| --- | --- |
| Note | To use [transactions](13-tinkergraph.md#tinkergraph-gremlin-tx), configure `gremlin.graph` as `org.apache.tinkerpop.gremlin.tinkergraph.structure.TinkerTransactionGraph`. |

The `IdManager` settings above refer to how TinkerGraph will control identifiers for vertices, edges and vertex
properties. There are several options for each of these settings: `ANY`, `LONG`, `INTEGER`, `UUID`, `STRING` or the
fully qualified class name of an `IdManager` implementation on the classpath. When not specified, the default values
for all settings is `ANY`, meaning that the graph will work with any object on the JVM as the identifier and will
generate new identifiers from `Long` when the identifier is not user supplied. TinkerGraph will also expect the
user to understand the types used for identifiers when querying, meaning that `g.V(1)` and `g.V(1L)` could return
two different vertices. `LONG`, `INTEGER` and `UUID` settings will try to coerce identifier values to the expected
type as well as generate new identifiers with that specified type.

|  |  |
| --- | --- |
| Tip | Setting the `IdManager` to `ANY` also allows `String` type ID values to be used. |

If the TinkerGraph is configured for persistence with `gremlin.tinkergraph.graphLocation` and
`gremlin.tinkergraph.graphFormat`, then the graph will be written to the specified location with the specified
format when `Graph.close()` is called. In addition, if these settings are present, TinkerGraph will attempt to
load the graph from the specified location.

|  |  |
| --- | --- |
| Important | If choosing `graphson` as the `gremlin.tinkergraph.graphFormat`, be sure to also establish the various `IdManager` settings as well to ensure that identifiers are properly coerced to the appropriate types as GraphSON can lose the identifier’s type during serialization (i.e. it will assume `Integer` when the default for TinkerGraph is `Long`, which could lead to load errors that result in a message like, "Vertex with id already exists"). |

It is important to consider the data being imported to TinkerGraph with respect to `defaultVertexPropertyCardinality`
setting. For example, if a `.gryo` file is known to contain multi-property data, be sure to set the default
cardinality to `list` or else the data will import as `single`. Consider the following:

console (groovy)

groovy

```
gremlin> graph = TinkerGraph.open()
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.io("data/tinkerpop-crew.kryo").read().iterate()
[WARN] o.a.t.g.s.u.Attachable$Method - location has SINGLE cardinality but with more than one value: [vp[location->san diego], vp[location->santa cruz], vp[location->brussels], vp[location->santa fe]]. Only last value will be retained.
[WARN] o.a.t.g.s.u.Attachable$Method - location has SINGLE cardinality but with more than one value: [vp[location->centreville], vp[location->dulles], vp[location->purcellville]]. Only last value will be retained.
[WARN] o.a.t.g.s.u.Attachable$Method - location has SINGLE cardinality but with more than one value: [vp[location->bremen], vp[location->baltimore], vp[location->oakland], vp[location->seattle]]. Only last value will be retained.
[WARN] o.a.t.g.s.u.Attachable$Method - location has SINGLE cardinality but with more than one value: [vp[location->spremberg], vp[location->kaiserslautern], vp[location->aachen]]. Only last value will be retained.
gremlin> g.V().properties()
==>vp[name->marko]
==>vp[location->santa fe]
==>vp[name->stephen]
==>vp[location->purcellville]
==>vp[name->matthias]
==>vp[location->seattle]
==>vp[name->daniel]
==>vp[location->aachen]
==>vp[name->gremlin]
==>vp[name->tinkergraph]
gremlin> conf = new BaseConfiguration()
==>org.apache.commons.configuration2.BaseConfiguration@7d8a5ec7
gremlin> conf.setProperty("gremlin.tinkergraph.defaultVertexPropertyCardinality","list")
==>null
gremlin> graph = TinkerGraph.open(conf)
==>tinkergraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> g.io("data/tinkerpop-crew.kryo").read().iterate()
gremlin> g.V().properties()
==>vp[name->marko]
==>vp[location->san diego]
==>vp[location->santa cruz]
==>vp[location->brussels]
==>vp[location->santa fe]
==>vp[name->stephen]
==>vp[location->centreville]
==>vp[location->dulles]
==>vp[location->purcellville]
==>vp[name->matthias]
==>vp[location->bremen]
==>vp[location->baltimore]
==>vp[location->oakland]
==>vp[location->seattle]
==>vp[name->daniel]
==>vp[location->spremberg]
==>vp[location->kaiserslautern]
==>vp[location->aachen]
==>vp[name->gremlin]
==>vp[name->tinkergraph]
```

```
graph = TinkerGraph.open()
g = traversal().with(graph)
g.io("data/tinkerpop-crew.kryo").read().iterate()
g.V().properties()
conf = new BaseConfiguration()
conf.setProperty("gremlin.tinkergraph.defaultVertexPropertyCardinality","list")
graph = TinkerGraph.open(conf)
g = traversal().with(graph)
g.io("data/tinkerpop-crew.kryo").read().iterate()
g.V().properties()
```

### Transactions

`TinkerGraph` includes optional transaction support and thread-safety through the `TinkerTransactionGraph` class.
The default configuration of TinkerGraph remains non-transactional.

|  |  |
| --- | --- |
| Note | This feature was first made available in TinkerPop 3.7.0. |

#### Transaction Semantics

`TinkerTransactionGraph` only has support for `ThreadLocal` transactions, so embedded graph transactions may not be fully
supported. You can think of the transaction as belonging to a thread, any traversals executed within the same thread
will share the same transaction even if you attempt to start a new transaction.

`TinkerTransactionGraph` provides the `read committed` transaction isolation level. This means that it will always try to
guard against dirty reads but will not prevent non-repeatable reads or phantom reads. While you may notice stricter
isolation semantics in some cases, you should not depend on this behavior as it may change in the future.

`TinkerTransactionGraph` employs optimistic locking as its locking strategy. This reduces complexity in the design as
there are fewer timeouts that the user needs to manage. However, a consequence of this approach is that a transaction
will throw a `TransactionException` if two different transactions attempt to lock the same element (see "Best Practices"
below).

#### Testing Remote Providers

These transaction semantics described above may not fit use cases for some production scenarios that require strict
ACID-like transactions. Therefore, it is recommended that `TinkerTransactionGraph` be used as a `Graph` for test
environments where you still require access to a `Graph` that supports transactions. `TinkerTransactionGraph` does fully
support TinkerPop’s `Transaction` interface which still makes it a useful `Graph` for exploring the
[Transaction API](#transactions).

A common scenario where this sort of testing is helpful is with [Remote Graph Providers](#connecting-rgp), where
developing unit tests might be hard against a graph service. Instead, configure `TinkerTransactionGraph`, either in an
embedded style if using Java or with Gremlin Server for other cases.

```
// consider this class that returns the results of some Gremlin. by constructing the
// GraphService in a way that takes a GraphTraversalSource it becomes possible to
// execute getPersons() under any graph system.
public class GraphService {
    private final GraphTraversalSource g;

    public GraphService(GraphTraversalSource g) {
        this.g = g;
    }

    public List<Vertex> getPersons() {
        return g.V().hasLabel("person").toList();
    }
}

// when writing tests for the GraphService it becomes possible to configure the test
// to run in a variety of scenarios. here we decide that TinkerTransactionGraph is a
// suitable test graph replacement for our actual production graph.
public class GraphServiceTest {
    private static final TinkerTransactionGraph graph = TinkerTransactionGraph.open();
    private static final GraphTraversalSource g = traversal.with(graph);
    private static final GraphService service = new GraphService(g);

    @Test
    public void shouldGetPersons() {
        final List<Vertex> persons = service.getPersons();
        assertEquals(6, persons.size());
    }
}

// or perhaps, since we're using a remote graph provider, we feel it would be better to
// start Gremlin Server with a TinkerTransactionGraph configured using a docker container,
// embedding it directly in our tests or running it as a separate process like:
//
// bin/gremlin-server.sh conf/gremlin-server-transaction.yaml
//
// and then connect to it with a driver in more of an integration test style. obviously,
// with this approach you could also configure your production graph directly or use custom
// build options to trigger different test configurations for a more dynamic approach
public class GraphServiceTest {
    private static final GraphTraversalSource g = traversal.with(
            new DriverRemoteConnection('ws://localhost:8182/gremlin'));
    private static final GraphService service = new GraphService(g);

    @Test
    public void shouldGetPersons() {
        final List<Vertex> persons = service.getPersons();
        assertEquals(6, persons.size());
    }
}
```

|  |  |
| --- | --- |
| Warning | There can be subtle behavioral differences between TinkerGraph and the graph ultimately intended for use. Be aware of the differences when writing tests to ensure that you are testing behaviors of your applications appropriately. |

#### Best Practices

Errors can occur before a transaction gets committed. Specifically for `TinkerTransactionGraph`, you may encounter many
`TransactionException` errors in a highly concurrent environment due its optimistic approach to locking. Users should
follow the try-catch-rollback pattern described in the
[transactions](https://tinkerpop.apache.org/docs/3.8.0/reference/#transactions) section in combination with
exponential backoff based retries to mitigate this issue.

#### Performance Considerations

While transactions impose minimal impact for mutating workloads, users should expect performance degradation for
read-only work relative to the non-transactional configuration. However, its approach to locking
(write-only, optimistic) and its in-memory nature, TinkerTransactionGraph is likely faster than other `Graph`
implementations that support transactions.

#### Examples

Constructing a simple graph using `TinkerTransactionGraph` in Java is presented below:

```
Graph graph = TinkerTransactionGraph.open();
g = traversal().with(graph)
GraphTraversalSource gtx = g.tx().begin();

try {
  Vertex marko = gtx.addV("person").property("name","marko").property("age",29).next();
  Vertex lop = gtx.addV("software").property("name","lop").property("lang","java").next();
  gtx.addE("created").from(marko).to(lop).property("weight",0.6d).iterate();

  gtx.tx().commit();
} catch (Exception ex) {
  gtx.tx().rollback();
}
```

The above Gremlin creates two vertices named "marko" and "lop" and connects them via a created-edge with a weight=0.6
property. In case of any errors `rollback()` will be called and no changes will be performed.

To use the embedded TinkerTransactionGraph in Gremlin Console:

console (groovy)

groovy

```
gremlin> graph = TinkerTransactionGraph.open() //// (1)
==>tinkertransactiongraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph) //// (2)
==>graphtraversalsource[tinkertransactiongraph[vertices:0 edges:0], standard]
gremlin> g.addV('test').property('name','one')
==>v[0]
gremlin> g.tx().commit() //// (3)
==>null
gremlin> g.V().valueMap()
==>[name:[one]]
gremlin> g.addV('test').property('name','two') //// (4)
==>v[2]
gremlin> g.V().valueMap()
==>[name:[one]]
==>[name:[two]]
gremlin> g.tx().rollback() //// (5)
==>null
gremlin> g.V().valueMap()
==>[name:[one]]
```

```
graph = TinkerTransactionGraph.open() //// (1)
g = traversal().with(graph) //// (2)
g.addV('test').property('name','one')
g.tx().commit() //// (3)
g.V().valueMap()
g.addV('test').property('name','two') //// (4)
g.V().valueMap()
g.tx().rollback() //// (5)
g.V().valueMap()
```

1. Open transactional graph.
2. Spawn a GraphTraversalSource with transactional graph.
3. Commit the add vertex operation
4. Add a second vertex without committing
5. Rollback the change

### Transactions

`TinkerGraph` includes optional transaction support and thread-safety through the `TinkerTransactionGraph` class.
The default configuration of TinkerGraph remains non-transactional.

|  |  |
| --- | --- |
| Note | This feature was first made available in TinkerPop 3.7.0. |

#### Transaction Semantics

`TinkerTransactionGraph` only has support for `ThreadLocal` transactions, so embedded graph transactions may not be fully
supported. You can think of the transaction as belonging to a thread, any traversals executed within the same thread
will share the same transaction even if you attempt to start a new transaction.

`TinkerTransactionGraph` provides the `read committed` transaction isolation level. This means that it will always try to
guard against dirty reads but will not prevent non-repeatable reads or phantom reads. While you may notice stricter
isolation semantics in some cases, you should not depend on this behavior as it may change in the future.

`TinkerTransactionGraph` employs optimistic locking as its locking strategy. This reduces complexity in the design as
there are fewer timeouts that the user needs to manage. However, a consequence of this approach is that a transaction
will throw a `TransactionException` if two different transactions attempt to lock the same element (see "Best Practices"
below).

#### Testing Remote Providers

These transaction semantics described above may not fit use cases for some production scenarios that require strict
ACID-like transactions. Therefore, it is recommended that `TinkerTransactionGraph` be used as a `Graph` for test
environments where you still require access to a `Graph` that supports transactions. `TinkerTransactionGraph` does fully
support TinkerPop’s `Transaction` interface which still makes it a useful `Graph` for exploring the
[Transaction API](#transactions).

A common scenario where this sort of testing is helpful is with [Remote Graph Providers](#connecting-rgp), where
developing unit tests might be hard against a graph service. Instead, configure `TinkerTransactionGraph`, either in an
embedded style if using Java or with Gremlin Server for other cases.

```
// consider this class that returns the results of some Gremlin. by constructing the
// GraphService in a way that takes a GraphTraversalSource it becomes possible to
// execute getPersons() under any graph system.
public class GraphService {
    private final GraphTraversalSource g;

    public GraphService(GraphTraversalSource g) {
        this.g = g;
    }

    public List<Vertex> getPersons() {
        return g.V().hasLabel("person").toList();
    }
}

// when writing tests for the GraphService it becomes possible to configure the test
// to run in a variety of scenarios. here we decide that TinkerTransactionGraph is a
// suitable test graph replacement for our actual production graph.
public class GraphServiceTest {
    private static final TinkerTransactionGraph graph = TinkerTransactionGraph.open();
    private static final GraphTraversalSource g = traversal.with(graph);
    private static final GraphService service = new GraphService(g);

    @Test
    public void shouldGetPersons() {
        final List<Vertex> persons = service.getPersons();
        assertEquals(6, persons.size());
    }
}

// or perhaps, since we're using a remote graph provider, we feel it would be better to
// start Gremlin Server with a TinkerTransactionGraph configured using a docker container,
// embedding it directly in our tests or running it as a separate process like:
//
// bin/gremlin-server.sh conf/gremlin-server-transaction.yaml
//
// and then connect to it with a driver in more of an integration test style. obviously,
// with this approach you could also configure your production graph directly or use custom
// build options to trigger different test configurations for a more dynamic approach
public class GraphServiceTest {
    private static final GraphTraversalSource g = traversal.with(
            new DriverRemoteConnection('ws://localhost:8182/gremlin'));
    private static final GraphService service = new GraphService(g);

    @Test
    public void shouldGetPersons() {
        final List<Vertex> persons = service.getPersons();
        assertEquals(6, persons.size());
    }
}
```

|  |  |
| --- | --- |
| Warning | There can be subtle behavioral differences between TinkerGraph and the graph ultimately intended for use. Be aware of the differences when writing tests to ensure that you are testing behaviors of your applications appropriately. |

#### Best Practices

Errors can occur before a transaction gets committed. Specifically for `TinkerTransactionGraph`, you may encounter many
`TransactionException` errors in a highly concurrent environment due its optimistic approach to locking. Users should
follow the try-catch-rollback pattern described in the
[transactions](https://tinkerpop.apache.org/docs/3.8.0/reference/#transactions) section in combination with
exponential backoff based retries to mitigate this issue.

#### Performance Considerations

While transactions impose minimal impact for mutating workloads, users should expect performance degradation for
read-only work relative to the non-transactional configuration. However, its approach to locking
(write-only, optimistic) and its in-memory nature, TinkerTransactionGraph is likely faster than other `Graph`
implementations that support transactions.

#### Examples

Constructing a simple graph using `TinkerTransactionGraph` in Java is presented below:

```
Graph graph = TinkerTransactionGraph.open();
g = traversal().with(graph)
GraphTraversalSource gtx = g.tx().begin();

try {
  Vertex marko = gtx.addV("person").property("name","marko").property("age",29).next();
  Vertex lop = gtx.addV("software").property("name","lop").property("lang","java").next();
  gtx.addE("created").from(marko).to(lop).property("weight",0.6d).iterate();

  gtx.tx().commit();
} catch (Exception ex) {
  gtx.tx().rollback();
}
```

The above Gremlin creates two vertices named "marko" and "lop" and connects them via a created-edge with a weight=0.6
property. In case of any errors `rollback()` will be called and no changes will be performed.

To use the embedded TinkerTransactionGraph in Gremlin Console:

console (groovy)

groovy

```
gremlin> graph = TinkerTransactionGraph.open() //// (1)
==>tinkertransactiongraph[vertices:0 edges:0]
gremlin> g = traversal().with(graph) //// (2)
==>graphtraversalsource[tinkertransactiongraph[vertices:0 edges:0], standard]
gremlin> g.addV('test').property('name','one')
==>v[0]
gremlin> g.tx().commit() //// (3)
==>null
gremlin> g.V().valueMap()
==>[name:[one]]
gremlin> g.addV('test').property('name','two') //// (4)
==>v[2]
gremlin> g.V().valueMap()
==>[name:[one]]
==>[name:[two]]
gremlin> g.tx().rollback() //// (5)
==>null
gremlin> g.V().valueMap()
==>[name:[one]]
```

```
graph = TinkerTransactionGraph.open() //// (1)
g = traversal().with(graph) //// (2)
g.addV('test').property('name','one')
g.tx().commit() //// (3)
g.V().valueMap()
g.addV('test').property('name','two') //// (4)
g.V().valueMap()
g.tx().rollback() //// (5)
g.V().valueMap()
```

1. Open transactional graph.
2. Spawn a GraphTraversalSource with transactional graph.
3. Commit the add vertex operation
4. Add a second vertex without committing
5. Rollback the change

