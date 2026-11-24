"""
The reporting structure: each manifest's `reports_to`, checked as one tree under `main`.

Interfaces: thalamus.contract.reporting, `thalamus reporting`, `thalamus contract check --experts`
Infrastructure: tmp_path config roots only
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from thalamus.contract.manifest import ExpertManifest, load_manifest
from thalamus.contract.reporting import (
    build,
    charter_domain,
    inherited_rules,
    reporting_graph,
)

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config"


def _config(tmp_path, manifests: dict[str, str | None]) -> Path:
    """One manifest per scope; the value is its `reports_to`, or None to leave it out."""
    (tmp_path / "experts").mkdir()
    for scope, up in manifests.items():
        body = f"scope: {scope}\nname: {scope}\n" + (f"reports_to: {up}\n" if up else "")
        (tmp_path / "experts" / f"{scope}.yaml").write_text(body)
    return tmp_path


def test_a_manifest_without_reports_to_reports_to_main(tmp_path):
    base = _config(tmp_path, {"career": None})
    assert load_manifest("career", base).reports_to == "main"
    tree = reporting_graph(base)
    assert tree.superior("career") == "main"
    assert tree.superior("main") is None


def test_a_chain_of_any_depth_ends_at_main(tmp_path):
    base = _config(tmp_path, {
        "career": None,
        "career-market": "career",
        "career-market-boards": "career-market",
        "chess": None,
    })
    tree = reporting_graph(base)
    assert tree.reports("main") == ["career", "chess"]
    assert tree.reports("career") == ["career-market"]
    assert tree.reports("career-market") == ["career-market-boards"]
    assert tree.lines() == [
        "main", "  career", "    career-market", "      career-market-boards", "  chess",
    ]
    assert tree.as_dict() == {
        "root": "main",
        "reports_to": {
            "career": "main", "career-market": "career",
            "career-market-boards": "career-market", "chess": "main",
        },
        "reports": {
            "main": ["career", "chess"],
            "career": ["career-market"],
            "career-market": ["career-market-boards"],
        },
    }


@pytest.mark.parametrize("superiors, message", [
    ({"a": "a"}, "`a` reports to itself"),
    ({"a": "b"}, "`a` reports to `b`, which is neither `main` nor a declared scope"),
    ({"a": "b", "b": "a"}, "reporting loop: a → b → a"),
    ({"a": "b", "b": "c", "c": "b"}, "reporting loop: b → c → b"),
    ({"main": "a", "a": "main"}, "`main` is the root"),
])
def test_a_broken_chain_is_refused(superiors, message):
    with pytest.raises(ValueError, match=message):
        build(superiors)


def test_the_refusal_names_the_manifest_to_fix(tmp_path):
    base = _config(tmp_path, {"career-market": "careers"})
    with pytest.raises(ValueError, match=r"career-market\.yaml: `career-market` reports to `careers`"):
        reporting_graph(base)


def test_the_committed_roster_is_a_valid_tree():
    tree = reporting_graph(REPO_CONFIG)
    assert set(tree.superiors) == {p.stem for p in (REPO_CONFIG / "experts").glob("*.yaml")}


def _cli(base: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "THALAMUS_CONFIG_DIR": str(base)}
    return subprocess.run(
        [sys.executable, "-m", "thalamus.cli", *args],
        capture_output=True, text=True, env=env,
    )


def test_the_command_prints_the_tree_and_its_json(tmp_path):
    base = _config(tmp_path, {"career": None, "career-market": "career"})
    text = _cli(base, "reporting")
    assert text.returncode == 0, text.stderr
    assert text.stdout.splitlines() == ["main", "  career", "    career-market"]
    data = json.loads(_cli(base, "reporting", "--json").stdout)
    assert data["reports_to"] == {"career": "main", "career-market": "career"}


def test_the_command_exits_1_on_a_broken_chain(tmp_path):
    base = _config(tmp_path, {"a": "b", "b": "a"})
    run = _cli(base, "reporting")
    assert run.returncode == 1
    assert "reporting loop" in run.stderr


def test_contract_check_experts_shows_each_scopes_superior(tmp_path):
    base = _config(tmp_path, {"career": None, "career-market": "career"})
    run = _cli(base, "contract", "check", "--experts")
    assert run.returncode == 0, run.stderr
    assert "career-market\n    reports to career" in run.stdout


# --- rules travel down the tree -------------------------------------------------------

MANAGER_RULES = "Advisory only. Never name a person.\nOne notification a day for the tree."


def _ruled(tmp_path, manifests: dict[str, tuple[str | None, str]]) -> Path:
    """One manifest per scope: (reports_to or None, rules or "")."""
    (tmp_path / "experts").mkdir()
    for scope, (up, rules) in manifests.items():
        doc = {"scope": scope, "name": scope, "domain": f"{scope} domain."}
        if up:
            doc["reports_to"] = up
        if rules:
            doc["rules"] = rules
        (tmp_path / "experts" / f"{scope}.yaml").write_text(yaml.safe_dump(doc))
    return tmp_path


def _tree(tmp_path) -> Path:
    return _ruled(tmp_path, {
        "career": (None, MANAGER_RULES),
        "career-market": ("career", ""),
        "career-market-boards": ("career-market", "Count by distinct board."),
        "chess": (None, ""),
    })


def test_a_specialists_charter_carries_its_managers_rules_verbatim(tmp_path):
    base = _tree(tmp_path)
    charter = charter_domain(load_manifest("career-market", base))
    assert charter.startswith("career-market domain.")
    assert MANAGER_RULES in charter
    assert "from `career`, which it reports to" in charter


def test_rules_reach_every_depth_top_most_first_and_add_to_each_other(tmp_path):
    base = _tree(tmp_path)
    leaf = load_manifest("career-market-boards", base)
    assert inherited_rules(leaf) == [
        ("career", MANAGER_RULES),
        ("career-market-boards", "Count by distinct board."),
    ]
    charter = charter_domain(leaf)
    assert charter.index(MANAGER_RULES) < charter.index("Count by distinct board.")


def test_a_scope_reporting_to_main_carries_only_its_own_rules(tmp_path):
    base = _tree(tmp_path)
    assert inherited_rules(load_manifest("chess", base)) == []
    assert charter_domain(load_manifest("chess", base)) == "chess domain."
    manager = charter_domain(load_manifest("career", base))
    assert "every scope that reports to it" in manager and MANAGER_RULES in manager


def test_a_manifest_reporting_to_main_reads_no_other_manifest(tmp_path):
    lone = ExpertManifest(scope="solo", name="solo", domain="d", rules="r")
    assert inherited_rules(lone, tmp_path / "nowhere") == [("solo", "r")]


def test_a_broken_tree_stops_the_charter_rather_than_dropping_rules(tmp_path):
    base = _ruled(tmp_path, {"a": ("b", ""), "b": ("a", MANAGER_RULES)})
    with pytest.raises(ValueError, match="reporting loop"):
        charter_domain(load_manifest("a", base))


def test_every_charter_carrier_reads_the_inherited_rules(tmp_path, monkeypatch):
    """The agent file, the codex profile, the delegated prompt and the consultation
    brief: a rule one of them left out would bind a pinned session and not the rest."""
    from thalamus.harness import consultation, delegate, pin

    base = _tree(tmp_path)
    monkeypatch.setenv("THALAMUS_CONFIG_DIR", str(base))
    manifest = load_manifest("career-market", base)
    assert MANAGER_RULES in pin.render_agent(manifest)
    assert "Advisory only. Never name a person." in pin.render_codex_profile(manifest)
    assert MANAGER_RULES in delegate.build_prompt("career-market", "Do it.", [])

    monkeypatch.setattr(consultation, "available_scopes", lambda: ["career-market"])
    monkeypatch.setattr(consultation, "load_manifest", lambda scope: manifest)
    monkeypatch.setattr(
        consultation, "_assemble_brief",
        lambda g, scope, q: (["## x\n\ny"], ["scope:career-market:thread:t"]),
    )
    monkeypatch.setattr(
        consultation, "open_exchange", lambda *a, **k: ("t", "scope:main:exchange:t")
    )
    assert MANAGER_RULES in consultation.consult_request(object(), "career-market", "q?", "main")


def test_an_edit_to_the_managers_rules_regenerates_every_descendants_agent(tmp_path):
    from thalamus.harness import pin

    base = _tree(tmp_path)
    agents = tmp_path / "agents"
    pin.write_all_agents(agents, base)
    for scope in ("career", "career-market", "career-market-boards"):
        assert MANAGER_RULES in (agents / f"{pin.agent_name(scope)}.md").read_text()
    assert MANAGER_RULES not in (agents / f"{pin.agent_name('chess')}.md").read_text()

    path = base / "experts" / "career.yaml"
    path.write_text(path.read_text().replace("Never name a person.", "Never name anyone."))
    pin.write_all_agents(agents, base)
    for scope in ("career-market", "career-market-boards"):
        body = (agents / f"{pin.agent_name(scope)}.md").read_text()
        assert "Never name anyone." in body and "Never name a person." not in body


def test_contract_check_experts_shows_whose_rules_bind_each_scope(tmp_path):
    run = _cli(_tree(tmp_path), "contract", "check", "--experts")
    assert run.returncode == 0, run.stderr
    assert "career-market-boards\n    reports to career-market\n    rules      from: career, career-market-boards" in run.stdout
    assert "chess\n    reports to main\n    rules      from: (none)" in run.stdout
