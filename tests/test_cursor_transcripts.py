"""
Cursor transcript adapter (docs/07, lab/010 wall 2, lab/028).

Interfaces: harness/cursor_transcripts.py, driven with synthetic transcripts in
the shape Cursor staff and users describe (forum threads 157311/166592, read
2026-07-29). Infrastructure: tmp_path for transcripts and ledgers; no live
graph, no Cursor.
Scope: this is a **contract test against documentation**, not against Cursor.
No Thalamus code has run inside a live Cursor, so the assertions divide into two
kinds and the distinction is the point. Some pin what we believe Cursor emits
and will need revisiting if that belief is wrong. The rest pin how the adapter
behaves when the format disappoints it — unknown blocks, missing fields,
malformed lines — and those hold regardless, because a parser that has never met
its input must degrade to an absent field rather than a wrong one.

The load-bearing test in this file is the ingress one: Cursor transcripts carry
no tool results for any tool, so an empty `external_texts` means "we cannot
know", and collapsing that into "nothing was fetched" would silently delete the
half of docs/05's laundering floor that no prompt content can lift.
"""

import json
from datetime import datetime, timezone

import pytest

from thalamus.harness import cursor_transcripts, extraction
from thalamus.substrate.schema import Tool


def write_transcript(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return path


def user(text):
    return {"role": "user", "message": {"content": [{"type": "text", "text": text}]}}


def assistant(*blocks):
    return {"role": "assistant", "message": {"content": list(blocks)}}


def text(body):
    return {"type": "text", "text": body}


def tool_use(name, **inputs):
    # Note the absent `id`: Cursor's tool_use blocks carry type/name/input only.
    return {"type": "tool_use", "name": name, "input": inputs}


@pytest.fixture
def transcript(tmp_path):
    return write_transcript(
        tmp_path / "conv-1.jsonl",
        [
            user("port the harness to cursor"),
            assistant(text("Reading the adapter."), tool_use("Read", file_path="/w/hooks.py")),
            assistant(tool_use("Edit", file_path="/w/hooks.py"), text("Done.")),
            user("now run the tests"),
        ],
    )


class TestParse:
    def test_recovers_turns_and_tool_calls(self, transcript):
        facts = cursor_transcripts.parse(transcript, session_id="conv-1")
        assert facts.user_turns == 2
        assert facts.tool_calls == 2
        assert facts.message_count == 4
        assert facts.first_prompt == "port the harness to cursor"

    def test_touches_are_recovered_from_tool_inputs(self, transcript):
        """Tool *inputs* survive in Cursor's format even though outputs do not,
        so the deterministic TOUCHES layer crosses intact."""
        facts = cursor_transcripts.parse(transcript, session_id="conv-1")
        assert set(facts.touched) == {"/w/hooks.py"}
        assert len(facts.touched["/w/hooks.py"]) == 2

    def test_anchors_cannot_be_mistaken_for_message_ids(self, transcript):
        """Cursor writes no message ids, so anchors are positional. They are
        namespaced so a synthesized anchor never passes for a real UUID."""
        facts = cursor_transcripts.parse(transcript, session_id="conv-1")
        anchors = facts.touched["/w/hooks.py"]
        assert all(a.startswith("cursor:msg:") for a in anchors)

    def test_time_and_place_come_from_the_ledgers_not_the_transcript(self, transcript):
        """No Cursor row carries a timestamp or a cwd; both are supplied by the
        hooks' own records, which is strictly better evidence than a guess."""
        started = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)
        ended = datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc)
        facts = cursor_transcripts.parse(
            transcript, session_id="conv-1", cwd="/home/u/work", started_at=started,
            ended_at=ended,
        )
        assert (facts.started_at, facts.ended_at) == (started, ended)
        assert facts.project == "work"

    def test_a_bare_string_content_is_accepted(self, tmp_path):
        """Documented shape is a block list, but every other harness also emits a
        bare string — a tolerant reader takes both."""
        path = write_transcript(
            tmp_path / "c.jsonl", [{"role": "user", "message": {"content": "hello"}}]
        )
        assert cursor_transcripts.parse(path).user_turns == 1

    def test_malformed_and_unknown_records_are_counted_not_silently_dropped(self, tmp_path):
        """Virtuous intolerance (RFC 9413; LangSec SecDev 2016): a parser written
        against a format it has never observed must make surprises loud. Silent
        tolerance would turn "Cursor changed the format" into "this session had
        fewer turns" — the exact failure this repo keeps rediscovering."""
        path = tmp_path / "c.jsonl"
        path.write_text(
            "\n".join(
                [
                    "{not json",                                                    # undecodable
                    json.dumps({"role": "system", "message": {"content": [text("x")]}}),  # new role
                    json.dumps({"role": "user"}),                                   # no message
                    json.dumps(user("the only real turn")),
                    "[]",                                                           # not an object
                ]
            )
            + "\n"
        )
        facts = cursor_transcripts.parse(path)
        assert facts.user_turns == 1
        assert facts.first_prompt == "the only real turn"
        assert facts.unrecognized == 4

    def test_an_unknown_content_block_does_not_condemn_its_record(self, tmp_path):
        """Blocks are a pre-declared extension point — Cursor may add block types
        without changing the record grammar, so an unknown block is tolerated while
        an unknown *record* is not."""
        path = write_transcript(
            tmp_path / "c.jsonl",
            [{"role": "user", "message": {"content": [{"type": "mystery"}, text("hi")]}}],
        )
        facts = cursor_transcripts.parse(path)
        assert facts.unrecognized == 0
        assert facts.user_turns == 1

    def test_a_well_formed_transcript_reports_nothing_unrecognized(self, transcript):
        assert cursor_transcripts.parse(transcript).unrecognized == 0

    def test_a_sqlite_transcript_path_fails_loudly_not_wrongly(self, tmp_path):
        """The premise this whole adapter rests on is that `transcript_path`
        resolves to JSONL. It is unverified: Cursor also keeps chat state in
        SQLite (`state.vscdb`), and the sessionEnd ledger has been recording
        whatever the hook was handed. If the premise is wrong the adapter must
        produce *nothing* and say so — never a half-parsed session, which would be
        a corrupted memory rather than a missing one."""
        import sqlite3

        db = tmp_path / "state.vscdb"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE cursorDiskKV (key TEXT, value BLOB)")
        con.execute("INSERT INTO cursorDiskKV VALUES ('composerData:x', ?)", ('{"a":1}',))
        con.commit()
        con.close()

        facts = cursor_transcripts.parse(db, session_id="sqlite-case")
        assert facts.user_turns == 0        # nothing distilled
        assert facts.unrecognized > 0       # and the mismatch is reported

    def test_a_transcript_path_that_does_not_exist_is_dropped_at_discovery(self, tmp_path):
        log = tmp_path / "log.jsonl"
        log.write_text(
            json.dumps({"session_id": "a", "scope": "main",
                        "transcript_path": str(tmp_path / "gone.jsonl")}) + "\n"
        )
        assert [s.exists for s in cursor_transcripts.discover(log)] == [False]

    def test_an_empty_transcript_yields_nothing_to_remember(self, tmp_path):
        path = write_transcript(tmp_path / "c.jsonl", [])
        assert cursor_transcripts.parse(path).user_turns == 0


