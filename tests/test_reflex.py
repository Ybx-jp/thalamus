"""
Memory reflex tests — the lexical rung, end to end minus the graph.

Interfaces: thalamus.harness.reflex (extract_anchors, anchor_key, fire, render_envelope,
            imperative_voice, ReflexBudget, FAILURE_PATTERN), the reflex.sh hook driven
            live (bash) with a stubbed `uv`, thalamus.eval.reflex.reflex_report
Infrastructure: tmp_path as $HOME and as the ledger/tap bases; `recall` replaced by a
                recording fake; no graph, no model
Scope: what the hook fires on, what one firing writes where, and the three controls
       that bound what a session pays — dedup, budget, the empty answer. The retrieval
       itself is `substrate.reader.recall`, tested in its own file; the graph-backed
       half (a known anchor set returns the expected ids and nothing from another scope)
       is a qe case, since `main` cannot write tests/qe/.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from thalamus.eval import traces as trace_mod
from thalamus.eval.attribution import attribute, cites_handle
from thalamus.eval.reflex import reflex_report
from thalamus.harness import reflex, retrieval
from thalamus.harness.reflex import (
    ARM_LEXICAL,
    ARM_PROPAGATION,
    FAILURE_PATTERN,
    PLANS,
    POINTER_OPEN,
    SESSION_CHAR_BUDGET,
    Firing,
    ReflexBudget,
    anchor_key,
    assign_plan,
    extract_anchors,
    fire,
    imperative_voice,
    load_firings,
    render_envelope,
)
from thalamus.substrate import vocabulary
from thalamus.substrate.reader import KnowledgeResult, MemoryResult
from thalamus.substrate.schema import Tier
from thalamus.substrate.vocabulary import Row

HOOK = (
    Path(__file__).resolve().parents[1]
    / "src" / "thalamus" / "harness" / "hooks" / "claude-code" / "reflex.sh"
)
POINTER_TAP = HOOK.with_name("reflex-pointer-tap.sh")

PYTEST_FAILURE = """\
tests/test_reflex.py ..F                                                 [100%]
=================================== FAILURES ===================================
____________________ test_budget_refuses_past_the_ceiling ______________________
>       assert fire(g, session_id="s1", observed=text) == ""
E       AssertionError: assert 'Thalamus memory reflex' == ''
tests/test_reflex.py:41: AssertionError
  File "/home/op/code/thalamus/.venv/lib/python3.12/site-packages/_pytest/runner.py", line 341, in from_call
    result: Optional[TResult] = func()
  File "/home/op/code/thalamus/src/thalamus/harness/reflex.py", line 210, in fire
    results = recall(g, query, limit=MAX_CANDIDATES, scope=scope)
