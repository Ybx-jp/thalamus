"""The trust rule served into agents must be the trust rule the write path runs.

`schema_summary()` (`src/thalamus/substrate/query.py:191`) renders the ontology into the
`memory_query` tool description, so its prose reaches every agent's context on every
session. The `DERIVED_FROM` note states the combination rule directly:

    "Effective tier = max(tier) over this closure — 'distillation does not launder'"

Prose shipped *into* an agent's context is executable documentation: the agent acts on
it, and there is no reader to notice it disagreeing with the code. This exact sentence
shipped reading `min(tier)` (`c091ee0`, corpus `derived-from-min-note`). Tier 0 is the
most trusted, so `min` is the *ceiling* — the laundering reading — served in the clause
whose next words are "distillation does not launder". Nothing under `tests/` compares
the served text against the implementation, so the fix left no guard.

The check is a consistency check between two independently authored statements of one
rule, not a string match against a remembered sentence:

1. the operator named in the served text, parsed out of it;
2. the operator the write path applies, established behaviourally by driving
   `_source_on_match` — the tier ratchet at `writer.py:184`, where the same bytes
   arriving under a second provenance are combined.

`min` and `max` disagree on the probe pair, so the probe discriminates. If the prose is
edited to the laundering reading, or the ratchet is inverted, the two answers separate
and this case reports which one moved.

The scope limit is real and worth stating: the note describes the rule over a
`DERIVED_FROM` *closure*, while the ratchet applies it to a two-reading upsert. They are
the same rule at different arities — "combine to the least trusted" — and the ratchet is
where it is executed today. A closure walk that implements a different operator would
not be caught here.
"""

from __future__ import annotations

import re

from ..model import Case, FailureClass, Finding, Substrate, Tier

# `Effective tier = max(tier) over ...`, with the operator captured. Deliberately loose
# about spacing and wording around it and strict about the operator itself.
_RULE = re.compile(r"[Ee]ffective\s+tier\s*=\s*(?P<op>[a-z]+)\s*\(\s*tier\s*\)")

_HELD, _INCOMING = 1, 3  # first-party and wild: min says 1, max says 3


class _Row:
    """The narrowest stub that satisfies the ratchet's read of the held properties.

    A stub rather than a live graph because the rule under test is arithmetic on two
    integers; standing up TinkerGraph to observe `max(1, 3)` would make this a deep-tier
    case and buy nothing. The stub answers exactly the traversal the function makes, so
    a change to how the ratchet *reads* held state breaks it loudly rather than being
    silently accommodated.
    """

    def __init__(self, stored: dict):
        self._stored = stored

    def V(self, _vid):  # noqa: N802 - mirrors the Gremlin step name
        return self

    def value_map(self, *_keys):
        return self

    def limit(self, _n):
        return self

    def to_list(self):
        return [self._stored]


def run() -> Finding | None:
    from thalamus.substrate import query, writer  # noqa: PLC0415

    served = query.schema_summary()

    # CONTROL: the served text must actually carry the rule. "No claim found" and "claim
    # verified" are the same clean exit otherwise, and the sentence being deleted is a
    # perfectly plausible future — at which point this case would guard nothing.
    match = _RULE.search(served)
    if match is None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the served schema description no longer states the effective-tier "
                    "rule, so this case cannot tell agreement from an absent claim",
            witness=f"no 'Effective tier = <op>(tier)' in schema_summary() "
                    f"({len(served)} chars served)",
            site="src/thalamus/contract/ontology.py (DERIVED_FROM note)",
        )
    served_op = match.group("op")

    # What the write path does with the same two readings.
    stored = {"tier": [_HELD], "origin": ["https://example.invalid/a"], "source": ["a"]}
    refreshed = writer._source_on_match(
        _Row(stored),
        "scope:qe:source:probe",
        {"tier": _INCOMING, "origin": "https://example.invalid/a", "source": "a"},
    )
    kept = refreshed.get("tier")

    predictions = {"max": max(_HELD, _INCOMING), "min": min(_HELD, _INCOMING)}

    # CONTROL: the ratchet must have combined the two readings at all. A `tier` absent
    # from the refresh set means the probe never reached the branch, and an unreached
    # branch agrees with every operator.
    if kept is None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the tier ratchet returned no tier for the probe, so no operator was "
                    "exercised and any served rule would pass",
            witness=f"held={_HELD} incoming={_INCOMING} refreshed keys={sorted(refreshed)}",
            site="src/thalamus/substrate/writer.py:_source_on_match",
        )

    implemented = [name for name, value in predictions.items() if value == int(kept)]
    if not implemented:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the tier ratchet kept a value that is neither of the two readings, "
                    "so the served rule cannot be compared against it",
            witness=f"held={_HELD} incoming={_INCOMING} kept={kept}",
            site="src/thalamus/substrate/writer.py:184",
        )

    if served_op in implemented:
        return None

    return Finding(
        failure_class=FailureClass.DOC_CODE_DRIFT,
        summary=(
            "the effective-tier rule served into every agent's context names a different "
            "operator than the write path applies — one of the two is the laundering "
            "reading, and the served one is the one agents act on"
        ),
        witness=(
            f"served='{served_op}(tier)'; ratchet held={_HELD} incoming={_INCOMING} "
            f"kept={kept}, which is {'/'.join(implemented)}"
        ),
        site="src/thalamus/contract/ontology.py (DERIVED_FROM note) vs writer.py:184",
    )


CASE = Case(
    name="served-tier-rule-matches-write-path",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.DOC_CODE_DRIFT, FailureClass.COLLAPSED_SENTINEL),
    summary="the tier-combination rule in the served tool description must be the "
            "one the tier ratchet implements",
    run=run,
)
