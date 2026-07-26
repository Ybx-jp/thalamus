"""
Pinned-session launcher tests: the derived agent definition and scope validation.

Interfaces: thalamus.harness.pin
Infrastructure: tmp_path manifests only — no tmux, no claude, no graph
Scope: the pure half of the launcher. Actually launching a pinned process is
verified live (docs/07, lab/003) — a launcher can only be tested by the process
it launches, which is exactly the lab/001 boundary.
"""

from pathlib import Path

import pytest

from thalamus.contract.manifest import available_scopes, load_manifest
from thalamus.harness.pin import (
    agent_name,
    render_agent,
    resolve,
    resolve_pin,
    spawn,
    write_agent,
    write_all_agents,
)

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config"


def test_agent_definition_is_derived_from_the_manifest():
    """
    Scenario: Render the pinned-agent definition for a live manifest

    Verifications:
    - frontmatter name/description and the body all come from manifest fields
    - the file declares itself GENERATED, pointing back at the manifest
    - the body states server-side enforcement and consultation routing

    Zero-glue: the manifest is the whole federation surface; the agent file is a
    derived artifact and must never carry hand-written persona to drift.
    """
    manifest = load_manifest("literature", REPO_CONFIG)

    rendered = render_agent(manifest)

    assert f"name: {agent_name('literature')}" in rendered
    assert "GENERATED from config/experts/literature.yaml" in rendered
    assert manifest.name in rendered
    assert "enforced server-side" in rendered
    assert "consult_request" in rendered


def test_write_agent_lands_in_the_projects_agents_dir(tmp_path):
    manifest = load_manifest("eval-methodology", REPO_CONFIG)

    path = write_agent(manifest, tmp_path)

    assert path == tmp_path / ".claude" / "agents" / "thalamus-eval-methodology.md"
    assert path.read_text() == render_agent(manifest)


def test_write_all_agents_writes_every_expert_into_the_dir(tmp_path):
    """
    Scenario: `spawn` regenerates all derived agents into ~/.claude/agents so a
    session opened in another project can --agent-pin AND spawn sibling consultation
    subagents — both are loaded per process from the agents dir, wherever cwd is.
    """
    write_all_agents(tmp_path, REPO_CONFIG)

    for scope in available_scopes(REPO_CONFIG):
        f = tmp_path / f"{agent_name(scope)}.md"
        assert f.exists()
        assert f"scope `{scope}`" in f.read_text()


def test_spawn_rejects_a_nonexistent_directory(tmp_path, monkeypatch):
    """spawn's cwd becomes the window's working dir — a bad path must fail loudly
    before any tmux window is created, not silently open somewhere wrong."""
    monkeypatch.setattr("thalamus.harness.pin.shutil.which", lambda _: "/usr/bin/tmux")

    with pytest.raises(ValueError, match="not a directory"):
        spawn("homelab", tmp_path / "does-not-exist", base=REPO_CONFIG)


def test_main_is_pinnable_without_a_manifest_and_unknown_scopes_are_not():
    """
    Scenario: Pin `main` (no manifest by design) and a scope nobody declared

    An unknown scope must fail with the available roster named — the same failure
    shape as every other manifest consumer.
    """
    assert resolve("main", REPO_CONFIG) is None

    with pytest.raises(FileNotFoundError, match="Available:.*literature"):
        resolve("nonexistent-expert", REPO_CONFIG)


def test_resolve_pin_prefers_the_picked_agent_over_the_env_scope():
    """
    Scenario: The agent picker launched `claude --agent thalamus-homelab` from a
    shell whose env still said THALAMUS_SCOPE=main (measured 2026-07-18: all
    three roster expert sessions were mis-armed exactly this way)

    The picked agent is operator intent and must win; the env is residue.
    """
    env = {"CLAUDE_CODE_AGENT": "thalamus-homelab", "THALAMUS_SCOPE": "main"}

    assert resolve_pin(env, REPO_CONFIG) == "homelab"


def test_resolve_pin_falls_back_to_env_then_main():
    """
    Scenario: No agent picked (roster main window / plain terminal), or the
    agent name doesn't map to a real manifest (never widen a pin on a typo)
    """
    assert resolve_pin({"THALAMUS_SCOPE": "literature"}, REPO_CONFIG) == "literature"
    assert resolve_pin({}, REPO_CONFIG) == "main"
    assert resolve_pin(
        {"CLAUDE_CODE_AGENT": "thalamus-nonexistent", "THALAMUS_SCOPE": "main"},
        REPO_CONFIG,
    ) == "main"
    # non-thalamus agents (e.g. Explore) never touch the pin
    assert resolve_pin(
        {"CLAUDE_CODE_AGENT": "Explore", "THALAMUS_SCOPE": "eval-methodology"},
        REPO_CONFIG,
    ) == "eval-methodology"
