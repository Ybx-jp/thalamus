"""
codex's live model catalog: where it is read from, what is offered, what a retired
slug becomes.

Interfaces: thalamus.harness.codex_models, AgentCLI.offered_models, pin.render_codex_profile
Infrastructure: a fake `codex` on PATH and a tmp CODEX_HOME — no real codex, no network
"""

import json
import os
import stat
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thalamus.harness import codex_models
from thalamus.harness.agents import AGENT_CLIS

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config"

pytestmark = pytest.mark.live_codex_catalog


def _entry(slug, priority, visibility="list", upgrade=None):
    return {"slug": slug, "priority": priority, "visibility": visibility,
            **({"upgrade": upgrade} if upgrade else {})}


LIVE = [
    _entry("gpt-6-astra", 1),
    _entry("gpt-hidden", 3, "hide"),
    _entry("gpt-5.6-sol", 4),
    _entry("gpt-5.6-luna", 8),
    _entry("gpt-5.5", 12, upgrade={"model": "gpt-5.6-sol",
                                   "retirement_at": "2026-10-14T19:00:00Z"}),
]


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    """A `codex` that reports a version and prints `LIVE` for `debug models`, counting
    how often it was asked for the catalog."""
    bin_dir, home = tmp_path / "bin", tmp_path / "codex-home"
    bin_dir.mkdir()
    home.mkdir()
    calls = tmp_path / "debug-calls"
    script = bin_dir / "codex"
    script.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo "codex-cli ${FAKE_VERSION:-0.200.0}"; exit 0; fi\n'
        f'if [ "$1" = "debug" ]; then echo x >> {calls}; cat {tmp_path / "live.json"}; exit 0; fi\n'
        "exit 1\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "live.json").write_text(json.dumps({"models": LIVE}))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("CODEX_HOME", str(home))
    codex_models._memo.clear()

    def debug_calls():
        return len(calls.read_text().splitlines()) if calls.exists() else 0

    return home, debug_calls


def _write_cache(home, version, models):
    (home / codex_models.CACHE_FILE).write_text(
        json.dumps({"client_version": version, "models": models})
    )


def test_a_cache_written_by_the_installed_version_is_read_without_asking_codex(fake_codex):
    home, debug_calls = fake_codex
    _write_cache(home, "0.200.0", [_entry("gpt-from-cache", 1)])

    assert codex_models.offered(codex_models.catalog()) == ("gpt-from-cache",)
    assert debug_calls() == 0


def test_an_update_invalidates_the_cache_and_the_catalog_is_asked_for(fake_codex):
    """
    Scenario: codex was updated since it last wrote its cache. The cache names the old
    client version, so it describes a catalog the installed binary may not serve.
    """
    home, debug_calls = fake_codex
    _write_cache(home, "0.154.0", [_entry("gpt-from-cache", 1)])

    offered = codex_models.offered(codex_models.catalog())

    assert "gpt-from-cache" not in offered
    assert offered[0] == "gpt-6-astra"
    assert debug_calls() == 1


def test_offered_is_listed_models_by_priority_minus_the_retired(fake_codex):
    models = codex_models.catalog()

    before = codex_models.offered(models, now=datetime(2026, 9, 24, tzinfo=UTC))
    after = codex_models.offered(models, now=datetime(2026, 10, 15, tzinfo=UTC))

    assert before == ("gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.5")
    assert after == ("gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-luna")


def test_current_follows_the_vendors_upgrade_and_leaves_unknown_slugs_alone(fake_codex):
    models = codex_models.catalog()

    assert codex_models.current("gpt-5.5", models) == "gpt-5.6-sol"
    assert codex_models.current("gpt-6-astra", models) == "gpt-6-astra"
    assert codex_models.current("gpt-gone", models) == "gpt-gone"


def test_an_upgrade_cycle_terminates():
    models = (codex_models.CatalogModel("a", 1, True, upgrade="b"),
              codex_models.CatalogModel("b", 2, True, upgrade="a"))

    assert codex_models.current("a", models) == "b"


def test_no_codex_on_path_means_no_catalog_and_the_pinned_list_stands(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    codex_models._memo.clear()

    assert codex_models.catalog() is None
    assert AGENT_CLIS["codex"].offered_models == AGENT_CLIS["codex"].models


def test_the_console_and_policy_offer_the_live_list(fake_codex):
    assert AGENT_CLIS["codex"].offered_models == (
        "gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.5",
    )


def test_a_retired_class_slug_renders_as_its_upgrade_in_the_codex_profile(
        fake_codex, tmp_path, monkeypatch):
    """
    Scenario: the vendor retires the model a class maps to and names its replacement.
    The next profile render must carry the replacement without the table being edited.
    """
    from thalamus.contract.manifest import load_manifest
    from thalamus.harness import pin

    monkeypatch.setitem(pin.CODEX_MODELS, "strong", "gpt-5.5")
    config = tmp_path / "config"
    (config / "experts").mkdir(parents=True)
    (config / "presets").mkdir()
    source = (REPO_CONFIG / "experts" / "literature.yaml").read_text()
    (config / "experts" / "literature.yaml").write_text(source + "\ncost: work\n")
    (config / "presets" / "cost.yaml").write_text("work:\n  model_class: strong\n")

    profile = tomllib.loads(pin.render_codex_profile(load_manifest("literature", config)))

    assert profile["model"] == "gpt-5.6-sol"
