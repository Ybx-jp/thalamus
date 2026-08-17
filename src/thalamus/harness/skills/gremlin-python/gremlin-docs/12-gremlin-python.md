# Gremlin-Python

Apache TinkerPop's Gremlin-Python implements Gremlin within the [Python](https://www.python.org/) language and can be used on any Python virtual machine including the popular [CPython](https://en.wikipedia.org/wiki/CPython) machine. Python's syntax has the same constructs as Java including "dot notation" for function chaining (`a.b.c`), round bracket function arguments (`a(b,c)`), and support for global namespaces (`a(b())` vs `a(__.b())`). As such, anyone familiar with Gremlin-Java will immediately be able to work with Gremlin-Python. Moreover, there are a few added constructs to Gremlin-Python that make traversals a bit more succinct.

## Installation

To install Gremlin-Python, use Python's [pip](https://en.wikipedia.org/wiki/Pip_(package_manager)) package manager.

```
pip install gremlinpython
pip install gremlinpython[kerberos]     # Optional, not available on Microsoft Windows
```

The following table outlines recommended runtime versions by the release in which their support began:

| Version | Min Python | Key Dependencies |
| --- | --- | --- |
| 3.4.0 | 2.7 | tornado |
| 3.5.0 | ≥3.0 | aiohttp |
| 3.6.0 | ≥3.8 | aiohttp |
| 3.6.8 | ≥3.9 | aiohttp |
| 3.7.0 | ≥3.8 | aiohttp |
| 3.7.3 | ≥3.9 | aiohttp |
| 3.8.0 | ≥3.10 | aiohttp |

## Connecting

The pattern for connecting basically distills down to creating a `GraphTraversalSource`. A `GraphTraversalSource` is created from the anonymous `traversal()` method where the "g" provided to the `DriverRemoteConnection` corresponds to the name of a `GraphTraversalSource` on the remote end.

```python
g = traversal().with_(DriverRemoteConnection('ws://localhost:8182/gremlin','g'))
```

If you need to send additional headers in the websockets connection, you can pass an optional `headers` parameter to the `DriverRemoteConnection` constructor.

```python
g = traversal().with_(DriverRemoteConnection(
    'ws://localhost:8182/gremlin', 'g', headers={'Header':'Value'}))
```

Gremlin-Python supports plain text and Kerberos SASL authentication, you can set it on the connection options.

```python
# Plain text authentication
g = traversal().with_(DriverRemoteConnection(
    'ws://localhost:8182/gremlin', 'g', username='stephen', password='password'))

# Kerberos authentication
g = traversal().with_(DriverRemoteConnection(
    'ws://localhost:8182/gremlin', 'g', kerberized_service='gremlin@hostname.your.org'))
```

The value specified for the kerberized\_service should correspond to the first part of the principal name configured for the gremlin service, but with the slash replaced by an *at* sign. The Gremlin-Python client reads the kerberos configurations from your system. It finds the KDC's hostname and port from the krb5.conf file at the [default location](https://web.mit.edu/kerberos/krb5-devel/doc/mitK5defaults.html) or as indicated in the KRB5\_CONFIG environment variable. It finds credentials from the credential cache or a keytab file at the [default locations](https://web.mit.edu/kerberos/krb5-devel/doc/mitK5defaults.html) or as indicated in the KRB5CCNAME or KRB5\_KTNAME environment variables.

If you authenticate to a remote Gremlin Server or Remote Gremlin Provider, this server normally has SSL activated and the websockets url will start with 'wss://'. If Gremlin-Server uses a self-signed certificate for SSL, Gremlin-Python needs access to a local copy of the CA certificate file (in openssl .pem format), to be specified in the SSL\_CERT\_FILE environment variable.

