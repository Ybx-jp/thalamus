"""
The CLI's top level: the parser it builds and the dispatch it does with the result.

Interfaces: thalamus.cli.main, thalamus.cli._main
Infrastructure: none — every `_cmd_*` handler is stubbed, and `parse_args` is either
                intercepted or replaced, so nothing here touches a graph or a process.
Scope: the wiring between `argparse` and the handlers, and nothing either side of it.
       What each handler *does* is covered in that handler's own file; this is the
       layer where a subcommand can be declared and never reached.

Every other CLI test in this suite calls a handler directly with a hand-built
`Namespace`, which is the right shape for testing a handler and leaves the parser and
the dispatch chain untested by construction (#232). A flag documented and never added,
a subcommand wired to the wrong handler, a changed default — none of it fails a test
there, because the parser is never built.

The dispatch chain is a long `if/elif` ending in `print_help(); sys.exit(1)`. So a
subcommand declared with `add_parser` and forgotten in the chain does not error at
import, does not error at parse, and fails only when a user runs it — the
built-but-never-used class, on the surface users actually type at.
"""

from __future__ import annotations

import argparse
import logging

import pytest

from thalamus import cli
from thalamus.substrate.writer import GraphUnavailable


class _ParserBuilt(Exception):
    """Carries the fully-built parser out of `_main` at the moment it would parse."""

    def __init__(self, parser: argparse.ArgumentParser):
        self.parser = parser


@pytest.fixture
def built_parser(monkeypatch) -> argparse.ArgumentParser:
    """The real parser, built by running the real `_main` up to `parse_args`.

    Interrupting at `parse_args` rather than re-declaring the parser here is the whole
    point: every `add_parser` and `add_argument` call in `_main` has run by then, so
    what comes back is what a user's command line is actually matched against. A copy
    maintained in this file would agree with itself and with nothing else.
    """
    def capture(self, *args, **kwargs):
        raise _ParserBuilt(self)

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", capture)
    with pytest.raises(_ParserBuilt) as built:
        cli._main()
    return built.value.parser


def _subcommands(parser: argparse.ArgumentParser) -> list[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return sorted(action.choices)
    raise AssertionError("the CLI declares no subcommands at all")


def _dispatch(monkeypatch, command: str | None) -> list[str]:
    """Run `_main`'s dispatch for `command`, returning the handlers it called.

    `parse_args` is replaced rather than intercepted, so the chain runs against a
    namespace naming the command and nothing else — which is all the chain reads.
    """
    namespace = argparse.Namespace(command=command, debug=False)
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args",
                        lambda self, *a, **k: namespace)

    called: list[str] = []
    for name in dir(cli):
        if name.startswith("_cmd_"):
            monkeypatch.setattr(
                cli, name, lambda *a, _name=name, **k: called.append(_name))

    cli._main()
    return called


def test_the_cli_declares_subcommands(built_parser):
    """The control for everything below.

    A parser that declared nothing would make "every declared subcommand dispatches"
    vacuously true, and this file would pass while the CLI had no commands at all.
    """
    commands = _subcommands(built_parser)

    assert len(commands) > 20, f"only {len(commands)} subcommand(s) found: {commands}"
    # Named rather than counted, so a rename that keeps the count is still caught.
    for staple in ("write", "extract", "ingest", "init", "arch", "contract", "eval"):
        assert staple in commands


def test_every_declared_subcommand_reaches_a_handler(built_parser, monkeypatch):
    """The property the `if/elif` chain exists to satisfy, over the parser's own list.

    Parametrizing over a hand-written list of commands would miss exactly the case
    worth catching — a command added to the parser and to no chain branch — because
    the hand-written list is the thing that would not be updated.
    """
    unreached = []
    for command in _subcommands(built_parser):
        try:
            called = _dispatch(monkeypatch, command)
        except SystemExit:
            unreached.append(f"{command}: fell through to print_help and exited")
            continue
        if len(called) != 1:
            unreached.append(f"{command}: called {called or 'no handler'}")

    assert not unreached, "subcommands the parser declares and the dispatch does not: " \
                          + "; ".join(unreached)


def test_each_subcommand_reaches_its_own_handler(built_parser, monkeypatch):
    """One handler per command is not enough on its own: two commands wired to the same
    handler satisfies it, and is how a copy-pasted `elif` branch goes wrong."""
    by_handler: dict[str, list[str]] = {}
    for command in _subcommands(built_parser):
        (handler,) = _dispatch(monkeypatch, command)
        by_handler.setdefault(handler, []).append(command)

    shared = {h: c for h, c in by_handler.items() if len(c) > 1}
    assert not shared, f"one handler serving several subcommands: {shared}"


def test_an_unknown_command_prints_help_and_exits_non_zero(monkeypatch, capsys):
    """The chain's `else`. It is also where a forgotten command lands, which is why the
    tests above read an exit here as a failure rather than as correct behaviour."""
    with pytest.raises(SystemExit) as exited:
        _dispatch(monkeypatch, "no-such-command")

    assert exited.value.code == 1
    assert "usage:" in capsys.readouterr().out


def test_no_command_at_all_prints_help_and_exits_non_zero(monkeypatch, capsys):
    """Bare `thalamus`. argparse leaves `command` None rather than erroring, so this
    reaches the same `else` and must not be mistaken for success by a shell."""
    with pytest.raises(SystemExit) as exited:
        _dispatch(monkeypatch, None)

    assert exited.value.code == 1
    assert "usage:" in capsys.readouterr().out


@pytest.mark.parametrize("debug,expected", [(True, logging.DEBUG), (False, logging.WARNING)])
def test_debug_sets_the_log_level_the_flag_promises(monkeypatch, debug, expected):
    """`--debug` is documented as logging Gremlin bytecode and server stack traces, and
    what makes that true is the level `basicConfig` is called with."""
    namespace = argparse.Namespace(command="schema", debug=debug)
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args",
                        lambda self, *a, **k: namespace)
    monkeypatch.setattr(cli, "_cmd_schema", lambda *a, **k: None)
    levels: list[int] = []
    monkeypatch.setattr(cli.logging, "basicConfig",
                        lambda **kwargs: levels.append(kwargs["level"]))

    cli._main()

    assert levels == [expected]


def test_a_graph_that_is_not_running_is_one_sentence_and_exit_one(monkeypatch, capsys):
    """`main` exists to wrap `_main` in this one translation.

    A stopped graph is the ordinary first-run state of a machine, and every command
    that reads memory hits it. Without the wrap the operator gets an aiohttp transport
    traceback, which names nothing they can act on.
    """
    monkeypatch.setattr(
        cli, "_main",
        lambda: (_ for _ in ()).throw(GraphUnavailable("start the graph: docker compose up -d")))

    with pytest.raises(SystemExit) as exited:
        cli.main()

    err = capsys.readouterr().err
    assert exited.value.code == 1
    assert err.strip() == "start the graph: docker compose up -d"
    assert "Traceback" not in err


def test_main_does_not_swallow_an_unrelated_failure(monkeypatch):
    """The control for the test above. A bare `except` there would turn every bug in
    every handler into the same one-line message about the graph being down."""
    monkeypatch.setattr(
        cli, "_main", lambda: (_ for _ in ()).throw(RuntimeError("something else")))

    with pytest.raises(RuntimeError, match="something else"):
        cli.main()
