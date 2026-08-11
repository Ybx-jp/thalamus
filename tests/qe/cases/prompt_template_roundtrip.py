"""The prompt's own example must survive the parser that reads the model's imitation.

Corpus record: `entity-name-with-commas` (`8874f3d`). The extraction template showed
`about: [Entity Name]` — a YAML flow sequence — so an entity whose name contains a comma
came back as several references, none of which any entity declared, and the contract
rejected the whole document with an opaque orphan-entity error. Real names do this all
the time: *Help Users Recognize, Diagnose, and Recover from Errors*.

A structural example inside a prompt is code. The model imitates its shape, our parser
reads the imitation, and no reviewer sits in between — so the example needs the same
round-trip test any other input format gets. Nothing under `tests/` pins the template's
shape today; `tests/test_ingest.py:218` covers near-name entity dedup, which is a
different question.

The example is lifted out of `_ARTICLE_PROMPT` rather than restated here. A copy would
keep passing after someone edited the template back to the flow form, which is precisely
the regression this case exists to catch.

The hostile name carries both punctuation classes that decide the parse — a comma, which
splits a flow sequence, and a colon, which turns a bare scalar into a mapping — and the
mutation control feeds the same document in the flow form. Without that control the
assertion is vacuous: a parser that accepted anything would pass it.
"""

from __future__ import annotations

import re

from ..model import Case, FailureClass, Finding, Substrate, Tier

_FENCE = re.compile(r"```yaml\n(?P<body>.*?)```", re.DOTALL)
_PLACEHOLDER = '"Entity Name"'

# Both punctuation classes that decide how YAML reads a name, in one real title.
_HOSTILE = "Help Users Recognize, Diagnose, and Recover from Errors: A Study"

_FILLED = {
    "title: ...": "title: A Document Title",
    "- description: ...": "- description: the document asserts something specific",
    "    description: ...": "    description: a one-line description",
    'citation: "..."': 'citation: "a verbatim phrase from the document"',
}


def _document(example: str, name: str, *, flow: bool) -> str:
    """The example, filled in, with `name` as the entity — optionally in the flow form.

    `flow` reproduces the shape the defect shipped with: an unquoted name inside
    `about: [ ... ]`, which is how the model wrote it when the template showed it.
    """
    body = example
    for placeholder, filled in _FILLED.items():
        body = body.replace(placeholder, filled)
    if not flow:
        return "```yaml\n" + body.replace(_PLACEHOLDER, f'"{name}"') + "```"
    body = re.sub(
        r"about:\n\s+- " + re.escape(_PLACEHOLDER), f"about: [{name}]", body
    ).replace(_PLACEHOLDER, name)
    return "```yaml\n" + body + "```"


def _roundtrip(text: str):
    """(entity names, referenced names, contract issues) for one model response."""
    from thalamus.contract.conformance import check_knowledge  # noqa: PLC0415
    from thalamus.harness.extraction import parse_extraction  # noqa: PLC0415
    from thalamus.harness.ingest import build_batch  # noqa: PLC0415

    data = parse_extraction(text)
    batch = build_batch(
        data,
        scope="qe",
        feed="qe-probe",
        origin="https://example.invalid/probe",
        content_hash="0" * 64,
        uri="archive://qe-probe",
        byte_size=1024,
    )
    names = [entity.name for entity in batch.entities]
    referenced = {ref for claim in batch.claims for ref in claim.about}
    return names, referenced, check_knowledge(batch)


def run() -> Finding | None:
    from thalamus.harness import ingest  # noqa: PLC0415

    prompt = getattr(ingest, "_ARTICLE_PROMPT", "")
    match = _FENCE.search(prompt)
    if not match:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no YAML example was found in the extraction prompt, so 'the example "
                    "round-trips' and 'there is no example' are the same clean result",
            witness=f"_ARTICLE_PROMPT is {len(prompt)} chars with no ```yaml block",
            site="src/thalamus/harness/ingest.py::_ARTICLE_PROMPT",
        )
    example = match.group("body")
    if _PLACEHOLDER not in example:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the template's example no longer carries the quoted entity "
                    "placeholder this case substitutes into, so nothing was exercised",
            witness=f"expected {_PLACEHOLDER} in the example; got: {example[:160]!r}",
            site="src/thalamus/harness/ingest.py::_ARTICLE_PROMPT",
        )

    # MUTATION CONTROL, first: the same document in the shape the defect shipped with
    # must NOT survive. If it does, either the parser stopped splitting flow sequences
    # or this probe's name lost its punctuation — and the assertion below would pass
    # against a parser that accepts anything.
    try:
        flow_names, flow_refs, _ = _roundtrip(_document(example, _HOSTILE, flow=True))
    except Exception as exc:  # noqa: BLE001
        flow_names, flow_refs = [], {f"raised {type(exc).__name__}"}
    if flow_names == [_HOSTILE] and flow_refs == {_HOSTILE}:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the flow-sequence form round-trips too, so this case cannot tell a "
                    "correct template from one that reintroduces the defect",
            witness=f"flow form yielded entities={flow_names} refs={sorted(flow_refs)}",
            site="tests/qe/cases/prompt_template_roundtrip.py::_HOSTILE",
        )

    try:
        names, referenced, issues = _roundtrip(_document(example, _HOSTILE, flow=False))
    except Exception as exc:  # noqa: BLE001
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary="the template's own example does not survive the parser that reads "
                    "the model's imitation of it",
            witness=f"{type(exc).__name__}: {exc}",
            site="src/thalamus/harness/ingest.py::_ARTICLE_PROMPT",
        )

    problems = []
    if names != [_HOSTILE]:
        problems.append(f"entities={names!r} (expected exactly [{_HOSTILE!r}])")
    if referenced != {_HOSTILE}:
        problems.append(f"about={sorted(referenced)!r} (expected one reference)")
    if issues:
        problems.append(f"contract issues={issues}")
    if not problems:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "an entity name containing a comma or colon does not survive the shipped "
            "template's own shape: the model imitates the example, the parser reads the "
            "imitation, and the name arrives as something else"
        ),
        witness=f"name={_HOSTILE!r}; " + "; ".join(problems),
        site="src/thalamus/harness/ingest.py::_ARTICLE_PROMPT vs extraction.parse_extraction",
    )


CASE = Case(
    name="prompt-example-survives-its-own-parser",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="the extraction template's example must round-trip a punctuated entity name",
    run=run,
)
