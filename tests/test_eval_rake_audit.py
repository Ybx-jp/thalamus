"""Rake-queue precision audit tests — Class A stage 0.5.

Interfaces: thalamus.eval.rake_audit
Infrastructure: none — pure sampling and arithmetic, no graph, no model
Scope: the properties that decide whether the resulting number means anything.

An audit is an instrument for producing one number that stage 2 will be built on
top of, so what gets pinned here is what would let that number lie:

- the draw must not prefer convincing candidates (arXiv 1709.01709's active-selection
  bias — the estimate would be biased toward the system that built the pool);
- the worksheet must not leak which items are decoys, or the control is worthless;
- the worksheet must not show the shared artifact keys, which are the proximity
  rule's own evidence — an annotator shown them is ratifying, not judging;
- `unclear` must land in neither numerator nor denominator (arXiv 2111.03382);
- the interval must price in that pairs cluster on rakes.

The graph read is exercised live like every other read path; the sampling and the
arithmetic are what can silently rot, so they are what get pinned.
"""

import random

from thalamus.eval.rake_audit import (
    cluster_interval,
    draw_sample,
    parse_worksheet,
    render_worksheet,
    sample_from_jsonl,
    sample_to_jsonl,
    score_sample,
    wilson_interval,
)
from thalamus.eval.rakes import Rake, SessionRow, build_rake_report


def _session(vid: str, ts: str, project: str = "thalamus", summary: str = "") -> SessionRow:
    return SessionRow(
        vid=vid,
        session_id=vid,
        project=project,
        ts=ts,
        summary=summary or f"session {vid} did some work",
        artifacts=(f"{vid}_file.py",),
    )


def _corpus(n_rakes: int = 6, n_sessions: int = 8):
    """A rake per module, each keyed on its own file, with later sessions touching it."""
    rakes = [
        Rake(
            vid=f"r{i}",
            description=f"problem {i}",
            solution=f"solution {i}",
            category="bug",
            artifacts=(f"mod{i}.py",),
            sessions=("s0",),
        )
        for i in range(n_rakes)
    ]
    sessions = {"s0": _session("s0", "2026-01-01")}
    sessions.update(
        {f"s{j}": _session(f"s{j}", f"2026-02-{j:02d}") for j in range(1, n_sessions + 1)}
    )
    artifact_sessions = {
        f"mod{i}.py": ["s0"] + [f"s{j}" for j in range(1, n_sessions + 1)]
        for i in range(n_rakes)
    }
    return rakes, sessions, artifact_sessions


def _sample(seed=1, size=10):
    rakes, sessions, artifact_sessions = _corpus()
    report = build_rake_report(rakes, sessions, artifact_sessions)
    return draw_sample(report, rakes, sessions, seed=seed, size=size), report


def test_the_draw_is_uniform_and_reproducible_from_the_seed():
    """Reproducibility is what lets --score regenerate the sample instead of trusting
    a key file the annotator could have seen."""
    a, _ = _sample(seed=7)
    b, _ = _sample(seed=7)
    assert [(i.rake_vid, i.session_vid, i.decoy) for i in a.items] == [
        (i.rake_vid, i.session_vid, i.decoy) for i in b.items
    ]

    c, _ = _sample(seed=8)
    assert [i.rake_vid for i in c.items] != [i.rake_vid for i in a.items]


def test_the_draw_never_prefers_candidates_the_rule_is_more_confident_about():
    """arXiv 1709.01709: judging the highest-ranked candidates first biases the
    estimate toward the system that produced the pool. Over many seeds every
    candidate must be reachable, not just a favoured head of the stratum."""
    rakes, sessions, artifact_sessions = _corpus()
    report = build_rake_report(rakes, sessions, artifact_sessions)
    stratum = {(c.rake_vid, c.session_vid) for c in report.specific_candidates}

    seen = set()
    for seed in range(60):
        s = draw_sample(report, rakes, sessions, seed=seed, size=5)
        seen.update((i.rake_vid, i.session_vid) for i in s.real)
    assert seen == stratum


def test_the_worksheet_does_not_reveal_which_items_are_decoys():
    """The decoys measure the annotator. An annotator who can spot them measures
    nothing."""
    sample, _ = _sample(seed=3, size=12)
    assert sample.decoys_drawn > 0
    text = render_worksheet(sample)

    for item in sample.items:
        assert f"## Item {item.number}" in text
    assert "decoy" not in text.lower()
    # Nor by structure: every item renders the same fields.
    blocks = text.split("## Item ")[1:]
    assert len({("Files it touched" in b) for b in blocks}) == 1


