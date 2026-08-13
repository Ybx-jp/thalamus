"""Structural metrics over an extracted dependency graph.

MacCormack, Rusnak and Baldwin's propagation cost is the headline: the density of the
visibility matrix, i.e. the share of all ordered module pairs where one can reach the
other through any chain of dependencies. It answers "if I change a module, how much of
the system can feel it" with a number rather than an impression.

Every function here recomputes from the edge list. Nothing is cached and nothing is
stored as truth (docs/09): the edge list is the observation, and a metric is a reading
of it that must move when the code moves. A stored number would be a fact about a
commit nobody is looking at.

The numbers are only comparable within one extractor policy. `propagation_cost` takes
the graph — which carries its policy — rather than a bare adjacency map, so a caller
cannot accidentally compare two readings taken under different rules.
"""

from __future__ import annotations

from dataclasses import dataclass

from thalamus.arch.extractor import DependencyGraph


@dataclass(frozen=True)
class Metrics:
    """What one scan measured. Recomputed per scan, never stored as truth."""

    modules: int
    dependencies: int
    propagation_cost: float
    cycles: tuple[tuple[str, ...], ...]
    modules_in_cycles: int

    def as_block(self) -> dict[str, object]:
        """The metric block as it lands in the model file's derived section."""
        return {
            "modules": self.modules,
            "dependencies": self.dependencies,
            "propagation_cost": round(self.propagation_cost * 100, 2),
            "cycles": [list(cycle) for cycle in self.cycles],
            "modules_in_cycles": self.modules_in_cycles,
        }


def visibility(graph: DependencyGraph) -> dict[str, set[str]]:
    """module -> every module it can reach, itself included.

    Transitive closure by repeated frontier expansion rather than matrix powers: the
    graph is sparse (197 edges over 76 modules), so reachability per node is cheaper
    than multiplying a 76x76 matrix, and it stays honest at any size this repo reaches.

    A module is visible to itself. That is MacCormack's definition — the identity term
    in the sum of matrix powers — and dropping it would understate the cost by exactly
    N cells, which is 1.3% here and would look like a real difference.
    """
    adjacency = graph.adjacency()
    reachable: dict[str, set[str]] = {}
    for module in graph.modules:
        seen = {module}
        frontier = [module]
        while frontier:
            current = frontier.pop()
            for neighbour in adjacency.get(current, ()):  # noqa: SIM118 - set lookup
                if neighbour not in seen:
                    seen.add(neighbour)
                    frontier.append(neighbour)
        reachable[module] = seen
    return reachable


def propagation_cost(graph: DependencyGraph) -> float:
    """Density of the visibility matrix, as a fraction of all ordered pairs.

    Returns 0.0 for an empty graph rather than dividing by zero — a repo with no
    modules has no propagation, and raising here would make the scanner fail on a
    fixture that is legitimately empty.
    """
    if not graph.modules:
        return 0.0
    reachable = visibility(graph)
    total = sum(len(targets) for targets in reachable.values())
    return total / (len(graph.modules) ** 2)


def cycles(graph: DependencyGraph) -> tuple[tuple[str, ...], ...]:
    """Strongly connected components of more than one module.

    Tarjan's algorithm, iterative: a recursive walk overflows Python's stack on a repo
    large enough to have the problem this is looking for.

    A single module is not a cycle even when it imports itself; self-edges are already
    dropped by the extractor. What this finds is `eval/corpora.py` and `eval/arms.py`
    holding each other up — which the module-level-only reading reports as zero.
    """
    adjacency = graph.adjacency()
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    found: list[tuple[str, ...]] = []
    counter = 0

    for root in graph.modules:
        if root in index:
            continue
        # (node, iterator over its successors) — the explicit call stack.
        work: list[tuple[str, list[str]]] = [(root, sorted(adjacency.get(root, ())))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)

        while work:
            node, successors = work[-1]
            if successors:
                successor = successors.pop()
                if successor not in index:
                    index[successor] = low[successor] = counter
                    counter += 1
                    stack.append(successor)
                    on_stack.add(successor)
                    work.append((successor, sorted(adjacency.get(successor, ()))))
                elif successor in on_stack:
                    low[node] = min(low[node], index[successor])
                continue

            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    found.append(tuple(sorted(component)))

    return tuple(sorted(found))


def measure(graph: DependencyGraph) -> Metrics:
    """Every metric for one scan, computed together."""
    found = cycles(graph)
    return Metrics(
        modules=len(graph.modules),
        dependencies=len(graph.counted_edges()),
        propagation_cost=propagation_cost(graph),
        cycles=found,
        modules_in_cycles=sum(len(cycle) for cycle in found),
    )


def fan_in(graph: DependencyGraph) -> dict[str, int]:
    """How many modules import each module directly."""
    counts = {module: 0 for module in graph.modules}
    for edge in graph.counted_edges():
        counts[edge.to_path] = counts.get(edge.to_path, 0) + 1
    return counts


def reachable_from(graph: DependencyGraph) -> dict[str, int]:
    """How many modules can reach each module — the citation render's headline shape.

    "`thalamus.contract.ontology` is import-reachable from 41 of 76 modules (54%)" is
    this number. It is the column sum of the visibility matrix, not the row sum: what
    depends on me, transitively, rather than what I depend on.
    """
    counts = {module: 0 for module in graph.modules}
    for source, targets in visibility(graph).items():
        for target in targets:
            if target != source:
                counts[target] = counts.get(target, 0) + 1
    return counts
