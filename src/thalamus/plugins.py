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

import re
import sys
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path

import pluggy

GROUP = "thalamus"

hookspec = pluggy.HookspecMarker(GROUP)
hookimpl = pluggy.HookimplMarker(GROUP)

# The harnesses a plugin may wire a hook script on. Claude Code's alone, because the
# reflex is the only plugin with hooks and it runs nowhere else; a harness joins when a
# plugin's script for it does.
HOOK_HARNESSES = ("claude",)

PLUGIN_HOOK_PATH = re.compile(r"/thalamus_[a-z0-9_]+/hooks/[^/]+/[^/]+$")
# Where a plugin's hook script must sit: `<its top-level package>/hooks/<harness>/`,
# under a package named `thalamus_*`. `thalamus init --uninstall` recognises the hooks
# a plugin added by this path alone, so it can remove them after the plugin itself is
# gone, and a script anywhere else is refused here rather than wired where uninstall
# cannot prove it ours. (A0234, cites-as-live)


@dataclass(frozen=True)
class Hook:
    """One hook script wiring: run `script` on `event`, for tools matching `matcher`.

    `matcher` None matches every tool, as in core's own wiring table. `harness` names
    the editor, in `HOOK_HARNESSES`.

    The script finds core's shell library through the path `thalamus init` records in
    `~/.thalamus/hook-library` (`install.HOOK_LIBRARY_RECORD`): sourcing
    `<that>/claude-code/resolve-scope.sh` gives it the same helpers core's own hooks
    use, and the library resolves the CLI and the checkout from its own location.
    """

    harness: str
    event: str
    matcher: str | None
    script: Path

    def refusal(self) -> str:
        """Why core will not wire this, or "" when it will."""
        if self.harness not in HOOK_HARNESSES:
            return f"no plugin hooks are wired on `{self.harness}`"
        if not self.script.is_absolute() or not PLUGIN_HOOK_PATH.search(str(self.script)):
            return (f"{self.script} is not under a `thalamus_*` package's "
                    "`hooks/<harness>/` directory")
        if not self.script.is_file():
            return f"{self.script} does not exist"
        return ""


class Spec:
    """The extension points core offers. Each is added when a plugin needs it."""

    @hookspec
    def register_commands(self, subparsers, groups) -> None:
        """Add subcommands to the `thalamus` CLI.

        `subparsers` is the object `argparse.ArgumentParser.add_subparsers` returned.
        `groups` maps a core command that has subcommands of its own — `eval` — to its
        subparsers object, so a plugin can add `thalamus eval <name>`. An
        implementation may take either argument alone.

        A command names its handler with `set_defaults(plugin_run=fn)`, and `fn` is
        called with the parsed arguments. A name core already uses is refused by
        argparse, and the refusal is reported as this plugin's failure.
        """

    @hookspec
    def register_hooks(self):
        """The hook scripts `thalamus init` wires for this plugin, as a list of `Hook`.

        Wired, verified by `thalamus init --check`, and removed by `--uninstall` beside
        core's own. A plugin any of whose hooks core refuses has none of them wired:
        half a plugin's wiring is a state its scripts were not written for.
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
        self._hooks: list[Hook] | None = None

    def register_commands(self, subparsers, groups=None) -> None:
        offered = {"subparsers": subparsers, "groups": dict(groups or {})}
        for impl in self.manager.hook.register_commands.get_hookimpls():
            try:
                impl.function(**{name: offered[name] for name in impl.argnames})
            except Exception as e:
                self._fail(impl.plugin_name, "register its commands", e)

    def hooks(self) -> list[Hook]:
        """Every plugin's hook wirings that core accepts, in load order.

        Asked once and kept: `thalamus init` reads them to write, to count and to verify,
        and a refusal is reported once."""
        if self._hooks is not None:
            return list(self._hooks)
        accepted: list[Hook] = []
        for impl in self.manager.hook.register_hooks.get_hookimpls():
            try:
                returned = impl.function()
                if not (isinstance(returned, (list, tuple))
                        and all(isinstance(hook, Hook) for hook in returned)):
                    raise TypeError("register_hooks must return a list of plugins.Hook")
                declared: list[Hook] = list(returned)
                refusals = [f"{hook.event} {hook.script.name}: {reason}"
                            for hook in declared if (reason := hook.refusal())]
                if refusals:
                    raise ValueError("; ".join(refusals))
            except Exception as e:
                self._fail(impl.plugin_name, "register its hooks", e)
                continue
            accepted.extend(declared)
        self._hooks = accepted
        return list(accepted)

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


_loaded: Plugins | None = None


def loaded() -> Plugins:
    """This process's plugins, loaded once: the CLI and `thalamus init` both read them,
    and a load failure is reported once rather than once per reader."""
    global _loaded
    if _loaded is None:
        _loaded = load()
    return _loaded