FAILED tests/test_reflex.py::test_budget_refuses_past_the_ceiling - AssertionError
========================= 1 failed, 2 passed in 0.31s ==========================
"""

_PATTERN = re.compile(FAILURE_PATTERN, re.MULTILINE)
_NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _memory(node_id="scope:main:session:abc", summary="the reflex budget was set at 24k chars"):
    return MemoryResult(
        session_id="abc", summary=summary, timestamp="2026-09-12T10:00:00",
        tool="claude-code", project="thalamus", node_id=node_id,
    )


def _fake_recall(results):
    calls = []

    def recall(g, query, limit=5, scope="main", knowledge_scopes=None):
        calls.append({"query": query, "limit": limit, "scope": scope,
                      "knowledge_scopes": knowledge_scopes})
        return list(results)

    recall.calls = calls
    return recall


@pytest.fixture
def served(monkeypatch):
    """`recall` answering with one first-party memory; scopes read from nowhere."""
    fake = _fake_recall([_memory()])
    monkeypatch.setattr(retrieval, "recall", fake)
    monkeypatch.setattr(reflex, "available_scopes", lambda: ["main", "qe"])
    return fake


def _fire(tmp_path, observed=PYTEST_FAILURE, **overrides):
    kwargs = dict(
        session_id="s1", observed=observed, scope="main", agent_id="", agent_type="",
        cwd="/w", now=_NOW, reflex_base=tmp_path / "reflex", traces_base=tmp_path / "traces",
        plan=ARM_LEXICAL,
    )
    kwargs.update(overrides)
    return fire(object(), **kwargs)


def _tap_lines(tmp_path):
    lines = []
    for path in sorted((tmp_path / "traces").glob("*.jsonl")):
        lines += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return lines


# --- the trigger ---------------------------------------------------------------


def test_the_hook_greps_with_the_modules_own_pattern():
    """The failure test lives in two languages; this holds them equal byte for byte."""
    match = re.search(r"^failure_re='(.*)'$", HOOK.read_text(), re.MULTILINE)
    assert match is not None
    assert match.group(1) == FAILURE_PATTERN


@pytest.mark.parametrize("output", [
    PYTEST_FAILURE,
    "Traceback (most recent call last):\n  File x\nValueError: bad\n",
    "bash: frobnicate: command not found\n",
    "error[E501]: line too long\n",
    "error: cannot find module\n",
    "ModuleNotFoundError: No module named 'x'\n",
])
def test_legible_failures_fire(output):
    assert _PATTERN.search(output)


@pytest.mark.parametrize("output", [
    "3 passed in 0.2s\n",
    "All checks passed!\n",
    "On branch master\nnothing to commit, working tree clean\n",
    # Prose that mentions the words is not a failure line.
    "The error handling in this module follows the FAILED convention.\n",
])
def test_clean_output_does_not_fire(output):
    assert not _PATTERN.search(output)


# --- anchors -------------------------------------------------------------------


def test_anchors_are_the_identifiers_and_not_the_interpreters_frames():
    anchors = extract_anchors(PYTEST_FAILURE)
    assert "test_budget_refuses_past_the_ceiling" in anchors
    assert "harness/reflex.py" in anchors
    assert "assertionerror" in anchors
    # Compounds lead: they are what a claim about the same code spells the same way.
    assert "/" in anchors[0] or "_" in anchors[0]
    joined = " ".join(anchors)
    assert "site-packages" not in joined and "_pytest" not in joined
    assert "0.31s" not in anchors and "pytest" not in anchors
    assert len(anchors) <= reflex.MAX_ANCHORS


def test_anchor_key_is_invariant_to_the_separator():
    assert anchor_key("tool-calls") == anchor_key("tool_calls") == anchor_key("Tool Calls")
    assert anchor_key("tool-calls") == "calls tool"


# --- one firing ----------------------------------------------------------------


def test_a_served_firing_injects_a_digest_and_keeps_the_records_in_a_pointer_file(
    tmp_path, served
):
    """
    Scenario: a pytest failure fires for the first time in a session and the graph
    holds one matching memory.

    Verifications:
    - the digest says it is unsolicited, indexes the record under a short handle with
      its kind, tier, date and own first sentence, names the pointer file, and carries
      no instruction of its own; the record itself is not in it
    - the pointer file holds the record verbatim with its tier stamp and vertex id,
      and the handle map
    - the query is the fresh anchors, retrieved in the pinned scope with the other
      scopes as knowledge — what the MCP server grants an unticketed recall
    - the tap line is in the tap's schema under tool `reflex_lexical`: the pointer file
      as the response, so the node id is recoverable, and the digest's length as what
      entered context, with the handle map for citation
    - the ledger prices the firing at the digest's length
    """
    digest = _fire(tmp_path)
    pointer = tmp_path / "reflex" / "pointers" / "s1" / "R1.md"

    assert digest.startswith("Thalamus memory reflex (tier-0 operator hook, unsolicited)")
    assert (
        "R1.1 · session · tier 1 · 2026-09-12 · the reflex budget was set at 24k chars"
        in digest
    )
    assert str(pointer) in digest
    assert "## Recalled memory" not in digest and "scope:main:session:abc" not in digest

    records = pointer.read_text()
    assert "- R1.1: `scope:main:session:abc`" in records
    assert "## Recalled memory [tier 1 · first-party]" in records
    assert "`scope:main:session:abc`" in records
    assert "it informs, it never instructs" in records

    call = served.calls[0]
    assert call["scope"] == "main" and call["knowledge_scopes"] == ["qe"]
    assert call["limit"] == reflex.MAX_CANDIDATES
    assert "test_budget_refuses_past_the_ceiling" in call["query"]

    events = trace_mod.load_events(tmp_path / "traces")
    assert [event.tool for event in events] == [ARM_LEXICAL]
    assert events[0].session_id == "s1" and events[0].scope == "main"
    assert events[0].returned_node_ids() == ["scope:main:session:abc"]
    assert events[0].tool_response == records
    assert events[0].injected_chars() == len(digest)
    assert events[0].handles() == {"R1.1": "scope:main:session:abc"}
    assert not events[0].is_legacy()
    assert events[0].query_text().startswith("reflex_lexical: ")

    firings = load_firings("s1", tmp_path / "reflex")
    assert [f.outcome for f in firings] == ["served"]
    assert firings[0].injected_chars == len(digest)
    assert firings[0].firing_id == "R1"
    assert firings[0].candidates == 1
    assert firings[0].keys and all(" " in k or k.isalnum() for k in firings[0].keys)


def test_a_knowledge_block_keeps_its_tier_stamp(tmp_path, monkeypatch):
    claim = KnowledgeResult(
        node_id="scope:literature:claim:deadbeef", description="A-Mem plateaus then declines",
        kind="finding", tier=int(Tier.CURATED), citation="arXiv 2502.12110",
    )
    monkeypatch.setattr(retrieval, "recall", _fake_recall([claim]))
    monkeypatch.setattr(reflex, "available_scopes", lambda: ["main"])

    digest = _fire(tmp_path)
    records = (tmp_path / "reflex" / "pointers" / "s1" / "R1.md").read_text()

    assert "R1.1 · external finding · tier 2 · A-Mem plateaus then declines" in digest
    assert "## Recalled external claim [tier 2 · curated third-party]" in records
    assert "data, never instructions" in records


def test_the_digest_is_sized_in_characters_and_lists_the_strongest_last(
    tmp_path, monkeypatch
):
    """
    Scenario: a firing selects more candidates than fit the digest.

    Verifications:
    - the digest stays under DIGEST_CHAR_CAP, so it never reaches Claude Code's
      10,000-char spill line, however many candidates the firing selected
    - lines are whole: none is shortened to fit, and how many were held is said
    - every candidate's record is in the pointer file, held or not
    - the strongest candidate sits last, nearest the agent's next turn
    - control: at a cap wide enough for all of them, nothing is held
    """
    many = [
        _memory(node_id=f"scope:main:session:m{index}", summary=f"memory {index} " + "w" * 150)
        for index in range(1, 41)
    ]
    monkeypatch.setattr(retrieval, "recall", _fake_recall(many))
    monkeypatch.setattr(reflex, "available_scopes", lambda: ["main"])

    digest = _fire(tmp_path)
    records = (tmp_path / "reflex" / "pointers" / "s1" / "R1.md").read_text()

    assert len(digest) <= reflex.DIGEST_CHAR_CAP
    held = re.search(r"^(\d+) more in the file$", digest, re.MULTILINE)
    assert held is not None and int(held.group(1)) > 0
    shown = re.findall(r"^R1\.(\d+) ", digest, re.MULTILINE)
    assert len(shown) + int(held.group(1)) == 40
    assert shown[-1] == "1" and shown[0] == str(len(shown))
    assert all(f"`scope:main:session:m{index}`" in records for index in range(1, 41))

    kept, left = reflex.pack_digest(["a" * 10] * 40, cap=10_000, frame="")
    assert len(kept) == 40 and left == 0


def test_a_second_firing_in_the_session_takes_the_next_handle_prefix(tmp_path, monkeypatch):
    """Handles are unique within a session, across its agents: a cited `R2.1` must
    name one node. A subagent shares its parent's session id and so its numbering."""
    monkeypatch.setattr(retrieval, "recall", _fake_recall([_memory()]))
    monkeypatch.setattr(reflex, "available_scopes", lambda: ["main"])

    first = _fire(tmp_path)
    second = _fire(tmp_path, agent_id="agent-7", agent_type="general-purpose")

    assert "R1.1 · " in first and "R2.1 · " in second
    handles = [event.handles() for event in trace_mod.load_events(tmp_path / "traces")]
    assert handles == [{"R1.1": "scope:main:session:abc"}, {"R2.1": "scope:main:session:abc"}]


