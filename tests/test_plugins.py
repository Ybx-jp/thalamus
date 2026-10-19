"""
Plugin loading — the `thalamus` entry-point group, `register_commands`,
`claim_command`, `capability_rows` and `register_hooks`.

Interfaces: thalamus.plugins.load/Plugins.register_commands/claim_command/
capability_rows/hooks/Hook, cli._main's dispatch on `plugin_run`, the installed
plugins' registration
Infrastructure: fake entry points patched into `thalamus.plugins.entry_points`; the
real installed plugins for the end-to-end cases; no graph, no model
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


def test_a_plugin_adds_a_subcommand_under_a_core_command_group(monkeypatch):
    """`groups` is how `thalamus eval reflex` reaches core's `eval`; an implementation
    may take that argument alone."""
    def register(groups):
        groups["eval"].add_parser("hello").set_defaults(plugin_run=lambda args: "ran")

    _with_points(monkeypatch, _Point("hello", _plugin("hello", register)))
    parser, subparsers = _parser()
    eval_sub = subparsers.add_parser("eval").add_subparsers(dest="eval_command")

    loaded = plugins.load()
    loaded.register_commands(subparsers, groups={"eval": eval_sub})

    args = parser.parse_args(["eval", "hello"])
    assert args.plugin_run(args) == "ran"
    assert loaded.failures == []


def _hook_plugin(name, hooks):
    module = types.ModuleType(f"fake_{name}")
    module.register_hooks = plugins.hookimpl(lambda: hooks)
    return module


def _script(root, package="thalamus_fake", name="tap.sh"):
    path = root / package / "hooks" / "claude-code" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\n")
    return path


def test_a_plugin_hook_under_its_package_hooks_dir_is_accepted(monkeypatch, tmp_path):
    hook = plugins.Hook("claude", "PostToolUse", "Bash", _script(tmp_path))
    _with_points(monkeypatch, _Point("fake", _hook_plugin("fake", [hook])))

    loaded = plugins.load()

    assert loaded.hooks() == [hook]
    assert loaded.failures == []


@pytest.mark.parametrize("bad", ["elsewhere", "harness", "missing"])
def test_one_refused_hook_drops_every_hook_that_plugin_declared(
        monkeypatch, tmp_path, capsys, bad):
    """
    Scenario: a plugin declares two hooks and core refuses one — a script outside a
    `thalamus_*` package's `hooks/<harness>/` (uninstall could not prove it ours), a
    harness no plugin hook is wired on, or a script that is not there

    Neither of that plugin's hooks is wired, and a second plugin's still is.
    """
    good = plugins.Hook("claude", "PostToolUse", "Bash", _script(tmp_path))
    refused = {
        "elsewhere": plugins.Hook("claude", "PostToolUse", None,
                                  _script(tmp_path, package="vendor")),
        "harness": plugins.Hook("cursor", "postToolUse", None, _script(tmp_path)),
        "missing": plugins.Hook("claude", "PostToolUse", None,
                                tmp_path / "thalamus_fake" / "hooks" / "claude-code" / "no.sh"),
    }[bad]
    other = plugins.Hook("claude", "SessionEnd", None,
                         _script(tmp_path, package="thalamus_other"))
    _with_points(monkeypatch,
                 _Point("fake", _hook_plugin("fake", [good, refused])),
                 _Point("other", _hook_plugin("other", [other])))

    loaded = plugins.load()

    assert loaded.hooks() == [other]
    assert [(f.plugin, f.stage) for f in loaded.failures] == [
        ("fake", "register its hooks")]
    assert "plugin `fake` failed to register its hooks" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["reflex"], ["eval", "reflex"], ["eval", "vocabulary"]])
def test_the_reflex_plugin_adds_its_commands_to_the_installed_cli(argv):
    """End to end through the real entry-point table, including the two that land
    under core's `eval` group."""
    result = subprocess.run(
        [sys.executable, "-m", "thalamus", *argv, "--help"],
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert f"thalamus {' '.join(argv)}" in result.stdout
    assert "failed to" not in result.stderr


@pytest.mark.parametrize("argv", [
    ["eval", "report"], ["eval", "uses"], ["eval", "pins"], ["eval", "gremlin"],
    ["eval", "recipes"], ["eval", "profile"], ["eval", "withholding"], ["pulse"],
])
def test_the_measure_plugin_adds_its_commands_to_the_installed_cli(argv):
    """End to end through the real entry-point table: the eval loop's reports under
    core's `eval` group, and the dashboard as a command of its own."""
    result = subprocess.run(
        [sys.executable, "-m", "thalamus", *argv, "--help"],
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert f"thalamus {' '.join(argv)}" in result.stdout
    assert "failed to" not in result.stderr


def _module(name, **hooks):
    module = types.ModuleType(f"fake_{name}")
    for hook, fn in hooks.items():
        setattr(module, hook, plugins.hookimpl(fn))
    return module


def _pin_cli():
    parser = argparse.ArgumentParser(prog="thalamus")
    subparsers = parser.add_subparsers(dest="command")
    pin_parser = subparsers.add_parser("pin")
    pin_parser.add_argument("scope")
    return parser, subparsers, pin_parser


def test_a_plugin_option_on_a_core_command_is_run_by_the_plugin_that_added_it(monkeypatch):
    """`commands` is how `--room` reaches core's `pin`, and `claim_command` is how the
    console, not core, then runs a `pin` that names one."""
    ran = []

    def register(commands):
        commands["pin"].add_argument("--room", default=None)

    def claim(command, args):
        if command == "pin" and args.room:
            ran.append(args.room)
            return True
        return None

    _with_points(monkeypatch, _Point("rooms", _module(
        "rooms", register_commands=register, claim_command=claim)))
    parser, subparsers, pin_parser = _pin_cli()

    loaded = plugins.load()
    loaded.register_commands(subparsers, commands={"pin": pin_parser})

    assert loaded.claim_command("pin", parser.parse_args(["pin", "qe", "--room", "atlas"]))
    assert ran == ["atlas"]
    # Without the option, the plugin answers None and core runs its own `pin`.
    assert not loaded.claim_command("pin", parser.parse_args(["pin", "qe"]))
    assert loaded.failures == []


def test_a_plugin_whose_registration_failed_claims_nothing(monkeypatch, capsys):
    """Its option may be on core's parser and its handlers are not, so the command
    runs as core's rather than half as the plugin's."""
    def register(commands):
        commands["pin"].add_argument("--room", default=None)
        raise RuntimeError("after the option, before the rest")

    def claim(command, args):
        raise AssertionError("never called")

    _with_points(monkeypatch, _Point("rooms", _module(
        "rooms", register_commands=register, claim_command=claim)))
    parser, subparsers, pin_parser = _pin_cli()

    loaded = plugins.load()
    loaded.register_commands(subparsers, commands={"pin": pin_parser})

    assert not loaded.claim_command("pin", parser.parse_args(["pin", "qe", "--room", "atlas"]))
    assert [(f.plugin, f.stage) for f in loaded.failures] == [
        ("rooms", "register its commands")]


def test_capability_rows_come_from_every_plugin_and_a_broken_one_costs_only_its_own(
        monkeypatch, capsys):
    good = [("room.peer_identity on claude [provided]", "confirmed", "")]
    _with_points(
        monkeypatch,
        _Point("good", _module("good", capability_rows=lambda: good)),
        _Point("raises", _module("raises", capability_rows=lambda: 1 / 0)),
        _Point("shapeless", _module("shapeless", capability_rows=lambda: ["not a row"])),
    )

    loaded = plugins.load()

    assert loaded.capability_rows() == good
    assert [(f.plugin, f.stage) for f in loaded.failures] == [
        ("raises", "report its capability rows"),
        ("shapeless", "report its capability rows"),
    ]


@pytest.mark.parametrize("argv", [
    ["spawn"], ["room"], ["ceremony"], ["dispatch"], ["console"],
])
def test_the_console_plugin_adds_its_commands_to_the_installed_cli(argv):
    result = subprocess.run(
        [sys.executable, "-m", "thalamus", *argv, "--help"],
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert f"thalamus {' '.join(argv)}" in result.stdout
    assert "failed to" not in result.stderr


@pytest.mark.parametrize("argv,option", [(["pin"], "--room"), (["eval", "cost"], "--by-occasion")])
def test_the_console_plugin_adds_its_options_to_core_commands(argv, option):
    result = subprocess.run(
        [sys.executable, "-m", "thalamus", *argv, "--help"],
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert option in result.stdout
