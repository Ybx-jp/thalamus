"""
Where the roster is read from, on both surfaces that read it.

Interfaces: contract/manifest.config_root and its bash mirror
thalamus_config_root in harness/hooks/claude-code/resolve-scope.sh.
Infrastructure: tmp_path as $HOME, with a manifest directory beneath it; no
live graph, no MCP server.
Scope: the override's *value*, not its precedence — precedence is covered in
test_claude_code_hooks.py. The two surfaces must resolve the same directory
from the same value, because a roster they disagree about is one the hooks
enforce boundaries from and the CLI cannot see.
"""

import subprocess
from pathlib import Path

from thalamus.contract import manifest

HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks" / "claude-code"


def bash(function, home, env=None):
    full_env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", "-c", f'. "{HOOKS}/resolve-scope.sh"; {function}'],
        capture_output=True, text=True, timeout=30, cwd=str(home), env=full_env,
    ).stdout.strip()


def roster_at(home):
    """A manifest directory at $HOME/notes, named `~/notes` by the override."""
    experts = home / "notes" / "experts"
    experts.mkdir(parents=True)
    (experts / "homelab.yaml").write_text("scope: homelab\n")
    return experts.parent


class TestATildeInTheOverrideIsExpanded:
    def test_python_resolves_it_against_home(self, tmp_path, monkeypatch):
        expected = roster_at(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("THALAMUS_CONFIG_DIR", "~/notes")

        assert manifest.config_root() == expected
        assert manifest.available_scopes() == ["homelab"]

    def test_bash_resolves_it_to_the_same_directory(self, tmp_path):
        expected = roster_at(tmp_path)
        env = {"THALAMUS_CONFIG_DIR": "~/notes"}

        assert bash("thalamus_config_root", tmp_path, env) == str(expected)
        assert bash("thalamus_roster", tmp_path, env) == "homelab"

    def test_an_absolute_override_is_untouched(self, tmp_path, monkeypatch):
        """The expansion anchors on a *leading* tilde and nothing else."""
        expected = roster_at(tmp_path)
        monkeypatch.setenv("THALAMUS_CONFIG_DIR", str(expected))

        assert manifest.config_root() == expected
        assert bash("thalamus_config_root", tmp_path, {"THALAMUS_CONFIG_DIR": str(expected)}) == str(expected)

    def test_without_the_override_both_surfaces_fall_back_to_the_checkout(self, tmp_path, monkeypatch):
        checkout = HOOKS.parents[4] / "config"
        monkeypatch.delenv("THALAMUS_CONFIG_DIR", raising=False)

        assert manifest.config_root() == checkout
        assert bash("thalamus_config_root", tmp_path) == str(checkout)
