"""
Memory reflex worker tests — the agentic plan's queue, worker, carrier and model loop.

Interfaces: thalamus.harness.transcripts (excerpt_for_job, tool_calls_after),
            thalamus.harness.extraction.run_tool_loop, thalamus.harness.agentic,
            thalamus.harness.reflex_queue, thalamus.harness.reflex_worker (run_job,
            work, deliver, sweep), reflex.fire on the agentic arm, the carrier half of
            reflex-pointer-tap.sh driven live with a stubbed `uv`
Infrastructure: tmp_path as $HOME and as the queue root; the model's HTTP endpoint
                replaced by a scripted urlopen; the plan, the graph reads and the
                session registry replaced by fakes. No graph, no model.
Scope: what a queued firing becomes — ready, delivered, or recorded with the reason it
       was not — and the controls around it: the wall clock, liveness, the budget,
       coalescing, torn lines and a dead worker's claim. The plan's retrieval quality
       is not tested here; `eval reflex` reads it per plan on live firings.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from thalamus.harness import (
    agentic,
    extraction,
    reflex,
    reflex_note,
    reflex_queue,
    reflex_worker,
)
from thalamus.harness.agents import cli_for
from thalamus.harness.extraction import StopLoop, run_tool_loop
from thalamus.harness.reflex import ARM_AGENTIC, SESSION_CHAR_BUDGET, Firing, load_firings
from thalamus.harness.transcripts import excerpt_for_job, tool_calls_after
from thalamus.substrate.reader import MemoryResult
from thalamus.substrate.vocabulary import Row

TAP = (
    Path(__file__).resolve().parents[1]
    / "src" / "thalamus" / "harness" / "hooks" / "claude-code" / "reflex-pointer-tap.sh"
)
_NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
FAILURE = "FAILED tests/test_budget.py::test_ceiling - AssertionError: reflex_budget over\n"


# --- the excerpt builder --------------------------------------------------------


def _transcript(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def _user(text, **extra):
    return {"type": "user", "message": {"content": text}, **extra}


def _call(use_id, name="Bash", command="pytest", **extra):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": use_id, "name": name, "input": {"command": command}},
    ]}, **extra}


def _result(use_id, text, **extra):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": use_id, "content": text},
    ]}, **extra}


def test_the_excerpt_keeps_the_agents_turns_and_the_trigger_and_labels_other_results(tmp_path):
    path = _transcript(tmp_path / "t.jsonl", [
        _user("fix the reflex budget test"),
        _call("t1", name="Read", command="x"),
        _result("t1", "SECRET FILE CONTENTS"),
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Running it."}]}},
        _call("t2"),
        _result("t2", FAILURE),
    ])
    excerpt = excerpt_for_job(path, {"t2"})
    assert "[user] fix the reflex budget test" in excerpt.text
    assert "[tool_result: Read]" in excerpt.text
    assert "SECRET FILE CONTENTS" not in excerpt.text
    assert "[assistant] Running it." in excerpt.text
    assert "reflex_budget over" in excerpt.text
    assert excerpt.found == {"t2"}


def test_the_excerpt_skips_sidechain_records_in_the_parent_and_keeps_them_in_a_subagents_file(tmp_path):
    records = [_user("parent prompt"), _call("s1", isSidechain=True),
               _result("s1", FAILURE, isSidechain=True)]
    path = _transcript(tmp_path / "t.jsonl", records)
    assert excerpt_for_job(path, {"s1"}).found == set()
    assert excerpt_for_job(path, {"s1"}, sidechain=True).found == {"s1"}


def test_the_excerpt_drops_the_oldest_items_first(tmp_path):
    path = _transcript(tmp_path / "t.jsonl", [_user("old " * 50), _user("newest prompt")])
    text = excerpt_for_job(path, set(), max_chars=40).text
    assert text == "[user] newest prompt"


def test_delivery_depth_counts_the_calls_after_the_trigger(tmp_path):
    path = _transcript(tmp_path / "t.jsonl", [_call("a"), _call("b"), _call("c")])
    assert tool_calls_after(path, "a") == 2
    assert tool_calls_after(path, "c") == 0
    assert tool_calls_after(path, "missing") is None


# --- the model loop --------------------------------------------------------------


def _script(monkeypatch, replies):
    """urlopen answering each request with the next scripted /api/chat reply."""
    sent = []

    def urlopen(request, timeout=None):
        sent.append(json.loads(request.data))
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return io.BytesIO(json.dumps(reply).encode())

    monkeypatch.setattr(extraction.urllib.request, "urlopen", urlopen)
    return sent


def _reply(*calls, content=""):
    return {
        "message": {"role": "assistant", "content": content, "tool_calls": [
            {"function": {"name": name, "arguments": args}} for name, args in calls
        ]},
        "load_duration": 2_000_000, "total_duration": 50_000_000,
        "prompt_eval_count": 100, "eval_count": 10,
    }


def test_the_loop_runs_each_call_and_ends_on_the_stop_tool(monkeypatch):
    sent = _script(monkeypatch, [
        _reply(("lexical_by_kind", {"query": "a b", "kind": "session"})),
        _reply(("stop", {"keep": [], "reason": "none"})),
    ])
    ran = []

    def execute(name, args):
        if name == "stop":
            raise StopLoop
        ran.append(name)
        return "no results"

    run = run_tool_loop(cli_for("local"), "m", [], [{"role": "user", "content": "x"}],
                        execute=execute, deadline=time.monotonic() + 30, max_turns=5)
    assert run.stopped == "stop_tool"
    assert ran == ["lexical_by_kind"]
    assert len(run.turns) == 2 and run.turns[0].load_ms == 2 and run.turns[0].total_ms == 50
    assert sent[0]["think"] is False and sent[0]["options"]["num_predict"] > 0
    assert sent[1]["messages"][-1] == {"role": "tool", "tool_name": "lexical_by_kind",
                                       "content": "no results"}


def test_the_loop_ends_on_a_reply_with_no_calls_and_on_its_turn_cap(monkeypatch):
    _script(monkeypatch, [_reply(content="done")])
    run = run_tool_loop(cli_for("local"), "m", [], [], execute=lambda n, a: "",
                        deadline=time.monotonic() + 30, max_turns=5)
    assert run.stopped == "no_tool_calls"

    _script(monkeypatch, [_reply(("by_path", {"path": "x"}))] * 2)
    run = run_tool_loop(cli_for("local"), "m", [], [], execute=lambda n, a: "",
                        deadline=time.monotonic() + 30, max_turns=2)
    assert run.stopped == "max_turns" and len(run.turns) == 2


def test_the_loop_stops_before_a_turn_once_the_session_is_gone_or_time_is_up(monkeypatch):
    sent = _script(monkeypatch, [_reply(("by_path", {"path": "x"}))])
    alive = iter([True, False])
    run = run_tool_loop(cli_for("local"), "m", [], [], execute=lambda n, a: "",
                        deadline=time.monotonic() + 30, max_turns=5,
                        alive=lambda: next(alive))
    assert run.stopped == "session_end" and len(sent) == 1

    sent = _script(monkeypatch, [])
    run = run_tool_loop(cli_for("local"), "m", [], [], execute=lambda n, a: "",
                        deadline=time.monotonic() - 1, max_turns=5)
    assert run.stopped == "deadline" and sent == []


# --- the plan ---------------------------------------------------------------------


class _Job:
    """A compiler job with fixed handles; `call` records and answers."""

    def __init__(self, handles):
        self.handles = dict(handles)
        self.calls = 0
        self.seen = []

    def call(self, name, args):
        self.calls += 1
        self.seen.append((name, args))
        return "R1.1 · session · tier 1 · 2026-09-01 · a record"


def test_the_plan_keeps_the_models_handles_in_order_and_records_the_stop(monkeypatch):
    job = _Job({"R1.1": "v1", "R1.2": "v2", "R1.3": "v3"})
    _script(monkeypatch, [
        _reply(("lexical_by_kind", {"missing": "the budget decision",
                                    "query": "reflex, budget", "kind": "decision"})),
        _reply(("stop", {"keep": ["R1.2", "R1.1", "R1.2", "R9.9"], "reason": "both bear",
                         "note": " The budget was set at 24k [R1.2]. "})),
    ])
    result = agentic.run(job, cli=cli_for("local"), model="m", anchors=["reflex_budget"],
                         excerpt="x", deadline=time.monotonic() + 30)
    assert result.stopped == "stop_tool" and result.reason == "both bear"
    assert result.note == "The budget was set at 24k [R1.2]."
    assert result.kept == ["v2", "v1"]
    assert result.unknown_kept == ["R9.9"]
    # `missing` is the stop log's, never an argument the compiler sees; commas are spacing.
    assert job.seen == [("lexical_by_kind", {"query": "reflex budget", "kind": "decision"})]
    assert result.hops[0].missing == "the budget decision"


def test_a_loop_the_caps_end_packs_what_it_returned_and_one_with_no_selection_packs_nothing(monkeypatch):
    job = _Job({f"R1.{n}": f"v{n}" for n in range(1, 8)})
    _script(monkeypatch, [_reply(("by_path", {"missing": "m", "path": "x"}))] * agentic.MAX_TURNS)
    result = agentic.run(job, cli=cli_for("local"), model="m", anchors=[], excerpt="",
                         deadline=time.monotonic() + 30)
    assert result.stopped == "max_turns"
    assert result.kept == [f"v{n}" for n in range(1, agentic.MAX_KEEP + 1)]

    _script(monkeypatch, [_reply(content="nothing here")])
    result = agentic.run(_Job({"R1.1": "v1"}), cli=cli_for("local"), model="m",
                         anchors=[], excerpt="", deadline=time.monotonic() + 30)
    assert result.stopped == "no_tool_calls" and result.kept == []


def test_every_vocabulary_tool_is_offered_with_a_required_statement_of_what_is_missing():
    schemas = {s["function"]["name"]: s["function"] for s in agentic.tool_schemas()}
    assert set(schemas) == set(agentic.TOOLS) | {"stop"}
    for name in agentic.TOOLS:
        assert "missing" in schemas[name]["parameters"]["required"]
    assert schemas["stop"]["parameters"]["required"] == ["keep", "reason"]


# --- the queue ----------------------------------------------------------------------


def _job_line(session="s1", agent="", ts="2026-09-24T12:00:00Z", use_id="t1", **extra):
    return {"ts": ts, "session_id": session, "agent_id": agent, "scope": "main",
            "tool_use_id": use_id, "anchors": ["reflex_budget", "test_ceiling"],
            "observed": FAILURE, "transcript": "", **extra}


def test_a_trigger_arriving_while_a_job_waits_joins_it(tmp_path):
    assert reflex_queue.enqueue(tmp_path, _job_line(use_id="t1")) is False
    assert reflex_queue.enqueue(tmp_path, _job_line(use_id="t2")) is True
    assert reflex_queue.enqueue(tmp_path, _job_line(agent="sub", use_id="t3")) is False
    claimed = reflex_worker.claim_next(tmp_path)
    assert claimed is not None
    assert [line["tool_use_id"] for line in claimed.lines] in (["t1", "t2"], ["t3"])


def test_a_torn_line_is_skipped_and_counted_while_its_complete_twin_is_taken(tmp_path):
    reflex_queue.enqueue(tmp_path, _job_line(use_id="t1"))
    pending = reflex_queue.key_dir(tmp_path, "s1", "") / "pending.jsonl"
    with pending.open("a") as handle:
        handle.write('{"ts": "2026-09-24T12:00:01Z", "session_id": "s1", "tool_u')
    claimed = reflex_worker.claim_next(tmp_path)
    assert [line["tool_use_id"] for line in claimed.lines] == ["t1"]
    assert claimed.torn == 1
    assert not pending.exists() and claimed.path.name == f"pending.{os.getpid()}.claimed"


def test_a_worker_finding_the_lock_held_runs_nothing(tmp_path):
    import fcntl
    reflex_queue.enqueue(tmp_path, _job_line())
    lock = reflex_queue.worker_lock_path(tmp_path)
    with lock.open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        assert reflex_queue.worker_running(tmp_path)
        assert reflex_worker.work(tmp_path, connect_graph=lambda: None) == 0
    assert not reflex_queue.worker_running(tmp_path)


def test_a_dead_workers_claim_is_died_and_a_live_ones_is_left(tmp_path):
    directory = reflex_queue.key_dir(tmp_path, "s1", "")
    directory.mkdir(parents=True)
    dead = subprocess.Popen(["true"])
    dead.wait()
    (directory / f"pending.{dead.pid}.claimed").write_text(json.dumps(_job_line()) + "\n")
    live = directory.parent / "sub"
    live.mkdir()
    (live / f"pending.{os.getppid()}.claimed").write_text(json.dumps(_job_line()) + "\n")
    counts = reflex_worker.sweep(tmp_path, alive=lambda s: True)
    assert counts["died"] == 1
    assert (live / f"pending.{os.getppid()}.claimed").exists()
    assert [row["outcome"] for row in reflex_queue.load_outcomes(tmp_path)] == ["died"]


def test_an_ended_sessions_ready_result_is_undelivered_after_the_grace(tmp_path):
    ready = reflex_queue.key_dir(tmp_path, "s1", "") / "ready" / "R1.json"
    ready.parent.mkdir(parents=True)
    ready.write_text("{}")
    assert reflex_worker.sweep(tmp_path, alive=lambda s: False)["undelivered"] == 0
    counts = reflex_worker.sweep(tmp_path, alive=lambda s: False, now=time.time() + 3600)
    assert counts["undelivered"] == 1
    assert not (tmp_path / "queue" / "s1").exists()


# --- a job, run -----------------------------------------------------------------------


def _memory(node_id):
    return MemoryResult(session_id="abc", summary="The reflex budget was set at 24k.",
                        timestamp="2026-09-12T10:00:00", tool="claude-code",
                        project="thalamus", node_id=node_id)


@pytest.fixture
def graph_reads(monkeypatch):
    monkeypatch.setattr(reflex_worker, "available_scopes", lambda: ["main"])
    monkeypatch.setattr(reflex_worker.vocabulary, "resolve",
                        lambda g, node, scope, knowledge: _memory(node))
    monkeypatch.setattr(
        reflex_worker.vocabulary, "rows_for",
        lambda g, vids, scope, knowledge: [
            Row(vid=v, kind="decision", tier=1, date="2026-09-12",
                summary="The reflex budget was set at 24k.") for v in vids
        ],
    )


def _plan(kept=(), stopped="stop_tool", sleep=0.0, note=""):
    def run(job, *, result, **kwargs):
        for node in kept:
            job.handle_for(node)
        if sleep:
            time.sleep(sleep)
        result.stopped = stopped
        result.kept = list(kept)
        result.note = note
        return result
    return run


def _claim(tmp_path, **line):
    reflex_queue.enqueue(tmp_path, _job_line(**line))
    return reflex_worker.claim_next(tmp_path)


def _run(tmp_path, claimed, **kwargs):
    kwargs.setdefault("alive", lambda session: True)
    return reflex_worker.run_job(claimed, g=object(), root=tmp_path, cli=cli_for("local"),
                                 model="m", now=lambda: _NOW, **kwargs)


def test_a_served_job_leaves_a_ready_digest_under_the_cap_naming_its_trigger(
        tmp_path, monkeypatch, graph_reads):
    monkeypatch.setattr(agentic, "run", _plan(kept=["scope:main:claim:a"]))
    claimed = _claim(tmp_path)
    assert _run(tmp_path, claimed) == "ready"
    ready = json.loads(next(tmp_path.glob("queue/s1/session/ready/*.json")).read_text())
    assert ready["outcome"] == "served" and ready["chars"] == len(ready["digest"])
    assert ready["chars"] <= reflex.DIGEST_CHAR_CAP
    assert "delivered late" in ready["digest"] and "2026-09-24T12:00:00Z" in ready["digest"]
    assert "R1.1 · decision · tier 1" in ready["digest"]
    assert ready["handles"] == {"R1.1": "scope:main:claim:a"}
    assert "`scope:main:claim:a`" in Path(ready["pointer"]).read_text()
    assert not claimed.path.exists()


def test_a_job_that_keeps_nothing_is_empty_and_leaves_no_pointer(tmp_path, monkeypatch, graph_reads):
    monkeypatch.setattr(agentic, "run", _plan())
    assert _run(tmp_path, _claim(tmp_path)) == "empty"
    assert not list(tmp_path.glob("pointers/s1/*.md"))
    assert [row["outcome"] for row in reflex_queue.load_outcomes(tmp_path)] == ["empty"]


def test_a_job_past_its_deadline_is_timeout_never_empty(tmp_path, monkeypatch, graph_reads):
    monkeypatch.setattr(agentic, "run", _plan(sleep=2.0))
    assert _run(tmp_path, _claim(tmp_path), deadline_seconds=0.2) == "timeout"
    assert [row["outcome"] for row in reflex_queue.load_outcomes(tmp_path)] == ["timeout"]


def test_a_job_whose_session_has_ended_makes_no_model_call(tmp_path, monkeypatch, graph_reads):
    called = []
    monkeypatch.setattr(agentic, "run", lambda *a, **k: called.append(1))
    assert _run(tmp_path, _claim(tmp_path), alive=lambda s: False) == "session_end"
    assert called == []
    assert _run(tmp_path, _claim(tmp_path, use_id="t9"), alive=lambda s: True) != "session_end"


# --- delivery ----------------------------------------------------------------------------


def _ready(tmp_path, monkeypatch, transcript=""):
    monkeypatch.setattr(agentic, "run", _plan(kept=["scope:main:claim:a"]))
    _run(tmp_path, _claim(tmp_path, transcript=transcript))


def test_delivery_writes_the_trace_at_delivery_time_with_its_depth_and_charges_the_budget(
        tmp_path, monkeypatch, graph_reads):
    transcript = _transcript(tmp_path / "t.jsonl", [_call("t1"), _call("t2"), _call("t3")])
    _ready(tmp_path, monkeypatch, transcript=str(transcript))
    later = _NOW + timedelta(seconds=40)
    digest = reflex_worker.deliver(tmp_path, session_id="s1", agent_id="", event="PostToolUse",
                                   traces_base=tmp_path / "traces", now=later)
    assert "delivered late" in digest
    [line] = [json.loads(x) for x in (tmp_path / "traces").glob("*.jsonl").__next__()
              .read_text().splitlines()]
    assert line["tool_name"] == ARM_AGENTIC and line["ts"] == "2026-09-24T12:00:40Z"
    assert line["tool_input"]["depth"] == 2
    assert line["tool_input"]["delivered_chars"] == len(digest)
    assert "`scope:main:claim:a`" in line["tool_response"]
    assert reflex_queue.delivered_chars(tmp_path, "s1") == len(digest)
    assert reflex_worker.deliver(tmp_path, session_id="s1", agent_id="") == ""


def test_a_ready_result_that_would_cross_the_budget_is_dropped_whole(
        tmp_path, monkeypatch, graph_reads):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "s1.jsonl").write_text(Firing(
        ts="", session_id="s1", agent_id="", outcome="served",
        injected_chars=SESSION_CHAR_BUDGET - 10,
    ).to_json() + "\n")
    _ready(tmp_path, monkeypatch)
    assert reflex_worker.deliver(tmp_path, session_id="s1", agent_id="") == ""
    assert reflex_queue.load_outcomes(tmp_path)[-1]["outcome"] == "budget"


def test_an_agentic_firing_is_queued_not_served_and_a_second_joins_it(tmp_path):
    kwargs = dict(session_id="s1", scope="main", now=_NOW, reflex_base=tmp_path,
                  traces_base=tmp_path / "traces", plan=ARM_AGENTIC, spawn=False,
                  tool_use_id="t1")
    assert reflex.fire(object(), observed=FAILURE, **kwargs) == ""
    assert reflex.fire(object(), observed="FAILED other_suite::test_thing - KeyError: "
                       "missing_column in frame_loader\n", **kwargs) == ""
    rows = load_firings("s1", tmp_path)
    assert [(row.outcome, row.arm) for row in rows] == [("queued", ARM_AGENTIC)] * 2
    assert rows[1].detail == "joined the pending job"
    claimed = reflex_worker.claim_next(tmp_path)
    assert len(claimed.lines) == 2
    assert not list((tmp_path / "traces").glob("*"))


# --- the carrier ---------------------------------------------------------------------------


def _stub_uv(tmp_path, prints):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "uv-argv.txt"
    stub = bin_dir / "uv"
    stub.write_text(f'#!/bin/bash\nprintf "%s\\n" "$*" >> "{log}"\nprintf "%s" {json.dumps(prints)}\n')
    stub.chmod(0o755)
    return bin_dir, log


def _run_tap(payload, home, bin_dir):
    return subprocess.run(
        [str(TAP)], input=json.dumps(payload), capture_output=True, text=True, timeout=30,
        env={"HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin"},
    )


def test_the_carrier_delivers_a_ready_result_to_the_agent_whose_key_it_is(tmp_path):
    bin_dir, log = _stub_uv(tmp_path, "DIGEST")
    ready = tmp_path / ".thalamus" / "reflex" / "queue" / "s1" / "sub" / "ready" / "R1.json"
    ready.parent.mkdir(parents=True)
    ready.write_text("{}")

    other = _run_tap({"session_id": "s1", "tool_name": "Read", "tool_input": {}}, tmp_path, bin_dir)
    assert other.returncode == 0 and other.stdout == "" and not log.exists()

    mine = _run_tap({"session_id": "s1", "agent_id": "sub", "tool_name": "Read",
                     "hook_event_name": "PostToolUse", "tool_input": {}}, tmp_path, bin_dir)
    out = json.loads(mine.stdout)
    assert out["hookSpecificOutput"] == {"hookEventName": "PostToolUse",
                                         "additionalContext": "DIGEST"}
    assert "--deliver --session-id s1 --agent-id sub" in log.read_text()


def test_the_carrier_runs_nothing_when_no_result_is_ready(tmp_path):
    bin_dir, log = _stub_uv(tmp_path, "DIGEST")
    result = _run_tap({"session_id": "s1", "tool_name": "Read", "tool_input": {}},
                      tmp_path, bin_dir)
    assert result.returncode == 0 and result.stdout == "" and not log.exists()


def test_job_outcomes_name_every_reason_a_job_can_end():
    assert set(reflex_queue.JOB_OUTCOMES) >= {
        "delivered", "empty", "timeout", "died", "session_end", "budget", "undelivered",
    }


def test_a_job_that_raises_is_recorded_as_error_and_the_worker_runs_the_next(tmp_path, monkeypatch):
    reflex_queue.enqueue(tmp_path, _job_line(session="s1"))
    reflex_queue.enqueue(tmp_path, _job_line(session="s2", ts="2026-09-24T12:00:05Z"))
    seen = []

    def run_job(claimed, **kwargs):
        seen.append(claimed.lines[0]["session_id"])
        if len(seen) == 1:
            raise RuntimeError("graph client wedged")
        claimed.path.unlink()
        return "empty"

    monkeypatch.setattr(reflex_worker, "run_job", run_job)
    closed = []
    ran = reflex_worker.work(tmp_path, connect_graph=object, close_graph=closed.append,
                             alive=lambda s: True)
    assert ran == 2 and seen == ["s1", "s2"]
    [row] = reflex_queue.load_outcomes(tmp_path)
    assert row["outcome"] == "error" and "graph client wedged" in row["detail"]
    assert len(closed) == 2  # the wedged client, then the fresh one at exit
    assert not list(tmp_path.glob("queue/*/*/pending*"))


# --- the note (step 6) -------------------------------------------------------------------


@pytest.mark.parametrize("note, status", [
    ("The budget was set at 24k [R1.1]. It was raised once [R1.1, R1.2].", "valid"),
    ("", "absent"),
    ("x [R1.1]. " * 60, "too_long"),
    ("The budget was set at 24k [R1.1]. It was raised once.", "uncited_sentence"),
    ("The budget was set at 24k [R1.9].", "unknown_handle"),
    ("Fix the budget test using [R1.1].", "imperative"),
])
def test_a_note_is_delivered_only_when_every_sentence_cites_a_served_record_and_none_instructs(
        note, status):
    """Each refusal has a passing twin: the first row differs from each failing row in
    the one property that row breaks."""
    assert reflex_note.check_note(note, {"R1.1", "R1.2"}).status == status


def test_valid_notes_split_between_shown_and_withheld_in_balanced_blocks(tmp_path):
    arms = [reflex_note.assign_note_arm(tmp_path, "s1", f"R{n}") for n in range(10)]
    for block in range(5):
        assert sorted(arms[2 * block: 2 * block + 2]) == sorted(reflex_note.NOTE_ARMS)
    again = [reflex_note.assign_note_arm(tmp_path / "other", "s1", f"R{n}") for n in range(10)]
    assert again == arms


def _ready_file(tmp_path):
    return json.loads(next(tmp_path.glob("queue/s1/session/ready/*.json")).read_text())


def test_a_shown_note_is_in_the_digest_and_a_withheld_one_only_in_the_record(
        tmp_path, monkeypatch, graph_reads):
    note = "The reflex budget was set at 24k chars [R1.1]."
    monkeypatch.setattr(reflex_note, "assign_note_arm",
                        lambda root, session, firing: reflex_note.SHOWN)
    monkeypatch.setattr(agentic, "run", _plan(kept=["scope:main:claim:a"], note=note))
    _run(tmp_path, _claim(tmp_path))
    ready = _ready_file(tmp_path)
    assert note in ready["digest"] and "written by the local model" in ready["digest"]
    assert ready["note_arm"] == "shown" and ready["note_status"] == "valid"
    assert ready["chars"] <= reflex.DIGEST_CHAR_CAP
    next(tmp_path.glob("queue/s1/session/ready/*.json")).unlink()

    # The second job's handles are R2.n: its note cites what it serves.
    note = "The reflex budget was set at 24k chars [R2.1]."
    monkeypatch.setattr(reflex_note, "assign_note_arm",
                        lambda root, session, firing: reflex_note.WITHHELD)
    monkeypatch.setattr(agentic, "run", _plan(kept=["scope:main:claim:a"], note=note))
    _run(tmp_path, _claim(tmp_path, use_id="t2"))
    ready = _ready_file(tmp_path)
    assert note not in ready["digest"] and ready["note"] == note
    assert ready["note_arm"] == "withheld"


def test_a_refused_note_draws_no_arm_and_the_records_still_go_out(
        tmp_path, monkeypatch, graph_reads):
    monkeypatch.setattr(agentic, "run", _plan(kept=["scope:main:claim:a"],
                                              note="Always rerun the suite [R1.1]."))
    assert _run(tmp_path, _claim(tmp_path)) == "ready"
    ready = _ready_file(tmp_path)
    assert ready["note_status"] == "imperative" and ready["note_arm"] == ""
    assert "Always rerun" not in ready["digest"] and "R1.1 · decision" in ready["digest"]
    assert not (tmp_path / "note_arms").exists()
