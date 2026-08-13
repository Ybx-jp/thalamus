"""Interfaces: thalamus.arch.model, thalamus.arch.graph
Infrastructure: none — model files are written into tmp_path; no graph connection
Scope: the authored/derived split and what may overwrite what, rule checking against a
       measured graph, scan identity, and the claim shapes a scan emits.
"""

from __future__ import annotations

from pathlib import Path

from thalamus.arch import graph as arch_graph
from thalamus.arch import model as arch_model
from thalamus.arch.extractor import ExtractorPolicy, scan_repo
from thalamus.arch.metrics import measure


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "src" / "app").mkdir(parents=True)
    (tmp_path / "src" / "app" / "__init__.py").write_text("")
    (tmp_path / "src" / "app" / "core.py").write_text("import app.util\n")
    (tmp_path / "src" / "app" / "util.py").write_text("")
    return tmp_path


def test_regenerate_preserves_the_authored_half_byte_for_byte(tmp_path):
    """The authored half is prose arguing for a boundary; a YAML round-trip eats it."""
    authored = (
        "# A comment the architect wrote and expects to survive.\n"
        "repo: demo\n"
        "root_commit: abc123\n"
        "layers:\n"
        "  # why this layer exists\n"
        "  - name: core\n"
        "    includes: ['src/app/**']\n"
        "\n"
    )
    existing = authored + arch_model.DERIVED_MARKER + "derived:\n  scan: old\n"

    rewritten = arch_model.regenerate(existing, {"scan": "new", "metrics": {}})

    assert rewritten.startswith(authored)
    assert "# A comment the architect wrote" in rewritten
    assert "# why this layer exists" in rewritten
    assert "scan: new" in rewritten
    assert "scan: old" not in rewritten


def test_regenerate_on_a_file_without_a_marker_appends_one(tmp_path):
    rewritten = arch_model.regenerate("repo: demo\n", {"scan": "first"})
    assert "repo: demo" in rewritten
    assert arch_model.DERIVED_MARKER.splitlines()[0] in rewritten
    assert "scan: first" in rewritten


def test_load_round_trips_a_rendered_model(tmp_path):
    model = arch_model.ArchModel(
        repo="demo",
        root_commit="abc123",
        policy=ExtractorPolicy(roots=("src",)),
        layers=[arch_model.Layer(name="core", includes=("src/app/**",))],
        rules=[arch_model.Rule(layer="core", may_depend_on=("util",))],
    )
    path = tmp_path / "model.yaml"
    path.write_text(arch_model.render(model, {"scan": "s", "metrics": {}}), encoding="utf-8")

    loaded = arch_model.load(path)

    assert loaded.repo == "demo"
    assert loaded.root_commit == "abc123"
    assert [layer.name for layer in loaded.layers] == ["core"]
    assert loaded.rules[0].may_depend_on == ("util",)
    assert loaded.policy.digest() == model.policy.digest()


def test_a_missing_model_file_is_an_empty_model_not_an_error(tmp_path):
    loaded = arch_model.load(tmp_path / "nope.yaml")
    assert loaded.repo == ""
    assert loaded.layers == []


def test_scan_id_names_both_the_commit_and_the_policy():
    policy = ExtractorPolicy()
    other = ExtractorPolicy(import_depth="module-level")
    commit = "041797abcdef"

    assert arch_model.scan_id("thalamus", commit, policy).startswith("arch:scan:thalamus:041797a:")
    assert arch_model.scan_id("thalamus", commit, policy) != arch_model.scan_id(
        "thalamus", commit, other
    )


def test_unplaced_reports_every_module_when_no_partition_is_declared(tmp_path):
    """An empty partition must not read as a pass."""
    repo = _repo(tmp_path)
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    model = arch_model.ArchModel()
    assert sorted(model.unplaced(graph)) == sorted(graph.modules)


