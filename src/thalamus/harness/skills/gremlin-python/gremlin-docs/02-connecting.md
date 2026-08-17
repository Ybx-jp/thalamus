## Connecting Gremlin

It was established in the initial introductory section that *Gremlin is Gremlin is Gremlin*, meaning that irrespective
of programming language, graph system, etc. the Gremlin written is always of the same general construct making it
possible for users to move between development languages and TinkerPop-enabled graph technology easily. This quality
of Gremlin generally applies to the traversal language itself. It applies less to the way in which the user connects
to a graph to utilize Gremlin, which might differ considerably depending on the programming language or graph database
chosen.

How one connects to a graph is a multi-faceted subject that essentially divides along a simple lines determined by the
answer to this question: Where is the Gremlin Traversal Machine (GTM)? The reason that this question is so important is
because the GTM is responsible for processing traversals. One can write Gremlin traversals in any language, but without
a GTM there will be no way to execute that traversal against a TinkerPop-enabled graph. The GTM is typically in one
of the following places:

* [Embedded](#connecting-embedded) in a Java application (i.e. Java Virtual Machine)
* [Hosted](02-connecting.md#connecting-gremlin-server) in [Gremlin Server](11-gremlin-server.md#gremlin-server)
* [Hosted](#connecting-rgp) by a Remote Gremlin Provider (RGP)

The following sections outline each of these models and what impact they have to using Gremlin.

### Embedded

![blueprints character 1](../images/blueprints-character-1.png) TinkerPop maintains the reference implementation for the GTM,
which is written in Java and thus available for the Java Virtual Machine (JVM). This is the classic model that
TinkerPop has long been based on and many examples, blog posts and other resources on the internet will be
demonstrated in this style. It is worth noting that the embedded mode is not restricted to just Java as a programming
language. Any JVM language can take this approach and in some cases there are language specific wrappers that can help
make Gremlin more convenient to use in the style and capability of that language. Examples of these wrappers include
[gremlin-scala](https://github.com/mpollmeier/gremlin-scala) and [Ogre](http://ogre.clojurewerkz.org/) (for Clojure).

In this mode, users will start by creating a `Graph` instance, followed by a `GraphTraversalSource` which is the class
from which Gremlin traversals are spawned. Graphs that allow this sort of direct instantiation are obviously ones
that are JVM-based (or have a JVM-based connector) and directly implement TinkerPop interfaces.

```
Graph graph = TinkerGraph.open();
```

The "graph" is then used to spawn a `GraphTraversalSource` as follows and typically, by convention, this variable is
named "g":

```
GraphTraversalSource g = traversal().with(graph);
List<Vertex> vertices = g.V().toList()
```

|  |  |
| --- | --- |
| Note | It may be helpful to read the [Gremlin Anatomy](https://tinkerpop.apache.org/docs/3.8.0/tutorials/gremlins-anatomy/) tutorial, which describes the component parts of Gremlin to get a better understanding of the terminology before proceeding further. |

While the TinkerPop Community strives to ensure consistent behavior among all modes of usage, the embedded mode does
provide the greatest level of flexibility and control. There are a number of features that can only work if using a
JVM language. The following list outlines a number of these available options:

* Lambdas can be written in the native language which is convenient, however, it will reduce the portability of Gremlin
  to do so should the need arise to switch away from the embedded mode. See more in the
  [Note on Lambdas](05a-traversal-concepts.md#a-note-on-lambdas) Section.
* Any features that involve extending TinkerPop Java interfaces - e.g. `VertexProgram`, `TraversalStrategy`, etc. are
  bound to the JVM. In some cases, these features can be made accessible to non-JVM languages, but they obviously must
  be initially developed for the JVM.
* Certain built-in `TraversalStrategy` implementations that rely on lambdas or other JVM-only configurations may not
  be available for use any other way.
* There are no boundaries put in place by serialization (e.g. GraphSON) as embedded graphs are only dealing with
  Java objects.
* Greater control of graph [transactions](#transactions).
* Direct access to lower-levels of the API - e.g. "structure" API methods like `Vertex` and `Edge` interface methods.
  As mentioned [elsewhere](01-introduction.md#graph-computing) in this documentation, TinkerPop does not recommend direct usage of these
  methods by end-users.

### Gremlin Server

![rexster character 3](../images/rexster-character-3.png) A JVM-based graph may be hosted in TinkerPop’s
[Gremlin Server](11-gremlin-server.md#gremlin-server). Gremlin Server exposes the graph as an endpoint to which different clients can
connect, essentially providing a remote GTM. Gremlin Server supports multiple methods for clients to interface with it:

* Websockets with a [custom sub-protocol](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#_graph_driver_provider_requirements)

  + String-based Gremlin scripts
  + Bytecode-based Gremlin traversals
* HTTP for string-based scripts

Users are encouraged to use the bytecode-based approach with websockets because it allows them to write Gremlin
in the language of their choice. Connecting looks somewhat similar to the [embedded](#connecting-embedded) approach
in that there is a need to create a `GraphTraversalSource`. In the embedded approach, the means for that object’s
creation is derived from a `Graph` object which spawns it. In this case, however, the `Graph` instance exists only on
the server which means that there is no `Graph` instance to create locally. The approach is to instead create a
`GraphTraversalSource` anonymously with `AnonymousTraversalSource` and then apply some "remote" options that describe
the location of the Gremlin Server to connect to:

java

groovy

csharp

javascript

python

go

```
// gremlin-driver module
import org.apache.tinkerpop.gremlin.driver.remote.DriverRemoteConnection;

// gremlin-core module
import static org.apache.tinkerpop.gremlin.process.traversal.AnonymousTraversalSource.traversal;

GraphTraversalSource g = traversal().with(
                DriverRemoteConnection.using("localhost", 8182));
```

```
// gremlin-driver module
import org.apache.tinkerpop.gremlin.driver.remote.DriverRemoteConnection;

// gremlin-core module
import static org.apache.tinkerpop.gremlin.process.traversal.AnonymousTraversalSource.traversal;

def g = traversal().with(
                DriverRemoteConnection.using('localhost', 8182))
```

```
using Gremlin.Net.IntegrationTest.Process.Traversal.DriverRemoteConnection;
using static Gremlin.Net.Process.Traversal.AnonymousTraversalSource;

var g = Traversal().With(new DriverRemoteConnection("localhost", 8182));
```

```
const traversal = gremlin.process.AnonymousTraversalSource.traversal;

const g = traversal().with(
                new DriverRemoteConnection('ws://localhost:8182/gremlin'));
```

```
from gremlin_python.process.anonymous_traversal_source import traversal

g = traversal().with(
          DriverRemoteConnection('ws://localhost:8182/gremlin'))
```

```
import (
    gremlingo "github.com/apache/tinkerpop/gremlin-go/v3/driver"
)

remote, err := gremlingo.NewDriverRemoteConnection("ws://localhost:8182/gremlin")
g := gremlingo.Traversal_().With(remote)
```

As shown in the embedded approach in the previous section, once "g" is defined, writing Gremlin is structurally and
conceptually the same irrespective of programming language.

|  |  |
| --- | --- |
| Tip | The variable `g`, the `TraversalSource`, only needs to be instantiated once and should then be re-used. |

#### Limitations

The previous section on the embedded model outlined a number of areas where it has some advantages that it gains due to
the fact that the full GTM is available to the user in the language of its origin, i.e. Java. Some of those items
touch upon important concepts to focus on here.

The first of these points is serialization. When Gremlin Server receives a request, the results must be serialized to
the form requested by the client and then the client deserializes those into objects native to the language. TinkerPop
has two such formats that it uses with [GraphBinary](https://tinkerpop.apache.org/docs/3.8.0/dev/io/#graphbinary) and
[GraphSON](https://tinkerpop.apache.org/docs/3.8.0/dev/io/#graphson). Users should prefer GraphBinary when available
in the programming language being used.

A good example is the `subgraph()`-step which returns a `Graph` instance as its result. The subgraph returned from
the server can be deserialized into an actual `Graph` instance on the client, which then means it is possible to
spawn a `GraphTraversalSource` from that to do local Gremlin traversals on the client-side. For non-JVM
[Gremlin Language Variants](12-gremlin-python.md#gremlin-drivers-variants) there is no local graph to deserialize that result into and
no GTM to process Gremlin so there isn’t much that can be done with such a result.

The second point is related to this issue. As there is no GTM, there is no "structure" API and thus graph elements like
`Vertex` and `Edge` are "references" only. A "reference" means that they only contain the `id` and `label` of the
element and not the properties. To be consistent, even JVM-based languages hold this limitation when talking to a
remote Gremlin Server.

|  |  |
| --- | --- |
| Important | Most SQL developers would not write a query as `SELECT * FROM table`. They would instead write the individual names of the fields they wanted in place of the wildcard. Writing "good" Gremlin is no different with this regard. Prefer explicit property key names in Gremlin unless it is completely impossible to do so. |

The third and final point involves transactions. Under this model, one traversal is equivalent to a single transaction
and there is no way in TinkerPop to string together multiple traversals into the same transaction.

### Remote Gremlin Provider

Remote Gremlin Providers (RGPs) are showing up more and more often in the graph database space. In TinkerPop terms,
this category of graph providers is defined by those who simply support the Gremlin language. Typically, these are
server-based graphs, often cloud-based, which accept Gremlin scripts or bytecode as a request and return results.
They will often implement Gremlin Server protocols, which enables TinkerPop drivers to connect to them as they would
with Gremlin Server. Therefore, the typical connection approach is identical to the method of connection presented in
the [previous section](02-connecting.md#connecting-gremlin-server) with the exact same caveats pointed out toward the end.

Despite leveraging TinkerPop protocols and drivers as being typical, RGPs are not required to do so to be considered
TinkerPop-enabled. RGPs may well have their own drivers and protocols that may plug into
[Gremlin Language Variants](12-gremlin-python.md#gremlin-drivers-variants) and may allow for more advanced options like better security,
cluster awareness, batched requests or other features. The details of these different systems are outside the scope
of this documentation, so be sure to consult their documentation for more information.

### Gremlin Server

![rexster character 3](../images/rexster-character-3.png) A JVM-based graph may be hosted in TinkerPop’s
[Gremlin Server](11-gremlin-server.md#gremlin-server). Gremlin Server exposes the graph as an endpoint to which different clients can
connect, essentially providing a remote GTM. Gremlin Server supports multiple methods for clients to interface with it:

* Websockets with a [custom sub-protocol](https://tinkerpop.apache.org/docs/3.8.0/dev/provider/#_graph_driver_provider_requirements)

  + String-based Gremlin scripts
  + Bytecode-based Gremlin traversals
* HTTP for string-based scripts

Users are encouraged to use the bytecode-based approach with websockets because it allows them to write Gremlin
in the language of their choice. Connecting looks somewhat similar to the [embedded](#connecting-embedded) approach
in that there is a need to create a `GraphTraversalSource`. In the embedded approach, the means for that object’s
creation is derived from a `Graph` object which spawns it. In this case, however, the `Graph` instance exists only on
the server which means that there is no `Graph` instance to create locally. The approach is to instead create a
`GraphTraversalSource` anonymously with `AnonymousTraversalSource` and then apply some "remote" options that describe
the location of the Gremlin Server to connect to:

java

groovy

csharp

javascript

python

go

```
// gremlin-driver module
import org.apache.tinkerpop.gremlin.driver.remote.DriverRemoteConnection;

// gremlin-core module
import static org.apache.tinkerpop.gremlin.process.traversal.AnonymousTraversalSource.traversal;

GraphTraversalSource g = traversal().with(
                DriverRemoteConnection.using("localhost", 8182));
```

```
// gremlin-driver module
import org.apache.tinkerpop.gremlin.driver.remote.DriverRemoteConnection;

// gremlin-core module
import static org.apache.tinkerpop.gremlin.process.traversal.AnonymousTraversalSource.traversal;

def g = traversal().with(
                DriverRemoteConnection.using('localhost', 8182))
```

```
using Gremlin.Net.IntegrationTest.Process.Traversal.DriverRemoteConnection;
using static Gremlin.Net.Process.Traversal.AnonymousTraversalSource;

var g = Traversal().With(new DriverRemoteConnection("localhost", 8182));
```

```
const traversal = gremlin.process.AnonymousTraversalSource.traversal;

const g = traversal().with(
                new DriverRemoteConnection('ws://localhost:8182/gremlin'));
```

```
from gremlin_python.process.anonymous_traversal_source import traversal

g = traversal().with(
          DriverRemoteConnection('ws://localhost:8182/gremlin'))
```

```
import (
    gremlingo "github.com/apache/tinkerpop/gremlin-go/v3/driver"
)

remote, err := gremlingo.NewDriverRemoteConnection("ws://localhost:8182/gremlin")
g := gremlingo.Traversal_().With(remote)
```

As shown in the embedded approach in the previous section, once "g" is defined, writing Gremlin is structurally and
conceptually the same irrespective of programming language.

|  |  |
| --- | --- |
| Tip | The variable `g`, the `TraversalSource`, only needs to be instantiated once and should then be re-used. |

#### Limitations

The previous section on the embedded model outlined a number of areas where it has some advantages that it gains due to
the fact that the full GTM is available to the user in the language of its origin, i.e. Java. Some of those items
touch upon important concepts to focus on here.

The first of these points is serialization. When Gremlin Server receives a request, the results must be serialized to
the form requested by the client and then the client deserializes those into objects native to the language. TinkerPop
has two such formats that it uses with [GraphBinary](https://tinkerpop.apache.org/docs/3.8.0/dev/io/#graphbinary) and
[GraphSON](https://tinkerpop.apache.org/docs/3.8.0/dev/io/#graphson). Users should prefer GraphBinary when available
in the programming language being used.

A good example is the `subgraph()`-step which returns a `Graph` instance as its result. The subgraph returned from
the server can be deserialized into an actual `Graph` instance on the client, which then means it is possible to
spawn a `GraphTraversalSource` from that to do local Gremlin traversals on the client-side. For non-JVM
[Gremlin Language Variants](12-gremlin-python.md#gremlin-drivers-variants) there is no local graph to deserialize that result into and
no GTM to process Gremlin so there isn’t much that can be done with such a result.

The second point is related to this issue. As there is no GTM, there is no "structure" API and thus graph elements like
`Vertex` and `Edge` are "references" only. A "reference" means that they only contain the `id` and `label` of the
element and not the properties. To be consistent, even JVM-based languages hold this limitation when talking to a
remote Gremlin Server.

|  |  |
| --- | --- |
| Important | Most SQL developers would not write a query as `SELECT * FROM table`. They would instead write the individual names of the fields they wanted in place of the wildcard. Writing "good" Gremlin is no different with this regard. Prefer explicit property key names in Gremlin unless it is completely impossible to do so. |

The third and final point involves transactions. Under this model, one traversal is equivalent to a single transaction
and there is no way in TinkerPop to string together multiple traversals into the same transaction.

#### Limitations

The previous section on the embedded model outlined a number of areas where it has some advantages that it gains due to
the fact that the full GTM is available to the user in the language of its origin, i.e. Java. Some of those items
touch upon important concepts to focus on here.

The first of these points is serialization. When Gremlin Server receives a request, the results must be serialized to
the form requested by the client and then the client deserializes those into objects native to the language. TinkerPop
has two such formats that it uses with [GraphBinary](https://tinkerpop.apache.org/docs/3.8.0/dev/io/#graphbinary) and
[GraphSON](https://tinkerpop.apache.org/docs/3.8.0/dev/io/#graphson). Users should prefer GraphBinary when available
in the programming language being used.

A good example is the `subgraph()`-step which returns a `Graph` instance as its result. The subgraph returned from
the server can be deserialized into an actual `Graph` instance on the client, which then means it is possible to
spawn a `GraphTraversalSource` from that to do local Gremlin traversals on the client-side. For non-JVM
[Gremlin Language Variants](12-gremlin-python.md#gremlin-drivers-variants) there is no local graph to deserialize that result into and
no GTM to process Gremlin so there isn’t much that can be done with such a result.

The second point is related to this issue. As there is no GTM, there is no "structure" API and thus graph elements like
`Vertex` and `Edge` are "references" only. A "reference" means that they only contain the `id` and `label` of the
element and not the properties. To be consistent, even JVM-based languages hold this limitation when talking to a
remote Gremlin Server.

|  |  |
| --- | --- |
| Important | Most SQL developers would not write a query as `SELECT * FROM table`. They would instead write the individual names of the fields they wanted in place of the wildcard. Writing "good" Gremlin is no different with this regard. Prefer explicit property key names in Gremlin unless it is completely impossible to do so. |

The third and final point involves transactions. Under this model, one traversal is equivalent to a single transaction
and there is no way in TinkerPop to string together multiple traversals into the same transaction.

