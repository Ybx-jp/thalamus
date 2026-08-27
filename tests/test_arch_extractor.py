"""Interfaces: thalamus.arch.extractor, thalamus.arch.metrics
Infrastructure: none — the fixture tree is written per test into tmp_path
Scope: resolution forms, the depth split, the policy digest, and the metrics computed
       over them. The hand-counted acceptance test lives in `tests/qe/cases/arch_extractor.py`;
       this file covers the pieces that case would only fail as a whole.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from thalamus.arch.extractor import (
    DEPTH_DEFERRED,
    DEPTH_MODULE,
    KIND_FROM,
    KIND_IMPORT,
    KIND_PACKAGE,
    ExtractorPolicy,
    scan_repo,
)
from thalamus.arch.metrics import cycles, measure, propagation_cost


def _tree(root: Path, files: dict[str, str]) -> Path:
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_external_imports_leave_no_edge(tmp_path):
    """Propagation cost is about this repo's own modules, not its dependency list."""
    repo = _tree(tmp_path, {"src/a.py": "import os\nimport json\n"})
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    assert graph.modules == ["src/a.py"]
    assert graph.edges == []


def test_self_import_is_not_an_edge(tmp_path):
    """A package importing its own submodule must not produce a self-loop."""
    repo = _tree(
        tmp_path,
        {"src/app/__init__.py": "from app import core\n", "src/app/core.py": ""},
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    assert [edge.as_row() for edge in graph.edges] == [
        "src/app/__init__.py -> src/app/core.py [from,module]"
    ]


def test_deepest_match_wins_over_the_package(tmp_path):
    """`from pkg import mod` resolves to the submodule, with the package as its own kind."""
    repo = _tree(
        tmp_path,
        {
            "src/pkg/__init__.py": "",
            "src/pkg/mod.py": "",
            "src/caller.py": "from pkg import mod\n",
        },
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    rows = {edge.to_path: edge.kind for edge in graph.edges}
    assert rows == {"src/pkg/mod.py": KIND_FROM, "src/pkg/__init__.py": KIND_PACKAGE}


def test_name_import_records_no_package_edge(tmp_path):
    """`from pkg.mod import name` has one dependency, not two.

    The package half would resolve to the same module the alias did, and a second row
    saying so is double-counting — the difference between two defensible edge counts on
    a real repo.
    """
    repo = _tree(
        tmp_path,
        {
            "src/pkg/__init__.py": "",
            "src/pkg/mod.py": "VALUE = 1\n",
            "src/caller.py": "from pkg.mod import VALUE\n",
        },
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    assert [edge.as_row() for edge in graph.edges] == [
        "src/caller.py -> src/pkg/mod.py [from,module]"
    ]


def test_relative_import_climbs(tmp_path):
    """`from .. import x` resolves against the importing module's package."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/util.py": "",
            "src/app/deep/__init__.py": "",
            "src/app/deep/inner.py": "from .. import util\n",
        },
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    targets = {edge.to_path for edge in graph.edges if edge.kind == KIND_FROM}
    assert targets == {"src/app/util.py"}


def test_deferred_imports_are_recorded_but_filtered(tmp_path):
    """One walk answers both readings: the edge is recorded, the policy counts it or not."""
    repo = _tree(
        tmp_path,
        {
            "src/a.py": "def f():\n    import b\n    return b\n",
            "src/b.py": "",
        },
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    assert [edge.depth for edge in graph.edges] == [DEPTH_DEFERRED]
    assert len(graph.counted_edges()) == 1

    module_only = dataclasses.replace(graph.policy, import_depth="module-level")
    graph.policy = module_only
    assert graph.counted_edges() == []


def test_import_inside_a_module_level_if_is_module_level(tmp_path):
    """An import under `if TYPE_CHECKING:` still executes at import time."""
    repo = _tree(
        tmp_path,
        {"src/a.py": "if True:\n    import b\n", "src/b.py": ""},
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    assert [edge.depth for edge in graph.edges] == [DEPTH_MODULE]
    assert graph.edges[0].kind == KIND_IMPORT


def test_module_level_beats_deferred_for_one_pair(tmp_path):
    """A dependency that exists at module level is a module-level dependency."""
    repo = _tree(
        tmp_path,
        {
            "src/a.py": "import b\n\n\ndef f():\n    import b\n    return b\n",
            "src/b.py": "",
        },
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    assert [edge.as_row() for edge in graph.edges] == ["src/a.py -> src/b.py [import,module]"]


def test_excluded_paths_are_not_scanned(tmp_path):
    """A module the policy excludes is not a module, so it cannot be a dependency."""
    repo = _tree(
        tmp_path,
        {"src/a.py": "import skipme\n", "src/skipme.py": ""},
    )
    policy = ExtractorPolicy(roots=("src",), exclude=("src/skipme.py",))
    graph = scan_repo(repo, policy)
    assert graph.modules == ["src/a.py"]
    assert graph.edges == []


def test_unparsable_module_is_reported_not_dropped(tmp_path):
    """A file the walker cannot read lowers every metric; silence would hide that."""
    repo = _tree(tmp_path, {"src/broken.py": "def (\n"})
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    assert graph.unresolved and "broken.py" in graph.unresolved[0]


def test_policy_digest_moves_with_the_policy_and_not_with_formatting():
    """The digest is over the block's meaning, not its spelling."""
    one = ExtractorPolicy()
    same = ExtractorPolicy(languages=("python",))
    different = dataclasses.replace(one, import_depth="module-level")

    assert one.digest() == same.digest()
    assert one.digest() != different.digest()
    assert "digest" not in one.block()


def test_cycles_and_propagation_over_a_known_shape(tmp_path):
    """A three-module chain with a back edge: hand-computable on both metrics."""
    repo = _tree(
        tmp_path,
        {
            "src/a.py": "import b\n",
            "src/b.py": "import c\n",
            "src/c.py": "import b\n",
        },
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    found = cycles(graph)
    assert found == (("src/b.py", "src/c.py"),)

    # a reaches {a,b,c}=3, b {b,c}=2, c {c,b}=2 -> 7 of 9 cells.
    assert propagation_cost(graph) == 7 / 9
    metrics = measure(graph)
    assert (metrics.modules, metrics.dependencies, metrics.modules_in_cycles) == (3, 3, 2)


def test_empty_repo_does_not_divide_by_zero(tmp_path):
    graph = scan_repo(tmp_path, ExtractorPolicy(roots=("src",)))
    assert graph.modules == []
    assert propagation_cost(graph) == 0.0