def test_violations_are_measured_against_declared_rules(tmp_path):
    repo = _repo(tmp_path)
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    model = arch_model.ArchModel(
        layers=[
            arch_model.Layer(name="core", includes=("src/app/core.py",)),
            arch_model.Layer(name="util", includes=("src/app/util.py",)),
        ],
        rules=[arch_model.Rule(layer="core", may_depend_on=())],
    )

    violations = model.violations(graph)

    assert len(violations) == 1
    assert violations[0].from_layer == "core"
    assert violations[0].to_layer == "util"
    assert "may not depend on" in violations[0].describe()


def test_a_layer_with_no_rule_permits_everything(tmp_path):
    """Naming a layer must not silently forbid every edge that touches it."""
    repo = _repo(tmp_path)
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    model = arch_model.ArchModel(
        layers=[
            arch_model.Layer(name="core", includes=("src/app/core.py",)),
            arch_model.Layer(name="util", includes=("src/app/util.py",)),
        ],
    )
    assert model.violations(graph) == []


def test_stale_authored_paths_reports_a_layer_matching_nothing():
    model = arch_model.ArchModel(
        layers=[arch_model.Layer(name="ghost", includes=("src/gone/**",))],
        derived={"edges": ["src/app/core.py -> src/app/util.py [import,module]"]},
    )
    stale = model.stale_authored_paths()
    assert len(stale) == 1
    assert "matches no module" in stale[0]


def test_findings_name_no_scan_id(tmp_path):
    """Claim identity is the description; folding the scan id in mints a vertex a run."""
    repo = tmp_path
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("import b\n")
    (repo / "src" / "b.py").write_text("def f():\n    import a\n    return a\n")

    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    metrics = measure(graph)
    found = arch_graph.findings(graph, metrics, arch_model.ArchModel())

    assert len(found) == 1
    assert "Import cycle" in found[0].description
    assert "arch:scan" not in found[0].description
    assert sorted(found[0].artifacts) == ["src/a.py", "src/b.py"]


def test_the_same_finding_keeps_one_identity_across_scans(tmp_path):
    """A persisting cycle is one claim with more evidence, not a claim per run."""
    repo = tmp_path
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("import b\n")
    (repo / "src" / "b.py").write_text("def f():\n    import a\n    return a\n")

    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    first = arch_graph.findings(graph, measure(graph), arch_model.ArchModel())
    second = arch_graph.findings(graph, measure(graph), arch_model.ArchModel())

    assert first[0].content_id() == second[0].content_id()


def test_a_clean_repo_emits_no_findings(tmp_path):
    repo = _repo(tmp_path)
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    found = arch_graph.findings(graph, measure(graph), arch_model.ArchModel())
    assert found == []


def test_scan_payload_is_first_party_and_names_the_scanner(tmp_path):
    payload = arch_graph.payload(
        repo="demo",
        origin="arch:scan:demo:abc1234:def5678",
        lineage="arch:scan:demo:def5678",
        commit="abc1234567",
        content_hash="f" * 64,
        uri="archive://" + "f" * 64,
        byte_size=10,
        found=[],
    )
    assert payload.scope == "architect"
    assert int(payload.provenance.tier) == 1
    assert payload.provenance.source == "agent:arch-scanner"
    assert payload.title == "Architecture scan — demo @ abc1234"


def test_citation_tells_the_reader_when_a_value_was_superseded():
    rendered = arch_graph.citation(
        "`thalamus.contract.ontology` is import-reachable from 41 of 76 modules (54%).",
        scan="arch:scan:thalamus:041797a:e3f1a0d",
        commit="041797abcd",
        policy_line="`import_depth=all`",
        superseded_by="arch:scan:thalamus:9c1f2ab:e3f1a0d",
    )
    assert "Structural fact" in rendered
    assert "Scanned at `041797a`" in rendered
    assert "Superseded by" in rendered
    assert "this value held at the commit named" in rendered


def test_citation_without_supersession_makes_no_such_claim():
    rendered = arch_graph.citation("x", scan="s", commit="abcdefg", policy_line="p")
    assert "Superseded" not in rendered
