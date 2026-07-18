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

