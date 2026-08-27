"""The staleness gate's comparison — `thalamus arch scan --check`.

Interfaces: thalamus.arch.model (derived_block, load, regenerate).

The gate compares the *measurement* and not the file text. The distinction is the whole
test: `scan` and `commit` name the tree that was measured, and writing the model then
committing it moves HEAD, so a fresh scan's stamp can never equal the stamp inside the
commit that carries the file. A gate keyed on the text is one that no tree can ever
satisfy — it fails on the commit that was supposed to fix it, forever.
"""

from __future__ import annotations

from thalamus.arch.extractor import DependencyEdge, DependencyGraph
from thalamus.arch.metrics import measure
from thalamus.arch.model import derived_block

_MEASURED = ("metrics", "counted_edges", "recorded_edges", "unresolved", "edges")


def _block(commit: str, pairs: tuple[tuple[str, str], ...]) -> dict:
    modules = sorted({p for pair in pairs for p in pair})
    graph = DependencyGraph(
        modules=modules,
        edges=[DependencyEdge(from_path=a, to_path=b, kind="from", depth="module")
               for a, b in pairs],
    )
    return derived_block(graph, measure(graph), commit, f"arch:scan:t:{commit[:7]}:d")


def _comparable(block: dict) -> dict:
    """What the gate actually compares — everything but the identity stamps."""
    return {k: v for k, v in block.items() if k not in ("scan", "commit")}


def test_the_same_tree_measured_at_two_commits_compares_equal():
    """The regression guard. This is the case that made the first gate unsatisfiable.

    Nothing about the code changed between these two blocks; only the commit the
    measurement is stamped with. A gate that called this stale would fail on the very
    commit that regenerated the model, and go on failing.
    """
    pairs = (("a.py", "b.py"), ("b.py", "c.py"))
    before = _block("1b78bfd1d05c", pairs)
    after = _block("41304b0d0b07", pairs)

    assert before != after, "the stamps should differ, or this test proves nothing"
    assert _comparable(before) == _comparable(after)


def test_a_changed_edge_is_stale_even_at_the_same_commit():
    same = "1b78bfd1d05c"
    before = _block(same, (("a.py", "b.py"),))
    after = _block(same, (("a.py", "b.py"), ("b.py", "c.py")))
    assert _comparable(before) != _comparable(after)


def test_every_measured_key_is_compared():
    """The gate ignores exactly two keys. If a scan starts recording a third measured
    key, it must be compared — an ignore-list that silently grows stops gating."""
    block = _block("1b78bfd1d05c", (("a.py", "b.py"),))
    assert set(block) - {"scan", "commit"} == set(_MEASURED), (
        f"derived_block's keys changed to {sorted(block)}; confirm the new key is a "
        "measurement that should be compared, not another identity stamp"
    )


def test_a_drift_report_names_the_key_that_moved():
    """The gate prints which keys differ, so a failure says what to look at."""
    same = "1b78bfd1d05c"
    stored = _comparable(_block(same, (("a.py", "b.py"),)))
    measured = _comparable(_block(same, (("a.py", "b.py"), ("b.py", "c.py"))))
    drifted = sorted(k for k in set(stored) | set(measured) if stored.get(k) != measured.get(k))
    assert "edges" in drifted and "counted_edges" in drifted


def test_this_repo_matches_its_committed_model():
    """The gate CI runs, run here, so a stale model fails the suite and not only CI."""
    from thalamus.arch import model as arch_model
    from thalamus.arch import routes as arch_routes
    from thalamus.arch.extractor import scan_repo

    repo = arch_model.REPO_ROOT
    model = arch_model.load(repo / arch_model.MODEL_PATH)
    graph = arch_routes.merge(
        scan_repo(repo, model.policy), arch_routes.extract_routes(repo, model.routes)
    )
    fresh = derived_block(graph, measure(graph), "unused", "unused")

    stored, measured = _comparable(model.derived), _comparable(fresh)
    drifted = sorted(k for k in set(stored) | set(measured) if stored.get(k) != measured.get(k))
    assert not drifted, (
        f"arch/model.yaml is stale in {drifted} — run `thalamus arch scan --write`"
    )
