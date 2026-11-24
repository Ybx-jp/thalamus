"""The handlers behind the commands `plugin.py` registers, one per command.

Each imports its report when it runs, so a `thalamus` invocation that runs none of them
pays only for the parsers.
"""

from __future__ import annotations

import sys

from thalamus.substrate.writer import close_connection, connect


def report(args) -> None:
    from thalamus_measure.report import scope_report

    graph = connect(args.url)
    try:
        print(
            scope_report(
                graph,
                scope=args.scope,
                top=args.top,
                since=args.since,
                until=args.until,
            ).render()
        )
    finally:
        close_connection(graph)


def uses(args) -> None:
    from thalamus_measure.uses import uses_report

    graph = connect(args.url)
    try:
        print(
            uses_report(
                graph,
                scope=args.scope,
                since=args.since,
                until=args.until,
            ).render()
        )
    finally:
        close_connection(graph)


def pins(args) -> None:
    from thalamus.contract.manifest import available_scopes
    from thalamus.eval.cost import load_engaged, load_pins
    from thalamus_measure.pins import pin_report

    graph = connect(args.url)
    try:
        result = pin_report(
            graph, load_pins(args.pins_file), available_scopes(),
            engaged=load_engaged(args.pins_file),
        )
    finally:
        close_connection(graph)
    print(result.render())


def gremlin(args) -> None:
    from thalamus_measure.gremlin import gremlin_report

    print(gremlin_report(traces_base=args.traces, guards_base=args.guards).render())


def recipes(args) -> None:
    from thalamus_measure.gremlin import (
        render_smoke,
        render_staged,
        smoke_recipes,
        staged_recipes,
    )

    if args.staged:
        print(render_staged(staged_recipes()))
        return
    results = smoke_recipes(args.url)
    print(render_smoke(results))
    if any(not r.ok for r in results):
        sys.exit(1)


def profile(args) -> None:
    from thalamus_measure.profile import (
        profile_corpus,
        profile_query,
        profile_report,
        render_corpus,
        render_query_profile,
    )

    if args.query:
        print(render_query_profile(profile_query(args.url, args.query, repeat=args.repeat)))
    elif args.corpus:
        print(render_corpus(profile_corpus(args.url, repeat=args.repeat)))
    else:
        print(profile_report(base=args.profiles, top=args.top).render(top=args.top))


def withholding(args) -> None:
    from thalamus_measure.withholding import recurrence_report

    graph = connect(args.url)
    try:
        print(recurrence_report(graph, scope=args.scope, draws=args.draws).render())
    finally:
        close_connection(graph)


def pulse(args) -> None:
    import uvicorn

    from thalamus_measure.pulse.web import create_pulse_app

    print(f"Thalamus Pulse: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    uvicorn.run(
        create_pulse_app(url=args.url),
        host=args.host,
        port=args.port,
        log_level="warning",
    )
