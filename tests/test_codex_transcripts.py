"""The codex transcript adapter — discovery, the rollout grammar, and the floor.

Interfaces: thalamus.harness.codex_transcripts.{session_id_of, discover,
claim_unresolved, parse, to_session_graph}, thalamus.harness.extraction.render_digest
and its jsonl-events envelope reader.

Every fixture below is written in the shape **measured** from a live codex-cli 0.147.0
rollout on 2026-08-17, including the two facts that make this reader different from
the Cursor one: rows are `{timestamp, type, payload}`, and a tool call is a code-mode
`custom_tool_call` whose structured twin is an `event_msg`.
"""

import json
from datetime import datetime, timezone

import pytest

from thalamus.harness import codex_transcripts as ct
from thalamus.harness import extraction
from thalamus.substrate.schema import Tool

SESSION = "01a013a2-e0bd-7f32-8698-f88dc96e63d3"
ROLLOUT = f"rollout-2026-08-17T23-50-36-{SESSION}.jsonl"
CWD = "/home/op/code/thalamus"


def _row(kind, payload, ts="2026-08-18T06:50:36.705Z"):
    return {"timestamp": ts, "type": kind, "payload": payload}


def _meta(cwd=CWD, session_id=SESSION):
    return _row("session_meta", {
        "session_id": session_id, "id": session_id, "cwd": cwd,
        "originator": "codex_exec", "cli_version": "0.147.0", "source": "exec",
        "base_instructions": {"text": "You are Codex…"},
    })


def _user(text):
    return _row("event_msg", {"type": "user_message", "message": text, "images": []},
                ts="2026-08-18T06:50:37.000Z")


def _assistant(text):
    return _row("event_msg", {"type": "agent_message", "message": text},
                ts="2026-08-18T06:50:44.000Z")


def _exec_call(call_id, cmd):
    program = (
        f'const r = await tools.exec_command({{"cmd":{json.dumps(cmd)},'
        f'"workdir":{json.dumps(CWD)},"yield_time_ms":10000}});\ntext(r.output);\n'
    )
    return _row("response_item", {
        "type": "custom_tool_call", "id": f"ctc_{call_id}", "status": "completed",
        "call_id": call_id, "name": "exec", "input": program,
    }, ts="2026-08-18T06:50:42.104Z")


def _search_call(call_id, query):
    program = (
        f'const r = await tools.web__run({{"search_query":[{{"q":{json.dumps(query)}}}],'
        '"response_length":"short"});\ntext(r);\n'
    )
    return _row("response_item", {
        "type": "custom_tool_call", "id": f"ctc_{call_id}", "status": "completed",
        "call_id": call_id, "name": "exec", "input": program,
    }, ts="2026-08-18T06:50:44.260Z")


def _output(call_id, text):
    return _row("response_item", {
        "type": "custom_tool_call_output", "id": f"ctco_{call_id}", "call_id": call_id,
        "output": [
            {"type": "input_text", "text": "Script completed\nWall time 1.0 seconds\nOutput:\n"},
            {"type": "input_text", "text": text},
        ],
    }, ts="2026-08-18T06:50:45.224Z")


def _patch_end(call_id, paths):
    return _row("event_msg", {
        "type": "patch_apply_end", "call_id": call_id, "turn_id": "t1",
        "stdout": "Success.", "stderr": "", "success": True, "status": "completed",
        "changes": {p: {"type": "update", "unified_diff": "@@\n+x\n", "move_path": None}
                    for p in paths},
    }, ts="2026-08-18T06:50:48.346Z")


def _search_end(query):
    return _row("event_msg", {
        "type": "web_search_end", "call_id": "exec-abc", "query": query,
        "action": {"type": "search", "query": query},
        "results": [{"type": "text_result", "domain": "example.org",
                     "url": "https://example.org/x", "title": "X", "snippet": "…"}],
    }, ts="2026-08-18T06:50:45.220Z")


def _task_complete(last="done"):
    return _row("event_msg", {
        "type": "task_complete", "turn_id": "t1", "last_agent_message": last,
        "started_at": 1787035836, "completed_at": 1787035849, "duration_ms": 12797,
    }, ts="2026-08-18T06:50:49.485Z")


def _write(tmp_path, rows, name=ROLLOUT):
    day = tmp_path / "sessions" / "2026" / "08" / "17"
    day.mkdir(parents=True, exist_ok=True)
    path = day / name
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


