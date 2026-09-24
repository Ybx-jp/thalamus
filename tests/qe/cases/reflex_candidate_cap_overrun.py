"""A firing whose anchors match both chunks and sessions must still keep the digest
the agent receives under `DIGEST_CHAR_CAP` — regression guard for issue #251.

`harness/reflex.py` used to document `MAX_CANDIDATES = 3` as "how many candidates it
may serve" and pass it straight through as `recall(..., limit=MAX_CANDIDATES, ...)`.
`limit` only ever bounded `substrate.reader.recall`'s mixed session/knowledge window —
chunk results are ranked in a window of their own, capped by `_CHUNK_WINDOW_CAP = 2`,
and prepended to `results` *before* `_mixed_window` is consulted. A firing whose
anchors matched both a Session/Claim and a Chunk therefore rendered up to
`MAX_CANDIDATES + _CHUNK_WINDOW_CAP` = 5 blocks against a documented cap of 3, and
three of six live envelopes measured for the issue served exactly that.

**Settled 2026-09-23 (issue #251's own "Open decision", architect `17fd7b29a8a344d4`):
none of the three repairs the issue floated.** Selected candidates go to a pointer
file and only a size-capped digest enters context (#258's delivery layer), so the
per-firing bound is now a character cap on the digest — `DIGEST_CHAR_CAP` — rather
than a block count, and the chunk tier stays in the candidate set: `recall()` still
returns up to `MAX_CANDIDATES + _CHUNK_WINDOW_CAP` results, `fire()` still writes all
of them to the pointer file, and only how much of their index the digest can afford is
now bounded. This case now asserts that settled invariant directly: however many
candidates a firing selects, the digest that reaches the agent's context stays under
`DIGEST_CHAR_CAP` — and so well under Claude Code's 10,000-char spill line (#258) —
while every selected candidate is still written to the pointer file, none dropped to
make the digest fit.

**Why this needs a real graph and cannot be hermetic.** The defect this guards against
is in how `recall()` composes two independently-capped windows over a live traversal,
not in anything a stubbed `recall` could show — a stub always answers however it is
told to. This mirrors `reflex_recall_scope_isolation.py`'s reasoning for the same
substrate choice.

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
replaced) to record what the real `substrate.reader.recall` returned, so the controls
below reason about the same list `fire()` turned into digest lines and pointer-file
records, without needing to re-split the rendered digest's prose back into anything.

**Positive control 1.** The recalled node ids must cover both seeded chunks' vertex ids
*and* all three seeded sessions' vertex ids — without this, whatever the digest's
length turns out to be could not be told apart from "the fixture didn't match and
something unrelated came back instead", which would misreport a broken fixture as a
confirmed invariant.

**Positive control 2.** The firing must actually have selected more than
`MAX_CANDIDATES` raw candidates (the 2 chunks + 3 sessions this fixture seeds). Without
this, a green digest-length assertion would be uninterpretable: the overrun scenario
issue #251 was filed against might simply not have reproduced, and a digest built from
3 or fewer short records stays under the cap for a reason that has nothing to do with
the invariant this case exists to guard.

**Regression guard, not an open defect.** Tagged `issue=251, fixed=True`. Before this
delivery-layer change, this case reported `blocks_served=5` against a documented cap of
3 (`FailureClass.DOC_CODE_DRIFT`); with the digest in place, the two extra candidates
still arrive — Positive control 2 shows that — but bounded in the digest by character
count rather than excluded from selection, matching the settled decision that the
chunk tier stays in the candidate set.

`qe` does not write `src/thalamus/harness/` or `src/thalamus/substrate/`, so no fix is
carried in this case even now: if this guard goes red, the operator's open decision is
which of `fire()`, `pack_digest`, or `DIGEST_CHAR_CAP` regressed.
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
    from thalamus.harness.reflex import (  # noqa: PLC0415
        DIGEST_CHAR_CAP,
        MAX_CANDIDATES,
        extract_anchors,
        pointers_dir,
    )
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
        probe_session_id = f"qe-chunkcap-probe-session-{nonce}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                digest = reflex.fire(
                    g,
                    session_id=probe_session_id,
                    observed=failure_text,
                    scope=scope,
                    agent_id="",
                    agent_type="",
                    cwd="/qe-chunkcap-probe",
                    now=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
                    reflex_base=tmp_path / "reflex",
                    traces_base=tmp_path / "traces",
                )
                records = ""
                pdir = pointers_dir(probe_session_id, tmp_path / "reflex")
                pointer_files = sorted(pdir.glob("R*.md")) if pdir.is_dir() else []
                if pointer_files:
                    records = pointer_files[0].read_text(encoding="utf-8")
        finally:
            reflex.recall = original_recall

        results = captured[-1] if captured else []
        ids = {getattr(result, "node_id", "") for result in results}

        # POSITIVE CONTROL 1: both seeded windows must actually be reachable in what
        # recall() returned, or nothing below can be attributed to the chunk-window/
        # mixed-window composition this case targets.
        if not (expected_chunk_vids <= ids and expected_session_vids <= ids):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    "positive control failed: the seeded chunks and/or sessions were "
                    "not both present in what reflex.fire()'s recall() call returned, "
                    "so nothing below can be attributed to the chunk-window/mixed-"
                    "window composition this case targets"
                ),
                witness=(
                    f"expected_chunks={sorted(expected_chunk_vids)!r} "
                    f"expected_sessions={sorted(expected_session_vids)!r} "
                    f"got={sorted(ids)!r}"
                ),
                site=_SITE,
            )

        # POSITIVE CONTROL 2: the fixture must actually overrun MAX_CANDIDATES (5
        # candidates: 2 chunks + 3 sessions), or a digest that fits the cap proves
        # nothing about the invariant #251 settled on — it could simply be short
        # because too few candidates were selected in the first place.
        if len(results) <= MAX_CANDIDATES:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    "positive control failed: the fixture did not reproduce the "
                    "multi-window overrun (chunks + sessions both matching) that "
                    "issue #251 was filed against, so a digest under DIGEST_CHAR_CAP "
                    "below would not demonstrate the settled invariant — it could "
                    "just as well be short because too few candidates were selected"
                ),
                witness=f"candidates_selected={len(results)} MAX_CANDIDATES={MAX_CANDIDATES}",
                site=_SITE,
            )

        if digest == "":
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    "a firing that selected more than MAX_CANDIDATES matching "
                    "candidates was refused outright rather than served as a "
                    "size-capped digest — the delivery layer should always be able "
                    "to fit at least a short index of the strongest record under "
                    "DIGEST_CHAR_CAP"
                ),
                witness=f"candidates_selected={len(results)} digest={digest!r}",
                site="src/thalamus/harness/reflex.py::fire",
            )

        if len(digest) > DIGEST_CHAR_CAP:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    "reflex.fire() served a digest over DIGEST_CHAR_CAP for a firing "
                    "whose recall() call returned more than MAX_CANDIDATES results "
                    "(2 chunks + 3 sessions): the settled repair for #251 bounds the "
                    "digest by character count regardless of how many candidates a "
                    "firing selects, and this firing's digest crossed that bound"
                ),
                witness=(
                    f"digest_len={len(digest)} DIGEST_CHAR_CAP={DIGEST_CHAR_CAP} "
                    f"candidates_selected={len(results)}"
                ),
                site="src/thalamus/harness/reflex.py::fire",
            )

        # Regression guard on the other half of the settled repair: the chunk tier
        # stays IN the candidate set (nothing is excluded to make the digest fit) —
        # every selected candidate's record must still be in the pointer file.
        missing_from_pointer = [
            node_id for node_id in ids if node_id and f"`{node_id}`" not in records
        ]
        if missing_from_pointer:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    "a candidate reflex.fire() selected is missing from the pointer "
                    "file: the settled repair for #251 keeps every selected "
                    "candidate's record in the pointer file and bounds only the "
                    "digest, never dropping a candidate from the candidate set to "
                    "make the digest fit"
                ),
                witness=f"missing={sorted(missing_from_pointer)!r}",
                site="src/thalamus/harness/reflex.py::render_pointer",
            )

        return None
    finally:
        g.V().has("scope", scope).drop().iterate()
        close_connection(g)


CASE = Case(
    name="reflex-candidate-cap-overrun-with-matching-chunks",
    tier=Tier.DEEP,
    substrate=(Substrate.NEEDS_GRAPH,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary=(
        "a firing whose anchors match both chunks and sessions must keep its digest "
        "under DIGEST_CHAR_CAP while keeping every selected candidate in the pointer file"
    ),
    run=run,
    # Settled 2026-09-23 (issue #251; architect `17fd7b29a8a344d4`): the per-firing
    # bound became a character cap on the digest (DIGEST_CHAR_CAP), not a candidate
    # count, and the chunk tier stays in the candidate set. `fire()` now packs a
    # digest deterministically against that cap and writes every selected candidate,
    # chunks included, to the pointer file regardless of how many there are.
    issue=251,
    fixed=True,
)