# --- the plans -----------------------------------------------------------------


@pytest.fixture
def spread(served, monkeypatch):
    """Word match answering with one session; `expand_one_hop` answering from
    `edges[(node, relation)]`, and `resolve` rendering any node as a session."""
    edges: dict[tuple[str, str], list[Row]] = {}

    def expand(g, node_id, relation, limit=5, scope="main", knowledge_scopes=None):
        return edges.get((node_id, relation), [])[:limit]

    tool = retrieval.TOOLS["expand_one_hop"]
    monkeypatch.setitem(retrieval.TOOLS, "expand_one_hop",
                        retrieval.Tool(tool.params, expand, knowledge=tool.knowledge))
    monkeypatch.setattr(
        vocabulary, "resolve",
        lambda g, node, scope, knowledge: _memory(node_id=node, summary=f"record {node}"),
    )
    return edges


def _decision(node_id, summary="the budget stays at 24k"):
    return Row(node_id, "decision", 1, "2026-09-20", summary)


def test_propagation_serves_the_word_match_hits_then_what_the_spread_reached(
    tmp_path, spread
):
    """
    Scenario: word match finds one session, and a decision shares a file with it.

    Verifications:
    - the digest is word match's line for the hit, then the reached decision's line
      naming the edge and the handle it came from; the hit sits last, nearest the
      agent's next turn, and the envelope says what a `via` line is
    - the pointer file holds both records and both handles
    - the trace is the propagation arm's, with the handle map covering both, how many
      records the spread added, and what the plan did
    - control: the same failure under word match serves the hit alone, with no `via`
      sentence in the envelope
    """
    spread[("scope:main:session:abc", "same_file")] = [_decision("scope:main:claim:d1")]

    digest = _fire(tmp_path, plan=ARM_PROPAGATION)
    records = (tmp_path / "reflex" / "pointers" / "s1" / "R1.md").read_text()

    linked = ("R1.2 · decision · tier 1 · 2026-09-20 · the budget stays at 24k"
              " · via same_file from R1.1")
    assert linked in digest
    assert digest.index(linked) < digest.index("R1.1 · session")
    assert "`via <relation> from <handle>`" in digest
    assert "- R1.1: `scope:main:session:abc`" in records
    assert "- R1.2: `scope:main:claim:d1`" in records

    (line,) = _tap_lines(tmp_path)
    assert line["tool_name"] == ARM_PROPAGATION
    assert line["tool_input"]["handles"] == {
        "R1.1": "scope:main:session:abc", "R1.2": "scope:main:claim:d1"}
    assert line["tool_input"]["linked"] == 1 and line["tool_input"]["hops"] == 2
    assert line["tool_input"]["calls"] > 1 and "ms" in line["tool_input"]
    (firing,) = load_firings("s1", tmp_path / "reflex")
    assert firing.arm == ARM_PROPAGATION and firing.candidates == 2

    control = _fire(tmp_path, session_id="s2")
    assert "R1.1 · session" in control and " · via " not in control
    assert "`via <relation>" not in control


def test_a_reached_record_that_does_not_fit_is_not_served(tmp_path, spread):
    """
    Verifications:
    - the spread adds at most MAX_CANDIDATES records, whatever it reached
    - they fill the room the hits leave, and the digest stays under the cap
    - one that does not fit is neither counted as held nor written to the pointer
      file: the file holds exactly the records the digest lists
    - control: at a size that fits, MAX_CANDIDATES of them are served
    """
    def reach(size):
        spread.clear()
        spread[("scope:main:session:abc", "same_file")] = [
            _decision(f"scope:main:claim:d{i}", summary=f"decision {i} " + "w" * size)
            for i in range(5)
        ]
        spread[("scope:main:claim:d0", "same_file")] = [
            _decision(f"scope:main:claim:f{i}", summary=f"further {i} " + "w" * size)
            for i in range(5)
        ]

    reach(1_200)
    digest = _fire(tmp_path, plan=ARM_PROPAGATION)
    records = (tmp_path / "reflex" / "pointers" / "s1" / "R1.md").read_text()

    assert len(digest) <= reflex.DIGEST_CHAR_CAP
    assert "more in the file" not in digest
    shown = set(re.findall(r"^(R1\.\d+) ", digest, re.MULTILINE))
    in_file = set(re.findall(r"^- (R1\.\d+): ", records, re.MULTILINE))
    assert shown == in_file
    (line,) = _tap_lines(tmp_path)
    assert line["tool_input"]["reached"] == 10
    assert 0 < line["tool_input"]["linked"] == len(shown) - 1 < reflex.MAX_CANDIDATES

    reach(150)
    _fire(tmp_path, session_id="s2", plan=ARM_PROPAGATION)
    assert _tap_lines(tmp_path)[-1]["tool_input"]["linked"] == reflex.MAX_CANDIDATES


def test_a_hit_with_nothing_linked_is_served_as_word_match_serves_it(tmp_path, spread):
    digest = _fire(tmp_path, plan=ARM_PROPAGATION)
    control = _fire(tmp_path, session_id="s2")

    assert digest.replace("/s1/", "/s2/") == control