class TestSessionIdentity:
    def test_the_id_is_read_off_the_tail_not_the_first_hyphen(self):
        """The filename embeds an ISO timestamp, whose own hyphens break any
        split-from-the-left rule. Measured name, measured id."""
        from pathlib import Path

        assert ct.session_id_of(Path(ROLLOUT)) == SESSION

    @pytest.mark.parametrize("name", [
        "notes.jsonl",                       # not a rollout at all
        "rollout-2026-08-17T23-50-36.jsonl",  # no id
        "rollout-2026-08-17T23-50-36-nope.jsonl",  # id is not a uuid
    ])
    def test_a_name_it_cannot_read_is_empty_not_a_guess(self, name):
        """A guessed id becomes a vertex ID, and scope+id is not walkable back."""
        from pathlib import Path

        assert ct.session_id_of(Path(name)) == ""


class TestDiscovery:
    def test_every_rollout_on_disk_is_found_with_no_hook_involved(self, tmp_path):
        """Codex writes a rollout for every session itself, so the filesystem is
        complete by construction — the opposite arrangement from Cursor, where the
        hook log is primary and the filesystem is the backfill."""
        _write(tmp_path, [_meta(), _user("hi")])
        found = ct.discover(tmp_path, ledger_path=tmp_path / "absent.jsonl")

        assert [s.session_id for s in found] == [SESSION]
        assert found[0].exists and not found[0].scope_resolved

    def test_the_pin_ledger_supplies_the_scope_and_the_last_row_wins(self, tmp_path):
        _write(tmp_path, [_meta(), _user("hi")])
        ledger = tmp_path / "pins.jsonl"
        ledger.write_text(
            json.dumps({"session_id": SESSION, "scope": "main"}) + "\n"
            + json.dumps({"session_id": SESSION, "scope": "qe"}) + "\n"
        )
        found = ct.discover(tmp_path, ledger_path=ledger)

        assert found[0].scope == "qe" and found[0].scope_resolved

    def test_one_session_can_be_asked_about_without_sweeping_the_tree(self, tmp_path):
        """`--transcript` already knows its file; it should not have to glob a whole
        sessions tree to learn where the session was pinned."""
        ledger = tmp_path / "pins.jsonl"
        ledger.write_text(json.dumps({"session_id": SESSION, "scope": "qe"}) + "\n")

        assert ct.ledger_scope(SESSION, ledger) == "qe"
        assert ct.ledger_scope("nobody", ledger) == ct.UNRESOLVED_SCOPE
        assert ct.ledger_scope(SESSION, tmp_path / "absent.jsonl") == ct.UNRESOLVED_SCOPE

    def test_an_unresolved_session_is_refused_rather_than_routed_to_main(self, tmp_path):
        """`main` is a real subgraph and scope is part of the vertex ID, so an
        unmade routing decision must never be made by a default."""
        _write(tmp_path, [_meta(), _user("hi")])
        found = ct.discover(tmp_path, ledger_path=tmp_path / "absent.jsonl")

        ready, refused = ct.claim_unresolved(found)
        assert not ready and [s.session_id for s in refused] == [SESSION]

        ready, refused = ct.claim_unresolved(found, "qe")
        assert not refused and [s.scope for s in ready] == ["qe"]