> **Note:** If connecting from an inherently single-threaded Python process where blocking while waiting for Gremlin traversals to complete is acceptable, it might be helpful to set `pool_size` and `max_workers` parameters to 1. See the [Configuration](#configuration) section just below. Examples where this could apply are serverless cloud functions or WSGI worker processes.

Some connection options can also be set on individual requests made through the using `with_()` step on the `TraversalSource`. For instance to set request timeout to 500 milliseconds:

```python
vertices = g.with_('evaluationTimeout', 500).V().out('knows').to_list()
```

The following options are allowed on a per-request basis in this fashion: `batchSize`, `requestId`, `userAgent` and `evaluationTimeout` (formerly `scriptEvaluationTimeout` which is also supported but now deprecated).

## Common Imports

There are a number of classes, functions and tokens that are typically used with Gremlin. The following imports provide most of the typical functionality required to use Gremlin:

```python
from gremlin_python import statics
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.strategies import *
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.traversal import T
from gremlin_python.process.traversal import Order
from gremlin_python.process.traversal import Cardinality
from gremlin_python.process.traversal import CardinalityValue
from gremlin_python.process.traversal import Column
from gremlin_python.process.traversal import Direction
from gremlin_python.process.traversal import Operator
from gremlin_python.process.traversal import P
from gremlin_python.process.traversal import TextP
from gremlin_python.process.traversal import Pop
from gremlin_python.process.traversal import Scope
from gremlin_python.process.traversal import Barrier
from gremlin_python.process.traversal import Bindings
from gremlin_python.process.traversal import WithOptions
```

These can be used analogously to how they are used in Gremlin-Java.

```python
>>> g.V().has_label('person').has('age',P.gt(30)).order().by('age',Order.desc).to_list()
[v[6], v[4]]
```

Moreover, by importing the `statics` of Gremlin-Python, the class prefixes can be omitted.

```python
>>> statics.load_statics(globals())
```

With statics loaded its possible to represent the above traversal as below.

```python
>>> g.V().has_label('person').has('age',gt(30)).order().by('age',desc).to_list()
[v[6], v[4]]
```

Statics includes all the `__`-methods and thus, anonymous traversals like `__.out()` can be expressed as below. That is, without the `__`-prefix.

```python
>>> g.V().repeat(out()).times(2).name.fold().to_list()
[['ripple', 'lop']]
```

There may be situations where certain graphs may want a more exact data type than what Python will allow as a language. To support these situations `gremlin-python` has a few special type classes that can be imported from `statics`. They include:

```python
from gremlin_python.statics import long         # Java long
from gremlin_python.statics import timestamp    # Java timestamp
from gremlin_python.statics import SingleByte   # Java byte type
from gremlin_python.statics import SingleChar   # Java char type
from gremlin_python.statics import GremlinType  # Java Class
```

## Configuration

The following table describes the various configuration options for the Gremlin-Python Driver. They can be passed to the `Client` or `DriverRemoteConnection` instance as keyword arguments:

| Key | Description | Default |
| --- | --- | --- |
| enable\_compression | Enables sending a user agent to the server during connection requests. | False |
| enable\_user\_agent\_on\_connect | Enables sending a user agent to the server during connection requests. | True |
| headers | Additional headers that will be added to each request message. | `None` |
| kerberized\_service | the first part of the principal name configured for the gremlin service | "" |
| max\_workers | Maximum number of worker threads. | Number of CPUs \* 5 |
| message\_serializer | The message serializer implementation. | `gremlin_python.driver.serializer.GraphBinarySerializersV1` |
| password | The password to submit on requests that require authentication. | "" |
| pool\_size | The number of connections used by the pool. | 4 |
| protocol\_factory | A callable that returns an instance of `AbstractBaseProtocol`. | `gremlin_python.driver.protocol.GremlinServerWSProtocol` |
| session | A unique string-based identifier (typically a UUID) to enable a session-based connection. This is not a valid configuration for `DriverRemoteConnection`. | None |
| transport\_factory | A callable that returns an instance of `AbstractBaseTransport`. | `gremlin_python.driver.aiohttp.transport.AiohttpTransport` |
| username | The username to submit on requests that require authentication. | "" |

Note that the `transport_factory` can allow for additional configuration of the `AiohttpTransport`, which allows pass through of the named parameters available in [AIOHTTP's ws\_connect](https://docs.aiohttp.org/en/stable/client_reference.html#aiohttp.ClientSession.ws_connect), and the ability to call the api from an event loop:

```python
import ssl
from ssl import Purpose
from gremlin_python.driver.aiohttp.transport import AiohttpTransport

g = traversal().with_(
  DriverRemoteConnection('ws://localhost:8182/gremlin','g',
                         transport_factory=lambda: AiohttpTransport(read_timeout=60,
                                                                    write_timeout=20,
                                                                    heartbeat=10,
                                                                    call_from_event_loop=True,
                                                                    max_content_length=100*1024*1024,
                                                                    ssl_options=ssl.create_default_context(Purpose.CLIENT_AUTH))))
```

Note that the `heartbeat` enables keep-alive functionality within aiohttp and it is not enabled by default. It is important that the heartbeat interval is not too short, as the wait for the server response to the heartbeat request is half the amount of this value. Therefore, if the heartbeat is ten seconds then the wait for the response is just five seconds. If the response is not received in that time period then the connection will be closed and any ongoing requests on that connection will fail to retrieve results. Therefore, if the heartbeat is set to one second, it only provides a half-second to get the response which raises the possibility considerably that the connection will be inadvertently closed.

Compression configuration options are described in the [zlib documentation](https://docs.python.org/3.6/library/zlib.html#zlib.compressobj). By default, compression settings are configured as shown in the above example.

## Traversal Strategies

In order to add and remove traversal strategies from a traversal source, Gremlin-Python has a `TraversalStrategy` class along with a collection of subclasses that mirror the standard Gremlin-Java strategies.

```python
>>> g = g.with_strategies(SubgraphStrategy(vertices=has_label('person'),edges=has('weight',gt(0.5))))
>>> g.V().name.to_list()
['marko', 'vadas', 'josh', 'peter']
>>> g.V().out_e().element_map().to_list()
[{<T.id: 1>: 8, <T.label: 4>: 'knows', <Direction.IN: 2>: {<T.id: 1>: 4, <T.label: 4>: 'person'}, <Direction.OUT: 3>: {<T.id: 1>: 1, <T.label: 4>: 'person'}, 'weight': 1.0}]
>>> g = g.without_strategies(SubgraphStrategy)
>>> g.V().name.to_list()
['marko', 'vadas', 'lop', 'josh', 'ripple', 'peter']
>>> g.V().out_e().element_map().to_list()
[{<T.id: 1>: 9, <T.label: 4>: 'created', <Direction.IN: 2>: {<T.id: 1>: 3, <T.label: 4>: 'software'}, <Direction.OUT: 3>: {<T.id: 1>: 1, <T.label: 4>: 'person'}, 'weight': 0.4}, {<T.id: 1>: 7, <T.label: 4>: 'knows', <Direction.IN: 2>: {<T.id: 1>: 2, <T.label: 4>: 'person'}, <Direction.OUT: 3>: {<T.id: 1>: 1, <T.label: 4>: 'person'}, 'weight': 0.5}, {<T.id: 1>: 8, <T.label: 4>: 'knows', <Direction.IN: 2>: {<T.id: 1>: 4, <T.label: 4>: 'person'}, <Direction.OUT: 3>: {<T.id: 1>: 1, <T.label: 4>: 'person'}, 'weight': 1.0}, {<T.id: 1>: 10, <T.label: 4>: 'created', <Direction.IN: 2>: {<T.id: 1>: 5, <T.label: 4>: 'software'}, <Direction.OUT: 3>: {<T.id: 1>: 4, <T.label: 4>: 'person'}, 'weight': 1.0}, {<T.id: 1>: 11, <T.label: 4>: 'created', <Direction.IN: 2>: {<T.id: 1>: 3, <T.label: 4>: 'software'}, <Direction.OUT: 3>: {<T.id: 1>: 4, <T.label: 4>: 'person'}, 'weight': 0.4}, {<T.id: 1>: 12, <T.label: 4>: 'created', <Direction.IN: 2>: {<T.id: 1>: 3, <T.label: 4>: 'software'}, <Direction.OUT: 3>: {<T.id: 1>: 6, <T.label: 4>: 'person'}, 'weight': 0.2}]
>>> g = g.with_computer(workers=2,vertices=has('name','marko'))
>>> g.V().name.to_list()
['marko']
>>> g.V().out_e().value_map().with_(WithOptions.tokens).to_list()
[{<T.id: 1>: 9, <T.label: 4>: 'created', 'weight': 0.4}, {<T.id: 1>: 7, <T.label: 4>: 'knows', 'weight': 0.5}, {<T.id: 1>: 8, <T.label: 4>: 'knows', 'weight': 1.0}]
```

> **Note:** Many of the `TraversalStrategy` classes in Gremlin-Python are proxies to the respective strategy on Apache TinkerPop's JVM-based Gremlin traversal machine. As such, their `apply(Traversal)` method does nothing. However, the strategy is encoded in the Gremlin-Python bytecode and transmitted to the Gremlin traversal machine for re-construction machine-side.

## Transactions

Transactions allow multiple traversals to be executed within a single atomic unit of work.

```python
g = traversal().with_(DriverRemoteConnection('ws://localhost:8182/gremlin'))

# Create a Transaction.
tx = g.tx()

# Spawn a new GraphTraversalSource, binding all traversals established from it to tx.
gtx = tx.begin()

try:
    # Execute a traversal within the transaction.
    gtx.add_v("person").property("name", "Lyndon").iterate()

    # Commit the transaction. The transaction can no longer be used and cannot be re-used.
    # A new transaction can be spawned through g.tx().
    # The context of g remains sessionless throughout the process.
    tx.commit()
except Exception as e:
    # Rollback the transaction if an error occurs.
    tx.rollback()
```

## The Lambda Solution

Supporting [anonymous functions](https://en.wikipedia.org/wiki/Anonymous_function) across languages is difficult as most languages do not support lambda introspection and thus, code analysis. In Gremlin-Python, a Gremlin lambda should be represented as a zero-arg callable that returns a string representation of the lambda expected for use in the traversal. The lambda should be written as a `Gremlin-Groovy` string. When the lambda is represented in `Bytecode` its language is encoded such that the remote connection host can infer which translator and ultimate execution engine to use.

```python
>>> g.V().out().map(lambda: "it.get().value('name').length()").sum().to_list()
[24]
```

> **Tip:** When running into situations where Groovy cannot properly discern a method signature based on the `Lambda` instance created, it will help to fully define the closure in the lambda expression - so rather than `lambda: ('it.get().value('name')','gremlin-groovy')`, prefer `lambda: ('x -> x.get().value('name')','gremlin-groovy')`.

Finally, Gremlin `Bytecode` that includes lambdas requires that the traversal be processed by the `ScriptEngine`. To avoid continued recompilation costs, it supports the encoding of bindings, which allow a remote engine to cache traversals that will be reused over and over again save that some parameterization may change. Thus, instead of translating, compiling, and then executing each submitted bytecode, it is possible to simply execute.

```python
>>> g.V(Bindings.of('x',1)).out('created').map(lambda: "it.get().value('name').length()").sum_().to_list()
[3]
>>> g.V(Bindings.of('x',4)).out('created').map(lambda: "it.get().value('name').length()").sum_().to_list()
[9]
```

> **Warning:** When possible, avoid lambdas. They can introduce performance overhead and limit query optimization.

## Submitting Scripts

The `Client` class implementation/interface is based on the Java Driver, with some restrictions. Most notably, Gremlin-Python does not yet implement the `Cluster` class. Instead, `Client` is instantiated directly. Usage is as follows:

```python
from gremlin_python.driver import client

# Import the Gremlin-Python client module and open a reference to localhost
client_conn = client.Client('ws://localhost:8182/gremlin', 'g')
```

Once a `Client` instance is ready, it is possible to issue some Gremlin:

```python
# Submit a script that simply returns a List of integers. 
# This method blocks until the request is written to the server and a ResultSet is constructed.
result_set = client_conn.submit('[1,2,3,4]')

# Even though the ResultSet is constructed, it does not mean that the server has sent back the results.
# The ResultSet is just a holder that is awaiting the results from the server. 
# The all method returns a concurrent.futures.Future that resolves to a list when it is complete.
future_results = result_set.all()

# Block until the script is evaluated and results are sent back by the server.
results = future_results.result()
assert results == [1, 2, 3, 4]

# Submit the same script to the server but don't block.
future_result_set = client_conn.submit_async('[1,2,3,4]')

# Wait until request is written to the server and ResultSet is constructed.
result_set = future_result_set.result()

# Read a single result off the result stream.
result = result_set.one()
assert results == [1, 2, 3, 4]

# Verify that all results have been read and stream is closed.
assert result_set.done.done()

# Close client and underlying pool connections.
client_conn.close()
```

### Per Request Settings

The `client.submit()` functions accept a `request_options` which expects a dictionary. The `request_options` provide a way to include options that are specific to the request made with the call to `submit()`. A good use-case for this feature is to set a per-request override to the `evaluationTimeout` so that it only applies to the current request.

```python
result_set = client_conn.submit('g.V().repeat(both()).times(100)', request_options={'evaluationTimeout': 5000})
```

The following options are allowed on a per-request basis in this fashion: `batchSize`, `requestId`, `userAgent`, `materializeProperties` and `evaluationTimeout` (formerly `scriptEvaluationTimeout` which is also supported but now deprecated).

> **Important:** The preferred method for setting a per-request timeout for scripts is demonstrated above, but those familiar with bytecode may try `g.with_('evaluationTimeout', 500)` within a script. Scripts with multiple traversals and multiple timeouts will be interpreted as a sum of all timeouts identified in the script for that request.

## Domain Specific Languages

Writing a Gremlin Domain Specific Language (DSL) in Python simply requires direct extension of several classes:

* `GraphTraversal` - which exposes the various steps used in traversal writing
* `__` - which spawns anonymous traversals from steps
* `GraphTraversalSource` - which spawns `GraphTraversal` instances

The Social DSL based on the "modern" toy graph might look like this:

```python
from gremlin_python.process.graph_traversal import GraphTraversal, GraphTraversalSource
from gremlin_python.process.graph_traversal import __ as AnonymousTraversal
from gremlin_python.structure.graph import Graph
from gremlin_python.process.traversal import P
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.traversal import Bytecode

class SocialTraversal(GraphTraversal):

    def knows(self, person_name):
        return self.out('knows').has_label('person').has('name', person_name)

    def youngest_friends_age(self):
        return self.out('knows').has_label('person').values('age').min_()

    def created_at_least(self, number):
        return self.out_e('created').count().is_(P.gte(number))

class __(AnonymousTraversal):

    graph_traversal = SocialTraversal

    @classmethod
    def knows(cls, *args):
        return cls.graph_traversal(None, None, Bytecode()).knows(*args)

    @classmethod
    def youngest_friends_age(cls, *args):
        return cls.graph_traversal(None, None, Bytecode()).youngest_friends_age(*args)

    @classmethod
    def created_at_least(cls, *args):
        return cls.graph_traversal(None, None, Bytecode()).created_at_least(*args)


class SocialTraversalSource(GraphTraversalSource):

    def __init__(self, *args, **kwargs):
        super(SocialTraversalSource, self).__init__(*args, **kwargs)
        self.graph_traversal = SocialTraversal

    def persons(self, *args):
        traversal = self.get_graph_traversal()
        traversal.bytecode.add_step('V')
        traversal.bytecode.add_step('hasLabel', 'person')

        if len(args) > 0:
            traversal.bytecode.add_step('has', 'name', P.within(args))

        return traversal
```

> **Note:** The `AnonymousTraversal` class above is just an alias for `__` as in `from gremlin_python.process.graph_traversal import __ as AnonymousTraversal`

Using the DSL is straightforward and just requires that the graph instance know the `SocialTraversalSource` should be used:

```python
social = traversal(SocialTraversalSource).with_(DriverRemoteConnection('ws://localhost:8182/gremlin','g'))
social.persons('marko').knows('josh')
social.persons('marko').youngest_friends_age()
social.persons().filter_(__.created_at_least(2)).count()
```

## Syntactic Sugar

Python supports meta-programming and operator overloading. There are three uses of these techniques in Gremlin-Python that makes traversals a bit more concise.

```python
>>> g.V().both()[1:3].to_list()
[v[2], v[4]]
>>> g.V().both()[1].to_list()
[v[2]]
>>> g.V().both().name.to_list()
['lop', 'lop', 'lop', 'vadas', 'josh', 'josh', 'josh', 'marko', 'marko', 'marko', 'peter', 'ripple']
```

## Differences from Gremlin-Java

In situations where Python reserved words and global functions overlap with standard Gremlin steps and tokens, those bits of conflicting Gremlin get an underscore appended as a suffix:

**Steps:**
- `all_()` - filter step
- `and_()` - filter step
- `any_()` - filter step
- `as_()` - modulator step
- `filter_()` - filter step
- `from_()` - modulator step
- `id_()` - map step
- `is_()` - filter step
- `in_()` - traversal step
- `max_()` - map step
- `min_()` - map step
- `not_()` - filter step
- `or_()` - filter step
- `range_()` - filter step
- `sum_()` - map step
- `with_()` - modulator step

**Tokens:**
- `Scope.global_`
- `Direction.from_`
- `Operator.sum_`

In addition, the enum construct for `Cardinality` cannot have functions attached to it the way it can be done in Java, therefore cardinality functions that take a value like `list()`, `set()`, and `single()` are referenced from a `CardinalityValue` class rather than `Cardinality` itself.

## Limitations

* Traversals that return a `Set` **might** be coerced to a `List` in Python. In the case of Python, number equality is different from JVM languages which produces different `Set` results when those types are in use. When this case is detected during deserialization, the `Set` is coerced to a `List` so that traversals return consistent results within a collection across different languages. If a `Set` is needed then convert `List` results to `Set` manually.

* Gremlin is capable of returning `Dictionary` results that use non-hashable keys (e.g. Dictionary as a key) and Python does not support that at a language level. Using GraphSON 3.0 or GraphBinary (after 3.5.0) makes it possible to return such results. In all other cases, Gremlin that returns such results will need to be re-written to avoid that sort of key.

* The `subgraph()`-step is not supported by any variant that is not running on the Java Virtual Machine as there is no `Graph` instance to deserialize a result into on the client-side. A workaround is to replace the step with `aggregate(local)` and then convert those results to something the client can use locally.

* Use of the aiohttp library in the default transport requires the use of asyncio's event loop to run the async functions. This can be an issue in situations where the application calling Gremlin-Python is already using an event loop. Certain types of event loops can be patched using nest-asyncio which allows Gremlin-Python to proceed without an error like "Cannot run the event loop while another loop is running". This is the preferred approach to avoiding the issue and can be enabled by passing `call_from_event_loop=True` to the `AiohttpTransport` class.

  However, in situations where the loop cannot be patched (e.g. uvloop), then the current suggested workaround is to run Gremlin-Python in a separate thread. This is not ideal for asynchronous web servers as the number of concurrent connections will be limited by the number of threads the system can handle. The following snippet shows how Gremlin-Python can be called from asynchronous code using a thread.

  ```python
  import asyncio
  from concurrent.futures import ThreadPoolExecutor
  from gremlin_python.process.anonymous_traversal import traversal
  from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection

  def print_vertices():
      g = traversal().with_(DriverRemoteConnection("ws://localhost:8182/gremlin"))
      # Do your traversal.

  async def run_in_thread():
      running_loop = asyncio.get_running_loop()

      with ThreadPoolExecutor() as pool:
          await running_loop.run_in_executor(pool, print_vertices)
  ```

## Application Examples

The TinkerPop source code contains some sample applications that demonstrate the basics of Gremlin-Python. They can be found in GitHub [here](https://github.com/apache/tinkerpop/tree/3.8.0/gremlin-examples/gremlin-python/) and are designed to connect to a running Gremlin Server configured with the `conf/gremlin-server.yaml` and `conf/gremlin-server-modern.yaml` files as included with the standard release packaging.

This guide assumes Gremlin Server will be executed using Docker. Alternatively, Gremlin Server can run locally.

To start Gremlin Server using Docker, first download an image of Gremlin Server from Docker Hub:

```bash
docker pull tinkerpop/gremlin-server
```

Clean server:

```bash
docker run -d -p 8182:8182 tinkerpop/gremlin-server
```

Modern toy graph server:

```bash
docker run -d -p 8182:8182 tinkerpop/gremlin-server conf/gremlin-server-modern.yaml
```

The remote connection and basic Gremlin examples can be run on a clean server, while traversal examples should be run on a server with the Modern graph preloaded.

### Prerequisites

* Compatible Python installed (Python 3.10+ for gremlinpython 3.8.0)
* pip installed

> **Note:** On some systems, you may need to use `python3` and `pip3` instead of `python` and `pip`.

Navigate to the examples directory:

```bash
cd gremlin-examples/gremlin-python
```

Install the requirements:

```bash
pip install -r requirements.txt
```

Run the examples:

```bash
python connections.py
python basic_gremlin.py
python modern_traversals.py
```