def test_plans_are_assigned_in_balanced_blocks_drawn_per_session():
    """
    Verifications:
    - every block of len(PLANS) assigned firings holds each plan once
    - the order is drawn per session and block, so it is recomputable from the ledger
      and differs between sessions
    - a firing stopped before assignment, or written with no plan, takes no slot
    """
    def run(session_id, count):
        history: list[Firing] = []
        for _ in range(count):
            arm = assign_plan(session_id, history)
            history.append(Firing(ts="", session_id=session_id, agent_id="",
                                  outcome="served", arm=arm))
            history.append(Firing(ts="", session_id=session_id, agent_id="",
                                  outcome="deduped"))
        return [row.arm for row in history if row.arm]

    arms = run("s1", 20)
    for block in range(10):
        assert sorted(arms[2 * block: 2 * block + 2]) == sorted(PLANS)
    assert run("s1", 20) == arms
    orders = {tuple(run(f"s{n}", 2)) for n in range(20)}
    assert len(orders) == 2


def test_an_unpinned_firing_records_its_plan_and_a_stopped_one_none(tmp_path, spread):
    _fire(tmp_path, plan="")
    _fire(tmp_path, plan="")  # deduped: no plan

    rows = load_firings("s1", tmp_path / "reflex")
    assert [(row.outcome, row.arm in PLANS) for row in rows] == [
        ("served", True), ("deduped", False)]
    assert rows[1].arm == ""
    (line,) = _tap_lines(tmp_path)
    assert line["tool_name"] == rows[0].arm


# --- the controls --------------------------------------------------------------


def test_a_rerun_of_the_same_failure_does_not_refire_but_another_agent_does(
    tmp_path, served
):
    """
    Scenario: the same pytest failure arrives three times — twice from the session
    itself, once from a subagent that shares its session id.

    Verifications:
    - the second arrival is deduped: no envelope, no tap line, a ledger row saying why
    - the subagent's arrival fires, because the key is (session, agent, anchor) —
      keying on the session alone would exempt every subagent from the reflex
    """
    first = _fire(tmp_path)
    second = _fire(tmp_path)
    third = _fire(tmp_path, agent_id="agent-7", agent_type="general-purpose")

    assert first and second == "" and third
    assert len(_tap_lines(tmp_path)) == 2
    outcomes = [(f.agent_id, f.outcome) for f in load_firings("s1", tmp_path / "reflex")]
    assert outcomes == [("", "served"), ("", "deduped"), ("agent-7", "served")]
    assert "already fired" in load_firings("s1", tmp_path / "reflex")[1].detail
    assert len(served.calls) == 2


def test_one_incidental_new_token_is_still_the_same_failure(tmp_path, served):
    """A rerun whose output differs by a timing figure or one new word must not
    re-query on that word alone — below the reader's floor, a one-keyword recall
    is the noisy shape the floor exists to stop."""
    _fire(tmp_path)
    again = _fire(tmp_path, observed=PYTEST_FAILURE + "\nplus frobnicator\n")

    assert again == ""
    assert load_firings("s1", tmp_path / "reflex")[-1].outcome == "deduped"


def test_the_budget_refuses_with_the_arithmetic_and_serves_nothing(tmp_path, served):
    """
    Scenario: a session has already been served its whole ceiling.

    Verifications:
    - the firing is refused before the graph is asked
    - the ledger row carries the refusal with its numbers
    - no tap line: nothing was injected, so nothing is priced
    - positive control: the same budget one character under the ceiling fits
    """
    ledger = tmp_path / "reflex" / "sessions" / "s1.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(Firing(
        ts="2026-09-13T11:00:00Z", session_id="s1", agent_id="", outcome="served",
        keys=["unrelated"], injected_chars=SESSION_CHAR_BUDGET,
    ).to_json() + "\n")

    assert _fire(tmp_path) == ""
    assert served.calls == []
    row = load_firings("s1", tmp_path / "reflex")[-1]
    assert row.outcome == "refused"
    assert f"{SESSION_CHAR_BUDGET:,}-char budget" in row.detail and "over by" in row.detail
    assert _tap_lines(tmp_path) == []

    assert ReflexBudget(spent=SESSION_CHAR_BUDGET - 10, cost=10).fits
    assert not ReflexBudget(spent=SESSION_CHAR_BUDGET - 10, cost=11).fits


def test_a_digest_that_would_cross_the_ceiling_is_refused_after_rendering(
    tmp_path, served
):
    """The exact check needs the rendered length, so it runs after retrieval; the
    refusal still serves nothing, leaves no tap line, and leaves no pointer file."""
    ledger = tmp_path / "reflex" / "sessions" / "s1.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(Firing(
        ts="2026-09-13T11:00:00Z", session_id="s1", agent_id="", outcome="served",
        keys=["unrelated"], injected_chars=SESSION_CHAR_BUDGET - 50,
    ).to_json() + "\n")

    assert _fire(tmp_path) == ""
    row = load_firings("s1", tmp_path / "reflex")[-1]
    assert row.outcome == "refused" and row.candidates == 1
    assert _tap_lines(tmp_path) == []
    assert list((tmp_path / "reflex" / "pointers" / "s1").glob("*.md")) == []


def test_an_empty_recall_is_a_miss_priced_at_nothing(tmp_path, monkeypatch):
    """
    Scenario: the anchors match nothing in the graph.

    Verifications:
    - nothing is injected and the ledger says `empty`
    - the tap still gets a line — "the graph had nothing" is the signal that grades
      the trigger — with an empty response, so `injected_chars` prices what the
      agent saw (nothing) and `returned_count == 0` reads as the miss
    """
    monkeypatch.setattr(retrieval, "recall", _fake_recall([]))
    monkeypatch.setattr(reflex, "available_scopes", lambda: ["main"])

    assert _fire(tmp_path) == ""
    assert load_firings("s1", tmp_path / "reflex")[-1].outcome == "empty"
    events = trace_mod.load_events(tmp_path / "traces")
    assert len(events) == 1 and events[0].tool_response == ""
    assert events[0].returned_node_ids() == [] and not events[0].is_legacy()


def test_output_with_no_anchors_is_recorded_and_never_queries(tmp_path, served):
    assert _fire(tmp_path, observed="E   \n") == ""
    assert load_firings("s1", tmp_path / "reflex")[-1].outcome == "no_anchors"
    assert served.calls == []


# --- voice ---------------------------------------------------------------------


