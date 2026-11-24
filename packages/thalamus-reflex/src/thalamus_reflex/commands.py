"""Handlers for the commands `plugin.py` registers.

Each imports what it runs inside the function: `plugin.py` imports this module on every
`thalamus` invocation, and only the command that ran should pay for the reflex.
"""

from __future__ import annotations

import sys


def reflex(args) -> None:
    """The hook's worker: everything it prints is injected, so it prints the digest or nothing."""
    from thalamus.substrate.writer import DEFAULT_URL, close_connection, connect
    from thalamus_reflex import reflex_worker
    from thalamus_reflex.reflex import fire, reflex_dir, shadow

    if getattr(args, "job_tools", None):
        from thalamus_reflex.reflex_channel import serve_tools

        serve_tools(args.job_tools)
        return
    if args.work:
        reflex_worker.work(
            reflex_dir(args.reflex_dir),
            connect_graph=lambda: connect(args.url),
            close_graph=close_connection,
        )
        return
    if args.sweep:
        counts = reflex_worker.sweep(reflex_dir(args.reflex_dir))
        print(", ".join(f"{count} {outcome}" for outcome, count in counts.items()))
        return
    if not args.session_id:
        print("reflex: --session-id is required", file=sys.stderr)
        sys.exit(2)
    if args.deliver:
        digest = reflex_worker.deliver(
            reflex_dir(args.reflex_dir), session_id=args.session_id, agent_id=args.agent_id,
            event=args.event,
        )
        if digest:
            print(digest)
        return
    if args.response_file is None:
        print("reflex: --response-file is required", file=sys.stderr)
        sys.exit(2)
    try:
        observed = args.response_file.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"reflex: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.shadow:
        shadow(session_id=args.session_id, observed=observed,
               agent_id=args.agent_id, event=args.event)
        return

    graph = connect(args.url)
    try:
        digest = fire(
            graph,
            session_id=args.session_id,
            observed=observed,
            scope=args.scope,
            agent_id=args.agent_id,
            agent_type=args.agent_type,
            cwd=args.cwd,
            tool_name=args.tool_name,
            event=args.event,
            transcript=args.transcript,
            tool_use_id=args.tool_use_id,
            worker_url=args.url if args.url != DEFAULT_URL else "",
        )
    finally:
        close_connection(graph)
    if digest:
        print(digest)


def eval_reflex(args) -> None:
    from thalamus.substrate.writer import GraphUnavailable, close_connection, connect
    from thalamus_reflex.report import reflex_report

    # The ledger half never needs the graph; the verdict half says so when it
    # cannot have it, rather than turning a report into a connection error.
    try:
        graph = connect(args.url)
    except GraphUnavailable:
        graph = None
    try:
        print(reflex_report(
            reflex_base=args.reflex, traces_base=args.traces, g=graph
        ).render())
    finally:
        if graph is not None:
            close_connection(graph)


def eval_vocabulary(args) -> None:
    from thalamus.contract.manifest import available_scopes
    from thalamus.substrate.writer import close_connection, connect
    from thalamus_reflex.vocabulary import anchor_sets, measure

    sets = anchor_sets(args.reflex, args.limit)
    graph = connect(args.url)
    try:
        knowledge = [s for s in available_scopes() if s != args.scope]
        print(measure(graph, sets, args.scope, knowledge).render())
    finally:
        close_connection(graph)
