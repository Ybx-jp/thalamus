"""`recall`'s `.has("scope", scope)` filter must not leak a fixture across scopes.

`reflex.fire` retrieves through `substrate.reader.recall(g, query, scope=scope, ...)`
(`harness/reflex.py:376`), and the whole trust model behind an unsolicited injection
rests on that call being scoped: a session pinned to one expert must never be served
another scope's episodic memory just because the words happen to match
(`reader.py`'s own module docstring — "the server, not the model, decides what a scope
can see"). `tests/test_reflex.py` covers `fire`'s call shape with a stubbed `recall` and
says so explicitly in its own header: "the graph-backed half (a known anchor set returns
the expected ids and nothing from another scope) is a qe case, since `main` cannot write
`tests/qe/`." This is that case.

**Why this needs a real graph and cannot be hermetic.** The property under test is three
lines of Gremlin — `g.V().has_label("Session").has("scope", scope)...` and the matching
`Claim` filter (`reader.py:677,692`) — actually filtering on a live traversal source. A
stub of `recall` (what every other reflex case in this tree uses) always answers however
it is told to, so it cannot show the filter itself holds; only a real `g.V()` walk can.

**Isolation, not the operator's data.** This writes two `SessionGraph` fixtures through
the house write path (`substrate.writer.write_session` — the same call `thalamus
extract --write` makes, never an ad-hoc `addV`) under two scopes generated fresh on
every run (`qe-scratch-reflex-<label>-<uuid4 hex>`), asserts the scope names collide
with neither `main` nor any real manifest in `available_scopes()`, and drops every
vertex carrying either scope in a `finally` block whether the case passes, fails, or
raises. Never written under `main` or a real expert scope, and never left behind.

**The experiment.** Both fixtures carry byte-identical claim text — the same nonce-
bearing anchors in both — so a leak has something to leak: if the scope filter were
removed, scope A's recall would return scope B's node too, not merely "one result
either way". The nonce (fresh per run) keeps the fixture from ever colliding with real
content already in the graph, since only a vertex actually stamped with the generated
scope can carry it.

**Positive control.** Scope B's own recall, on the identical query, must return scope
B's own fixture. Without this, "scope A did not see B" cannot be told apart from
"nothing here is reachable by this query at all" — a query that matches nothing anywhere
would pass the isolation check for the wrong reason.

**Shown capable of going red.** Comment out the `.has("scope", scope)` clause in
`recall`'s session branch (`reader.py:677`) and rerun against a live graph: scope A's
recall then also returns scope B's node id, and this case reports `BOUNDARY_LEAK` naming
both ids. `qe` does not write `src/thalamus/substrate/`, so the mutation is not carried
in the case.
"""

from __future__ import annotations

import uuid

from ..model import Case, FailureClass, Finding, Substrate, Tier


def _scratch_scope(label: str) -> str:
    return f"qe-scratch-reflex-{label}-{uuid.uuid4().hex[:10]}"