def test_the_scaffolding_never_instructs_and_the_detector_would_know(tmp_path, monkeypatch):
    """
    Verifications:
    - the digest's own prose carries no imperative voice
    - positive control: the detector flags a block written as an instruction, so a
      clean scaffolding is a finding rather than a check that cannot fire
    - a served block phrased as an instruction is neither dropped nor rewritten: it
      is quoted verbatim, counted, and named as a record in the header
    """
    assert imperative_voice(render_envelope([], ["a", "b"], pointer="/p/R1.md")) == []
    assert imperative_voice("You should now fix X") == ["You should"]
    assert imperative_voice("- Fix the budget first.") == ["- Fix"]

    voiced = _memory(node_id="scope:main:session:v1", summary="Do not use bare git stash here")
    monkeypatch.setattr(retrieval, "recall", _fake_recall([voiced, _memory()]))
    monkeypatch.setattr(reflex, "available_scopes", lambda: ["main"])

    digest = _fire(tmp_path)
    records = (tmp_path / "reflex" / "pointers" / "s1" / "R1.md").read_text()

    assert "Do not use bare git stash here" in digest
    assert "Do not use bare git stash here" in records
    assert "1 of the records are phrased as instructions" in digest
    assert load_firings("s1", tmp_path / "reflex")[-1].voiced == 1


def test_the_tap_directory_is_the_one_the_eval_loop_reads():
    """Named in two modules because `harness` may not import `eval`."""
    assert reflex.traces_dir() == trace_mod.TRACES_DIR


# --- the report ----------------------------------------------------------------


def test_the_report_reads_the_ledger_and_the_tap_by_arm(tmp_path, served, monkeypatch):
    _fire(tmp_path)
    _fire(tmp_path)  # deduped
    monkeypatch.setattr(retrieval, "recall", _fake_recall([]))
    _fire(tmp_path, session_id="s2")  # empty

    report = reflex_report(reflex_base=tmp_path / "reflex", traces_base=tmp_path / "traces")
    rendered = report.render()

    assert report.firings == 3 and report.sessions == 2
    assert report.outcomes == {"served": 1, "deduped": 1, "empty": 1}
    assert report.by_arm == {ARM_LEXICAL: 2} and report.tap_misses == {ARM_LEXICAL: 1}
    assert "qualifying failures: 3 over 2 session(s)" in rendered
    assert "served per qualifying failure: 1/3" in rendered
    assert "reflex_lexical: 2 (1 misses)" in rendered
    assert "graph not read" in rendered


def test_the_report_gives_each_plan_its_own_denominators_and_effort(tmp_path, spread):
    """
    Verifications:
    - outcomes are counted per plan over the firings that took one; a deduped firing
      belongs to none
    - each arm's trace numbers — calls, nodes, wall time, records served — are read per
      arm, and records the spread reached only for the arm that spreads
    """
    spread[("scope:main:session:abc", "same_file")] = [_decision("scope:main:claim:d1")]
    _fire(tmp_path, plan=ARM_PROPAGATION)
    _fire(tmp_path, plan=ARM_PROPAGATION)  # deduped
    _fire(tmp_path, session_id="s2")

    report = reflex_report(reflex_base=tmp_path / "reflex", traces_base=tmp_path / "traces")
    rendered = report.render()

    assert report.by_plan == {ARM_PROPAGATION: {"served": 1}, ARM_LEXICAL: {"served": 1}}
    assert report.effort[ARM_PROPAGATION]["records"] == [2]
    assert report.effort[ARM_PROPAGATION]["linked"] == [1]
    assert report.effort[ARM_LEXICAL]["records"] == [1]
    assert "linked" not in report.effort[ARM_LEXICAL]
    assert "  reflex_propagation: 1 served / 0 empty / 0 refused" in rendered
    assert "records served 2/2/2 (n=1); of them reached by the spread 1/1/1 (n=1)" in rendered


def test_the_event_is_recorded_on_every_firing_and_the_report_splits_by_it(
    tmp_path, served, monkeypatch
):
    """
    Verifications:
    - the event reaches the ledger row on a served firing and on one that retrieved
      nothing, and the trace line of a firing that retrieved
    - a row with no event (written before it was recorded) is its own population,
      never folded into either event
    """
    _fire(tmp_path, event="PostToolUseFailure")
    monkeypatch.setattr(retrieval, "recall", _fake_recall([]))
    _fire(tmp_path, session_id="s2", event="PostToolUse")
    _fire(tmp_path, session_id="s3")

    assert [row.event for row in load_firings("s1", tmp_path / "reflex")] == [
        "PostToolUseFailure"]
    assert [line["tool_input"]["event"] for line in _tap_lines(tmp_path)
            if line["tool_name"] == ARM_LEXICAL] == ["PostToolUseFailure", "PostToolUse", ""]

    report = reflex_report(reflex_base=tmp_path / "reflex", traces_base=tmp_path / "traces")
    rendered = report.render()

    assert report.by_event == {"PostToolUseFailure": 1, "PostToolUse": 1, "": 1}
    assert report.served_by_event == {"PostToolUseFailure": 1}
    assert "PostToolUseFailure (non-zero exit): 1 / 1" in rendered
    assert "PostToolUse (exit 0): 0 / 1" in rendered
    assert "unrecorded (exit 0 only; written before the event was recorded): 0 / 1" in rendered


