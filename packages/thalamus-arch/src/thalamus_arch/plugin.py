"""`thalamus arch`: the same commands as `thalamus-arch`, when thalamus is installed.

Loaded only through thalamus's `thalamus` entry-point group, so it runs only in a
process that has thalamus and its pluggy. The marker is pluggy's own, built for that
group, rather than thalamus's `hookimpl`: pluggy matches an implementation to its hook
by project name, so the two are the same marker, and this package imports nothing of
thalamus.
"""

from __future__ import annotations

import functools

import pluggy

from thalamus_arch import cli

hookimpl = pluggy.HookimplMarker("thalamus")


@hookimpl
def register_commands(subparsers) -> None:
    parser = subparsers.add_parser(
        "arch", help="Measure a repo's import graph against its declared layers"
    )
    cli.add_commands(parser)

    @functools.wraps(cli.run)
    def run(args):
        return cli.run(args, parser)

    parser.set_defaults(plugin_run=run)