class TestParse:
    def test_time_place_and_turns_all_come_from_the_file(self, tmp_path):
        """None of Cursor's three structural gaps apply: the rollout timestamps every
        row and records its own cwd, so nothing is handed in from a ledger."""
        path = _write(tmp_path, [
            _meta(), _user("do the thing"), _assistant("did it"), _task_complete(),
        ])
        facts = ct.parse(path)

        assert facts.session_id == SESSION
        assert facts.cwd == CWD
        assert facts.harness == "codex"
        assert facts.user_turns == 1 and facts.prompt_turns == 1
        assert facts.started_at == datetime(2026, 8, 18, 6, 50, 36, 705000, tzinfo=timezone.utc)
        assert facts.ended_at == datetime(2026, 8, 18, 6, 50, 49, 485000, tzinfo=timezone.utc)
        assert facts.has_substance

    def test_scaffolding_rows_are_not_counted_as_the_operator_speaking(self, tmp_path):
        """`response_item` user rows are the injected `<environment_context>` block and
        `developer` rows are the skills/permissions preamble. Counting either would
        make every session look like it had turns it did not."""
        path = _write(tmp_path, [
            _meta(),
            _row("response_item", {"type": "message", "role": "developer",
                                   "content": [{"type": "input_text", "text": "<skills…>"}]}),
            _row("response_item", {"type": "message", "role": "user",
                                   "content": [{"type": "input_text",
                                                "text": "<environment_context>…"}]}),
        ])
        facts = ct.parse(path)

        assert facts.user_turns == 0 and not facts.has_substance
        assert facts.unrecognized == 0

    def test_touched_files_come_from_the_patch_event_not_the_javascript(self, tmp_path):
        """The call is a JS program with no `file_path` in it; `patch_apply_end` is
        the same operation in a declared shape. Reading the program would be exactly
        the inference this layer refuses."""
        path = _write(tmp_path, [
            _meta(), _user("edit it"),
            _row("response_item", {
                "type": "custom_tool_call", "id": "ctc_1", "call_id": "call_1",
                "name": "exec", "status": "completed",
                "input": 'const r = await tools.apply_patch("*** Begin Patch\\n…");',
            }),
            _patch_end("exec-5909589e", [f"{CWD}/src/a.py", f"{CWD}/src/b.py"]),
        ])
        facts = ct.parse(path)

        assert set(facts.touched) == {f"{CWD}/src/a.py", f"{CWD}/src/b.py"}
        # The anchor is codex's own call_id, not a synthesized row index: unlike
        # Cursor, codex writes real identifiers, so provenance needs no addressing
        # scheme invented for it.
        assert facts.touched[f"{CWD}/src/a.py"] == ["exec-5909589e"]
        assert facts.tool_calls == 1

    def test_the_ingress_floor_is_computable_from_the_transcript_alone(self, tmp_path):
        """Codex embeds tool output, so an empty `external_texts` means nothing was
        fetched — the Claude Code meaning, not Cursor's "we cannot know"."""
        path = _write(tmp_path, [
            _meta(), _user("look it up"),
            _search_call("call_9", "RFC 9413"),
            _output("call_9", "RFC 9413: Maintaining Robust Protocols — third-party prose"),
            _search_end("RFC 9413"),
        ])
        facts = ct.parse(path)

        assert facts.ingress_verifiable is True and facts.ingress_verdict == "verified"
        assert facts.ingress_detected == 1, "one search is one fetch, not two surfaces"
        assert len(facts.external_texts) == 1
        assert "third-party prose" in facts.external_texts[0]

    def test_a_shell_output_is_not_treated_as_external_content(self, tmp_path):
        """A command's stdout is a tier-1 observation of the operator's own machine.
        Widening ingress to every tool result would floor the whole corpus."""
        path = _write(tmp_path, [
            _meta(), _user("run it"),
            _exec_call("call_2", "cat note.txt"), _output("call_2", "hello"),
        ])
        facts = ct.parse(path)

        assert facts.external_texts == [] and facts.ingress_detected == 0
        assert facts.tool_calls == 1

    def test_a_direct_search_with_no_code_mode_call_is_still_detected(self, tmp_path):
        """A non-code-mode model calls the tool directly and writes no JS program, so
        `web_search_end` is the fallback surface rather than a duplicate."""
        path = _write(tmp_path, [_meta(), _user("look it up"), _search_end("RFC 9413")])

        assert ct.parse(path).ingress_detected == 1

    def test_an_unknown_record_is_counted_and_never_absorbed(self, tmp_path):
        """Silent tolerance turns "codex changed the format" into "that session had
        fewer turns". Recognition is complete and kept apart from processing."""
        path = _write(tmp_path, [
            _meta(), _user("hi"),
            _row("brand_new_top_level_kind", {"type": "whatever"}),
            _row("event_msg", {"type": "some_future_event"}),
            _row("response_item", {"type": "function_call", "name": "shell"}),
        ])
        facts = ct.parse(path)

        assert facts.unrecognized == 3
        assert facts.user_turns == 1, "the rows it did understand still counted"

    def test_an_undecodable_line_is_counted_rather_than_skipped(self, tmp_path):
        path = _write(tmp_path, [_meta(), _user("hi")])
        path.write_text(path.read_text() + "{not json\n")

        assert ct.parse(path).unrecognized == 1

    def test_the_first_cwd_wins_so_a_session_that_moved_is_not_reattributed(self, tmp_path):
        """cwd answers "which project is this session's", fixed when the session
        starts — the same rule the Claude Code reader applies."""
        path = _write(tmp_path, [
            _meta(cwd="/home/op/code/thalamus"), _user("hi"),
            _row("turn_context", {"turn_id": "t1", "cwd": "/home/op/code/other",
                                  "model": "gpt-5.6-terra"}),
        ])

        assert ct.parse(path).cwd == "/home/op/code/thalamus"


