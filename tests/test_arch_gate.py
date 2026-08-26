"""The gate over the structural model — what CI acts on, as opposed to what it prints.

Interfaces: thalamus.arch.model (Accepted, GateResult, ArchModel.gate, load, render).

The distinction under test is that `rules` reports every violation while `gate` sorts
them into new, accepted and stale. A gate that filtered the report would hide the
design's real shape from the architect reading it; a report with no verdict cannot fail
a build. Both halves have to hold at once.
"""

from __future__ import annotations

from pathlib import Path

from thalamus.arch.extractor import DependencyEdge, DependencyGraph
from thalamus.arch.model import Accepted, ArchModel, Layer, Rule, load, render


def _graph(*pairs: tuple[str, str]) -> DependencyGraph:
    """A graph over exactly the modules named in `pairs`, every edge counted."""
    modules = sorted({path for pair in pairs for path in pair})
    edges = [
        DependencyEdge(from_path=a, to_path=b, kind="from", depth="module") for a, b in pairs
    ]
    return DependencyGraph(modules=modules, edges=edges)


def _model(**kwargs) -> ArchModel:
    """A two-layer model where `high` may depend on `low` and `low` on nothing."""
    return ArchModel(
        layers=[
            Layer(name="low", includes=("low/**",)),
            Layer(name="high", includes=("high/**",)),
        ],
        rules=[Rule(layer="low", may_depend_on=()), Rule(layer="high", may_depend_on=("low",))],
        **kwargs,
    )


def test_clean_graph_gates_green():
    result = _model().gate(_graph(("high/a.py", "low/b.py")))
    assert result.exit_code == 0
    assert not result.new_violations and not result.new_unplaced and not result.stale


def test_undeclared_violation_is_new_and_exits_one():
    result = _model().gate(_graph(("low/a.py", "high/b.py")))
    assert result.exit_code == 1
    assert [(v.from_path, v.to_path) for v in result.new_violations] == [
        ("low/a.py", "high/b.py")
    ]


def test_accepted_violation_does_not_fail_the_gate():
    model = _model(
        accepted=[Accepted(from_path="low/a.py", to_path="high/b.py", reason="deliberate")]
    )
    result = model.gate(_graph(("low/a.py", "high/b.py")))
    assert result.exit_code == 0
    assert not result.new_violations
    assert [entry.reason for entry in result.accepted_hits] == ["deliberate"]


def test_acceptance_that_no_longer_happens_exits_two():
    """A tolerated defect that got fixed is neither green nor a regression.

    Collapsing it into either loses the only signal that keeps the exception list from
    accumulating entries for edges refactored away long ago.
    """
    model = _model(
        accepted=[Accepted(from_path="low/a.py", to_path="high/b.py", reason="deliberate")]
    )
    result = model.gate(_graph(("high/a.py", "low/b.py")))
    assert result.exit_code == 2
    assert [entry.key for entry in result.stale] == [("low/a.py", "high/b.py")]


def test_a_new_violation_outranks_a_stale_acceptance():
    model = _model(
        accepted=[Accepted(from_path="low/gone.py", to_path="high/gone.py", reason="old")]
    )
    result = model.gate(_graph(("low/a.py", "high/b.py")))
    assert result.exit_code == 1
    assert result.new_violations and result.stale


def test_unplaced_module_fails_the_gate_and_can_be_accepted():
    graph = _graph(("high/a.py", "elsewhere/c.py"))
    assert _model().gate(graph).new_unplaced == ["elsewhere/c.py"]

    model = _model(accepted=[Accepted(module="elsewhere/c.py", reason="vendored")])
    result = model.gate(graph)
    assert result.exit_code == 0
    assert not result.new_unplaced


def test_accepted_survives_a_render_load_round_trip(tmp_path: Path):
    """The exception list is authored YAML, so it has to come back off disk intact."""
    model = _model(
        accepted=[
            Accepted(from_path="low/a.py", to_path="high/b.py", reason="an edge reason"),
            Accepted(module="elsewhere/c.py", reason="a module reason"),
        ]
    )
    path = tmp_path / "model.yaml"
    path.write_text(render(model, {}), encoding="utf-8")
    reloaded = load(path)

    assert [entry.key for entry in reloaded.accepted] == [
        ("low/a.py", "high/b.py"),
        ("elsewhere/c.py", ""),
    ]
    assert [entry.reason for entry in reloaded.accepted] == ["an edge reason", "a module reason"]


def test_this_repo_gates_green():
    """The committed model accepts exactly what this repo measures.

    Not a tautology: it fails if a violation is added without a declared reason, and
    equally if one of the four accepted edges is fixed and its entry left behind.
    """
    from thalamus.arch import model as arch_model
    from thalamus.arch import routes as arch_routes
    from thalamus.arch.extractor import scan_repo

    repo = arch_model.REPO_ROOT
    model = load(repo / arch_model.MODEL_PATH)
    graph = arch_routes.merge(
        scan_repo(repo, model.policy), arch_routes.extract_routes(repo, model.routes)
    )
    result = model.gate(graph)

    assert result.new_violations == [], [v.describe() for v in result.new_violations]
    assert result.new_unplaced == []
    assert result.stale == [], [entry.describe() for entry in result.stale]


def test_every_accepted_entry_states_a_reason():
    """The reason is the whole mechanism. An entry without one is an entry nobody can
    ever remove, because the next reader has no basis on which to judge it."""
    from thalamus.arch import model as arch_model

    model = load(arch_model.REPO_ROOT / arch_model.MODEL_PATH)
    assert model.accepted, "the repo declares exceptions; this test guards their reasons"
    for entry in model.accepted:
        assert entry.reason.strip(), f"{entry.key} is accepted with no reason"
        assert len(entry.reason.split()) >= 10, f"{entry.key} reason is too thin to act on"
