# The Traversal

![gremlin running](../images/gremlin-running.png)

At the most general level there is `Traversal<S,E>` which implements `Iterator<E>`, where the `S` stands for start and
the `E` stands for end. A traversal is composed of four primary components:

1. `Step<S,E>`: an individual function applied to `S` to yield `E`. Steps are chained within a traversal.
2. `TraversalStrategy`: interceptor methods to alter the execution of the traversal (e.g. query re-writing).
3. `TraversalSideEffects`: key/value pairs that can be used to store global information about the traversal.
4. `Traverser<T>`: the object propagating through the `Traversal` currently representing an object of type `T`.

The classic notion of a graph traversal is provided by `GraphTraversal<S,E>` which extends `Traversal<S,E>`.
`GraphTraversal` provides an interpretation of the graph data in terms of vertices, edges, etc. and thus, a graph
traversal [DSL](http://en.wikipedia.org/wiki/Domain-specific_language).

![step types](../images/step-types.png)

A `GraphTraversal<S,E>` is spawned from a `GraphTraversalSource`. It can also be spawned anonymously (i.e. empty)
via `__`. A graph traversal is composed of an ordered list of steps. All the steps provided by `GraphTraversal`
inherit from the more general forms diagrammed above. A list of all the steps (and their descriptions) are provided
in the TinkerPop [GraphTraversal JavaDoc](https://tinkerpop.apache.org/javadocs/3.8.0/core/org/apache/tinkerpop/gremlin/process/traversal/dsl/graph/GraphTraversal.html).

|  |  |
| --- | --- |
| Important | The basics for starting a traversal are described in [The Graph Process](#the-graph-process) section as well as in the [Getting Started](https://tinkerpop.apache.org/docs/3.8.0/tutorials/getting-started/) tutorial. |

|  |  |
| --- | --- |
| Note | To reduce the verbosity of the expression, it is good to `import static org.apache.tinkerpop.gremlin.process.traversal.dsl.graph.__.*`. This way, instead of doing `__.inE()` for an anonymous traversal, it is possible to simply write `inE()`. Be aware of language-specific reserved keywords when using anonymous traversals. For example, `in` and `as` are reserved keywords in Groovy, therefore you must use the verbose syntax `__.in()` and `__.as()` to avoid collisions. |

|  |  |
| --- | --- |
| Important | The underlying `Step` implementations provided by TinkerPop should encompass most of the functionality required by a DSL author. It is important that DSL authors leverage the provided steps as then the common optimization and decoration strategies can reason on the underlying traversal sequence. If new steps are introduced, then common traversal strategies may not function properly. |

## Traversal Transactions

![gremlin coins](../images/gremlin-coins.png) A [database transaction](http://en.wikipedia.org/wiki/Database_transaction)
represents a unit of work to execute against the database. A traversals unit of work is affected by usage convention
(i.e. the method of [connecting](02-connecting.md#connecting-gremlin)) and the graph provider's transaction model. Without diving
deeply into different conventions and models the most general and recommended approach to working with transactions is
demonstrated as follows:

```
GraphTraversalSource g = traversal().with(graph);
// or
GraphTraversalSource g = traversal().with(conn);

Transaction tx = g.tx();

// spawn a GraphTraversalSource from the Transaction. Traversals spawned
// from gtx will be essentially be bound to tx
GraphTraversalSource gtx = tx.begin();
try {
    gtx.addV('person').iterate();
    gtx.addV('software').iterate();

    tx.commit();
} catch (Exception ex) {
    tx.rollback();
}
```

The above example is straightforward and represents a good starting point for discussing the nuances of transactions
in relation to the usage convention and graph provider caveats alluded to earlier.

Focusing on remote contexts first, note that it is still possible to issue traversals from `g`, but those will have a
transaction scope outside of `gtx` and will simply `commit()` on the server if successfully executed or `rollback()`
on the server otherwise (i.e. one traversal is one transaction). Each isolated transaction will require its own
`Transaction` object. Multiple `begin()` calls on the same `Transaction` object will produce `GraphTraversalSource`
instances that are bound to the same transaction, therefore:

```
GraphTraversalSource g = traversal().with(conn);
Transaction tx1 = g.tx();
Transaction tx2 = g.tx();

// both gtx1a and gtx1b will be bound to the same transaction
GraphTraversalSource gtx1a = tx1.begin();
GraphTraversalSource gtx1b = tx1.begin();

// g and gtx2 will not have knowledge of what happens in tx1
GraphTraversalSource gtx2 = tx2.begin();
```

In remote cases, `GraphTraversalSource` instances spawned from `begin()` are safe to use in multiple threads though
on the server side they will be processed serially as they arrive. The default behavior of `close()` on a
`Transaction` for remote cases is to `commit()`, so the following re-write of the earlier example is also valid:

```
// note here that we dispense with creating a Transaction object and
// simply spawn the gtx in a more inline fashion
GraphTraversalSource gtx = g.tx().begin();
try {
    gtx.addV('person').iterate();
    gtx.addV('software').iterate();
    gtx.close();
} catch (Exception ex) {
    tx.rollback();
}
```

|  |  |
| --- | --- |
| Important | Transactions with non-JVM languages are always "remote". For specific transaction syntax in a particular language, please see the "Transactions" sub-section of your language of interest in the [Gremlin Drivers and Variants](12-gremlin-python.md#gremlin-drivers-variants) section. |

In embedded cases, that initial recommended model for defining transactions holds, but users have more options here
on deeper inspection. For embedded use cases (and perhaps even in configuration of a graph instance in Gremlin Server),
the type of `Transaction` object that is returned from `g.tx()` is an important indicator as to the features of that
graph's transaction model. In most cases, inspection of that object will indicate an instance that derives from the
`AbstractThreadLocalTransaction` class, which means that the transaction is bound to the current thread and therefore
all traversals that execute within that thread are tied to that transaction.

A `ThreadLocal` transaction differs then from the remote case described before because technically any traversal
spawned from `g` or from a `Transaction` will fall under the same transaction scope. As a result, it is wise, when
trying to write context agnostic Gremlin, to follow the more rigid conventions of the initial example.

The sub-sections that follow offer a bit more insight into each of the usage contexts.

### Embedded

When on the JVM using an [embedded graph](#connecting-embedded), there is considerable flexibility for working with
transactions. With the Graph API, transactions are controlled by an implementation of the `Transaction` interface and
that object can be obtained from the `Graph` interface using the `tx()` method. It is important to note that the
`Transaction` object does not represent a "transaction" itself. It merely exposes the methods for working with
transactions (e.g. committing, rolling back, etc).

Most `Graph` implementations that `supportsTransactions` will implement an "automatic" `ThreadLocal` transaction,
which means that when a read or write occurs after the `Graph` is instantiated, a transaction is automatically
started within that thread. There is no need to manually call a method to "create" or "start" a transaction. Simply
modify the graph as required and call `graph.tx().commit()` to apply changes or `graph.tx().rollback()` to undo them.
When the next read or write action occurs against the graph, a new transaction will be started within that current
thread of execution.

When using transactions in this fashion, especially in web application (e.g. HTTP server), it is important to ensure
that transactions do not leak from one request to the next. In other words, unless a client is somehow bound via
session to process every request on the same server thread, every request must be committed or rolled back at the end
of the request. By ensuring that the request encapsulates a transaction, it ensures that a future request processed
on a server thread is starting in a fresh transactional state and will not have access to the remains of one from an
earlier request. A good strategy is to rollback a transaction at the start of a request, so that if it so happens that
a transactional leak does occur between requests somehow, a fresh transaction is assured by the fresh request.

|  |  |
| --- | --- |
| Tip | The `tx()` method is on the `Graph` interface, but it is also available on the `TraversalSource` spawned from a `Graph`. Calls to `TraversalSource.tx()` are proxied through to the underlying `Graph` as a convenience. |

|  |  |
| --- | --- |
| Tip | Some graphs may throw an exception that implements `TemporaryException`. In this case, this marker interface is designed to inform the client that it may choose to retry the operation at a later time for possible success. |

|  |  |
| --- | --- |
| Warning | TinkerPop provides for basic transaction control, however, like many aspects of TinkerPop, it is up to the graph system provider to choose the specific aspects of how their implementation will work and how it fits into the TinkerPop stack. Be sure to understand the transaction semantics of the specific graph implementation that is being utilized as it may present differing functionality than described here. |

#### Configuring

Determining when a transaction starts is dependent upon the behavior assigned to the `Transaction`. It is up to the
`Graph` implementation to determine the default behavior and unless the implementation doesn't allow it, the behavior
itself can be altered via these `Transaction` methods:

```
public Transaction onReadWrite(Consumer<Transaction> consumer);

public Transaction onClose(Consumer<Transaction> consumer);
```

Providing a `Consumer` function to `onReadWrite` allows definition of how a transaction starts when a read or a write
occurs. `Transaction.READ_WRITE_BEHAVIOR` contains pre-defined `Consumer` functions to supply to the `onReadWrite`
method. It has two options:

* `AUTO` - automatic transactions where the transaction is started implicitly to the read or write operation
* `MANUAL` - manual transactions where it is up to the user to explicitly open a transaction, throwing an exception
  if the transaction is not open

Providing a `Consumer` function to `onClose` allows configuration of how a transaction is handled when
`Transaction.close()` is called. `Transaction.CLOSE_BEHAVIOR` has several pre-defined options that can be supplied to
this method:

* `COMMIT` - automatically commit an open transaction
* `ROLLBACK` - automatically rollback an open transaction
* `MANUAL` - throw an exception if a transaction is open, forcing the user to explicitly close the transaction

|  |  |
| --- | --- |
| Important | As transactions are `ThreadLocal` in nature, so are the transaction configurations for `onReadWrite` and `onClose`. |

Once there is an understanding for how transactions are configured, most of the rest of the `Transaction` interface
is self-explanatory. Note that [Neo4j-Gremlin](#neo4j-gremlin) is used for the examples to follow as TinkerGraph does
not support transactions.

|  |  |
| --- | --- |
| Important | The following example is meant to demonstrate specific use of `ThreadLocal` transactions and is at odds with the more generalized transaction convention that is recommended for both embedded and remote contexts. Please be sure to understand the preferred approach described at in the [Traversal Transactions Section](#transactions) before using this method. |

```
gremlin> graph = Neo4jGraph.open('/tmp/neo4j')
==>neo4jgraph[EmbeddedGraphDatabase [/tmp/neo4j]]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[neo4jgraph[community single [/tmp/neo4j]], standard]
gremlin> graph.features()
==>FEATURES
> GraphFeatures
>-- Transactions: true  //1
>-- Computer: false
>-- Persistence: true
...
gremlin> g.tx().onReadWrite(Transaction.READ_WRITE_BEHAVIOR.AUTO) //2
==>org.apache.tinkerpop.gremlin.neo4j.structure.Neo4jGraph$Neo4jTransaction@1c067c0d
gremlin> g.addV("person").("name","stephen")  //3
==>v[0]
gremlin> g.tx().commit() //4
==>null
gremlin> g.tx().onReadWrite(Transaction.READ_WRITE_BEHAVIOR.MANUAL) //5
==>org.apache.tinkerpop.gremlin.neo4j.structure.Neo4jGraph$Neo4jTransaction@1c067c0d
gremlin> g.tx().isOpen()
==>false
gremlin> g.addV("person").("name","marko") //6
Open a transaction before attempting to read/write the transaction
gremlin> g.tx().open() //7
==>null
gremlin> g.addV("person").("name","marko") //8
==>v[1]
gremlin> g.tx().commit()
==>null
```

1. Check `features` to ensure that the graph supports transactions.
2. By default, `Neo4jGraph` is configured with "automatic" transactions, so it is set here for demonstration purposes only.
3. When the vertex is added, the transaction is automatically started. From this point, more mutations can be staged
   or other read operations executed in the context of that open transaction.
4. Calling `commit` finalizes the transaction.
5. Change transaction behavior to require manual control.
6. Adding a vertex now results in failure because the transaction was not explicitly opened.
7. Explicitly open a transaction.
8. Adding a vertex now succeeds as the transaction was manually opened.

|  |  |
| --- | --- |
| Note | It may be important to consult the documentation of the `Graph` implementation you are using when it comes to the specifics of how transactions will behave. TinkerPop allows some latitude in this area and implementations may not have the exact same behaviors and [ACID](https://en.wikipedia.org/wiki/ACID) guarantees. |

### Gremlin Server

The available capability for transactions with [Gremlin Server](11-gremlin-server.md#gremlin-server) is dependent upon the method of
interaction that is used. The preferred method for [interacting with Gremlin Server](02-connecting.md#connecting-gremlin-server)
is via websockets and bytecode based requests. The start of the [Transactions Section](#transactions) describes this
approach in detail with examples.

Gremlin Server also has the option to accept Gremlin-based scripts. The scripting approach provides access to the
Graph API and thus also the transactional model described in the [embedded](#tx-embedded) section. Therefore a single
script can have the ability to execute multiple transactions per request with complete control provided to the
developer to commit or rollback transactions as needed.

There are two methods for sending scripts to Gremlin Server: sessionless and session-based. With sessionless requests
there will always be an attempt to close the transaction at the end of the request with a commit if there are no errors
or a rollback if there is a failure. It is therefore unnecessary to close transactions manually within scripts
themselves. By default, session-based requests do not have this quality. The transaction will be held open on the
server until the user closes it manually. There is an option to have automatic transaction management for sessions.
More information on this topic can be found in the [Considering Transactions](#considering-transactions) Section and
the [Considering Sessions](#sessions) Section.

### Remote Gremlin Providers

At this time, transactional patterns for Remote Gremlin Providers are largely in line with Gremlin Server. As most of
RGPs do not expose a `Graph` instance, access to lower level transactional functions available to embedded graphs
even in a sessionless fashion are not typically permitted. For example, without a `Graph` instance it is not possible
to [configure](https://tinkerpop.apache.org/docs/3.8.0/reference/#tx-embedded) transaction close or read-write
behaviors. The nature of what a "transaction" means will be dependent on the RGP as is the case with any
TinkerPop-enabled graph system, so it is important to consult that systems documentation for more details.

## Configuration Steps

Many of the methods on the `GraphTraversalSource` are meant to configure the source for usage. These configuration
affect the manner in which a traversals are spawned from it. Configuration methods can be identified by their names
with make use of "with" as a prefix:

### With Configuration

The `with()` configuration adds arbitrary data to a `TraversalSource` which can then be used by graph providers as
configuration options for a traversal execution. This configuration is similar to [with()](06-steps/modulator-steps.md#with-step)-modulator which
has similar functionality when applied to an individual step.

```
g.with('providerDefinedVariable', 0.33).V()
```

The `0.33` value for the "providerDefinedVariable" will be bound to each traversal spawned that way. Consult the
graph system being used to determine if any such configuration options are available.

### WithBulk Configuration

The `withBulk()` configuration allows for control of bulking operations. This value is `true` by default allowing for
normal [bulking](06-steps/terminal-steps.md#barrier-step) operations, but when set to `false`, introduces a subtle change in that behavior as
shown in examples in [sack()-step](06-steps/sideeffect-steps.md#sack-step).

### WithComputer Configuration

The `withComputer()` configuration adds a `Computer` that will be used to process the traversal and is necessary for
OLAP based processing and steps that require that processing. See [examples](10-spark.md#sparkgraphcomputer) related to
`SparkGraphComputer` or see examples in the computer required steps, like [pageRank()](06-steps/map-steps.md#pagerank-step) or
[shortestPath()](06-steps/map-steps.md#shortestpath-step).

### WithSack Configuration

The `withSack()` configuration adds a "sack" that can be accessed by traversals spawned from this source. This
functionality is shown in more detail in the examples for [sack()](06-steps/sideeffect-steps.md#sack-step)-step.

### WithSideEffect Configuration

The `withSideEffect()` configuration adds an arbitrary `Object` to traversals spawned from this source which can be
accessed as a side-effect given the supplied key.

```
gremlin> g.withSideEffect('x',['dog','cat','fish']).
           V().has('person','name','marko').select('x').unfold()
==>dog
==>cat
==>fish
```

More practical examples can be found in other examples elsewhere in the documentation. The `math()`-step
[example](06-steps/map-steps.md#math-step) and the `where()`-step [example](06-steps/filter-steps.md#where-step) should both be helpful in examining this
configuration step more closely.

### WithStrategies Configuration

The `withStrategies()` configuration allows inclusion of additional `TraversalStrategy` instances to be applied to
any traversals spawned from the configured source. Please see the [Traversal Strategy Section](07-traversal-strategies.md#traversalstrategy)
for more details on how this configuration works.

### WithoutStrategies Configuration

The `withoutStrategies()` configuration removes a particular `TraversalStrategy` from those to be applied to traversals
spawned from the configured source. Please see the [Traversal Strategy Section](07-traversal-strategies.md#traversalstrategy) for more details
on how this configuration works.

## Start Steps

Not all steps are capable of starting a `GraphTraversal`. Only those steps on the `GraphTraversalSource` can do that.
Many of the methods on `GraphTraversalSource` are actually for its [configuration](#configuration-steps) and start
steps should not be confused with those.

Spawn steps, which actually yield a traversal, typically match the names of existing steps:

* `addE()` - Adds an `Edge` to start the traversal ([example](06-steps/start-steps.md#addedge-step)).
* `addV()` - Adds a `Vertex` to start the traversal ([example](06-steps/start-steps.md#addvertex-step)).
* `call()` - Makes a provider-specific service call to start the traversal ([example](06-steps/start-steps.md#call-step)).
* `E()` - Reads edges from the graph to start the traversal ([example](06-steps/start-steps.md#e-step)).
* `inject()` - Inserts arbitrary objects to start the traversal ([example](06-steps/start-steps.md#inject-step)).
* `mergeE()` - Adds an `Edge` in a "create if not exist" fashion to start the traversal ([example](06-steps/start-steps.md#mergeedge-step))
* `mergeV()` - Adds a `Vertex` in a "create if not exist" fashion to start the traversal ([example](06-steps/start-steps.md#mergevertex-step))
* `union()` - Merges the results of an arbitrary number of child traversals to start the traversal ([example](06-steps/branch-steps.md#union-step)).
* `V()` - Reads vertices from the graph to start the traversal ([example](06-steps/start-steps.md#graph-step)).

## Graph Traversal Steps

Gremlin steps are chained together to produce the actual traversal and are triggered by way of [start steps](06-steps/start-steps.md#start-steps)
on the `GraphTraversalSource`. For complete step documentation organized by category, see the [Steps Reference](06-steps/index.md):

* [Start Steps](06-steps/start-steps.md) - Steps that begin a traversal
* [Filter Steps](06-steps/filter-steps.md) - Steps that filter traversers based on conditions
* [Map Steps](06-steps/map-steps.md) - Steps that transform traversers to different values
* [SideEffect Steps](06-steps/sideeffect-steps.md) - Steps that perform side effects
* [Branch Steps](06-steps/branch-steps.md) - Steps that split or redirect the traversal flow
* [Terminal Steps](06-steps/terminal-steps.md) - Steps that end a traversal and produce results
* [Modulator Steps](06-steps/modulator-steps.md) - Steps that modify the behavior of other steps

|  |  |
| --- | --- |
| Important | More details about the Gremlin language can be found in the Provider Documentation within the [Gremlin Semantics Section](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#gremlin-semantics). |

## Additional Concepts

For more detailed information about traversal concepts, see [Traversal Concepts](05a-traversal-concepts.md):

* [Traversal Parameterization](05a-traversal-concepts.md#traversal-parameterization) - GValues for protection against injection attacks
* [Predicates](05a-traversal-concepts.md#a-note-on-predicates) - P and TextP predicates for filtering
* [Types](05a-traversal-concepts.md#a-note-on-types) - GType enums and type filtering
* [Maps](05a-traversal-concepts.md#a-note-on-maps) - Working with Map results
* [Barrier Steps](05a-traversal-concepts.md#a-note-on-barrier-steps) - Understanding lazy vs barrier processing
* [Scopes](05a-traversal-concepts.md#a-note-on-scopes) - Local vs global scope
* [Lambdas](05a-traversal-concepts.md#a-note-on-lambdas) - Why to avoid lambdas

## Related Topics

* [Traversal Strategies](07-traversal-strategies.md) - How traversals are optimized and verified
* [Domain Specific Languages](08-dsl.md) - Creating custom DSLs on top of Gremlin