class TestIngressFidelity:
    """The load-bearing distinction: absent-this-time vs structurally unavailable."""

    def test_a_cursor_transcript_is_never_ingress_verifiable(self, transcript):
        facts = cursor_transcripts.parse(transcript, session_id="conv-1")
        assert facts.ingress_verifiable is False
        assert facts.external_texts == []

    def test_ingress_calls_are_still_counted_even_though_results_are_gone(self, tmp_path):
        """We can see that it fetched, just not what came back — so the reason
        reported is sharper than a bare 'unverifiable'."""
        path = write_transcript(
            tmp_path / "c.jsonl",
            [user("look it up"), assistant(tool_use("web_search", query="cursor hooks"))],
        )
        assert cursor_transcripts.parse(path).ingress_detected == 1

    def test_unverifiable_ingress_floors_every_claim(self):
        """With no tool results to match against, the mechanical layer has nothing
        to run — and honoring only the extractor's self-marks would leave exactly
        the liftable half of docs/05's defence standing."""
        graph = _graph_with_claims()
        floored = extraction.apply_ingress_floor(graph, [], ingress_verifiable=False)
        assert all(c.external for c in floored.claims())
        assert all(
            "unverifiable" in c.provenance.source for c in floored.claims()
        )

    def test_verifiable_ingress_still_only_floors_what_echoes(self):
        """The Cursor rule must not leak into the Claude Code path, where an empty
        list really does mean nothing was fetched."""
        graph = _graph_with_claims()
        floored = extraction.apply_ingress_floor(graph, [], ingress_verifiable=True)
        assert not any(c.external for c in floored.claims())

    def test_a_session_with_no_claims_is_left_alone(self):
        from thalamus.substrate.schema import SessionGraph

        graph = SessionGraph(session_id="s", timestamp=datetime.now(), tool=Tool.CURSOR,
                             summary="nothing extracted")
        assert extraction.apply_ingress_floor(graph, [], ingress_verifiable=False) is graph