class TestSessionGraph:
    def test_the_graph_is_the_shared_one_stamped_as_codex(self, tmp_path):
        path = _write(tmp_path, [_meta(), _user("hi"), _assistant("ok")])
        graph = ct.to_session_graph(
            ct.parse(path), content_hash="abc123", uri="file:///x", byte_size=10,
            scope="main",
        )

        assert graph.tool == Tool.CODEX
        assert graph.session_id == SESSION


class TestDigest:
    def test_the_digest_reads_the_semantic_layer_not_the_program(self, tmp_path):
        path = _write(tmp_path, [
            _meta(), _user("edit and search"),
            _search_call("call_9", "RFC 9413"),
            _output("call_9", "third-party prose"),
            _search_end("RFC 9413"),
            _row("response_item", {
                "type": "custom_tool_call", "id": "ctc_3", "call_id": "call_3",
                "name": "exec", "status": "completed",
                "input": 'const r = await tools.apply_patch("*** Begin Patch\\n…");',
            }),
            _patch_end("exec-1", [f"{CWD}/src/a.py"]),
            _assistant("done"),
        ])
        digest = extraction.render_digest(path.read_bytes(), harness="codex")

        assert "USER: edit and search" in digest
        assert "ASSISTANT: done" in digest
        assert "tool: web_search RFC 9413" in digest
        assert f"tool: apply_patch {CWD}/src/a.py" in digest
        # The call and its structured event describe one operation; rendering both
        # spends the budget saying one thing twice.
        assert "tools.apply_patch" not in digest
        assert "tools.web__run" not in digest
        # The external-origin label is decided here, not by the model.
        assert "result [EXTERNAL CONTENT]: " in digest

    def test_a_shell_call_keeps_its_program_because_nothing_else_describes_it(self, tmp_path):
        path = _write(tmp_path, [
            _meta(), _user("run it"),
            _exec_call("call_2", "cat note.txt"), _output("call_2", "hello"),
        ])
        digest = extraction.render_digest(path.read_bytes(), harness="codex")

        assert "tool: exec_command" in digest and "cat note.txt" in digest
        assert "result: " in digest and "[EXTERNAL CONTENT]" not in digest


class TestEnvelopeReader:
    """`codex exec --json` streams events; there is no single object to load."""

    def _cli(self):
        from thalamus.harness.agents import cli_for
        return cli_for("codex")

    def _read(self, lines):
        return extraction._read_jsonl_events(
            "".join(json.dumps(line) + "\n" for line in lines), self._cli()
        )

    def test_the_final_agent_message_is_the_answer_and_the_counts_are_the_terminus(self):
        run = self._read([
            {"type": "thread.started", "thread_id": SESSION},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "i0", "type": "agent_message",
                                                "text": "thinking out loud"}},
            {"type": "item.completed", "item": {"id": "i1", "type": "command_execution",
                                                "command": "ls", "exit_code": 0}},
            {"type": "item.completed", "item": {"id": "i2", "type": "agent_message",
                                                "text": "the real answer"}},
            {"type": "turn.completed", "usage": {
                "input_tokens": 100, "cached_input_tokens": 40,
                "cache_write_input_tokens": 0, "output_tokens": 7,
                "reasoning_output_tokens": 3}},
        ])

        assert run.text == "the real answer"
        assert (run.input_tokens, run.output_tokens) == (100, 7)
        assert (run.cache_read_tokens, run.cache_write_tokens) == (40, 0)
        # Not zero: codex carries no dollar figure anywhere, and 0.0 would read as
        # "this call was free" to `eval cost`.
        assert run.cost_usd is None

    def test_a_failed_turn_is_an_error_and_not_an_empty_summary(self):
        """`codex exec` can exit 0 having printed `turn.failed`. Returning "" there
        would file a session with a blank summary and call it distilled."""
        with pytest.raises(extraction.ExtractionError, match="401"):
            self._read([
                {"type": "turn.started"},
                {"type": "turn.failed", "error": {"message": "unexpected status 401"}},
            ])

    def test_a_stream_with_no_terminus_is_refused(self):
        with pytest.raises(extraction.ExtractionError, match="no turn.completed"):
            self._read([{"type": "thread.started", "thread_id": SESSION}])

    def test_an_unreadable_line_does_not_stop_a_finished_turn(self):
        """A future codex adding an event kind must not break extraction; the
        terminal event is what says the turn actually finished."""
        run = extraction._read_jsonl_events(
            '{"type":"turn.started"}\nnot json at all\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n',
            self._cli(),
        )

        assert run.text == "ok" and run.input_tokens == 1
        # Absent counts stay None rather than becoming 0: "not reported" and "none
        # used" are different answers.
        assert run.cache_read_tokens is None
