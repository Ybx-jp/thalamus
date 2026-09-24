"""The reflex digest's own scaffolding prose must never address the reader as an
instruction.

`harness/reflex.py`'s module docstring states the design's whole claim to safety: the
reflex fires off a Bash result the agent did not run, in order to summon memory nobody
asked for, and the one thing that keeps that from reading as a command is that the
scaffolding *says* it is unsolicited and never itself speaks in the imperative — only a
quoted, tier-stamped record may, sitting in the pointer file rather than the digest
itself, and a voiced record is counted and named in the digest's header rather than
dropped or rewritten (`render_envelope`'s docstring, `src/thalamus/harness/reflex.py`).

That is a UNIVERSAL over the scaffolding text `render_envelope` emits regardless of what
it is fed — no anchor list, no voiced count, no pointer path, and no served item can make
the wrapper's own sentences read as "you should now do X". `imperative_voice` is the
detector `reflex.fire` already trusts to decide whether to append the "N of the records
are phrased as instructions" line, so this case drives the same regex
`tests/test_reflex.py::test_the_scaffolding_never_instructs_and_the_detector_would_know`
exercises, but as its own qe entry: dev's suite can be skipped locally or drift out of
CI's required-checks list, and this property — informs-never-instructs holding at the
one seam a model reads unprompted — is exactly the kind of universal this suite exists to
keep a permanent, adversarial eye on rather than trust to one dev unit test.

**Positive control.** `imperative_voice("You should now fix X")` must flag the line, or a
clean result below is uninterpretable — a detector that never fires on anything would
report the scaffolding as silent for the wrong reason, and every real regression alike.

**Shown capable of going red.** Add an imperative sentence to `render_envelope`'s own
`lines` list in `src/thalamus/harness/reflex.py` (e.g. append `"Now fix the anchors
above."` to the list the function builds before joining it into the digest) and rerun
this case: it reports `INVARIANT_FALSIFIED` with the added sentence as its witness.
`qe` does not write `src/thalamus/harness/`, so the mutation is not carried in the
case; this is the repeatable check for the next reader instead.
"""

from __future__ import annotations

from ..model import Case, FailureClass, Finding, Substrate, Tier


def run() -> Finding | None:
    from thalamus.harness.reflex import imperative_voice, render_envelope  # noqa: PLC0415

    # CONTROL: the detector must be shown capable of firing on a plain instruction, or
    # a clean scaffolding result below cannot be told apart from a detector that never
    # flags anything no matter what it is given.
    control_hits = imperative_voice("You should now fix X")
    if not control_hits:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "positive control failed: imperative_voice did not flag a line "
                "written as a plain instruction, so a clean envelope result cannot "
                "be told apart from a detector that never fires"
            ),
            witness="imperative_voice('You should now fix X') == []",
            site="tests/qe/cases/reflex_envelope_voice.py::run",
        )

    anchors = ["reflex-scaffolding-anchor-a", "reflex-scaffolding-anchor-b"]
    bare = render_envelope([], anchors)
    with_pointer = render_envelope(
        ["R1.1 · session · tier 1 · 2026-09-23 · a served record's gist"],
        anchors, voiced=1, pointer="/home/qe/.thalamus/reflex/pointers/s1/R1.md",
    )
    hits = imperative_voice(bare) + imperative_voice(with_pointer)
    if not hits:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "render_envelope's own scaffolding prose reads as an instruction to the "
            "agent, contradicting reflex.py's contract that the wrapper never "
            "addresses the reader in the imperative — only a quoted served record, "
            "sitting in the pointer file, may, and it is counted and named, never "
            "authored, by the scaffolding itself"
        ),
        witness=f"imperative_voice(render_envelope(...)) = {hits!r}",
        site="src/thalamus/harness/reflex.py::render_envelope",
    )


CASE = Case(
    name="reflex-envelope-scaffolding-never-instructs",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="render_envelope's own scaffolding prose must carry no imperative voice",
    run=run,
)