class TestDiscovery:
    def test_reads_the_session_end_log(self, tmp_path):
        log = tmp_path / "cursor-session-end.jsonl"
        log.write_text(
            "\n".join(
                json.dumps(r)
                for r in [
                    {"session_id": "a", "scope": "main", "transcript_path": str(tmp_path / "a.jsonl"),
                     "ts": "2026-07-29T09:00:00Z", "distilled": False},
                    {"session_id": "b", "scope": "literature",
                     "transcript_path": str(tmp_path / "b.jsonl"),
                     "ts": "2026-07-29T10:00:00Z", "distilled": False},
                ]
            )
            + "\n"
        )
        (tmp_path / "a.jsonl").write_text("")
        found = {s.session_id: s for s in cursor_transcripts.discover(log)}
        assert set(found) == {"a", "b"}
        assert found["b"].scope == "literature"
        assert found["a"].exists and not found["b"].exists

    def test_the_newest_row_per_session_wins(self, tmp_path):
        """A re-logged session must not distill twice under two scopes — vertex
        IDs include scope, so that would fork the Session vertex."""
        log = tmp_path / "log.jsonl"
        log.write_text(
            "\n".join(
                json.dumps({"session_id": "a", "scope": s, "transcript_path": "/t.jsonl",
                            "ts": "2026-07-29T09:00:00Z"})
                for s in ("main", "homelab")
            )
            + "\n"
        )
        assert [s.scope for s in cursor_transcripts.discover(log)] == ["homelab"]

    def test_rows_without_a_transcript_pointer_are_ignored(self, tmp_path):
        log = tmp_path / "log.jsonl"
        log.write_text(json.dumps({"session_id": "a", "scope": "main"}) + "\n")
        assert cursor_transcripts.discover(log) == []

    def test_a_missing_log_is_empty_not_an_error(self, tmp_path):
        assert cursor_transcripts.discover(tmp_path / "nope.jsonl") == []

    def test_session_context_comes_from_the_pin_ledger(self, tmp_path):
        ledger = tmp_path / "pins.jsonl"
        ledger.write_text(
            "\n".join(
                json.dumps(r)
                for r in [
                    {"session_id": "a", "scope": "main", "cwd": "/home/u/proj",
                     "ts": "2026-07-29T09:00:00Z"},
                    {"session_id": "other", "cwd": "/elsewhere", "ts": "2026-07-29T08:00:00Z"},
                ]
            )
            + "\n"
        )
        cwd, started = cursor_transcripts.session_context("a", ledger)
        assert cwd == "/home/u/proj"
        assert started == datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)


class TestSessionGraph:
    def test_is_stamped_as_cursor(self, transcript):
        facts = cursor_transcripts.parse(transcript, session_id="conv-1", cwd="/home/u/work")
        graph = cursor_transcripts.to_session_graph(
            facts, content_hash="h" * 64, uri="archive://x", byte_size=10
        )
        assert graph.tool == Tool.CURSOR

    def test_passes_the_federation_contract(self, transcript):
        from thalamus.contract.conformance import check_session

        facts = cursor_transcripts.parse(transcript, session_id="conv-1", cwd="/home/u/work")
        graph = cursor_transcripts.to_session_graph(
            facts, content_hash="h" * 64, uri="archive://x", byte_size=10
        )
        assert check_session(graph) == []


class TestDigest:
    def test_renders_role_keyed_records(self, transcript):
        """render_digest discriminates on `type`, which Cursor rows do not have.
        Without the `role` fallback a Cursor digest is empty and every extraction
        silently returns nothing."""
        digest = extraction.render_digest(transcript.read_bytes())
        assert "USER: port the harness to cursor" in digest
        assert "ASSISTANT: Reading the adapter." in digest
        assert "tool: Read /w/hooks.py" in digest

    def test_carries_no_result_lines(self, transcript):
        assert "result:" not in extraction.render_digest(transcript.read_bytes())

    def test_claude_code_digests_are_unchanged(self):
        """The tolerant reader must not alter the primary harness's rendering."""
        payload = (
            "\n".join(
                json.dumps(r)
                for r in [
                    {"type": "user", "message": {"content": "hello"}},
                    {"type": "assistant", "message": {"content": [
                        {"type": "text", "text": "hi"},
                        {"type": "tool_use", "id": "t1", "name": "Read",
                         "input": {"file_path": "/a.py"}}]}},
                    {"type": "user", "message": {"content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "file body"}]}},
                ]
            )
            + "\n"
        ).encode()
        digest = extraction.render_digest(payload)
        assert digest.splitlines() == [
            "USER: hello",
            "ASSISTANT: hi",
            "  tool: Read /a.py",
            "  result: file body",
        ]


def _graph_with_claims():
    from thalamus.substrate.schema import Decision, Provenance, SessionGraph, Tier

    return SessionGraph(
        session_id="cur-1",
        timestamp=datetime.now(),
        tool=Tool.CURSOR,
        summary="a cursor session",
        decisions=[
            Decision(
                description="use the spool for deferred injection",
                rationale="beforeSubmitPrompt cannot inject",
                provenance=Provenance(tier=Tier.FIRST_PARTY, source="session:cur-1"),
            )
        ],
    )
