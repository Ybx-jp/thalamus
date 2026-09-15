"""A firing must serve no more than `MAX_CANDIDATES` blocks — it serves more.

`harness/reflex.py` documents `MAX_CANDIDATES = 3` (`reflex.py:80`) as "how many
candidates it may serve"; the comment beside it calls the constant "the stopping rule
the design owes". `fire()` passes it straight through: `recall(..., limit=MAX_CANDIDATES,
...)` (`reflex.py:385`). But `limit` only bounds `substrate.reader.recall`'s mixed
session/knowledge window — chunk results are ranked in a window of their own, capped by
`_CHUNK_WINDOW_CAP = 2` (`reader.py:113`), and are prepended to `results` *before*
`_mixed_window` is ever consulted (`reader.py:757-768`). A firing whose anchors match
both a Session/Claim and a Chunk therefore renders up to `MAX_CANDIDATES +
_CHUNK_WINDOW_CAP` = 5 blocks against a documented cap of 3 — issue #251.

**Why this needs a real graph and cannot be hermetic.** The defect is in how `recall()`
composes two independently-capped windows over a live traversal, not in anything a
stubbed `recall` could show — a stub always answers however it is told to. This
mirrors `reflex_recall_scope_isolation.py`'s reasoning for the same substrate choice.

**Isolation, not the operator's data.** Two Chunk vertices (via `write_knowledge_checked`,
the same door `thalamus ingest` writes through) and three Session vertices (via
`write_session`, the same door `thalamus extract --write` uses) are written under one
scratch scope generated fresh per run (`qe-scratch-reflex-chunkcap-<uuid4 hex>`),
asserted to collide with neither `main` nor any real manifest scope, and every vertex
carrying that scope is dropped in a `finally` block whether the case passes, fails, or
raises. Never written under `main` or a real expert scope, and never left behind.

**The experiment.** Both the two chunks' `text` and all three sessions' `summary` carry
the same anchors `extract_anchors()` pulls from one nonce-bearing synthetic failure —
the identical query `reflex.fire()` will itself derive from that failure text — so a
real firing has something in both windows to match. `reflex.recall` is wrapped (not
replaced) to record what the real `substrate.reader.recall` returned, so the assertion
counts the same list `fire()` turns into blocks via `blocks = [r.format() for r in
results]` (`reflex.py`), without needing to re-split the rendered envelope's prose back
into blocks.

**Positive control.** The recalled node ids must cover both seeded chunks' vertex ids
*and* all three seeded sessions' vertex ids — without this, "5 blocks came back" could
not be told apart from "the fixture didn't match and something unrelated came back
instead", which would misreport a broken fixture as a confirmed defect.

**Confirmed as a real defect, not asserted.** Filed as issue #251, tagged `issue=251,
fixed=False`. Watched to reproduce before tagging: this case currently reports 5 blocks
served against `MAX_CANDIDATES=3` (2 chunks + 3 sessions), matching the issue's own
measurement (three of six live envelopes served 5 blocks). The assertion is written
against the `MAX_CANDIDATES` import, not the literal 3, so whichever of the issue's
three open repairs lands, this case flips to `fixed=True` with its control unchanged.

`qe` does not write `src/thalamus/harness/` or `src/thalamus/substrate/`, so no fix is
carried in this case — the repair (exclude chunks from the reflex's call, split
`MAX_CANDIDATES` across both windows, or raise the documented cap and re-price the
budget) is the operator's open decision on the issue.
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "tests/qe/cases/reflex_candidate_cap_overrun.py::run"


def _scratch_scope() -> str:
    return f"qe-scratch-reflex-chunkcap-{uuid.uuid4().hex[:10]}"


def run() -> Finding | None:
    from thalamus.contract.conformance import (  # noqa: PLC0415
        refuse_unless_conformant,
        write_knowledge_checked,
    )
    from thalamus.contract.manifest import available_scopes  # noqa: PLC0415
    from thalamus.contract.ontology import MAIN_SCOPE, vid  # noqa: PLC0415
    from thalamus.harness import reflex  # noqa: PLC0415
    from thalamus.harness.reflex import MAX_CANDIDATES, extract_anchors  # noqa: PLC0415
    from thalamus.substrate.schema import (  # noqa: PLC0415
        Chunk,
        KnowledgeBatch,
        LiteratureClaim,
        SessionGraph,
        Solution,
        Source,
        SourceKind,
        Tool,
    )
    from thalamus.substrate.writer import (  # noqa: PLC0415
        GraphUnavailable,
        close_connection,
        connect,
        write_session,
    )

    scope = _scratch_scope()
    real_scopes = set(available_scopes()) | {MAIN_SCOPE}
    if scope in real_scopes:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "the generated scratch scope collided with main or a real expert "
                "manifest scope; refusing to write or drop against it"
            ),
            witness=f"scope={scope!r} real={sorted(real_scopes)}",
            site=_SITE,
        )

    nonce = uuid.uuid4().hex[:10]
    failure_text = (
        f"FAILED tests/test_reflex_chunkcap_probe.py::test_widget_{nonce}\n"
        f"E       AssertionError: reflex_chunkcap_marker_{nonce} broke\n"
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
            site=_SITE,
        )
    query = " ".join(anchors)

    try:
        g = connect()
    except GraphUnavailable as exc:
        # Substrate.NEEDS_GRAPH only probes a bare TCP connect; a live gremlin
        # handshake can still fail past that. Not evidence about the defect, so
        # this is the check's own precondition failing, not a finding.
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "the graph answered the TCP probe but refused a real gremlin "
                "connection, so no fixture could be written or read"
            ),
            witness=str(exc),
            site=_SITE,
        )

    try:
        source = Source(
            content_hash=f"qe-chunkcap-{nonce}",
            kind=SourceKind.ARTICLE,
            title="qe reflex chunk-cap probe source",
            uri=f"archive://qe-chunkcap-{nonce}",
            origin=f"https://example.invalid/qe-chunkcap-probe-{nonce}",
        )
        chunk_specs = [
            Chunk(text=f"chunk probe passage zero: {query}", ordinal=0, start=0, end=64),
            Chunk(text=f"chunk probe passage one: {query}", ordinal=1, start=0, end=64),
        ]
        batch = KnowledgeBatch(
            scope=scope,
            source=source,
            claims=[
                LiteratureClaim(
                    description="qe chunk-cap probe placeholder claim, unrelated filler "
                    "text so check_knowledge's non-empty-claims rule is satisfied "
                    "without adding a third matching candidate"
                ),
            ],
            chunks=chunk_specs,
        )
        write_knowledge_checked(g, batch, manifest=None)

        session_ids = [f"qe-scratch-reflex-chunkcap-s{i}-{nonce}" for i in range(3)]
        for index, session_id in enumerate(session_ids):
            session = SessionGraph(
                session_id=session_id,
                tool=Tool.CLAUDE_CODE,
                summary=f"qe reflex chunk-cap probe session {index}: {query}",
                scope=scope,
                solutions=[
                    Solution(description=query, approach="fixture-only, no real approach"),
                ],
            )
            write_session(g, session, gate=refuse_unless_conformant)

        expected_chunk_vids = {
            vid("Chunk", chunk.local_id(source.content_hash), scope) for chunk in chunk_specs
        }
        expected_session_vids = {vid("Session", sid, scope) for sid in session_ids}

        original_recall = reflex.recall
        captured: list[list] = []

        def _counting_recall(*args, **kwargs):
            results = original_recall(*args, **kwargs)
            captured.append(results)
            return results

        reflex.recall = _counting_recall
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                reflex.fire(
                    g,
                    session_id=f"qe-chunkcap-probe-session-{nonce}",
                    observed=failure_text,
                    scope=scope,
                    agent_id="",
                    agent_type="",
                    cwd="/qe-chunkcap-probe",
                    now=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
                    reflex_base=tmp_path / "reflex",
                    traces_base=tmp_path / "traces",
                )
        finally:
            reflex.recall = original_recall

        results = captured[-1] if captured else []
        ids = {getattr(result, "node_id", "") for result in results}

        # CONTROL: both seeded windows must actually be reachable in the served
        # result, or "5 blocks came back" cannot be told apart from "the fixture
        # didn't match and something unrelated filled the window instead".
        if not (expected_chunk_vids <= ids and expected_session_vids <= ids):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    "positive control failed: the seeded chunks and/or sessions were "
                    "not both present in what reflex.fire()'s recall() call returned, "
                    "so the served block count below cannot be attributed to the "
                    "chunk-window/mixed-window composition this case targets"
                ),
                witness=(
                    f"expected_chunks={sorted(expected_chunk_vids)!r} "
                    f"expected_sessions={sorted(expected_session_vids)!r} "
                    f"got={sorted(ids)!r}"
                ),
                site=_SITE,
            )

        if len(results) <= MAX_CANDIDATES:
            return None

        return Finding(
            failure_class=FailureClass.DOC_CODE_DRIFT,
            summary=(
                f"reflex.fire() served {len(results)} blocks against a documented "
                f"MAX_CANDIDATES={MAX_CANDIDATES}: recall()'s chunk window "
                "(_CHUNK_WINDOW_CAP) is prepended ahead of the mixed session/"
                "knowledge window before `limit` is ever consulted, so the two "
                "windows' caps sum instead of sharing one ceiling"
            ),
            witness=f"blocks_served={len(results)} node_ids={sorted(ids)!r}",
            site="src/thalamus/harness/reflex.py::fire",
        )
    finally:
        g.V().has("scope", scope).drop().iterate()
        close_connection(g)


CASE = Case(
    name="reflex-candidate-cap-overrun-with-matching-chunks",
    tier=Tier.DEEP,
    substrate=(Substrate.NEEDS_GRAPH,),
    classes=(FailureClass.DOC_CODE_DRIFT, FailureClass.COLLAPSED_SENTINEL),
    summary="a firing whose anchors match both chunks and sessions serves more than MAX_CANDIDATES",
    run=run,
    issue=251,
    fixed=False,
)
