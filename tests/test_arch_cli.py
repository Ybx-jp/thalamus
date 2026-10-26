"""
The arch tool's two command lines — `thalamus-arch`, and `thalamus arch` beside the core.

Interfaces: thalamus_arch.cli.add_commands/run/main, thalamus_arch.plugin
.register_commands, thalamus_arch.model.repo_root
Infrastructure: the installed workspace (both console scripts, the `thalamus`
entry-point group); a git repository built in tmp_path; no graph, no model
Scope: that both spellings offer the same subcommands from one builder, that the
plugin's marker is the one core's loader accepts, and where `--repo` defaults to
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from thalamus_arch import cli
from thalamus_arch.model import repo_root

SUBCOMMANDS = {"scan", "show", "diff", "rules", "dead", "refs"}


def _subcommands(parser: argparse.ArgumentParser) -> set[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def test_both_command_lines_offer_the_same_subcommands():
    """The standalone parser and the one the plugin hands core are built by one
    function, so a subcommand added to one is in the other."""
    from thalamus_arch import plugin

    standalone = argparse.ArgumentParser(prog="thalamus-arch")
    cli.add_commands(standalone)

    top = argparse.ArgumentParser(prog="thalamus")
    subparsers = top.add_subparsers(dest="command")
    plugin.register_commands(subparsers)

    assert _subcommands(standalone) == SUBCOMMANDS
    assert _subcommands(subparsers.choices["arch"]) == SUBCOMMANDS


def test_core_loads_the_plugin_with_its_own_marker_and_reports_no_failure():
    """`plugin.py` marks its hook with a pluggy marker it builds itself rather than
    core's `hookimpl`. pluggy matches by project name, so core's loader must accept it
    and register `arch`; a mismatch would load the module and register nothing."""
    from thalamus import plugins

    loaded = plugins.load()
    top = argparse.ArgumentParser(prog="thalamus")
    subparsers = top.add_subparsers(dest="command")
    loaded.register_commands(subparsers, groups={}, commands={})

    assert not [f for f in loaded.failures if f.plugin == "arch"], loaded.failures
    assert _subcommands(subparsers.choices["arch"]) == SUBCOMMANDS


@pytest.mark.parametrize("argv", [["thalamus-arch"], [sys.executable, "-m", "thalamus", "arch"]])
def test_each_installed_command_line_answers(argv):
    if argv[0] == "thalamus-arch":
        found = shutil.which("thalamus-arch", path=str(Path(sys.executable).parent))
        assert found, "the workspace installs the thalamus-arch script"
        argv = [found]
    result = subprocess.run([*argv, "rules", "--help"], capture_output=True, text=True,
                            timeout=60)

    assert result.returncode == 0, result.stderr
    assert "--gate" in result.stdout


def test_the_repo_defaults_to_the_top_of_the_git_repository(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "pkg" / "sub").mkdir(parents=True)

    assert repo_root(tmp_path / "pkg" / "sub") == tmp_path.resolve()


def test_outside_a_repository_the_repo_is_the_directory_itself(tmp_path, monkeypatch):
    """No enclosing repository: the directory is measured as given, and its missing
    model file reports an empty partition rather than borrowing another tree's."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

    assert repo_root(tmp_path) == tmp_path.resolve()
