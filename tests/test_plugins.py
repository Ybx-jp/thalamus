"""
Plugin loading — the `thalamus` entry-point group and the `register_commands` hook.

Interfaces: thalamus.plugins.load/Plugins.register_commands, cli._main's dispatch on
`plugin_run`, the thalamus-ingest plugin's registration
Infrastructure: fake entry points patched into `thalamus.plugins.entry_points`; the
real installed thalamus-ingest for the end-to-end case; no graph, no model
Scope: that an installed plugin's commands reach the CLI, and that a broken plugin
costs only its own commands. The second is the property every hook script relies on,
because SessionEnd distillation runs through the same `thalamus` entry point.
"""

import argparse
import subprocess
import sys
import types

import pytest

from thalamus import plugins


class _Point:
    """The two attributes of an `importlib.metadata.EntryPoint` that `load` reads."""

    def __init__(self, name, module=None, error=None):
        self.name = name
        self.value = f"fake_{name}"
        self._module = module
        self._error = error

    def load(self):
        if self._error is not None:
            raise self._error
        return self._module


def _plugin(name, register):
    module = types.ModuleType(f"fake_{name}")
    module.register_commands = plugins.hookimpl(register)
    return module


def _with_points(monkeypatch, *points):
    monkeypatch.setattr(plugins, "entry_points", lambda group: list(points))


def _parser():
    parser = argparse.ArgumentParser(prog="thalamus")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("extract")
    return parser, subparsers


def test_a_plugin_command_reaches_the_parser_with_its_handler(monkeypatch):
    def register(subparsers):
        hello = subparsers.add_parser("hello")
        hello.set_defaults(plugin_run=lambda args: "ran")

    _with_points(monkeypatch, _Point("hello", _plugin("hello", register)))
    parser, subparsers = _parser()

    loaded = plugins.load()
    loaded.register_commands(subparsers)

    args = parser.parse_args(["hello"])
    assert args.plugin_run(args) == "ran"
    assert loaded.failures == []


def test_a_plugin_that_fails_to_import_costs_only_itself(monkeypatch, capsys):
    """
    Scenario: one plugin's import raises; another plugin and the core are fine

    A broken install must not take `thalamus extract` down with it — that is the
    SessionEnd hook's path, and it runs unattended.
    """
    def register(subparsers):
        subparsers.add_parser("hello")

    _with_points(
        monkeypatch,
        _Point("broken", error=ImportError("No module named 'gone'")),
        _Point("hello", _plugin("hello", register)),
    )
    parser, subparsers = _parser()

    loaded = plugins.load()
    loaded.register_commands(subparsers)

    assert parser.parse_args(["extract"]).command == "extract"
    assert parser.parse_args(["hello"]).command == "hello"
    assert [(f.plugin, f.stage) for f in loaded.failures] == [
        ("broken", "load (fake_broken)")
    ]
    assert "plugin `broken` failed to load" in capsys.readouterr().err


def test_a_plugin_cannot_take_a_name_core_already_uses(monkeypatch, capsys):
    def register(subparsers):
        subparsers.add_parser("extract")

    _with_points(monkeypatch, _Point("squatter", _plugin("squatter", register)))
    parser, subparsers = _parser()

    loaded = plugins.load()
    loaded.register_commands(subparsers)

    assert [(f.plugin, f.stage) for f in loaded.failures] == [
        ("squatter", "register its commands")
    ]
    assert not hasattr(parser.parse_args(["extract"]), "plugin_run")
    assert "plugin `squatter` failed to register its commands" in capsys.readouterr().err


def test_a_hook_with_the_wrong_signature_is_refused_at_load(monkeypatch):
    """pluggy validates an implementation's argument names against the spec, so a
    plugin written against a different hook signature fails loudly at load rather
    than being called with arguments it does not take."""
    def register(parser):
        raise AssertionError("never called")

    _with_points(monkeypatch, _Point("stale", _plugin("stale", register)))

    loaded = plugins.load()

    assert [f.plugin for f in loaded.failures] == ["stale"]


@pytest.mark.parametrize("command", ["ingest", "backfill-chunks"])
def test_the_ingest_plugin_adds_its_commands_to_the_installed_cli(command):
    """End to end through the real entry-point table: the workspace installs
    thalamus-ingest, and `thalamus <command> --help` answers from it."""
    result = subprocess.run(
        [sys.executable, "-m", "thalamus", command, "--help"],
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert f"thalamus {command}" in result.stdout
    assert "failed to" not in result.stderr
