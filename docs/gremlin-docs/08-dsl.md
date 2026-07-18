## Domain Specific Languages

Gremlin is a [domain specific language](http://en.wikipedia.org/wiki/Domain-specific_language) (DSL) for traversing
graphs. It operates in the language of vertices, edges and properties. Typically, applications built with Gremlin are
not of the graph domain, but instead model their domain within a graph. For example, the
["modern" toy graph](https://tinkerpop.apache.org/docs/3.8.0/images/tinkerpop-modern.png) models
software and person domain objects with the relationships between them (i.e. a person "knows" another person and a
person "created" software).

An analyst who wanted to find out if "marko" knows "josh" could write the following Gremlin:

```
g.V().hasLabel('person').has('name','marko').
  out('knows').hasLabel('person').has('name','josh').hasNext()
```

While this method achieves the desired answer, it requires the analyst to traverse the graph in the domain language
of the graph rather than the domain language of the social network. A more natural way for the analyst to write this
traversal might be:

```
g.persons('marko').knows('josh').hasNext()
```

In the statement above, the traversal is written in the language of the domain, abstracting away the underlying
graph structure from the query. The two traversal results are equivalent and, indeed, the "Social DSL" produces
the same set of traversal steps as the "Graph DSL" thus producing equivalent strategy application and performance
runtimes.

To further the example of the Social DSL consider the following:

```
// Graph DSL - find the number of persons who created at least 2 projects
g.V().hasLabel('person').
  where(outE("created").count().is(P.gte(2))).count()

// Social DSL - find the number of persons who created at least 2 projects
social.persons().where(createdAtLeast(2)).count()

// Graph DSL - determine the age of the youngest friend "marko" has
g.V().hasLabel('person').has('name','marko').
  out("knows").hasLabel("person").values("age").min()

// Social DSL - determine the age of the youngest friend "marko" has
social.persons("marko").youngestFriendsAge()
```

Learn more about how to implement these DSLs in the [Gremlin Language Variants](12-gremlin-python.md#gremlin-drivers-variants) section
specific to the programming language of interest.

## Translators

![gremlin translator](../images/gremlin-translator.png)

There are times when is helpful to translate Gremlin from one programming language to another. Perhaps a large Gremlin
example is found on StackOverflow written in Java, but the programming language the developer has chosen is Python.
Fortunately, TinkerPop has developed `Translator` infrastructure that will convert Gremlin from one programming
language syntax to another.

The functionality relevant to most users is actually a sub-function of `Translator` infrastructure and is more
specifically a `ScriptTranslator` which takes Gremlin `Bytecode` of a traversal and generates a `String` representation
of that `Bytecode` in the programming language syntax that the `ScriptTranslator` instance supports. The translation
therefore allows Gremlin to be converted from the host programming language of the `Translator` to another.

The following translators are available, where the first column identifies the host programming language and the
columns represent the language that Gremlin can be generated in:

|  | Java | Groovy | Javascript | .NET | Python | Go |
| --- | --- | --- | --- | --- | --- | --- |
| **Java** | - | X | X | X | X | X |
| **Groovy** |  | X | X |  | X |  |
| **Javascript** |  | X | - |  |  |  |
| **.NET** |  | X |  | - |  |  |
| **Python** |  | X |  |  | - |  |
| **Go** |  | X |  |  |  | - |

Each programming language has its own API for translation, but the pattern is quite similar from one to the next:

|  |  |
| --- | --- |
| Warning | While `Translator` implementations have been around for some time, they are still in their early stages from an interface perspective. API changes may occur in the near future. |

java

javascript

python

csharp

go

```
// gremlin-core module
import org.apache.tinkerpop.gremlin.process.traversal.translator.*;

GraphTraversalSource g = ...;
Traversal<Vertex,Integer> t = g.V().has("person","name","marko").
                                where(in("knows")).
                                values("age").
                                map(Lambda.function("it.get() + 1"));

Translator.ScriptTranslator groovyTranslator = GroovyTranslator.of("g");
System.out.println(groovyTranslator.translate(t).getScript());
// OUTPUT: g.V().has("person","name","marko").where(__.in("knows")).values("age").map({it.get() + 1})

Translator.ScriptTranslator dotnetTranslator = DotNetTranslator.of("g");
System.out.println(dotnetTranslator.translate(t).getScript());
// OUTPUT: g.V().Has("person","name","marko").Where(__.In("knows")).Values<object>("age").Map<object>(Lambda.Groovy("it.get() + 1"))

Translator.ScriptTranslator pythonTranslator = PythonTranslator.of("g");
System.out.println(pythonTranslator.translate(t).getScript());
// OUTPUT: g.V().has('person','name','marko').where(__.in_('knows')).age.map(lambda: "it.get() + 1")

Translator.ScriptTranslator javascriptTranslator = JavascriptTranslator.of("g");
System.out.println(javascriptTranslator.translate(t).getScript());
// OUTPUT: g.V().has("person","name","marko").where(__.in_("knows")).values("age").map(() => "it.get() + 1")

Translator.ScriptTranslator golangTranslator = GolangTranslator.of("g");
System.out.println(golangTranslator.translate(t).getScript());
// OUTPUT: g.V().Has("person", "name", "marko").Where(gremlingo.T__.In("knows")).Values("age").Map(&gremlingo.Lambda{Script:"it.get() + 1", Language:""})
```

```
const g = ...;
const t = g.V().has("person","name","marko").
            where(in_("knows")).
            values("age");

// Groovy
const translator = new gremlin.process.Translator('g');
console.log(translator.translate(t));
// OUTPUT: g.V().has('person','name','marko').where(__.in('knows')).values('age')
```

```
from gremlin_python.process.translator import *

g = ...
t = (g.V().has('person','name','marko').
          where(__.in_("knows")).
          values("age"))

# Groovy
translator = Translator().of('g');
print(translator.translate(t.bytecode));
# OUTPUT: g.V().has('person','name','marko').where(__.in('knows')).values('age')
```

```
var g = ...;
var t = g.V().Has("person", "name", "marko").Where(In("knows")).Values<int>("age");

// Groovy
var translator = GroovyTranslator.Of("g");
Console.WriteLine(translator.Translate(t));
// OUTPUT: g.V().has('person', 'name', 'marko').where(__.in('knows')).values('age')
```

```
g := ...
t := g.V().Has("person", "name", "marko").
    Where(T__.In("knows")).
    Values("age")

// Groovy
translator := NewTranslator("g")
print(translator.Translate(t.Bytecode))
// OUTPUT: g.V().has('person','name','marko').where(in('knows')).values('age')
```

The JVM-based translator has the added option of parameter extraction, where the translation process will attempt to
identify opportunities to generate an output that would replace constant values with parameters. The parameters would
then be extracted and returned as part of the `Script` object:

```
Traversal<Vertex,Integer> t = g.V().has("person","name","marko").
                                where(__.in("knows")).
                                values("age");
// specify true to attempt parameter extraction
Translator.ScriptTranslator translator = GroovyTranslator.of("g", true);
Script s = translator.translate(t);
System.out.println(s.getScript());
// OUTPUT: g.V().has(_args_0,_args_1,_args_2).where(__.in(_args_3)).values(_args_4)
System.out.println(s.parameters);
// OUTPUT: Optional[{_args_0=person, _args_2=marko, _args_1=name, _args_4=age, _args_3=knows}]
```

The `GroovyTranslator` can take a `TypeTranslator` argument which allows some customization of how types get
converted to script form. The `DefaultTypeTranslator` is used if a specific implementation is not specified. A built-in
alternative to this implementation is the `LanguageTypeTranslator` which will prefer use of the Gremlin language
`datetime()` function rather than the JVM specific `Date` and `Timestamp` conversions. This translator can be helpful
when generating scripts that will be sent to Gremlin Server or Remote Graph Providers supporting the `datetime()` form.

The `PythonTranslator` can take a `TypeTranslator` argument to disable the syntactic sugar which the default translator
applies to converted queries. The `DefaultTypeTranslator` is used if a specific implementation is not specified.

```
Traversal<Vertex,String> t = g.V().range(0, 10).has("person","name","marko").
                                limit(2).
                                values("name");
// default translator
Translator.ScriptTranslator translator = PythonTranslator.of("g");
String defaultQueryTranslation = translator.translate(t)
System.out.println(defaultQueryTranslation);
// OUTPUT: g.V()[0:10].has('person','name','marko')[0:2].name

// no synantic sugar translator
Translator.ScriptTranslator noSugarTranslator = PythonTranslator.of("g", new PythonTranslator.NoSugarTranslator(false));
String noSugarTranslation = noSugarTranslator.translate(t)
System.out.println(noSugarTranslation);
// OUTPUT: g.V().range_(0,10).has('person','name','marko').limit(2).values('name')

// With parameter extraction
Translator.ScriptTranslator noSugarTranslatorWithParameters = PythonTranslator.of("g", new PythonTranslator.NoSugarTranslator(true));
String noSugarTranslationWithParameters = noSugarTranslatorWithParameters.translate(t)
System.out.println(noSugarTranslationWithParameters);
// OUTPUT: g.V().range_(0,10).has(_args_0,_args_1,_args_2).limit(2).values(_args_1)
```

# Gremlin Compilers

There are many languages built to query data. SQL is typically used to query relational data. There is SPARQL for RDF
data. Cypher is used to do pattern matching in graph data. The list could go on. Compilers convert languages like
these to Gremlin so that it becomes possible to use them in any context that Gremlin is used. In other words, a
Gremlin Compiler enables a particular query language to work on any TinkerPop-enabled graph system.

## SPARQL-Gremlin

![gremlintron](../images/gremlintron.png)

The SPARQL-Gremlin compiler, transforms [SPARQL](https://en.wikipedia.org/wiki/SPARQL) queries into Gremlin
traversals. It uses the [Apache Jena](https://jena.apache.org/index.html) SPARQL processor
[ARQ](https://jena.apache.org/documentation/query/index.html), which provides access to a syntax tree of a
SPARQL query.

The goal of this work is to bridge the query interoperability gap between the two famous, yet fairly disconnected,
graph communities: Semantic Web (which relies on the RDF data model) and Graph database (which relies on property graph
data model).

|  |  |
| --- | --- |
| Note | The foundational research work on SPARQL-Gremlin compiler (aka Gremlinator) can be found in the [Gremlinator paper](https://arxiv.org/pdf/1801.02911.pdf). This paper presents the graph query language semantics of SPARQL and Gremlin, and a formal mapping between SPARQL pattern matching graph patterns and Gremlin traversals. |

```
<dependency>
   <groupId>org.apache.tinkerpop</groupId>
   <artifactId>sparql-gremlin</artifactId>
   <version>3.8.0</version>
</dependency>
```

The SPARQL-Gremlin compiler converts [SPARQL](https://en.wikipedia.org/wiki/SPARQL) queries into Gremlin so that
they can be executed across any TinkerPop-enabled graph system. To use this compiler in the Gremlin Console, first
install and activate the "tinkerpop.sparql" plugin:

```
gremlin> :install org.apache.tinkerpop sparql-gremlin 3.8.0
==>Loaded: [org.apache.tinkerpop, sparql-gremlin, 3.8.0]
gremlin> :plugin use tinkerpop.sparql
==>tinkerpop.sparql activated
```

Installing this plugin will download appropriate dependencies and import certain classes to the console so that they
may be used as follows:

console (groovy)

groovy

```
gremlin> graph = TinkerFactory.createModern()
==>tinkergraph[vertices:6 edges:6]
gremlin> g = traversal(SparqlTraversalSource).with(graph) //// (1)
==>sparqltraversalsource[tinkergraph[vertices:6 edges:6], standard]
gremlin> g.sparql("""SELECT ?name ?age
                     WHERE { ?person v:name ?name . ?person v:age ?age }
                     ORDER BY ASC(?age)""") //// (2)
==>[name:vadas,age:27]
==>[name:marko,age:29]
==>[name:josh,age:32]
==>[name:peter,age:35]
```

```
graph = TinkerFactory.createModern()
g = traversal(SparqlTraversalSource).with(graph) //// (1)
g.sparql("""SELECT ?name ?age
            WHERE { ?person v:name ?name . ?person v:age ?age }
            ORDER BY ASC(?age)""")                                                                     //2
```

1. Define `g` as a `TraversalSource` that uses the `SparqlTraversalSource` - by default, the `traversal()` method
   usually returns a `GraphTraversalSource` which includes the standard Gremlin starts steps like `V()` or `E()`. In this
   case, the `SparqlTraversalSource` enables starts steps that are specific to SPARQL only - in this case the `sparql()`
   start step.
2. Execute a SPARQL query against the TinkerGraph instance. The `SparqlTraversalSource` uses a
   [TraversalStrategy](07-traversal-strategies.md#traversalstrategy) to transparently converts that SPARQL query into a standard Gremlin traversal
   and then when finally iterated, executes that against the TinkerGraph.

### Prefixes

The SPARQL-Gremlin compiler supports the following prefixes to traverse the graph:

| Prefix | Purpose |
| --- | --- |
| `v:<id|label|<name>>` | access to vertex id, label or property value |
| `e:<label>` | out-edge traversal |
| `p:<name>` | property traversal |

Note that element IDs and labels are treated like normal properties, hence they can be accessed using the same pattern:

console (groovy)

groovy

```
gremlin> g.sparql("""SELECT ?name ?id ?label
             WHERE {
             ?element v:name ?name .
             ?element v:id ?id .
             ?element v:label ?label .}""")
==>[name:marko,id:1,label:person]
==>[name:vadas,id:2,label:person]
==>[name:lop,id:3,label:software]
==>[name:josh,id:4,label:person]
==>[name:ripple,id:5,label:software]
==>[name:peter,id:6,label:person]
```

```
g.sparql("""SELECT ?name ?id ?label
    WHERE {
    ?element v:name ?name .
    ?element v:id ?id .
    ?element v:label ?label .}""")
```

### Supported Queries

The SPARQL-Gremlin compiler currently supports translation of the SPARQL 1.0 specification, especially `SELECT`
queries, though there is an on-going effort to cover the entire SPARQL 1.1 query feature spectrum. The supported
SPARQL query types are:

* Union
* Optional
* Order-By
* Group-By
* STAR-shaped or *neighbourhood queries*
* Query modifiers, such as:

  + Filter with *restrictions*
  + Count
  + LIMIT
  + OFFSET

### Limitations

The current implementation of SPARQL-Gremlin compiler (i.e. SPARQL-Gremlin) does not support the following cases:

* SPARQL queries with variables in the predicate position are not currently covered, with an exception of the following
  case:

```
g.sparql("""SELECT * WHERE { ?x ?y ?z . }""")
```

* A SPARQL Union query with un-balanced patterns, i.e. a gremlin union traversal can only be generated if the input
  SPARQL query has the same number of patterns on both the side of the union operator. For instance, the following
  SPARQL query cannot be mapped, since a union is executed between different number of graph patterns (two patterns
  `union` 1 pattern).

```
g.sparql("""SELECT *
            WHERE {
                {?person e:created ?software .
                ?person v:name "josh" .}
                UNION
                {?software v:lang "java" .} }""")
```

* A non-Group key variable cannot be projected in a SPARQL query. This is a SPARQL language limitation rather than
  that of Gremlin/TinkerPop. Apache Jena throws the exception "Non-group key variable in SELECT" if this occurs.
  For instance, in a SPARQL query with GROUP-BY clause, only the variable on which the grouping is declared, can be
  projected. The following query is valid:

```
g.sparql("""SELECT ?age
            WHERE {
                ?person v:label "person" .
                ?person v:age ?age .
                ?person v:name ?name .} GROUP BY (?age)""")
```

Whereas, the following SPARQL query will be invalid:

```
g.sparql("""SELECT ?person
            WHERE {
              ?person v:label "person" .
              ?person v:age ?age .
              ?person v:name ?name .} GROUP BY (?age)""")
```

* In a SPARQL query with an ORDER-BY clause, the ordering occurs with respect to the first projected variable in the
  query. It is possible to choose any number of variable to be projected, however, the first variable in the selection
  will be the ordering decider. For instance, in the query:

```
g.sparql("""SELECT ?name ?age
            WHERE {
                ?person v:label "person" .
                ?person v:age ?age .
                ?person v:name ?name . } ORDER BY (?age)""")
```

the result set will be ordered according to the `?name` variable (in ascending order by default) despite having passed
`?age` in the order by. Whereas, for the following query:

```
g.sparql("""SELECT ?age ?name
            WHERE {
                ?person v:label "person" .
                ?person v:age ?age .
                ?person v:name ?name . } ORDER BY (?age)""")
```

the result set will be ordered according to the `?age` (as it is the first projected variable). Finally, for the
select all case (`SELECT *`):

```
g.sparql("""SELECT *
            WHERE { ?person v:label "person" . ?person v:age ?age . ?person v:name ?name . } ORDER BY (?age)""")
```

the the variable encountered first will be the ordering decider, i.e. since we have `?person` encountered first,
the result set will be ordered according to the `?person` variable (which are vertex id).

* In the current implementation, `OPTIONAL` clause doesn’t work under nesting with `UNION` clause (i.e. multiple optional
  clauses with in a union clause) and `ORDER-By` clause (i.e. declaring ordering over triple patterns within optional
  clauses). Everything else with SPARQL `OPTIONAL` works just fine.

### Examples

The following section presents examples of SPARQL queries that are currently covered by the SPARQL-Gremlin compiler.

#### Select All

Select all vertices in the graph.

console (groovy)

groovy

```
gremlin> g.sparql("""SELECT * WHERE { }""")
==>v[1]
==>v[2]
==>v[3]
==>v[4]
==>v[5]
==>v[6]
```

```
g.sparql("""SELECT * WHERE { }""")
```

#### Match Constant Values

Select all vertices with the label `person`.

console (groovy)

groovy

```
gremlin> g.sparql("""SELECT * WHERE {  ?person v:label "person" .}""")
==>v[1]
==>v[2]
==>v[4]
==>v[6]
```

```
g.sparql("""SELECT * WHERE {  ?person v:label "person" .}""")
```

#### Select Specific Elements

Select the values of the properties `name` and `age` for each `person` vertex.

console (groovy)

groovy

```
gremlin> g.sparql("""SELECT ?name ?age
         WHERE {
           ?person v:label "person" .
           ?person v:name ?name .
           ?person v:age ?age . }""")
==>[name:marko,age:29]
==>[name:vadas,age:27]
==>[name:josh,age:32]
==>[name:peter,age:35]
```

```
g.sparql("""SELECT ?name ?age
WHERE {
  ?person v:label "person" .
  ?person v:name ?name .
  ?person v:age ?age . }""")
```

#### Pattern Matching

Select only those persons who created a project.

console (groovy)

groovy

```
gremlin> g.sparql("""SELECT ?name ?age
         WHERE {
           ?person v:label "person" .
           ?person v:name ?name .
           ?person v:age ?age .
           ?person e:created ?project . }""")
==>[name:marko,age:29]
==>[name:josh,age:32]
==>[name:josh,age:32]
==>[name:peter,age:35]
```

```
g.sparql("""SELECT ?name ?age
WHERE {
  ?person v:label "person" .
  ?person v:name ?name .
  ?person v:age ?age .
  ?person e:created ?project . }""")
```

#### Filtering

Select only those persons who are older than 30.

console (groovy)

groovy

```
gremlin> g.sparql("""SELECT ?name ?age
         WHERE {
           ?person v:label "person" .
           ?person v:name ?name .
           ?person v:age ?age .
             FILTER (?age > 30) }""")
==>[name:josh,age:32]
==>[name:peter,age:35]
```

```
g.sparql("""SELECT ?name ?age
WHERE {
  ?person v:label "person" .
  ?person v:name ?name .
  ?person v:age ?age .
    FILTER (?age > 30) }""")
```

#### Deduplication

Select the distinct names of the created projects.

console (groovy)

groovy

```
gremlin> g.sparql("""SELECT DISTINCT ?name
         WHERE {
           ?person v:label "person" .
           ?person v:age ?age .
           ?person e:created ?project .
           ?project v:name ?name .
             FILTER (?age > 30)}""")
==>ripple
==>lop
```

```
g.sparql("""SELECT DISTINCT ?name
WHERE {
  ?person v:label "person" .
  ?person v:age ?age .
  ?person e:created ?project .
  ?project v:name ?name .
    FILTER (?age > 30)}""")
```

#### Multiple Filters

Select the distinct names of all Java projects.

console (groovy)

groovy

```
gremlin> g.sparql("""SELECT DISTINCT ?name
         WHERE {
           ?person v:label "person" .
           ?person v:age ?age .
           ?person e:created ?project .
           ?project v:name ?name .
           ?project v:lang ?lang .
             FILTER (?age > 30 && ?lang = "java") }""")
==>ripple
==>lop
```

```
g.sparql("""SELECT DISTINCT ?name
WHERE {
  ?person v:label "person" .
  ?person v:age ?age .
  ?person e:created ?project .
  ?project v:name ?name .
  ?project v:lang ?lang .
    FILTER (?age > 30 && ?lang = "java") }""")
```

#### Union

Select all persons who have developed a software in java using union.

console (groovy)

groovy

```
gremlin> g.sparql("""SELECT *
         WHERE {
           {?person e:created ?software .}
           UNION
           {?software v:lang "java" .} }""")
==>[software:v[3],person:v[1]]
==>[software:v[3]]
==>[software:v[5],person:v[4]]
==>[software:v[3],person:v[4]]
==>[software:v[5]]
==>[software:v[3],person:v[6]]
```

```
g.sparql("""SELECT *
WHERE {
  {?person e:created ?software .}
  UNION
  {?software v:lang "java" .} }""")
```

#### Optional

Return the names of the persons who have created a software in java and optionally python.

```
g.sparql("""SELECT ?person
WHERE {
  ?person v:label "person" .
  ?person e:created ?software .
  ?software v:lang "java" .
  OPTIONAL {?software v:lang "python" . }}""")
```

#### Order By

Select all vertices with the label `person` and order them by their age.

console (groovy)

groovy

```
gremlin> g.sparql("""SELECT ?age ?name
         WHERE {
           ?person v:label "person" .
           ?person v:age ?age .
           ?person v:name ?name .
         } ORDER BY (?age)""")
==>[age:27,name:vadas]
==>[age:29,name:marko]
==>[age:32,name:josh]
==>[age:35,name:peter]
```

```
g.sparql("""SELECT ?age ?name
WHERE {
  ?person v:label "person" .
  ?person v:age ?age .
  ?person v:name ?name .
} ORDER BY (?age)""")
```

#### Group By

Select all vertices with the label `person` and group them by their age.

console (groovy)

groovy

```
gremlin> g.sparql("""SELECT ?age
         WHERE {
           ?person v:label "person" .
           ?person v:age ?age .
         } GROUP BY (?age)""")
==>[32:[32],35:[35],27:[27],29:[29]]
```

```
g.sparql("""SELECT ?age
WHERE {
  ?person v:label "person" .
  ?person v:age ?age .
} GROUP BY (?age)""")
```

#### Mixed/complex/aggregation-based queries

Count the number of projects which have been created by persons under the age of 30 and group them by age. Return only
the top two.

```
g.sparql("""SELECT (COUNT(?project) as ?p)
WHERE {
  ?person v:label "person" .
  ?person v:age ?age . FILTER (?age < 30)
  ?person e:created ?project .
} GROUP BY (?age) LIMIT 2""")
```

#### Meta-Property Access

Accessing the Meta-Property of a graph element. Meta-Property can be perceived as the reified statements in an RDF
graph.

console (groovy)

groovy

```
gremlin> g = traversal(SparqlTraversalSource).with(graph)
==>sparqltraversalsource[tinkergraph[vertices:6 edges:14], standard]
gremlin> g.sparql("""SELECT ?name ?startTime
         WHERE {
           ?person v:name "daniel" .
           ?person p:location ?location .
           ?location v:value ?name .
           ?location v:startTime ?startTime }""")
==>[name:spremberg,startTime:1982]
==>[name:kaiserslautern,startTime:2005]
==>[name:aachen,startTime:2009]
```

```
g = traversal(SparqlTraversalSource).with(graph)
g.sparql("""SELECT ?name ?startTime
WHERE {
  ?person v:name "daniel" .
  ?person p:location ?location .
  ?location v:value ?name .
  ?location v:startTime ?startTime }""")
```

#### STAR-shaped queries

STAR-shaped queries are the queries that form/follow a star-shaped execution plan. These in terms of graph traversals
can be perceived as path queries or neighborhood queries. For instance, getting all the information about a specific
`person` or `software`.

console (groovy)

groovy

```
gremlin> g.sparql("""SELECT ?age ?software ?lang ?name
         WHERE {
           ?person v:name "josh" .
           ?person v:age ?age .
           ?person e:created ?software .
           ?software v:lang ?lang .
           ?software v:name ?name . }""")
```

```
g.sparql("""SELECT ?age ?software ?lang ?name
WHERE {
  ?person v:name "josh" .
  ?person v:age ?age .
  ?person e:created ?software .
  ?software v:lang ?lang .
  ?software v:name ?name . }""")
```

### With Gremlin

The `sparql()`-step takes a SPARQL query and returns a result. That result can be further processed by standard Gremlin
steps as shown below:

console (groovy)

groovy

```
gremlin> g = traversal(SparqlTraversalSource).with(graph)
==>sparqltraversalsource[tinkergraph[vertices:6 edges:6], standard]
gremlin> g.sparql("SELECT ?name ?age WHERE { ?person v:name ?name . ?person v:age ?age }")
==>[name:marko,age:29]
==>[name:vadas,age:27]
==>[name:josh,age:32]
==>[name:peter,age:35]
gremlin> g.sparql("SELECT ?name ?age WHERE { ?person v:name ?name . ?person v:age ?age }").select("name")
==>marko
==>vadas
==>josh
==>peter
gremlin> g.sparql("SELECT * WHERE { }").out("knows").values("name")
==>vadas
==>josh
gremlin> g.withSack(1.0f).sparql("SELECT * WHERE { }").
           repeat(outE().sack(mult).by("weight").inV()).
             times(2).
           sack()
==>1.0
==>0.4
```

```
g = traversal(SparqlTraversalSource).with(graph)
g.sparql("SELECT ?name ?age WHERE { ?person v:name ?name . ?person v:age ?age }")
g.sparql("SELECT ?name ?age WHERE { ?person v:name ?name . ?person v:age ?age }").select("name")
g.sparql("SELECT * WHERE { }").out("knows").values("name")
g.withSack(1.0f).sparql("SELECT * WHERE { }").
  repeat(outE().sack(mult).by("weight").inV()).
    times(2).
  sack()
```

Mixing SPARQL with Gremlin steps introduces some interesting possibilities for complex traversals.