def test_the_worksheet_withholds_the_shared_artifact_key():
    """The shared key is the proximity rule's own evidence. Printing it turns the
    audit into a request for ratification."""
    rakes, sessions, artifact_sessions = _corpus(n_rakes=1)
    report = build_rake_report(rakes, sessions, artifact_sessions)
    sample = draw_sample(report, rakes, sessions, seed=2, size=4)

    text = render_worksheet(sample)
    assert "mod0.py" not in text  # the key that generated every pair
    assert "problem 0" in text  # but the problem itself is shown
    assert "solution 0" in text


def test_unclear_lands_in_neither_numerator_nor_denominator():
    """arXiv 2111.03382 — flagged, never dropped, and never quietly absorbed into
    a ratio it would move."""
    sample, _ = _sample(seed=5, size=8)
    real = [i.number for i in sample.items if not i.decoy]
    labels = {real[0]: "hit", real[1]: "miss", real[2]: "unclear", real[3]: "unclear"}

    score = score_sample(sample, labels, [])

    assert score.decided == 2
    assert score.precision == 0.5
    assert score.counts["unclear"] == 2
    assert "unclear:  2" in score.render()
    assert "neither numerator nor denominator" in score.render()


def test_decoy_labels_are_scored_apart_from_the_queue_estimate():
    sample, _ = _sample(seed=5, size=8)
    real = [i.number for i in sample.items if not i.decoy]
    decoy = [i.number for i in sample.items if i.decoy]
    labels = {n: "hit" for n in real} | {n: "hit" for n in decoy}

    score = score_sample(sample, labels, [])

    assert score.decided == len(real)  # decoys never enter the queue's ratio
    assert score.decoy_counts["hit"] == len(decoy)
    assert "upper* bound on annotator laxity" in score.render()


def test_the_clustered_interval_is_wider_than_the_pairwise_one():
    """Eight pairs on one rake are not eight independent observations. If the
    bootstrap did not widen, it would be decoration."""
    per_rake = {"r1": [True] * 8, "r2": [False] * 8}
    lo_c, hi_c = cluster_interval(per_rake, random.Random(0), draws=2000)
    lo_w, hi_w = wilson_interval(8, 16)

    assert (hi_c - lo_c) > (hi_w - lo_w)


def test_a_worksheet_with_a_deleted_label_line_is_reported_not_silently_shifted():
    """Joining labels to the wrong items would corrupt the estimate invisibly."""
    text = "## Item 1\n- **label**: hit\n\n## Item 2\n\n## Item 3\n- **label**: miss\n"
    labels, problems = parse_worksheet(text)

    assert any("label line" in p for p in problems)
    assert any("unlabelled" in p for p in problems)
    assert labels == {1: "hit", 2: "miss"} or "3" in str(problems)


def test_a_blank_label_line_reads_as_unlabelled_not_as_the_line_below_it():
    """`\\s` crosses newlines, so an unfilled `- **label**: ` will happily match the
    `-` opening the next line. Every item on a fresh worksheet then reports as a
    malformed label, which buries the one message that matters."""
    text = render_worksheet(_sample(seed=6, size=4)[0])
    labels, problems = parse_worksheet(text)

    assert labels == {}
    assert not any("unrecognized" in p for p in problems)
    assert any("unlabelled" in p for p in problems)


def test_an_unrecognized_label_is_refused_rather_than_coerced():
    labels, problems = parse_worksheet("## Item 1\n- **label**: probably?\n")
    assert labels == {}
    assert any("probably" in p for p in problems)


def test_the_key_round_trips_so_scoring_survives_a_graph_that_moved_on():
    """The stratum is a function of the live graph. A session distilled between
    drawing and labelling would reshuffle a seed-regenerated sample and join the
    labels onto the wrong pairs — silently, since item numbers still line up."""
    sample, _ = _sample(seed=11, size=10)
    restored = sample_from_jsonl(sample_to_jsonl(sample))

    assert [(i.number, i.rake_vid, i.session_vid, i.decoy) for i in restored.items] == [
        (i.number, i.rake_vid, i.session_vid, i.decoy) for i in sample.items
    ]
    assert restored.stratum_size == sample.stratum_size
    assert restored.distinct_rakes == sample.distinct_rakes

    labels = {i.number: "hit" for i in sample.items if not i.decoy}
    assert score_sample(restored, labels, []).precision == 1.0


def test_scoring_an_empty_worksheet_estimates_nothing():
    sample, _ = _sample(seed=4, size=6)
    score = score_sample(sample, {}, [])
    assert "No decided labels" in score.render()