def test_a_shadowed_call_records_its_anchors_and_never_touches_the_graph(
    tmp_path, monkeypatch
):
    """
    Verifications:
    - the row carries the anchors `fire` would have extracted, the event, and whether
      they clear the query gate against this agent's live firings
    - keys a live firing already spent count as seen; another agent's do not
    - nothing is recalled, served, or written to the trace tap
    """
    def no_recall(*_args, **_kwargs):
        raise AssertionError("shadow must not retrieve")

    monkeypatch.setattr(retrieval, "recall", no_recall)
    observed = "src/thalamus/harness/reflex.py: MIN_NEW_ANCHORS SESSION_CHAR_BUDGET\n"

    fresh = reflex.shadow(session_id="s1", observed=observed, event="PostToolUse",
                          now=_NOW, reflex_base=tmp_path / "reflex")
    assert fresh.anchors == extract_anchors(observed) and len(fresh.anchors) >= 2
    assert fresh.fresh == len(fresh.anchors) and fresh.would_query
    assert fresh.output_chars == len(observed)

    # A live firing by the same agent spends the keys; the shadow row then sees them.
    spent = Firing(ts="t", session_id="s1", agent_id="", outcome="served",
                   keys=fresh.keys)
    reflex._append_firing(spent, tmp_path / "reflex")
    again = reflex.shadow(session_id="s1", observed=observed, event="PostToolUse",
                          now=_NOW, reflex_base=tmp_path / "reflex")
    other = reflex.shadow(session_id="s1", observed=observed, agent_id="a-9",
                          event="PostToolUse", now=_NOW, reflex_base=tmp_path / "reflex")

    assert again.fresh == 0 and not again.would_query
    assert other.would_query
    assert len(reflex.load_shadow(tmp_path / "reflex")) == 3
    assert not (tmp_path / "traces").exists()


def test_the_report_counts_the_shadowed_population_by_event(tmp_path):
    base = tmp_path / "reflex"
    reflex.shadow(session_id="s1", observed="MIN_NEW_ANCHORS SESSION_CHAR_BUDGET\n",
                  event="PostToolUse", now=_NOW, reflex_base=base)
    reflex.shadow(session_id="s1", observed="3 passed in 0.2s\n",
                  event="PostToolUse", now=_NOW, reflex_base=base)
    reflex.shadow(session_id="s2", observed="Exit code 1\n",
                  event="PostToolUseFailure", now=_NOW, reflex_base=base)

    report = reflex_report(reflex_base=base, traces_base=tmp_path / "traces")
    rendered = report.render()

    assert report.shadowed == {"PostToolUse": 2, "PostToolUseFailure": 1}
    assert report.shadow_would_query == {"PostToolUse": 1}
    assert "PostToolUse (exit 0): 2 / 1 / 1" in rendered
    assert "PostToolUseFailure (non-zero exit): 1 / 0 / 0" in rendered


def test_the_report_says_so_when_nothing_has_fired(tmp_path):
    assert "No reflex firings yet" in reflex_report(
        reflex_base=tmp_path / "none", traces_base=tmp_path / "none"
    ).render()


# --- the hook ------------------------------------------------------------------


def _stub_uv(tmp_path, prints="", copy_response=True):
    """A `uv` that records its argv and hands back a canned envelope."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    argv_log = tmp_path / "uv-argv.txt"
    seen = tmp_path / "uv-response.txt"
    stub = bin_dir / "uv"
    body = [
        "#!/bin/bash",
        f'printf "%s\\n" "$*" >> "{argv_log}"',
    ]
    if copy_response:
        # Copied then renamed, so a detached run's reader sees the whole file or none.
        body.append(
            'while [ $# -gt 0 ]; do [ "$1" = "--response-file" ] && cp "$2" '
            f'"{seen}.part" && mv "{seen}.part" "{seen}"; shift; done'
        )
    if prints:
        body.append(f"printf '%s' {json.dumps(prints)}")
    stub.write_text("\n".join(body) + "\n")
    stub.chmod(0o755)
    return bin_dir, argv_log, seen


def _run_hook(payload, home, bin_dir, **env):
    return subprocess.run(
        [str(HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=30,
        env={"HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin", **env},
    )


def _await(condition, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out waiting on the detached shadow run"
        time.sleep(0.02)


def _await_argv(argv_log):
    """The detached shadow child's argv, once it has written it."""
    _await(lambda: argv_log.exists() and argv_log.read_text().endswith("\n"))
    return argv_log.read_text()


def _bash_call(stdout="", stderr="", interrupted=False, **overrides):
    payload = {
        "hook_event_name": "PostToolUse", "session_id": "cc-1", "cwd": "/w",
        "tool_name": "Bash", "tool_input": {"command": "uv run pytest"},
        "tool_response": {"stdout": stdout, "stderr": stderr,
                          "interrupted": interrupted, "isImage": False},
        "agent_id": "", "agent_type": "",
    }
    payload.update(overrides)
    return payload


def _failed_bash_call(error, is_interrupt=False, **overrides):
    """A `PostToolUseFailure` payload as Claude Code 2.1.281 delivered it for
    `python3 -c '…; sys.exit(3)'`: no `tool_response`, the output in `error`."""
    payload = {
        "hook_event_name": "PostToolUseFailure", "session_id": "cc-1", "cwd": "/w",
        "tool_name": "Bash", "tool_input": {"command": "uv run pytest"},
        "tool_use_id": "toolu_1", "error": error, "is_interrupt": is_interrupt,
        "duration_ms": 60,
    }
    payload.update(overrides)
    return payload


