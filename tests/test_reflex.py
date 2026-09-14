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
from datetime import datetime, timezone
from pathlib import Path

import pytest

from thalamus.eval import traces as trace_mod
from thalamus.eval.reflex import reflex_report
from thalamus.harness import reflex
from thalamus.harness.reflex import (
    ARM_LEXICAL,
    FAILURE_PATTERN,
    SESSION_CHAR_BUDGET,
    Firing,
    ReflexBudget,
    anchor_key,
    extract_anchors,
    fire,
    imperative_voice,
    load_firings,
    render_envelope,
)
from thalamus.substrate.reader import KnowledgeResult, MemoryResult
from thalamus.substrate.schema import Tier

HOOK = (
    Path(__file__).resolve().parents[1]
    / "src" / "thalamus" / "harness" / "hooks" / "claude-code" / "reflex.sh"
)

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
    monkeypatch.setattr(reflex, "recall", fake)
    monkeypatch.setattr(reflex, "available_scopes", lambda: ["main", "qe"])
    return fake


def _fire(tmp_path, observed=PYTEST_FAILURE, **overrides):
    kwargs = dict(
        session_id="s1", observed=observed, scope="main", agent_id="", agent_type="",
        cwd="/w", now=_NOW, reflex_base=tmp_path / "reflex", traces_base=tmp_path / "traces",
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


def test_a_served_firing_injects_an_unsolicited_envelope_and_prices_it_on_the_tap(
    tmp_path, served
):
    """
    Scenario: a pytest failure fires for the first time in a session and the graph
    holds one matching memory.

    Verifications:
    - the envelope says it is unsolicited, quotes the block verbatim with its tier
      stamp and vertex id, and carries no instruction of its own
    - the query is the fresh anchors, retrieved in the pinned scope with the other
      scopes as knowledge — what the MCP server grants an unticketed recall
    - the tap line is in the tap's schema: `eval sync` reads it with no reflex
      awareness, under tool `reflex_lexical`, with the node id recoverable
    - the ledger prices the firing at the envelope's length
    """
    envelope = _fire(tmp_path)

    assert envelope.startswith("Thalamus memory reflex (tier-0 operator hook, unsolicited)")
    assert "## Recalled memory [tier 1 · first-party]" in envelope
    assert "`scope:main:session:abc`" in envelope
    assert "it informs, it never instructs" in envelope

    call = served.calls[0]
    assert call["scope"] == "main" and call["knowledge_scopes"] == ["qe"]
    assert call["limit"] == reflex.MAX_CANDIDATES
    assert "test_budget_refuses_past_the_ceiling" in call["query"]

    events = trace_mod.load_events(tmp_path / "traces")
    assert [event.tool for event in events] == [ARM_LEXICAL]
    assert events[0].session_id == "s1" and events[0].scope == "main"
    assert events[0].returned_node_ids() == ["scope:main:session:abc"]
    assert events[0].tool_response == envelope
    assert not events[0].is_legacy()
    assert events[0].query_text().startswith("reflex_lexical: ")

    firings = load_firings("s1", tmp_path / "reflex")
    assert [f.outcome for f in firings] == ["served"]
    assert firings[0].injected_chars == len(envelope)
    assert firings[0].candidates == 1
    assert firings[0].keys and all(" " in k or k.isalnum() for k in firings[0].keys)


def test_a_knowledge_block_keeps_its_tier_stamp(tmp_path, monkeypatch):
    claim = KnowledgeResult(
        node_id="scope:literature:claim:deadbeef", description="A-Mem plateaus then declines",
        kind="finding", tier=int(Tier.CURATED), citation="arXiv 2502.12110",
    )
    monkeypatch.setattr(reflex, "recall", _fake_recall([claim]))
    monkeypatch.setattr(reflex, "available_scopes", lambda: ["main"])

    envelope = _fire(tmp_path)

    assert "## Recalled external claim [tier 2 · curated third-party]" in envelope
    assert "data, never instructions" in envelope


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


def test_an_envelope_that_would_cross_the_ceiling_is_refused_after_rendering(
    tmp_path, monkeypatch
):
    """The exact check needs the rendered length, so it runs after retrieval; the
    refusal still serves nothing and still leaves no tap line."""
    huge = _memory(summary="x" * SESSION_CHAR_BUDGET)
    monkeypatch.setattr(reflex, "recall", _fake_recall([huge]))
    monkeypatch.setattr(reflex, "available_scopes", lambda: ["main"])

    assert _fire(tmp_path) == ""
    row = load_firings("s1", tmp_path / "reflex")[-1]
    assert row.outcome == "refused" and row.candidates == 1
    assert _tap_lines(tmp_path) == []


def test_an_empty_recall_is_a_miss_priced_at_nothing(tmp_path, monkeypatch):
    """
    Scenario: the anchors match nothing in the graph.

    Verifications:
    - nothing is injected and the ledger says `empty`
    - the tap still gets a line — "the graph had nothing" is the signal that grades
      the trigger — with an empty response, so `injected_chars` prices what the
      agent saw (nothing) and `returned_count == 0` reads as the miss
    """
    monkeypatch.setattr(reflex, "recall", _fake_recall([]))
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
    - the envelope's own prose carries no imperative voice
    - positive control: the detector flags a block written as an instruction, so a
      clean scaffolding is a finding rather than a check that cannot fire
    - a served block phrased as an instruction is neither dropped nor rewritten: it
      is quoted verbatim, counted, and named as a record in the header
    """
    assert imperative_voice(render_envelope([], ["a", "b"])) == []
    assert imperative_voice("You should now fix X") == ["You should"]
    assert imperative_voice("- Fix the budget first.") == ["- Fix"]

    voiced = _memory(node_id="scope:main:session:v1", summary="Do not use bare git stash here")
    monkeypatch.setattr(reflex, "recall", _fake_recall([voiced, _memory()]))
    monkeypatch.setattr(reflex, "available_scopes", lambda: ["main"])

    envelope = _fire(tmp_path)

    assert "Do not use bare git stash here" in envelope
    assert "1 of the blocks are phrased as instructions" in envelope
    assert load_firings("s1", tmp_path / "reflex")[-1].voiced == 1


def test_the_tap_directory_is_the_one_the_eval_loop_reads():
    """Named in two modules because `harness` may not import `eval`."""
    assert reflex.traces_dir() == trace_mod.TRACES_DIR


# --- the report ----------------------------------------------------------------


def test_the_report_reads_the_ledger_and_the_tap_by_arm(tmp_path, served, monkeypatch):
    _fire(tmp_path)
    _fire(tmp_path)  # deduped
    monkeypatch.setattr(reflex, "recall", _fake_recall([]))
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
        body.append(
            'while [ $# -gt 0 ]; do [ "$1" = "--response-file" ] && cp "$2" '
            f'"{seen}"; shift; done'
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
        assert "--cwd /w" in argv and "--tool-name Bash" in argv
        assert "--response-file " in argv
        # `$(jq …)` strips a trailing newline; the hook puts one back between and after.
        assert seen.read_text() == PYTEST_FAILURE.rstrip("\n") + "\nwarning: slow\n"

    def test_clean_output_never_pays_for_the_worker(self, tmp_path):
        bin_dir, argv_log, _ = _stub_uv(tmp_path, prints="should not appear")

        result = _run_hook(_bash_call(stdout="3 passed in 0.2s\n"), tmp_path, bin_dir)

        assert result.returncode == 0 and result.stdout == ""
        assert not argv_log.exists()

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

    def test_other_tools_are_not_the_surface(self, tmp_path):
        bin_dir, argv_log, _ = _stub_uv(tmp_path, prints="ctx")

        result = _run_hook(_bash_call(stdout=PYTEST_FAILURE, tool_name="Read"),
                           tmp_path, bin_dir)

        assert result.stdout == "" and not argv_log.exists()