def run() -> Finding | None:
    from thalamus.contract.manifest import available_scopes  # noqa: PLC0415
    from thalamus.contract.ontology import MAIN_SCOPE, vid  # noqa: PLC0415
    from thalamus.harness.reflex import extract_anchors  # noqa: PLC0415
    from thalamus.substrate.reader import recall  # noqa: PLC0415
    from thalamus.substrate.schema import SessionGraph, Solution, Tool  # noqa: PLC0415
    from thalamus.substrate.writer import (  # noqa: PLC0415
        GraphUnavailable,
        close_connection,
        connect,
    )

    scope_a = _scratch_scope("a")
    scope_b = _scratch_scope("b")
    real_scopes = set(available_scopes()) | {MAIN_SCOPE}

    # Never main, never a real expert scope. Freshly generated per run, but asserted
    # rather than merely assumed — a collision here would mean this case's cleanup
    # drops vertices it does not own.
    if {scope_a, scope_b} & real_scopes:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "the generated scratch scope collided with main or a real expert "
                "manifest scope; refusing to write or drop against it"
            ),
            witness=f"scope_a={scope_a!r} scope_b={scope_b!r} real={sorted(real_scopes)}",
            site="tests/qe/cases/reflex_recall_scope_isolation.py::run",
        )

    nonce = uuid.uuid4().hex[:10]
    failure_text = (
        f"FAILED tests/test_reflex_scratch_probe.py::test_widget_{nonce}\n"
        f"E       AssertionError: reflex_scratch_marker_{nonce} broke\n"
    )
    anchors = extract_anchors(failure_text)
    if len(anchors) < 2:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "the synthetic failure text yielded fewer than 2 anchors, so no "
                "query strong enough to clear recall's own match floor is available"
            ),
            witness=f"anchors={anchors!r}",
            site="tests/qe/cases/reflex_recall_scope_isolation.py::run",
        )
    query = " ".join(anchors)

    try:
        g = connect()
    except GraphUnavailable as exc:
        # Substrate.NEEDS_GRAPH only probes a bare TCP connect; a live gremlin
        # handshake can still fail past that. Not evidence about recall's own
        # filter, so this is the check's own precondition failing, not a finding.
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "the graph answered the TCP probe but refused a real gremlin "
                "connection, so no fixture could be written or read"
            ),
            witness=str(exc),
            site="tests/qe/cases/reflex_recall_scope_isolation.py::run",
        )

    try:
        session_a = SessionGraph(
            session_id=f"qe-scratch-reflex-a-{nonce}",
            tool=Tool.CLAUDE_CODE,
            summary="qe reflex graph isolation fixture, scope A",
            scope=scope_a,
            solutions=[Solution(description=query, approach="fixture-only, no real approach")],
        )
        session_b = SessionGraph(
            session_id=f"qe-scratch-reflex-b-{nonce}",
            tool=Tool.CLAUDE_CODE,
            summary="qe reflex graph isolation fixture, scope B",
            scope=scope_b,
            # Byte-identical claim text to scope A's — a leak needs something to leak.
            solutions=[Solution(description=query, approach="fixture-only, no real approach")],
        )
        from thalamus.substrate.writer import write_session  # noqa: PLC0415

        write_session(g, session_a)
        write_session(g, session_b)

        vid_a = vid("Session", session_a.session_id, scope_a)
        vid_b = vid("Session", session_b.session_id, scope_b)

        results_b = recall(g, query, limit=5, scope=scope_b, knowledge_scopes=[])
        ids_b = [r.node_id for r in results_b]

        # CONTROL: scope B's own recall, on the identical query, must return scope
        # B's own fixture — otherwise "A did not see B" is indistinguishable from
        # "nothing here is reachable by this query at all".
        if vid_b not in ids_b:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    "positive control failed: scope B's own fixture, containing "
                    "the identical anchor text, was not recalled under its own "
                    "scope, so isolation cannot be told apart from a query that "
                    "matches nothing at all"
                ),
                witness=f"scope_b recall ids={ids_b!r} expected {vid_b!r} among them",
                site="tests/qe/cases/reflex_recall_scope_isolation.py::run",
            )

        results_a = recall(g, query, limit=5, scope=scope_a, knowledge_scopes=[])
        ids_a = [r.node_id for r in results_a]

        if ids_a == [vid_a]:
            return None

        if vid_b in ids_a:
            return Finding(
                failure_class=FailureClass.BOUNDARY_LEAK,
                summary=(
                    "recall(scope=A) returned scope B's fixture node: the "
                    "`.has(\"scope\", scope)` filter did not exclude a session "
                    "written under a different scope, even though its content is "
                    "byte-identical to the one that legitimately matched"
                ),
                witness=f"scope_a recall ids={ids_a!r} scope_a={scope_a!r} scope_b={scope_b!r}",
                site="src/thalamus/substrate/reader.py::recall",
            )

        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "scope A's own fixture was not the single result recall(scope=A) "
                "returned for its own anchors, so 'no leak' cannot be read off "
                "this run either way"
            ),
            witness=f"scope_a recall ids={ids_a!r} expected exactly {vid_a!r}",
            site="tests/qe/cases/reflex_recall_scope_isolation.py::run",
        )
    finally:
        for scope in (scope_a, scope_b):
            g.V().has("scope", scope).drop().iterate()
        close_connection(g)


CASE = Case(
    name="reflex-recall-scope-filter-holds-on-a-live-graph",
    tier=Tier.DEEP,
    substrate=(Substrate.NEEDS_GRAPH,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="recall()'s scope filter must not serve one scratch scope's fixture under another",
    run=run,
)
