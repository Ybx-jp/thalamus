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

