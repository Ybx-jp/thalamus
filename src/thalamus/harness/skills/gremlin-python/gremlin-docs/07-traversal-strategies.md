## TraversalStrategy

![traversal strategy](../images/traversal-strategy.png) A `TraversalStrategy` analyzes a `Traversal` and, if the traversal
meets its criteria, can mutate it accordingly. Traversal strategies are executed at compile-time and form the foundation
of the Gremlin traversal machine’s compiler. There are 5 categories of strategies which are itemized below:

* There is an application-level feature that can be embedded into the traversal logic (**decoration**).
* There is a more efficient way to express the traversal at the TinkerPop level (**optimization**).
* There is a more efficient way to express the traversal at the graph system/language/driver level (**provider optimization**).
* There are some final adjustments/cleanups/analyses required before executing the traversal (**finalization**).
* There are certain traversals that are not legal for the application or traversal engine (**verification**).

|  |  |
| --- | --- |
| Note | The [`explain()`](06-steps/terminal-steps.md#explain-step)-step shows the user how each registered strategy mutates the traversal. |

TinkerPop ships with a generous number of `TraversalStrategy` definitions, most of which are applied implicitly when
executing a gremlin traversal. Users and providers can add `TraversalStrategy` definitions for particular needs. The
following sections detail how traversal strategies are applied and defined and describe a collection of traversal
strategies that are generally useful to end-users.

### Application

One can explicitly add or remove `TraversalStrategy` strategies on the `GraphTraversalSource` with the `with_strategies()`
and `withoutStrategies()` [start steps](06-steps/start-steps.md#start-steps), see the [ReadOnlyStrategy](#readonlystrategy) and the
[barrier() step](06-steps/terminal-steps.md#barrier-step) for examples. End users typically do this as part of issuing a gremlin traversal, either
on a locally opened graph or a remotely accessed graph. However, when configuring Gremlin Server, traversal strategies
can also be applied on exposed `GraphTraversalSource` instances and as part of an `Authorizer` implementation, see
[Gremlin Server Authorization](https://tinkerpop.apache.org/docs/3.8.0/reference/#authorization).
Therefore, one should keep the following in mind when modifying the list of `TraversalStrategy` strategies:

* A `TraversalStrategy` added to the traversal can be removed again later on. An example is the
  `conf/gremlin-server-modern-readonly.yaml` file from the Gremlin Server distribution, which applies the `ReadOnlyStrategy`
  to the `GraphTraversalSource` that remote clients can connect to. However, a remote client can remove it on its turn
  by applying the `withoutStrategies()` step with the `ReadOnlyStrategy`.
* When a `TraversalStrategy` of a particular type is added, it replaces any instances of its type that exist prior to
  it. Multiple instances of a `TraversalStrategy` can therefore not be registered and their functionality is no way
  merged automatically. Therefore, if there is a particular strategy registered whose functionality needs to be changed
  it is important to either find and modify the existing instance or construct a new one copying the options to keep
  from the old to the new instance.

### Definition

A simple `OptimizationStrategy` is the `IdentityRemovalStrategy`.

```
public final class IdentityRemovalStrategy extends AbstractTraversalStrategy<TraversalStrategy.OptimizationStrategy> implements TraversalStrategy.OptimizationStrategy {

    private static final IdentityRemovalStrategy INSTANCE = new IdentityRemovalStrategy();

    private IdentityRemovalStrategy() {
    }

    @Override
    public void apply(Traversal.Admin<?, ?> traversal) {
        if (traversal.getSteps().size() <= 1)
            return;

        for (IdentityStep<?> identityStep : TraversalHelper.getStepsOfClass(IdentityStep.class, traversal)) {
            if (identityStep.getLabels().isEmpty() || !(identityStep.getPreviousStep() instanceof EmptyStep)) {
                TraversalHelper.copyLabels(identityStep, identityStep.getPreviousStep(), false);
                traversal.removeStep(identityStep);
            }
        }
    }

    public static IdentityRemovalStrategy instance() {
        return INSTANCE;
    }
}
```

This strategy simply removes any `IdentityStep` steps in the Traversal as `aStep().identity().identity().bStep()`
is equivalent to `aStep().bStep()`. For those traversal strategies that require other strategies to execute prior or
post to the strategy, then the following two methods can be defined in `TraversalStrategy` (with defaults being an
empty set). If the `TraversalStrategy` is in a particular traversal category (i.e. decoration, optimization,
provider-optimization, finalization, or verification), then priors and posts are only possible within the respective category.

```
public Set<Class<? extends S>> applyPrior();
public Set<Class<? extends S>> applyPost();
```

|  |  |
| --- | --- |
| Important | `TraversalStrategy` categories are sorted within their category and the categories are then executed in the following order: decoration, optimization, provider optimization, finalization, and verification. If a designed strategy does not fit cleanly into these categories, then it can implement `TraversalStrategy` and its prior and posts can reference strategies within any category. However, such generalization are strongly discouraged. |

An example of a `GraphSystemOptimizationStrategy` is provided below.

```
g.V().has('name','marko')
```

The expression above can be executed in a `O(|V|)` or `O(log(|V|)` fashion in [TinkerGraph](13-tinkergraph.md#tinkergraph-gremlin)
depending on whether there is or is not an index defined for "name."

```
public final class TinkerGraphStepStrategy extends AbstractTraversalStrategy<TraversalStrategy.ProviderOptimizationStrategy> implements TraversalStrategy.ProviderOptimizationStrategy {

    private static final TinkerGraphStepStrategy INSTANCE = new TinkerGraphStepStrategy();

    private TinkerGraphStepStrategy() {
    }

    @Override
    public void apply(Traversal.Admin<?, ?> traversal) {
        if (TraversalHelper.onGraphComputer(traversal))
            return;

        for (GraphStepContract originalGraphStep : TraversalHelper.getStepsOfAssignableClass(GraphStepContract.class, traversal)) {
            TinkerGraphStep<?, ?> tinkerGraphStep = new TinkerGraphStep<>(originalGraphStep);
            TraversalHelper.replaceStep(originalGraphStep, tinkerGraphStep, traversal);
            Step<?, ?> currentStep = tinkerGraphStep.getNextStep();
            while (currentStep instanceof HasStep || currentStep instanceof NoOpBarrierStep) {
                if (currentStep instanceof HasStep) {
                    for (HasContainer hasContainer : ((HasContainerHolder) currentStep).getHasContainers()) {
                        if (!GraphStep.processHasContainerIds(tinkerGraphStep, hasContainer))
                            tinkerGraphStep.addHasContainer(hasContainer);
                    }
                    TraversalHelper.copyLabels(currentStep, currentStep.getPreviousStep(), false);
                    traversal.removeStep(currentStep);
                }
                currentStep = currentStep.getNextStep();
            }
        }
    }

    public static TinkerGraphStepStrategy instance() {
        return INSTANCE;
    }
}
```

The traversal is redefined by simply taking a chain of `has()`-steps after `g.V()` (`TinkerGraphStep`) and providing
their `HasContainers` to `TinkerGraphStep`. Then its up to `TinkerGraphStep` to determine if an appropriate index exists.
Given that the strategy uses non-TinkerPop provided steps, it should go into the `ProviderOptimizationStrategy` category
to ensure the added step does not interfere with the assumptions of the `OptimizationStrategy` strategies.

console (groovy)

groovy

```
gremlin> t = g.V().has('name','marko'); null
==>null
gremlin> t.to_string()
==>[GraphStep(vertex,[]), HasStep([name.eq(marko)])]
gremlin> t.iterate(); null
==>null
gremlin> t.to_string()
==>[TinkerGraphStep(vertex,[name.eq(marko)]), DiscardStep]
```

```
t = g.V().has('name','marko'); null
t.to_string()
t.iterate(); null
t.to_string()
```

|  |  |
| --- | --- |
| Warning | The reason that `OptimizationStrategy` and `ProviderOptimizationStrategy` are two different categories is that optimization strategies should only rewrite the traversal using TinkerPop steps. This ensures that the optimizations executed at the end of the optimization strategy round are TinkerPop compliant. From there, provider optimizations can analyze the traversal and rewrite the traversal as desired using graph system specific steps (e.g. replacing `GraphStep.HasStep…​HasStep` with `TinkerGraphStep`). If provider optimizations use graph system specific steps and implement `OptimizationStrategy`, then other TinkerPop optimizations may fail to optimize the traversal or mis-understand the graph system specific step behaviors (e.g. `ProviderVertexStep extends VertexStep`) and yield incorrect semantics. |

Finally, here is a complicated traversal that has various components that are optimized by the default TinkerPop strategies.

console (groovy)

groovy

```
gremlin> g.V().has_label('person'). //// (1)
                 and(has('name'), //// (2)
                     has('name','marko'),
                     filter(has('age',gt(20)))). //// (3)
           match(__.as_('a').has('age',lt(32)), //// (4)
                 __.as_('a').repeat(out_e().in_v()).times(2).as_('b')). //// (5)
             where('a',neq('b')). //// (6)
             where(__.as_('b').both().count().is_(gt(1))). //// (7)
           select('b'). //// (8)
           group_count().
             by(out().count()). //// (9)
           explain()
==>Traversal Explanation
================================================================================================================================================================================================================================================
Original Traversal                    [GraphStep(vertex,[]), HasStep([~label.eq(person)]), AndStep([[TraversalFilterStep([PropertiesStep([name],value)])], [HasStep([name.eq(marko)])], [TraversalFilterStep([HasStep([age.gt(20)])])]]), Mat
                                         chStep(null,AND,[[MatchStartStep(a), HasStep([age.lt(32)]), MatchEndStep(null)], [MatchStartStep(a), RepeatStep([VertexStep(OUT,edge), EdgeVertexStep(IN), RepeatEndStep],until(loops(2)),emit(false)),
                                          MatchEndStep(b)]]), WherePredicateStep(a,neq(b)), WhereTraversalStep([WhereStartStep(b), VertexStep(BOTH,vertex), CountGlobalStep, IsStep(gt(1))]), SelectOneStep(last,b,null), GroupCountStep([Vertex
                                         Step(OUT,vertex), CountGlobalStep])]

ConnectiveStrategy              [D]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), AndStep([[TraversalFilterStep([PropertiesStep([name],value)])], [HasStep([name.eq(marko)])], [TraversalFilterStep([HasStep([age.gt(20)])])]]), Mat
                                         chStep(null,AND,[[MatchStartStep(a), HasStep([age.lt(32)]), MatchEndStep(null)], [MatchStartStep(a), RepeatStep([VertexStep(OUT,edge), EdgeVertexStep(IN), RepeatEndStep],until(loops(2)),emit(false)),
                                          MatchEndStep(b)]]), WherePredicateStep(a,neq(b)), WhereTraversalStep([WhereStartStep(b), VertexStep(BOTH,vertex), CountGlobalStep, IsStep(gt(1))]), SelectOneStep(last,b,null), GroupCountStep([Vertex
                                         Step(OUT,vertex), CountGlobalStep])]
IdentityRemovalStrategy         [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), AndStep([[TraversalFilterStep([PropertiesStep([name],value)])], [HasStep([name.eq(marko)])], [TraversalFilterStep([HasStep([age.gt(20)])])]]), Mat
                                         chStep(null,AND,[[MatchStartStep(a), HasStep([age.lt(32)]), MatchEndStep(null)], [MatchStartStep(a), RepeatStep([VertexStep(OUT,edge), EdgeVertexStep(IN), RepeatEndStep],until(loops(2)),emit(false)),
                                          MatchEndStep(b)]]), WherePredicateStep(a,neq(b)), WhereTraversalStep([WhereStartStep(b), VertexStep(BOTH,vertex), CountGlobalStep, IsStep(gt(1))]), SelectOneStep(last,b,null), GroupCountStep([Vertex
                                         Step(OUT,vertex), CountGlobalStep])]
MatchPredicateStrategy          [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), AndStep([[TraversalFilterStep([PropertiesStep([name],value)])], [HasStep([name.eq(marko)])], [TraversalFilterStep([HasStep([age.gt(20)])])]]), Mat
                                         chStep(null,AND,[[MatchStartStep(a), HasStep([age.lt(32)]), MatchEndStep(null)], [MatchStartStep(a), RepeatStep([VertexStep(OUT,edge), EdgeVertexStep(IN), RepeatEndStep],until(loops(2)),emit(false)),
                                          MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchStartStep(b), WhereTraversalStep([WhereStartStep(null), VertexStep(BOTH,vertex), CountGlobalStep, Is
                                         Step(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([VertexStep(OUT,vertex), CountGlobalStep])]
FilterRankingStrategy           [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), AndStep([[TraversalFilterStep([PropertiesStep([name],value)])], [HasStep([name.eq(marko)])], [TraversalFilterStep([HasStep([age.gt(20)])])]]), Mat
                                         chStep(null,AND,[[MatchStartStep(a), HasStep([age.lt(32)]), MatchEndStep(null)], [MatchStartStep(a), RepeatStep([VertexStep(OUT,edge), EdgeVertexStep(IN), RepeatEndStep],until(loops(2)),emit(false)),
                                          MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchStartStep(b), WhereTraversalStep([WhereStartStep(null), VertexStep(BOTH,vertex), CountGlobalStep, Is
                                         Step(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([VertexStep(OUT,vertex), CountGlobalStep])]
InlineFilterStrategy            [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],value)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep(a)
                                         , RepeatStep([VertexStep(OUT,edge), EdgeVertexStep(IN), RepeatEndStep],until(loops(2)),emit(false)), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [Match
                                         StartStep(b), WhereTraversalStep([WhereStartStep(null), VertexStep(BOTH,vertex), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([VertexStep(OUT,ve
                                         rtex), CountGlobalStep])]
IncidentToAdjacentStrategy      [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],value)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep(a)
                                         , RepeatStep([VertexStepPlaceholder(OUT,vertex), RepeatEndStep],until(loops(2)),emit(false)), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchStartSt
                                         ep(b), WhereTraversalStep([WhereStartStep(null), VertexStep(BOTH,vertex), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([VertexStep(OUT,vertex),
                                         CountGlobalStep])]
AdjacentToIncidentStrategy      [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep
                                         (a), RepeatStep([VertexStepPlaceholder(OUT,vertex), RepeatEndStep],until(loops(2)),emit(false)), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchStar
                                         tStep(b), WhereTraversalStep([WhereStartStep(null), VertexStepPlaceholder(BOTH,edge), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([VertexStepPl
                                         aceholder(OUT,edge), CountGlobalStep])]
RepeatUnrollStrategy            [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep
                                         (a), VertexStepPlaceholder(OUT,vertex), VertexStepPlaceholder(OUT,vertex), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchStartStep(b), WhereTravers
                                         alStep([WhereStartStep(null), VertexStepPlaceholder(BOTH,edge), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([VertexStepPlaceholder(OUT,edge), C
                                         ountGlobalStep])]
CountStrategy                   [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep
                                         (a), VertexStepPlaceholder(OUT,vertex), VertexStepPlaceholder(OUT,vertex), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchStartStep(b), WhereTravers
                                         alStep([WhereStartStep(null), VertexStepPlaceholder(BOTH,edge), RangeGlobalStep(0,2), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([VertexStepPl
                                         aceholder(OUT,edge), CountGlobalStep])]
PathRetractionStrategy          [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep
                                         (a), VertexStepPlaceholder(OUT,vertex), VertexStepPlaceholder(OUT,vertex), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchStartStep(b), WhereTravers
                                         alStep([WhereStartStep(null), VertexStepPlaceholder(BOTH,edge), RangeGlobalStep(0,2), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([VertexStepPl
                                         aceholder(OUT,edge), CountGlobalStep])]
EarlyLimitStrategy              [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep
                                         (a), VertexStepPlaceholder(OUT,vertex), VertexStepPlaceholder(OUT,vertex), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchStartStep(b), WhereTravers
                                         alStep([WhereStartStep(null), VertexStepPlaceholder(BOTH,edge), RangeGlobalStep(0,2), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([VertexStepPl
                                         aceholder(OUT,edge), CountGlobalStep])]
LazyBarrierStrategy             [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep
                                         (a), VertexStepPlaceholder(OUT,vertex), NoOpBarrierStep(2500), VertexStepPlaceholder(OUT,vertex), NoOpBarrierStep(2500), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEn
                                         dStep(null)], [MatchStartStep(b), WhereTraversalStep([WhereStartStep(null), VertexStepPlaceholder(BOTH,edge), RangeGlobalStep(0,2), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneS
                                         tep(last,b,null), GroupCountStep([VertexStepPlaceholder(OUT,edge), CountGlobalStep])]
ByModulatorOptimizationStrategy [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep
                                         (a), VertexStepPlaceholder(OUT,vertex), NoOpBarrierStep(2500), VertexStepPlaceholder(OUT,vertex), NoOpBarrierStep(2500), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEn
                                         dStep(null)], [MatchStartStep(b), WhereTraversalStep([WhereStartStep(null), VertexStepPlaceholder(BOTH,edge), RangeGlobalStep(0,2), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneS
                                         tep(last,b,null), GroupCountStep([VertexStepPlaceholder(OUT,edge), CountGlobalStep])]
GValueReductionStrategy         [O]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep
                                         (a), VertexStep(OUT,vertex), NoOpBarrierStep(2500), VertexStep(OUT,vertex), NoOpBarrierStep(2500), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchSt
                                         artStep(b), WhereTraversalStep([WhereStartStep(null), VertexStep(BOTH,edge), RangeGlobalStep(0,2), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep(
                                         [VertexStep(OUT,edge), CountGlobalStep])]
TinkerGraphCountStrategy        [P]   [GraphStep(vertex,[]), HasStep([~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep
                                         (a), VertexStep(OUT,vertex), NoOpBarrierStep(2500), VertexStep(OUT,vertex), NoOpBarrierStep(2500), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchSt
                                         artStep(b), WhereTraversalStep([WhereStartStep(null), VertexStep(BOTH,edge), RangeGlobalStep(0,2), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep(
                                         [VertexStep(OUT,edge), CountGlobalStep])]
TinkerGraphStepStrategy         [P]   [TinkerGraphStep(vertex,[~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep(a), Ve
                                         rtexStep(OUT,vertex), NoOpBarrierStep(2500), VertexStep(OUT,vertex), NoOpBarrierStep(2500), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchStartStep
                                         (b), WhereTraversalStep([WhereStartStep(null), VertexStep(BOTH,edge), RangeGlobalStep(0,2), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([Vertex
                                         Step(OUT,edge), CountGlobalStep])]
ProfileStrategy                 [F]   [TinkerGraphStep(vertex,[~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep(a), Ve
                                         rtexStep(OUT,vertex), NoOpBarrierStep(2500), VertexStep(OUT,vertex), NoOpBarrierStep(2500), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchStartStep
                                         (b), WhereTraversalStep([WhereStartStep(null), VertexStep(BOTH,edge), RangeGlobalStep(0,2), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([Vertex
                                         Step(OUT,edge), CountGlobalStep])]
StandardVerificationStrategy    [V]   [TinkerGraphStep(vertex,[~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep(a), Ve
                                         rtexStep(OUT,vertex), NoOpBarrierStep(2500), VertexStep(OUT,vertex), NoOpBarrierStep(2500), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchStartStep
                                         (b), WhereTraversalStep([WhereStartStep(null), VertexStep(BOTH,edge), RangeGlobalStep(0,2), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([Vertex
                                         Step(OUT,edge), CountGlobalStep])]

Final Traversal                       [TinkerGraphStep(vertex,[~label.eq(person)]), TraversalFilterStep([PropertiesStep([name],property)]), HasStep([name.eq(marko), age.gt(20), age.lt(32)])@[a], MatchStep(null,AND,[[MatchStartStep(a), Ve
                                         rtexStep(OUT,vertex), NoOpBarrierStep(2500), VertexStep(OUT,vertex), NoOpBarrierStep(2500), MatchEndStep(b)], [MatchStartStep(a), WherePredicateStep(null,neq(b)), MatchEndStep(null)], [MatchStartStep
                                         (b), WhereTraversalStep([WhereStartStep(null), VertexStep(BOTH,edge), RangeGlobalStep(0,2), CountGlobalStep, IsStep(gt(1))]), MatchEndStep(null)]]), SelectOneStep(last,b,null), GroupCountStep([Vertex
                                         Step(OUT,edge), CountGlobalStep])]
```

```
g.V().has_label('person'). //// (1)
        and(has('name'), //// (2)
            has('name','marko'),
            filter(has('age',gt(20)))). //// (3)
  match(__.as_('a').has('age',lt(32)), //// (4)
        __.as_('a').repeat(out_e().in_v()).times(2).as_('b')). //// (5)
    where('a',neq('b')). //// (6)
    where(__.as_('b').both().count().is_(gt(1))). //// (7)
  select('b'). //// (8)
  group_count().
    by(out().count()). //// (9)
  explain()
```

1. `TinkerGraphStepStrategy` pulls in `has()`-step predicates for global, graph-centric index lookups.
2. `FilterRankStrategy` sorts filter steps by their time/space execution costs.
3. `InlineFilterStrategy` de-nests filters to increase the likelihood of filter concatenation and aggregation.
4. `InlineFilterStrategy` pulls out named predicates from `match()`-step to more easily allow provider strategies to use indices.
5. `RepeatUnrollStrategy` will unroll loops and `IncidentToAdjacentStrategy` will turn `out_e().in_v()`-patterns into `out()`.
6. `MatchPredicateStrategy` will pull in `where()`-steps so that they can be subjected to `match()`-steps runtime query optimizer.
7. `CountStrategy` will limit the traversal to only the number of traversers required for the `count().is_(x)`-check.
8. `PathRetractionStrategy` will remove paths from the traversers and increase the likelihood of bulking as path data is not required after `select('b')`.
9. `AdjacentToIncidentStrategy` will turn `out()` into `out_e()` to increase data access locality.

#### A note on Traversal Parameters

Certain gremlin steps are able to accept parameterized arguments in the form of one of more `GValue` objects. Please see
the [parameterizable steps documentation](05a-traversal-concepts.md#traversal-parameterization) for a complete listing of such steps.

When authoring strategies that interact with parameterizable steps, it’s important to work with `StepContract` interfaces
rather than concrete step classes. Parameterizable steps can exist as either concrete implementations or as placeholder
steps that hold `GValue` objects (parameterized arguments). The placeholders are temporary proxies for the concrete
steps which exist during strategy execution, but must be "reduced" to concrete steps prior to traversal execution. Both
concrete and placeholder forms of a step implement the same contract interface, allowing strategies to work uniformly
with either representation.

```
// Use contract interfaces for parameterizable steps
 for (GraphStepContract originalGraphStep : TraversalHelper.getStepsOfAssignableClass(GraphStepContract.class, traversal)) {
    // Work with all matching instances of a step through its contract  (1)
 }
if (step instanceof GraphStepContract) {
    GraphStepContract graphStep = (GraphStepContract) step;
    // Work with the step through its contract
}

// Instead of checking concrete classes
if (step instanceof GraphStep) {
    // This approach has the risk of missing instances of GraphStepPlaceholder
}
```

1. Note that use of `TraversalHelper.getStepsOfAssignableClass(GraphStepContract.class, traversal))` will match all
   instances of TinkerPop’s reference implementations of `GraphStepContract`, ie `GraphStep` and `GraphStepPlaceholder`,
   but will not match and provider specific implementations of the contract such as `TinkerGraphStep`. Similar rules apply
   to matching any StepContract via this method.

The contract-based approach ensures strategies work correctly whether the step is in its concrete form or placeholder
form with `GValue` parameters. Common contract interfaces include:

* `AddVertexStepContract` - for `AddVertexStep` and `AddVertexStartStep`
* `AddEdgeStepContract` - for `AddEdgeStep` and `AddEdgeStartStep`
* `VertexStepContract` - for `VertexStep`
* `GraphStepContract` - for `GraphStep`
* `MergeStepContract` - for `MergeVertexStep` and `MergeEdgeStep`

Strategy authors should consult the `GValueReductionStrategy` to understand how placeholder steps are converted to
concrete steps, and consider whether their strategy should execute before or after this conversion based on whether
they need to work with `GValue` objects or concrete step implementations. As this is an `OptimizationStrategy`, any
`ProviderOptimizationStrategy` are excluded by default from the above considerations regarding parameterizable steps.
Any providers who wish to leverage `GValue` in a `ProviderOptimizationStrategy` should first remove
`GValueReductionStrategy`, and take ownership over ensuring all placeholder steps are reduced to concrete steps
afterward. `ProviderGValueReductionStrategy` is offered for such purposes.

### EdgeLabelVerificationStrategy

`EdgeLabelVerificationStrategy` prevents traversals from writing traversals that do not explicitly specify and edge
label when using steps like `out()`, 'in_()', 'both()' and their related `E` oriented steps, providing the
option to throw an exception, log a warning or do both when one of these keys is encountered in a mutating step.

java

groovy

csharp

javascript

python

```
EdgeLabelVerificationStrategy verificationStrategy = EdgeLabelVerificationStrategy.build()
                                                                                  .throwException().create()
// results in VerificationException - as out() does not have a label specified
g.with_strategies(verificationStrategy).V(1).out().iterate();
```

```
// results in VerificationException - as out() does not have a label specified
g.with_strategies(new EdgeLabelVerificationStrategy(throwException: true))
     .V(1).out().iterate()
```

```
// results in VerificationException - as out() does not have a label specified
g.with_strategies(new EdgeLabelVerificationStrategy(throwException: true))
     .V(1).Out().Iterate();
```

```
// results in Error - as out() does not have a label specified
g.with_strategies(new EdgeLabelVerificationStrategy(throwException: true))
     .V(1).out().iterate();
```

```
# results in Error - as out() does not have a label specified
g.with_strategies(EdgeLabelVerificationStrategy(throw_exception=True))
     .V(1).out().iterate()
```

### ElementIdStrategy

`ElementIdStrategy` provides control over element identifiers. Some Graph implementations, such as TinkerGraph,
allow specification of custom identifiers when creating elements:

console (groovy)

groovy

```
gremlin> g = traversal().with(TinkerGraph.open())
==>graphtraversalsource[tinkergraph[vertices:0 edges:0], standard]
gremlin> v = g.add_v().property(id,'42a').next()
==>v[42a]
gremlin> g.V('42a')
==>v[42a]
```

```
g = traversal().with(TinkerGraph.open())
v = g.add_v().property(id,'42a').next()
g.V('42a')
```

Other `Graph` implementations, such as Neo4j, generate element identifiers automatically and cannot be assigned.
As a helper, `ElementIdStrategy` can be used to make identifier assignment possible by using vertex and edge indices
under the hood.

console (groovy)

groovy

```
gremlin> graph = Neo4jGraph.open('/tmp/neo4j')
==>neo4jgraph[community single [/tmp/neo4j]]
gremlin> strategy = ElementIdStrategy.build().create()
==>ElementIdStrategy
gremlin> g = traversal().with(graph).with_strategies(strategy)
==>graphtraversalsource[neo4jgraph[community single [/tmp/neo4j]], standard]
gremlin> g.add_v().property(id, '42a').id()
==>42a
```

```
graph = Neo4jGraph.open('/tmp/neo4j')
strategy = ElementIdStrategy.build().create()
g = traversal().with(graph).with_strategies(strategy)
g.add_v().property(id, '42a').id()
```

|  |  |
| --- | --- |
| Important | The key that is used to store the assigned identifier should be indexed in the underlying graph database. If it is not indexed, then lookups for the elements that use these identifiers will perform a linear scan. |

### EventStrategy

The purpose of the `EventStrategy` is to raise events to one or more `MutationListener` objects as changes to the
underlying `Graph` occur within a `Traversal`. Such a strategy is useful for logging changes, triggering certain
actions based on change, or any application that needs notification of some mutating operation during a `Traversal`.
If the transaction is rolled back, the event queue is reset.

The following events are raised to the `MutationListener`:

* New vertex
* New edge
* Vertex property changed
* Edge property changed
* Vertex property removed
* Edge property removed
* Vertex removed
* Edge removed

To start processing events from a `Traversal` first implement the `MutationListener` interface. An example of this
implementation is the `ConsoleMutationListener` which writes output to the console for each event. The following
console session displays the basic usage:

console (groovy)

groovy

```
gremlin> import org.apache.tinkerpop.gremlin.process.traversal.step.util.event.*
==>org.apache.tinkerpop.gremlin.process.traversal.step.util.event.*
gremlin> graph = TinkerFactory.createModern()
==>tinkergraph[vertices:6 edges:6]
gremlin> l = new ConsoleMutationListener(graph)
==>MutationListener[tinkergraph[vertices:6 edges:6]]
gremlin> strategy = EventStrategy.build().addListener(l).create()
==>EventStrategy
gremlin> g = traversal().with(graph).with_strategies(strategy)
==>graphtraversalsource[tinkergraph[vertices:6 edges:6], standard]
gremlin> g.add_v().property('name','stephen')
Vertex [v[0]] added to graph [tinkergraph[vertices:7 edges:6]]
==>v[0]
gremlin> g.V().has('name','stephen').
           property(list, 'location', 'centreville', 'startTime', 1990, 'endTime', 2000).
           property(list, 'location', 'dulles', 'startTime', 2000, 'endTime', 2006).
           property(list, 'location', 'purcellville', 'startTime', 2006)
Vertex [v[0]] property [vp[empty]] change to [centreville] in graph [tinkergraph[vertices:7 edges:6]]
Vertex [v[0]] property [vp[empty]] change to [dulles] in graph [tinkergraph[vertices:7 edges:6]]
Vertex [v[0]] property [vp[empty]] change to [purcellville] in graph [tinkergraph[vertices:7 edges:6]]
==>v[0]
gremlin> g.V().has('name','stephen').
           property(set, 'location', 'purcellville', 'startTime', 2006, 'endTime', 2019)
Vertex [v[0]] property [vp[location->purcellville]] change to [purcellville] in graph [tinkergraph[vertices:7 edges:6]]
==>v[0]
gremlin> g.E().drop()
Edge [e[7][1-knows->2]] removed from graph [tinkergraph[vertices:7 edges:6]]
Edge [e[8][1-knows->4]] removed from graph [tinkergraph[vertices:7 edges:5]]
Edge [e[9][1-created->3]] removed from graph [tinkergraph[vertices:7 edges:4]]
Edge [e[10][4-created->5]] removed from graph [tinkergraph[vertices:7 edges:3]]
Edge [e[11][4-created->3]] removed from graph [tinkergraph[vertices:7 edges:2]]
Edge [e[12][6-created->3]] removed from graph [tinkergraph[vertices:7 edges:1]]
```

```
import org.apache.tinkerpop.gremlin.process.traversal.step.util.event.*
graph = TinkerFactory.createModern()
l = new ConsoleMutationListener(graph)
strategy = EventStrategy.build().addListener(l).create()
g = traversal().with(graph).with_strategies(strategy)
g.add_v().property('name','stephen')
g.V().has('name','stephen').
  property(list, 'location', 'centreville', 'startTime', 1990, 'endTime', 2000).
  property(list, 'location', 'dulles', 'startTime', 2000, 'endTime', 2006).
  property(list, 'location', 'purcellville', 'startTime', 2006)
g.V().has('name','stephen').
  property(set, 'location', 'purcellville', 'startTime', 2006, 'endTime', 2019)
g.E().drop()
```

By default, the `EventStrategy` is configured with an `EventQueue` that raises events as they occur within execution
of a `Step`. As such, the final line of Gremlin execution that drops all edges shows a bit of an inconsistent count,
where the removed edge count is accounted for after the event is raised. The strategy can also be configured with a
`TransactionalEventQueue` that captures the changes within a transaction and does not allow them to fire until the
transaction is committed.

|  |  |
| --- | --- |
| Warning | `EventStrategy` is not meant for usage in tracking global mutations across separate processes. In other words, a mutation in one JVM process is not raised as an event in a different JVM process. In addition, events are not raised when mutations occur outside of the `Traversal` context. |

Another default configuration for `EventStrategy` revolves around the concept of "detachment". Graph elements are
detached from the graph as copies when passed to referring mutation events. Therefore, when adding a new `Vertex` in
TinkerGraph, the event will not contain a `TinkerVertex` but will instead include a `DetachedVertex`. This behavior
can be modified with the `detach()` method on the `EventStrategy.Builder` which accepts the following inputs: `null`
meaning no detachment and the return of the original element, `DetachedFactory` which is the same as the default
behavior, and `ReferenceFactory` which will return "reference" elements only with no properties.

|  |  |
| --- | --- |
| Important | If setting the `detach()` configuration to `null`, be aware that transactional graphs will likely create a new transaction immediately following the `commit()` that raises the events. The graph elements raised in the events may also not behave as "snapshots" at the time of their creation as they are "live" references to actual database elements. |

### GValueReductionStrategy

`GValueReductionStrategy` converts placeholder steps that hold `GValue` objects to their concrete implementations.
While not an optimization in and of itself, the `GValue` functionality provides a mechanism for traversal optimization
and parameterization, so this strategy falls in the optimization category. Converting to concrete steps at this stage
also allows provider optimization strategies to execute on concrete steps rather than step interfaces, which are much
easier to reason about for the vast majority of providers.

This strategy is automatically applied and typically does not need to be explicitly configured by users. However,
providers hoping to do more advanced optimizations that require `GValue` objects to be present for their strategies
will need to remove `GValueReductionStrategy` and offer their own mechanism for converting step placeholders to
concrete steps. `ProviderGValueReductionStrategy` is a base class available to help with this need.

The strategy operates by calling the `reduce()` method on any step that implements `GValueHolder`:

```
@Override
public void apply(final Traversal.Admin<?, ?> traversal) {
    final List<Step> steps = traversal.getSteps();
    for (int i = 0; i < steps.size(); i++) {
        if (steps.get(i) instanceof GValueHolder) {
            ((GValueHolder) steps.get(i)).reduce();
        }
    }
}
```

### PartitionStrategy

![partition graph](../images/partition-graph.png)

`PartitionStrategy` partitions the vertices and edges of a graph into `String` named partitions (i.e. buckets,
subgraphs, etc.). The idea behind `PartitionStrategy` is presented in the image above where each element is in a
single partition (represented by its color). Partitions can be read from, written to, and linked/joined by edges
that span one or two partitions (e.g. a tail vertex in one partition and a head vertex in another).

There are three primary configurations in `PartitionStrategy`:

1. Partition Key - The property key that denotes a String value representing a partition.
2. Write Partition - A `String` denoting what partition all future written elements will be in.
3. Read Partitions - A `Set<String>` of partitions that can be read from.

The best way to understand `PartitionStrategy` is via example.

console (groovy)

groovy

```
gremlin> graph = TinkerFactory.createModern()
==>tinkergraph[vertices:6 edges:6]
gremlin> strategyA = new PartitionStrategy(partitionKey: "_partition", writePartition: "a", readPartitions: ["a"])
==>PartitionStrategy
gremlin> strategyB = new PartitionStrategy(partitionKey: "_partition", writePartition: "b", readPartitions: ["b"])
==>PartitionStrategy
gremlin> gA = traversal().with(graph).with_strategies(strategyA)
==>graphtraversalsource[tinkergraph[vertices:6 edges:6], standard]
gremlin> gA.add_v() // this vertex has a property of {_partition:"a"}
==>v[0]
gremlin> gB = traversal().with(graph).with_strategies(strategyB)
==>graphtraversalsource[tinkergraph[vertices:7 edges:6], standard]
gremlin> gB.add_v() // this vertex has a property of {_partition:"b"}
==>v[13]
gremlin> gA.V()
==>v[0]
gremlin> gB.V()
==>v[13]
```

```
graph = TinkerFactory.createModern()
strategyA = new PartitionStrategy(partitionKey: "_partition", writePartition: "a", readPartitions: ["a"])
strategyB = new PartitionStrategy(partitionKey: "_partition", writePartition: "b", readPartitions: ["b"])
gA = traversal().with(graph).with_strategies(strategyA)
gA.add_v() // this vertex has a property of {_partition:"a"}
gB = traversal().with(graph).with_strategies(strategyB)
gB.add_v() // this vertex has a property of {_partition:"b"}
gA.V()
gB.V()
```

The following examples demonstrate the above `PartitionStrategy` definition for "strategyA" in other programming
languages:

java

csharp

javascript

python

```
PartitionStrategy strategyA = PartitionStrategy.build().partitionKey("_partition")
                                                       .writePartition("a")
                                                       .readPartitions("a").create();
```

```
PartitionStrategy strategyA = new PartitionStrategy(
                                      partitionKey: "_partition", writePartition: "a",
                                      readPartitions: new List<string>(){"a"});
```

```
const strategyA = new PartitionStrategy(partitionKey: "_partition", writePartition: "a", readPartitions: ["a"])
```

```
strategyA = PartitionStrategy(partitionKey="_partition", writePartition="a", readPartitions=["a"])
```

Partitions may also extend to `VertexProperty` elements if the `Graph` can support meta-properties and if the
`includeMetaProperties` value is set to `true` when the `PartitionStrategy` is built. The `partitionKey` will be
stored in the meta-properties of the `VertexProperty` and blind the traversal to those properties. Please note that
the `VertexProperty` will only be hidden by way of the `Traversal` itself. For example, calling `Vertex.property(k)`
bypasses the context of the `PartitionStrategy` and will thus allow all properties to be accessed.

By writing elements to particular partitions and then restricting read partitions, the developer is able to create
multiple graphs within a single address space. Moreover, by supporting references between partitions, it is possible
to merge those multiple graphs (i.e. join partitions).

### ReadOnlyStrategy

`ReadOnlyStrategy` is largely self-explanatory. A `Traversal` that has this strategy applied will throw an
`IllegalStateException` if the `Traversal` has any mutating steps within it.

java

groovy

csharp

javascript

python

```
ReadOnlyStrategy verificationStrategy = ReadOnlyStrategy.instance();
// results in VerificationException
g.with_strategies(verificationStrategy).add_v('person').iterate();
```

```
// results in VerificationException
g.with_strategies(ReadOnlyStrategy).add_v('person').iterate();
```

```
// results in VerificationException
g.with_strategies(new ReadOnlyStrategy()).add_v("person").Iterate();
```

```
// results in Error
g.with_strategies(new ReadOnlyStrategy()).add_v("person").iterate();
```

```
# results in Error
g.with_strategies(ReadOnlyStrategy()).add_v("person").iterate()
```

### ReservedKeysVerificationStrategy

`ReservedKeysVerificationStrategy` prevents traversals from adding property keys that are protected, providing the
option to throw an exception, log a warning or do both when one of these keys is encountered in a mutating step. By
default "id" and "label" are considered "reserved" but the default can be changed by building with the
`reservedKeys()` options and supply a `Set` of keys to trigger the `VerificationException`.

java

groovy

csharp

javascript

python

```
ReservedKeysVerificationStrategy verificationStrategy = ReservedKeysVerificationStrategy.build()
                                                                                        .throwException().create()
// results in VerificationException
g.with_strategies(verificationStrategy).add_v('person').property("id",123).iterate();
```

```
// results in VerificationException
g.with_strategies(new ReservedKeysVerificationStrategy(throwException: true))
     .add_v('person').property("id",123).iterate()
```

```
// results in VerificationException
g.with_strategies(new ReservedKeysVerificationStrategy(throwException: true))
     .add_v('person').Property("id",123).Iterate();
```

```
// results in Error
g.with_strategies(new ReservedKeysVerificationStrategy(throwException: true))
     .add_v('person').property("id",123).iterate();
```

```
# results in Error
g.with_strategies(ReservedKeysVerificationStrategy(throw_exception=True))
     .add_v('person').property("id",123).iterate()
```

### SeedStrategy

There are number of components of the Gremlin language that, by design, can produce non-deterministic results:

* [coin()](06-steps/filter-steps.md#coin-step)
* [order()](06-steps/map-steps.md#order-step) when `Order.shuffle` is used
* [sample()](06-steps/filter-steps.md#sample-step)

To get these steps to return deterministic results, `SeedStrategy` allows assignment of a seed value to the `Random`
operations of the steps. The following example demonstrates the random nature of `shuffle`:

console (groovy)

groovy

```
gremlin> g.V().values('name').fold().order(local).by(shuffle)
==>[vadas,peter,ripple,marko,lop,josh]
gremlin> g.V().values('name').fold().order(local).by(shuffle)
==>[lop,vadas,peter,marko,josh,ripple]
gremlin> g.V().values('name').fold().order(local).by(shuffle)
==>[josh,ripple,peter,marko,vadas,lop]
gremlin> g.V().values('name').fold().order(local).by(shuffle)
==>[vadas,peter,lop,josh,marko,ripple]
gremlin> g.V().values('name').fold().order(local).by(shuffle)
==>[josh,marko,ripple,lop,peter,vadas]
```

```
g.V().values('name').fold().order(local).by(shuffle)
g.V().values('name').fold().order(local).by(shuffle)
g.V().values('name').fold().order(local).by(shuffle)
g.V().values('name').fold().order(local).by(shuffle)
g.V().values('name').fold().order(local).by(shuffle)
```

With `SeedStrategy` in place, however, the same order is applied each time:

console (groovy)

groovy

```
gremlin> seedStrategy = SeedStrategy.build().seed(999998L).create()
==>SeedStrategy
gremlin> g.with_strategies(seedStrategy).V().values('name').fold().order(local).by(shuffle)
==>[peter,josh,marko,lop,ripple,vadas]
gremlin> g.with_strategies(seedStrategy).V().values('name').fold().order(local).by(shuffle)
==>[peter,josh,marko,lop,ripple,vadas]
gremlin> g.with_strategies(seedStrategy).V().values('name').fold().order(local).by(shuffle)
==>[peter,josh,marko,lop,ripple,vadas]
gremlin> g.with_strategies(seedStrategy).V().values('name').fold().order(local).by(shuffle)
==>[peter,josh,marko,lop,ripple,vadas]
gremlin> g.with_strategies(seedStrategy).V().values('name').fold().order(local).by(shuffle)
==>[peter,josh,marko,lop,ripple,vadas]
```

```
seedStrategy = SeedStrategy.build().seed(999998L).create()
g.with_strategies(seedStrategy).V().values('name').fold().order(local).by(shuffle)
g.with_strategies(seedStrategy).V().values('name').fold().order(local).by(shuffle)
g.with_strategies(seedStrategy).V().values('name').fold().order(local).by(shuffle)
g.with_strategies(seedStrategy).V().values('name').fold().order(local).by(shuffle)
g.with_strategies(seedStrategy).V().values('name').fold().order(local).by(shuffle)
```

|  |  |
| --- | --- |
| Important | `SeedStrategy` only makes specific steps behave in a deterministic fashion and does not necessarily make the entire traversal deterministic itself. If the underlying graph database or processing engine happens to not guarantee iteration order, then it is possible that the final result of the traversal will appear to be non-deterministic. In these cases, it would be necessary to enforce a deterministic iteration with `order()` prior to these steps that make use of randomness to return results. |

### SubgraphStrategy

`SubgraphStrategy` is similar to `PartitionStrategy` in that it constrains a `Traversal` to certain vertices, edges,
and vertex properties as determined by a `Traversal`-based criterion defined individually for each.

console (groovy)

groovy

```
gremlin> graph = TinkerFactory.createTheCrew()
==>tinkergraph[vertices:6 edges:14]
gremlin> g = traversal().with(graph)
==>graphtraversalsource[tinkergraph[vertices:6 edges:14], standard]
gremlin> g.V().as_('a').values('location').as_('b'). //// (1)
           select('a','b').by('name').by()
==>[a:marko,b:san diego]
==>[a:marko,b:santa cruz]
==>[a:marko,b:brussels]
==>[a:marko,b:santa fe]
==>[a:stephen,b:centreville]
==>[a:stephen,b:dulles]
==>[a:stephen,b:purcellville]
==>[a:matthias,b:bremen]
==>[a:matthias,b:baltimore]
==>[a:matthias,b:oakland]
==>[a:matthias,b:seattle]
==>[a:daniel,b:spremberg]
==>[a:daniel,b:kaiserslautern]
==>[a:daniel,b:aachen]
gremlin> g = g.with_strategies(new SubgraphStrategy(vertexProperties: has_not('endTime'))) //// (2)
==>graphtraversalsource[tinkergraph[vertices:6 edges:14], standard]
gremlin> g.V().as_('a').values('location').as_('b'). //// (3)
           select('a','b').by('name').by()
==>[a:marko,b:santa fe]
==>[a:stephen,b:purcellville]
==>[a:matthias,b:seattle]
==>[a:daniel,b:aachen]
gremlin> g.V().as_('a').values('location').as_('b').
           select('a','b').by('name').by().explain()
==>Traversal Explanation
=============================================================================================================================================================================================================================================
Original Traversal                    [GraphStep(vertex,[])@[a], PropertiesStep([location],value)@[b], SelectStep(last,[a, b],[value(name), identity])]

SubgraphStrategy                [D]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), TraversalFilterStep([NotStep([PropertiesStep([endTime],value)])]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity
                                         ])]
ConnectiveStrategy              [D]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), TraversalFilterStep([NotStep([PropertiesStep([endTime],value)])]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity
                                         ])]
IdentityRemovalStrategy         [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), TraversalFilterStep([NotStep([PropertiesStep([endTime],value)])]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity
                                         ])]
MatchPredicateStrategy          [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), TraversalFilterStep([NotStep([PropertiesStep([endTime],value)])]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity
                                         ])]
FilterRankingStrategy           [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), TraversalFilterStep([NotStep([PropertiesStep([endTime],value)])]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity
                                         ])]
InlineFilterStrategy            [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],value)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
IncidentToAdjacentStrategy      [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],value)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
AdjacentToIncidentStrategy      [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
RepeatUnrollStrategy            [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
CountStrategy                   [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
PathRetractionStrategy          [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
EarlyLimitStrategy              [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
LazyBarrierStrategy             [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
ByModulatorOptimizationStrategy [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
GValueReductionStrategy         [O]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
TinkerGraphCountStrategy        [P]   [GraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
TinkerGraphStepStrategy         [P]   [TinkerGraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
ProfileStrategy                 [F]   [TinkerGraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
StandardVerificationStrategy    [V]   [TinkerGraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]

Final Traversal                       [TinkerGraphStep(vertex,[])@[a], PropertiesStep([location],property), NotStep([PropertiesStep([endTime],property)]), PropertyValueStep@[b], SelectStep(last,[a, b],[value(name), identity])]
```

```
graph = TinkerFactory.createTheCrew()
g = traversal().with(graph)
g.V().as_('a').values('location').as_('b'). //// (1)
  select('a','b').by('name').by()
g = g.with_strategies(new SubgraphStrategy(vertexProperties: has_not('endTime'))) //// (2)
g.V().as_('a').values('location').as_('b'). //// (3)
  select('a','b').by('name').by()
g.V().as_('a').values('location').as_('b').
  select('a','b').by('name').by().explain()
```

1. Get all vertices and their vertex property locations.
2. Create a `SubgraphStrategy` where vertex properties must not have an `endTime`-property (thus, the current location).
3. Get all vertices and their current vertex property locations.

The following examples demonstrate the above `SubgraphStrategy` definition in other programming languages:

java

csharp

javascript

python

```
g.with_strategies(SubgraphStrategy.build().vertexProperties(has_not("endTime")).create());
```

```
g.with_strategies(new SubgraphStrategy(vertexProperties: has_not("endTime")));
```

```
g.with_strategies(new SubgraphStrategy(vertexProperties: has_not("endTime")));
```

```
g.with_strategies(SubgraphStrategy(vertex_properties=has_not("endTime")))
```

|  |  |
| --- | --- |
| Important | This strategy is implemented such that the vertices attached to an `Edge` must both satisfy the vertex criterion (if present) in order for the `Edge` to be considered a part of the subgraph. |

The example below uses all three filters: vertex, edge, and vertex property. People vertices must have lived in more
than three places, edges must be labeled "develops," and vertex properties must be the persons current location or a
non-location property.

console (groovy)

groovy

```
gremlin> graph = TinkerFactory.createTheCrew()
==>tinkergraph[vertices:6 edges:14]
gremlin> g = traversal().with(graph).with_strategies(SubgraphStrategy.build().
           vertices(or(has_not('location'),properties('location').count().is_(gt(3)))).
           edges(has_label('develops')).
           vertexProperties(or(has_label(neq('location')),has_not('endTime'))).create())
==>graphtraversalsource[tinkergraph[vertices:6 edges:14], standard]
gremlin> g.V().elementMap()
==>[id:1,label:person,name:marko,location:santa fe]
==>[id:8,label:person,name:matthias,location:seattle]
==>[id:10,label:software,name:gremlin]
==>[id:11,label:software,name:tinkergraph]
gremlin> g.E().elementMap()
==>[id:13,label:develops,IN:[id:10,label:software],OUT:[id:1,label:person],since:2009]
==>[id:14,label:develops,IN:[id:11,label:software],OUT:[id:1,label:person],since:2010]
==>[id:21,label:develops,IN:[id:10,label:software],OUT:[id:8,label:person],since:2012]
gremlin> g.V().out_e().in_v().
           path().
             by('name').
             by().
             by('name')
==>[marko,e[13][1-develops->10],gremlin]
==>[marko,e[14][1-develops->11],tinkergraph]
==>[matthias,e[21][8-develops->10],gremlin]
```

```
graph = TinkerFactory.createTheCrew()
g = traversal().with(graph).with_strategies(SubgraphStrategy.build().
  vertices(or(has_not('location'),properties('location').count().is_(gt(3)))).
  edges(has_label('develops')).
  vertexProperties(or(has_label(neq('location')),has_not('endTime'))).create())
g.V().elementMap()
g.E().elementMap()
g.V().out_e().in_v().
  path().
    by('name').
    by().
    by('name')
```

### VertexProgramDenyStrategy

Like the `ReadOnlyStrategy`, the `VertexProgramDenyStrategy` denies the execution of specific traversals. A `Traversal`
that has the `VertexProgramDenyStrategy` applied will throw an `IllegalStateException` if it uses the
`withComputer()` step. This `TraversalStrategy` can be useful for configuring `GraphTraversalSource` instances in
Gremlin Server with the `ScriptFileGremlinPlugin`.

```
gremlin> oltpOnly = g.with_strategies(VertexProgramDenyStrategy.instance())
==>graphtraversalsource[tinkergraph[vertices:5 edges:7], standard]
gremlin> oltpOnly.withComputer().V().elementMap()
The TraversalSource does not allow the use of a GraphComputer
Type ':help' or ':h' for help.
Display stack trace? [yN]
```

