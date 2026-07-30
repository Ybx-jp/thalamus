"""Gold label set tests (I2; lab/034).

Interfaces: thalamus.eval.gold — the n derivation, stratified draw, workbook
            blinding, label round-trip, Cohen's kappa.
Infrastructure: synthetic Cases and a tmp_path gold directory.
Scope: the properties that decide whether the labels mean anything — that the
       labeller cannot see the judge's answer, that `unclear` never becomes
       agreement, and that the sample size is derived rather than chosen.
"""

from datetime import datetime, timezone

from thalamus.eval import calibration, gold
from thalamus.eval.attribution import OutputTurn, OutputWindow


def _case(trace: str, session: str, kind: str, tool: str, n_nodes: int = 2):
    return calibration.Case(
        trace_id=f"scope:main:trace:{trace}",
        session_id=session,
        scope="main",
        tool=tool,
        ts=datetime(2026, 7, 30, tzinfo=timezone.utc),
        nodes={f"scope:main:{kind}:{trace}{i}": f"node text {i}" for i in range(n_nodes)},
        window=OutputWindow(
            turns=[OutputTurn(index=i, parts=[("prose", f"turn {i} body")]) for i in range(3)]
        ),
    )


def _corpus():
    cases = []
    for i in range(20):
        kind = "claim" if i % 2 else "thread"
        tool = "memory_recall" if i % 3 else "memory_open_threads"
        cases.append(_case(f"t{i}", f"s{i % 5}", kind, tool, n_nodes=3))
    calibration._assign_strata(cases)
    verdicts = {
        c.trace_id: {nid: (index % 3 != 0) for index, nid in enumerate(c.nodes)} for c in cases
    }
    return cases, verdicts


def test_the_sample_size_is_derived_not_chosen():
    """
    Scenario: someone asks why 256.

    Verification: it falls out of SE(kappa) = sqrt(p_o(1-p_o)/(n(1-p_e)^2)) at
    p_o=0.80, p_e=0.50, SE=0.05. The ~100 that was previously proposed gives
    SE=0.08, which cannot separate "substantial" from "moderate" agreement.
    """
    assert gold.required_n(0.80, 0.50, 0.05) == 256
    assert gold.required_n(0.80, 0.50, 0.08) == 100


def test_the_workbook_never_shows_the_judge_s_answer():
    """A labeller who can see the judge's verdict is measuring their agreement
    with a suggestion. The verdict is kept in the manifest, not the workbook."""
    cases, verdicts = _corpus()
    items = gold.draw(cases, verdicts, n=12, seed=1)
    text = gold.workbook(items, batch=1, of=1)

    assert "judge_verdict" not in text
    assert "used: True" not in text and "used: False" not in text
    # ...but it is recorded, so scoring cannot be accused of picking the comparison
    # after the labels arrived.
    assert all(item.judge_verdict is not None for item in items)
    # Every item still offers a label slot.
    # Untouched items read as "?" — not yet judged is not the same state as
    # "unclear", and only the second is data.
    assert text.count("label: ?") == len(items)
    assert "label: unclear\n" not in text


def test_the_draw_is_stratified_and_reproducible():
    cases, verdicts = _corpus()
    first = gold.draw(cases, verdicts, n=20, seed=7)
    again = gold.draw(cases, verdicts, n=20, seed=7)
    assert [i.item_id for i in first] == [i.item_id for i in again]
    # More than one stratum is represented — a sample from one cell would tell us
    # nothing about where the judge is weak.
    assert len({gold.stratum_of(i.node_kind, i.tool, i.window_stratum) for i in first}) > 1


def test_labels_round_trip_through_the_workbook(tmp_path):
    cases, verdicts = _corpus()
    items = gold.draw(cases, verdicts, n=6, seed=3)
    gold.write_batches(items, base=tmp_path, size=6)

    path = next(tmp_path.glob("batch-*.md"))
    text = path.read_text()
    for index, item in enumerate(items):
        replacement = ["used", "unused", "unclear"][index % 3]
        text = text.replace(
            f"item: {item.item_id}\nlabel: ?",
            f"item: {item.item_id}\nlabel: {replacement}",
        )
    path.write_text(text)

    labels = gold.read_labels(tmp_path)
    assert len(labels) == len(items)
    assert {label.label for label in labels.values()} == {"used", "unused", "unclear"}
    assert [i.item_id for i in gold.load_sample(tmp_path)] == [i.item_id for i in items]


def test_unclear_is_excluded_from_kappa_rather_than_absorbed():
    """
    Scenario: the labeller cannot tell, for some items, from what is shown.

    Verification: those items are counted and reported, never folded into either
    class. Absorbing them would manufacture agreement out of the labeller's own
    uncertainty — the one thing a gold set exists to prevent.
    """
    items = [
        gold.GoldItem(
            item_id=f"i{n}", trace_id="t", node_id=f"scope:main:claim:{n}", session_id="s",
            tool="memory_recall", node_kind="claim", window_stratum=0,
            node_text="x", window_excerpt="y", judge_verdict=(n < 5),
        )
        for n in range(10)
    ]
    labels = {f"i{n}": gold.GoldLabel(item_id=f"i{n}", label="used" if n < 5 else "unused")
              for n in range(8)}
    labels["i8"] = gold.GoldLabel(item_id="i8", label="unclear")
    labels["i9"] = gold.GoldLabel(item_id="i9", label="unclear")

    result = gold.agreement(items, labels)
    assert result.n == 8 and result.unclear == 2
    assert result.observed == 1.0
    assert result.kappa == 1.0
    assert result.sensitivity == 1.0 and result.specificity == 1.0


def test_a_judge_that_agrees_only_by_chance_scores_near_zero():
    """The whole point of kappa over raw agreement: a judge that says "used" to
    everything agrees with a mostly-used human most of the time and has learned
    nothing."""
    items = [
        gold.GoldItem(
            item_id=f"i{n}", trace_id="t", node_id=f"scope:main:claim:{n}", session_id="s",
            tool="memory_recall", node_kind="claim", window_stratum=0,
            node_text="x", window_excerpt="y", judge_verdict=True,
        )
        for n in range(20)
    ]
    labels = {
        f"i{n}": gold.GoldLabel(item_id=f"i{n}", label="used" if n < 16 else "unused")
        for n in range(20)
    }
    result = gold.agreement(items, labels)
    assert result.observed == 0.8
    assert abs(result.kappa) < 1e-9  # all the agreement is chance