class TestTheHook:
    def test_a_failure_is_handed_to_the_worker_and_its_answer_injected(self, tmp_path):
        """
        Verifications:
        - the worker is reached through `uv run --project <checkout>` with the
          resolved fields as flags and the bulk output by file
        - the file holds stdout then stderr, as the model saw them
        - the worker's stdout becomes the hook's additionalContext, verbatim
        """
        bin_dir, argv_log, seen = _stub_uv(tmp_path, prints="Thalamus memory reflex: hi")

        result = _run_hook(
            _bash_call(stdout=PYTEST_FAILURE, stderr="warning: slow"), tmp_path, bin_dir,
        )

        assert result.returncode == 0, result.stderr
        out = json.loads(result.stdout)["hookSpecificOutput"]
        assert out == {"hookEventName": "PostToolUse",
                       "additionalContext": "Thalamus memory reflex: hi"}
        argv = argv_log.read_text()
        checkout = str(HOOK.parents[5])
        assert f"run --project {checkout} thalamus reflex" in argv
        assert "--session-id cc-1" in argv and "--scope main" in argv
        assert "--cwd /w" in argv and "--tool-name Bash --event PostToolUse " in argv
        assert "--response-file " in argv
        # `$(jq …)` strips a trailing newline; the hook puts one back between and after.
        assert seen.read_text() == PYTEST_FAILURE.rstrip("\n") + "\nwarning: slow\n"

    def test_clean_output_is_shadow_logged_off_the_agents_path(self, tmp_path):
        """
        Verifications:
        - the hook injects nothing and hands the output to `--shadow`, never to a
          retrieving worker
        - the shadow run is detached: the hook has returned before it finishes, and
          the child removes the response file itself
        """
        bin_dir, argv_log, seen = _stub_uv(tmp_path, prints="should not appear")

        result = _run_hook(_bash_call(stdout="3 passed in 0.2s\n"), tmp_path, bin_dir)

        assert result.returncode == 0 and result.stdout == ""
        argv = _await_argv(argv_log)
        assert "thalamus reflex --shadow" in argv
        assert "--event PostToolUse " in argv and "--scope" not in argv
        # The stub logs argv before it copies the response, and it runs detached; the
        # file can exist before `cp` has finished writing it, so wait on the content.
        _await(lambda: seen.exists() and seen.read_text() == "3 passed in 0.2s\n")
        response = argv.split("--response-file ")[1].split()[0]
        _await(lambda: not Path(response).exists())

    def test_an_interrupted_call_fires_with_nothing_legible_printed(self, tmp_path):
        """The one exact signal in the payload: a hard kill flushes no traceback."""
        bin_dir, argv_log, _ = _stub_uv(tmp_path, prints="ctx")

        result = _run_hook(_bash_call(stdout="", interrupted=True), tmp_path, bin_dir)

        assert json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"] == "ctx"
        assert "thalamus reflex" in argv_log.read_text()

    def test_a_silent_worker_injects_nothing(self, tmp_path):
        bin_dir, argv_log, _ = _stub_uv(tmp_path, prints="")

        result = _run_hook(_bash_call(stdout=PYTEST_FAILURE), tmp_path, bin_dir)

        assert result.returncode == 0 and result.stdout == ""
        assert argv_log.exists()

    def test_the_subagent_that_ran_the_command_is_named(self, tmp_path):
        bin_dir, argv_log, _ = _stub_uv(tmp_path)

        _run_hook(_bash_call(stdout=PYTEST_FAILURE, agent_id="a-9",
                             agent_type="general-purpose"), tmp_path, bin_dir)

        argv = argv_log.read_text()
        assert "--agent-id a-9" in argv and "--agent-type general-purpose" in argv

    def test_the_sandbox_never_fires(self, tmp_path):
        bin_dir, argv_log, _ = _stub_uv(tmp_path, prints="ctx")

        result = _run_hook(_bash_call(stdout=PYTEST_FAILURE), tmp_path, bin_dir,
                           THALAMUS_SANDBOX="1")

        assert result.stdout == "" and not argv_log.exists()

    def test_a_nonzero_exit_fires_on_the_failure_event_and_answers_on_it(self, tmp_path):
        """
        Verifications:
        - the `error` string is the output the failure test reads and the worker gets
        - the answer is addressed to the event that ran the hook, not `PostToolUse`
        """
        bin_dir, argv_log, seen = _stub_uv(tmp_path, prints="ctx")
        error = "Exit code 1\n" + PYTEST_FAILURE.rstrip("\n")

        result = _run_hook(_failed_bash_call(error), tmp_path, bin_dir)

        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["hookSpecificOutput"] == {
            "hookEventName": "PostToolUseFailure", "additionalContext": "ctx"}
        assert "--tool-name Bash --event PostToolUseFailure " in argv_log.read_text()
        assert seen.read_text() == error + "\n"

    def test_a_nonzero_exit_with_nothing_legible_does_not_fire(self, tmp_path):
        """The exit status alone is not the failure test: `grep` finding nothing is
        exit 1. Control for the test above — same event, output that reads clean."""
        bin_dir, argv_log, _ = _stub_uv(tmp_path, prints="ctx")

        result = _run_hook(_failed_bash_call("Exit code 1\n"), tmp_path, bin_dir)

        assert result.returncode == 0 and result.stdout == ""
        argv = _await_argv(argv_log)
        assert "--shadow" in argv and "--event PostToolUseFailure " in argv

    def test_an_aborted_call_on_the_failure_event_fires(self, tmp_path):
        bin_dir, argv_log, _ = _stub_uv(tmp_path, prints="ctx")

        result = _run_hook(_failed_bash_call("Exit code 137\n", is_interrupt=True),
                           tmp_path, bin_dir)

        assert json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"] == "ctx"
        assert argv_log.exists()

    def test_other_tools_are_not_the_surface(self, tmp_path):
        bin_dir, argv_log, _ = _stub_uv(tmp_path, prints="ctx")

        result = _run_hook(_bash_call(stdout=PYTEST_FAILURE, tool_name="Read"),
                           tmp_path, bin_dir)

        assert result.stdout == "" and not argv_log.exists()


# --- citation through a handle -------------------------------------------------


def test_a_cited_handle_resolves_to_the_node_it_stands_for():
    """
    Verifications:
    - an output naming `R1.1` is a citation of the node the digest showed under it,
      recorded as such, where the vertex id itself never appears
    - a handle is matched as itself: `R1.1` is not cited by `R1.10` or `XR1.1`
    - control: with no handle map the same output cites nothing, so the verdict
      above comes from the map and not from the words
    """
    node = "scope:main:session:abc"
    [verdict] = attribute({node: "zzz qqq"}, "as R1.1 records, the cap moved",
                          handles={"R1.1": node})
    assert verdict.used and verdict.evidence == "cited by handle R1.1"

    assert cites_handle("R1.1", "see r1.1.")
    assert not cites_handle("R1.1", "see r1.10")
    assert not cites_handle("R1.1", "see xr1.1")

    [control] = attribute({node: "zzz qqq"}, "as R1.1 records, the cap moved")
    assert not control.used


