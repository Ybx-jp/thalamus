"""How a separately installed package adds to thalamus.

A plugin is a distribution that declares a module under the `thalamus` entry-point
group, and that module implements hooks from `Spec` with the `hookimpl` marker:

    [project.entry-points.thalamus]
    ingest = "thalamus_ingest.plugin"

The machinery is pluggy's, which is what pytest, `llm` and Datasette load their
plugins with; `llm`'s `register_commands(cli)` is the shape `register_commands` copies.
A plugin depends on `thalamus-memory` and never on another plugin.

A plugin that fails to load costs only its own surfaces. Every hook script and the
SessionEnd distillation run through the same `thalamus` entry point, so one broken
install must not take the core commands down with it: each entry point is loaded, and
each implementation called, on its own, and a failure is reported on stderr and
skipped.

Stdlib and pluggy only, because every `thalamus` invocation imports this module.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib.metadata import entry_points

import pluggy

GROUP = "thalamus"

hookspec = pluggy.HookspecMarker(GROUP)
hookimpl = pluggy.HookimplMarker(GROUP)


class Spec:
    """The extension points core offers. Each is added when a plugin needs it."""

    @hookspec
    def register_commands(self, subparsers) -> None:
        """Add subcommands to the `thalamus` CLI.

        `subparsers` is the object `argparse.ArgumentParser.add_subparsers` returned.
        A command names its handler with `set_defaults(plugin_run=fn)`, and `fn` is
        called with the parsed arguments. A name core already uses is refused by
        argparse, and the refusal is reported as this plugin's failure.
        """


@dataclass(frozen=True)
class Failure:
    plugin: str
    stage: str
    error: str

    def report(self) -> str:
        return f"thalamus: plugin `{self.plugin}` failed to {self.stage}: {self.error}"


class Plugins:
    """The loaded plugins, and what went wrong loading the rest."""

    def __init__(self, manager: pluggy.PluginManager, failures: list[Failure]):
        self.manager = manager
        self.failures = failures

    def register_commands(self, subparsers) -> None:
        for impl in self.manager.hook.register_commands.get_hookimpls():
            try:
                impl.function(subparsers=subparsers)
            except Exception as e:
                self._fail(impl.plugin_name, "register its commands", e)

    def _fail(self, plugin: str, stage: str, error: Exception) -> None:
        failure = Failure(plugin, stage, f"{type(error).__name__}: {error}")
        self.failures.append(failure)
        print(failure.report(), file=sys.stderr)


def load(group: str = GROUP) -> Plugins:
    """Load every plugin installed under `group`.

    Each entry point is loaded on its own, so one that raises is reported and skipped
    and the rest still load. (A0233, cites-as-live)
    """
    manager = pluggy.PluginManager(GROUP)
    manager.add_hookspecs(Spec)
    plugins = Plugins(manager, [])
    for point in entry_points(group=group):
        if manager.has_plugin(point.name):
            continue
        try:
            manager.register(point.load(), name=point.name)
        except Exception as e:
            plugins._fail(point.name, f"load ({point.value})", e)
    return plugins
