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

from thalamus.contract.manifest import load_manifest
from thalamus.contract.reporting import build, reporting_graph

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