def test_a_trace_prices_what_entered_context_and_falls_back_to_the_response():
    reflex_line = trace_mod.TraceEvent(
        ts=_NOW, session_id="s1", cwd="/w", tool=ARM_LEXICAL,
        tool_input={"delivered_chars": 12, "handles": {"R1.1": "scope:main:session:abc"}},
        tool_response="x" * 500,
    )
    recall_line = trace_mod.TraceEvent(
        ts=_NOW, session_id="s1", cwd="/w", tool="memory_recall", tool_response="x" * 500,
    )
    assert reflex_line.injected_chars() == 12
    assert reflex_line.handles() == {"R1.1": "scope:main:session:abc"}
    assert recall_line.injected_chars() == 500 and recall_line.handles() == {}


# --- the pointer-file tap ------------------------------------------------------


def _run_tap(payload, home, **env):
    return subprocess.run(
        [str(POINTER_TAP)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=30,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin", **env},
    )


class TestThePointerTap:
    def _pointer(self, home, session="s1", firing="R2"):
        path = home / ".thalamus" / "reflex" / "pointers" / session / f"{firing}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# records\n- R2.1: `scope:main:session:abc`\n")
        return path

    def test_a_read_of_a_pointer_file_is_a_trace_line_carrying_its_records(self, tmp_path):
        """
        Verifications:
        - a `Read` naming a pointer file writes one `reflex_pointer_open` line in the
          tap's schema, the file's records as its response, joined by the pointer path
        - `eval sync`'s loader keeps it and recovers the node the read put in context
        - `eval reflex` counts it against the served digest it opened, not as an arm
        """
        pointer = self._pointer(tmp_path)
        payload = {"session_id": "s1", "cwd": "/w", "tool_name": "Read",
                   "tool_input": {"file_path": str(pointer)}, "tool_response": {},
                   "agent_id": "", "agent_type": ""}

        result = _run_tap(payload, tmp_path)

        assert result.returncode == 0, result.stderr
        assert result.stdout == ""
        events = trace_mod.load_events(tmp_path / ".thalamus" / "traces")
        assert [event.tool for event in events] == [POINTER_OPEN]
        assert events[0].tool_input == {"firing_id": "R2", "pointer": str(pointer),
                                        "via": "Read"}
        assert events[0].returned_node_ids() == ["scope:main:session:abc"]

        served = trace_mod.TraceEvent(
            ts=_NOW, session_id="s1", cwd="/w", tool=ARM_LEXICAL,
            tool_input={"pointer": str(pointer), "delivered_chars": 300},
            tool_response="`scope:main:session:abc`",
        )
        with (tmp_path / ".thalamus" / "traces" / "2026-09.jsonl").open("a") as handle:
            handle.write(json.dumps({
                "ts": "2026-09-13T12:00:00Z", "session_id": "s1", "cwd": "/w",
                "tool_name": served.tool, "tool_input": served.tool_input,
                "tool_response": served.tool_response,
            }) + "\n")
        ledger = tmp_path / "reflex" / "sessions" / "s1.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(Firing(ts="2026-09-13T12:00:00Z", session_id="s1", agent_id="",
                                 outcome="served", firing_id="R2").to_json() + "\n")
        report = reflex_report(reflex_base=tmp_path / "reflex",
                               traces_base=tmp_path / ".thalamus" / "traces")
        assert report.by_arm == {ARM_LEXICAL: 1}
        assert report.opens == 1 and report.opened == {str(pointer)}
        assert report.spilled == 0
        assert "pointer files opened per served digest: 1/1" in report.render()

    def test_a_bash_read_counts_and_a_path_only_in_the_output_does_not(self, tmp_path):
        pointer = self._pointer(tmp_path)
        traces = tmp_path / ".thalamus" / "traces"

        _run_tap({"session_id": "s1", "tool_name": "Bash",
                  "tool_input": {"command": "ls ~/.thalamus/reflex/pointers/s1"},
                  "tool_response": {"stdout": str(pointer)}}, tmp_path)
        assert not traces.exists()

        _run_tap({"session_id": "s1", "tool_name": "Bash",
                  "tool_input": {"command": f"sed -n 1,40p {pointer}"},
                  "tool_response": {"stdout": "..."}}, tmp_path)
        events = trace_mod.load_events(traces)
        assert [event.tool_input["via"] for event in events] == ["Bash"]

    def test_a_call_that_names_no_pointer_exits_before_anything_runs(self, tmp_path):
        result = _run_tap({"session_id": "s1", "tool_name": "Read",
                           "tool_input": {"file_path": "/w/README.md"}}, tmp_path,
                          PATH="/nonexistent")
        assert result.returncode == 0 and result.stdout == ""
        assert not (tmp_path / ".thalamus").exists()

    def test_the_sandbox_never_records(self, tmp_path):
        pointer = self._pointer(tmp_path)
        _run_tap({"session_id": "s1", "tool_name": "Read",
                  "tool_input": {"file_path": str(pointer)}}, tmp_path, THALAMUS_SANDBOX="1")
        assert not (tmp_path / ".thalamus" / "traces").exists()


@pytest.mark.parametrize("cap", [600, 700, 900, 1_300, 2_000])
def test_the_rendered_digest_is_within_the_cap_it_was_packed_against(cap):
    """The closing count and the block separator are paid for up front, so no cap —
    one that holds lines back or one that holds none — renders a digest past it.
    Control: the frame alone is far under every cap here, so the bound is exercised
    by the lines and not by an oversized frame."""
    frame = render_envelope([], ["alpha-one", "beta-two"], pointer="/p/R1.md")
    assert len(frame) < 600
    lines = [f"R1.{index} · session · tier 1 · " + "x" * (40 + index * 7) for index in range(1, 30)]

    kept, held = reflex.pack_digest(lines, cap, frame)
    digest = render_envelope(kept[::-1], ["alpha-one", "beta-two"], pointer="/p/R1.md")

    assert len(digest) <= cap
    assert held == len(lines) - len([line for line in kept if line.startswith("R1.")])
