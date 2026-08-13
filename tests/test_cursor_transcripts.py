"""
Cursor transcript adapter (docs/07, lab/010 wall 2, lab/028).

Interfaces: harness/cursor_transcripts.py, driven with synthetic transcripts in
the shape Cursor staff and users describe (forum threads 157311/166592, read
2026-07-29). Infrastructure: tmp_path for transcripts and ledgers; no live
graph, no Cursor.
Scope: the transcript-shape assertions are a **contract test against
documentation**, not against Cursor, and they divide into two kinds. Some pin
what we believe Cursor emits and will need revisiting if that belief is wrong.
The rest pin how the adapter behaves when the format disappoints it — unknown
blocks, missing fields, malformed lines — and those hold regardless, because a
parser meeting an unfamiliar input must degrade to an absent field rather than a
wrong one. Two things are the exception, copied from observation rather than from
documentation: the on-disk layout the discovery tests build, read off a live
Cursor install (lab/054), and the tool names and input keys — `Read`/`Write`/
`StrReplace` naming a file in `path`, `Grep`/`Glob` naming a search root — read
off the Cursor transcript corpus on the same box.

The load-bearing test in this file is the ingress one: Cursor transcripts carry
no tool results for any tool, so an empty `external_texts` means "we cannot
know", and collapsing that into "nothing was fetched" would silently delete the
half of docs/05's laundering floor that no prompt content can lift.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

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


@pytest.fixture(autouse=True)
def _no_real_pin_ledger(tmp_path, monkeypatch):
    """Discovery consults the pin ledger for scope, so no test may fall through to
    the machine's own. Tests that exercise it pass their ledger explicitly."""
    monkeypatch.setattr(cursor_transcripts, "PIN_LEDGER", tmp_path / "absent-pins.jsonl")


@pytest.fixture
def transcript(tmp_path):
    return write_transcript(
        tmp_path / "conv-1.jsonl",
        [
            user("port the harness to cursor"),
            assistant(text("Reading the adapter."), tool_use("Read", path="/w/hooks.py")),
            assistant(
                tool_use("StrReplace", path="/w/hooks.py", old_string="a", new_string="b"),
                text("Done."),
            ),
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

    def test_a_search_root_is_not_a_touched_file(self, tmp_path):
        """Cursor spells a file `path` on Read/Write/StrReplace and a *search
        root* `path` on Grep, overloading one key where Claude Code's `file_path`
        never is. Reading the key without its tool would file every grepped
        directory as a touched file — a wrong anchor, which provenance cannot
        recover from as it can from a missing one."""
        path = write_transcript(
            tmp_path / "conv-2.jsonl",
            [
                user("find it"),
                assistant(
                    tool_use("Grep", pattern="scope", path="/w/src"),
                    tool_use("Glob", glob_pattern="*.py", target_directory="/w/src"),
                    tool_use("Read", path="/w/src/pin.py"),
                ),
            ],
        )
        facts = cursor_transcripts.parse(path, session_id="conv-2")
        assert facts.tool_calls == 3
        assert set(facts.touched) == {"/w/src/pin.py"}

    def test_anchors_cannot_be_mistaken_for_message_ids(self, transcript):
        """Cursor writes no message ids, so anchors are positional. They are
        namespaced so a synthesized anchor never passes for a real UUID."""
        facts = cursor_transcripts.parse(transcript, session_id="conv-1")
        anchors = facts.touched["/w/hooks.py"]
        assert all(a.startswith("cursor:msg:") for a in anchors)

    def test_time_and_place_come_from_the_ledgers_not_the_transcript(self, transcript, tmp_path):
        """No Cursor row carries a timestamp or a cwd; both are supplied by the
        hooks' own records, which is strictly better evidence than a guess.

        `project` still resolves through the checkout, the same as Claude Code's. This
        reader assembles its own facts rather than going through `transcripts.parse`,
        so that resolution is a second call site and this is what pins it — without it
        every Cursor session distills with no project at all.
        """
        checkout = tmp_path / "work"
        checkout.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=checkout, check=True, capture_output=True)
        started = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)
        ended = datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc)
        facts = cursor_transcripts.parse(
            transcript, session_id="conv-1", cwd=str(checkout), started_at=started,
            ended_at=ended,
        )
        assert (facts.started_at, facts.ended_at) == (started, ended)
        assert facts.repo_root == str(checkout)
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
        assert [s.exists for s in cursor_transcripts.discover(log, tmp_path / "none")] == [False]

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
        found = {s.session_id: s for s in cursor_transcripts.discover(log, tmp_path / "none")}
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
        assert [s.scope for s in cursor_transcripts.discover(log, tmp_path / "none")] == ["homelab"]

    def test_rows_without_a_transcript_pointer_are_ignored(self, tmp_path):
        log = tmp_path / "log.jsonl"
        log.write_text(json.dumps({"session_id": "a", "scope": "main"}) + "\n")
        assert cursor_transcripts.discover(log, tmp_path / "none") == []

    def test_a_missing_log_is_empty_not_an_error(self, tmp_path):
        assert cursor_transcripts.discover(tmp_path / "nope.jsonl", tmp_path / "none") == []

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


def _cursor_tree(root, sessions):
    """Build Cursor's real on-disk layout (lab/054) for a list of sessions.

    Each entry is (project_dir_name, session_id, cwd_or_None). `cwd` None writes
    no meta.json at all, which is the shape of a session Cursor recorded before
    it wrote one, or one whose chats entry has been cleaned up.
    """
    projects, chats = root / "projects", root / "chats"
    for index, (project, session_id, cwd) in enumerate(sessions):
        transcript_dir = projects / project / "agent-transcripts" / session_id
        transcript_dir.mkdir(parents=True, exist_ok=True)
        (transcript_dir / f"{session_id}.jsonl").write_text(
            json.dumps({"role": "user", "message": {"content": "hello"}}) + "\n"
        )
        if cwd is not None:
            # The hash directory is not derivable from the session id — that is
            # why the reader globs for it rather than addressing it.
            meta_dir = chats / f"{index:032x}" / session_id
            meta_dir.mkdir(parents=True, exist_ok=True)
            (meta_dir / "meta.json").write_text(json.dumps({
                "schemaVersion": 1, "createdAtMs": 1786398926686,
                "updatedAtMs": 1786398973904, "hasConversation": True, "cwd": cwd,
            }))
    return projects, chats


class TestFilesystemDiscovery:
    """The second discovery surface: sessions no hook ever saw.

    Reading only the sessionEnd log made every session predating the hooks
    undiscoverable while its transcript sat on disk — lost by policy rather than
    by format, which bites hardest on the machine Thalamus arrives at late
    (lab/054).
    """

    def test_a_session_no_hook_saw_is_found_with_its_scope_unresolved(self, tmp_path, monkeypatch):
        projects, chats = _cursor_tree(tmp_path, [("home-u-work", "sess-a", "/home/u/work")])
        monkeypatch.setattr(cursor_transcripts, "CURSOR_CHATS", chats)
        found = cursor_transcripts.discover(tmp_path / "nolog.jsonl", projects)
        assert [s.session_id for s in found] == ["sess-a"]
        assert found[0].found_by == frozenset({cursor_transcripts.DISCOVERED_BY_FILESYSTEM})
        # The load-bearing assertion: NOT `main`. Routing an unattested session
        # into the operator's own subgraph is a decision nobody made.
        assert found[0].scope == cursor_transcripts.UNRESOLVED_SCOPE
        assert not found[0].scope_resolved

    def test_cwd_is_read_from_cursors_own_record_not_the_directory_name(
        self, tmp_path, monkeypatch
    ):
        """Un-sanitizing `home-u-work` back to a path is a guess that arrives
        with no error signal; meta.json is evidence Cursor wrote at the time."""
        projects, chats = _cursor_tree(tmp_path, [("home-u-work", "sess-a", "/home/u/actual")])
        monkeypatch.setattr(cursor_transcripts, "CURSOR_CHATS", chats)
        found = cursor_transcripts.discover(tmp_path / "nolog.jsonl", projects)
        assert found[0].cwd == "/home/u/actual"
        assert found[0].ended_at is not None

    def test_a_session_with_no_meta_json_is_still_found_without_a_cwd(
        self, tmp_path, monkeypatch
    ):
        """Absent, not guessed. The transcript is still distillable."""
        projects, chats = _cursor_tree(tmp_path, [("home-u-work", "sess-a", None)])
        monkeypatch.setattr(cursor_transcripts, "CURSOR_CHATS", chats)
        found = cursor_transcripts.discover(tmp_path / "nolog.jsonl", projects)
        assert [s.session_id for s in found] == ["sess-a"]
        assert found[0].cwd == "" and found[0].ended_at is None

    def test_extraction_sandboxes_are_refused_by_project_name(self, tmp_path, monkeypatch):
        """Every headless extraction is a full Cursor session that files its own
        transcript, so the sweep would otherwise distill the act of remembering."""
        projects, chats = _cursor_tree(tmp_path, [
            ("tmp-thalamus-extract-brs58tqj", "sand-a", "/tmp/thalamus-extract-brs58tqj"),
            ("home-u-work", "sess-a", "/home/u/work"),
        ])
        monkeypatch.setattr(cursor_transcripts, "CURSOR_CHATS", chats)
        found = cursor_transcripts.discover(tmp_path / "nolog.jsonl", projects)
        assert [s.session_id for s in found] == ["sess-a"]

    def test_a_sandbox_is_still_refused_when_its_project_dir_is_unrecognisable(
        self, tmp_path, monkeypatch
    ):
        """Defence in depth, and the reason recovering a real cwd earns its keep:
        the project name carries no marker here, and only meta.json's cwd does."""
        projects, chats = _cursor_tree(
            tmp_path, [("some-other-name", "sand-a", "/tmp/thalamus-extract-mq2pdfe7")]
        )
        monkeypatch.setattr(cursor_transcripts, "CURSOR_CHATS", chats)
        assert cursor_transcripts.discover(tmp_path / "nolog.jsonl", projects) == []

    def test_a_missing_projects_tree_is_empty_not_an_error(self, tmp_path):
        assert cursor_transcripts.discover(tmp_path / "nolog.jsonl", tmp_path / "nope") == []


class TestSurfaceMerge:
    """Per-field merge: each surface supplies what only it can know.

    Hook rows carry a resolved scope no filesystem read can recover; the
    filesystem sees sessions the log never recorded; the pin ledger holds the
    launch scope of a session whose sessionEnd hook never fired.
    Last-writer-wins across the whole record would let a filesystem row's
    unresolved scope overwrite a resolved one, which is why the rule is per-field
    (TOKI, arXiv 2606.06240).
    """

    def test_the_hook_row_supplies_the_scope_and_both_surfaces_are_recorded(
        self, tmp_path, monkeypatch
    ):
        projects, chats = _cursor_tree(tmp_path, [("home-u-work", "sess-a", "/home/u/work")])
        monkeypatch.setattr(cursor_transcripts, "CURSOR_CHATS", chats)
        log = tmp_path / "log.jsonl"
        log.write_text(json.dumps({
            "session_id": "sess-a", "scope": "homelab", "ts": "2026-08-10T09:00:00Z",
            "transcript_path": str(
                projects / "home-u-work" / "agent-transcripts" / "sess-a" / "sess-a.jsonl"),
        }) + "\n")
        found = cursor_transcripts.discover(log, projects)
        assert len(found) == 1
        assert found[0].scope == "homelab" and found[0].scope_resolved
        assert found[0].found_by == frozenset({
            cursor_transcripts.DISCOVERED_BY_HOOK,
            cursor_transcripts.DISCOVERED_BY_FILESYSTEM,
        })

    def test_the_filesystem_fills_a_cwd_the_hook_row_lacks(self, tmp_path, monkeypatch):
        projects, chats = _cursor_tree(tmp_path, [("home-u-work", "sess-a", "/home/u/actual")])
        monkeypatch.setattr(cursor_transcripts, "CURSOR_CHATS", chats)
        log = tmp_path / "log.jsonl"
        log.write_text(json.dumps({
            "session_id": "sess-a", "scope": "main", "ts": "2026-08-10T09:00:00Z",
            "transcript_path": str(
                projects / "home-u-work" / "agent-transcripts" / "sess-a" / "sess-a.jsonl"),
        }) + "\n")
        assert cursor_transcripts.discover(log, projects)[0].cwd == "/home/u/actual"

    def test_the_pin_ledger_supplies_a_scope_no_session_end_row_recorded(
        self, tmp_path, monkeypatch
    ):
        """A session whose sessionEnd hook never fired — a crash, a `kill-window`,
        a console close past its grace budget — is found only by the filesystem,
        which knows no scope. Its launch scope is in our own tier-0 ledger, so
        refusing it as unroutable discarded an answer we already held."""
        projects, chats = _cursor_tree(tmp_path, [("home-u-work", "sess-a", "/home/u/work")])
        monkeypatch.setattr(cursor_transcripts, "CURSOR_CHATS", chats)
        ledger = tmp_path / "pins.jsonl"
        ledger.write_text(json.dumps({
            "session_id": "sess-a", "scope": "homelab", "cwd": "/home/u/work",
            "ts": "2026-08-10T09:00:00Z",
        }) + "\n")
        found = cursor_transcripts.discover(tmp_path / "nolog.jsonl", projects, ledger)
        assert len(found) == 1
        assert found[0].scope == "homelab" and found[0].scope_resolved
        assert cursor_transcripts.DISCOVERED_BY_LEDGER in found[0].found_by
        assert cursor_transcripts.claim_unresolved(found)[1] == []

    def test_a_session_end_scope_outranks_the_launch_scope(self, tmp_path, monkeypatch):
        """PerRule, not last-writer-wins by file: a session can be rescoped after
        launch, so the row written at the end is the one that knows."""
        projects, chats = _cursor_tree(tmp_path, [("home-u-work", "sess-a", "/home/u/work")])
        monkeypatch.setattr(cursor_transcripts, "CURSOR_CHATS", chats)
        log = tmp_path / "log.jsonl"
        log.write_text(json.dumps({
            "session_id": "sess-a", "scope": "qe", "ts": "2026-08-10T10:00:00Z",
            "transcript_path": str(
                projects / "home-u-work" / "agent-transcripts" / "sess-a" / "sess-a.jsonl"),
        }) + "\n")
        ledger = tmp_path / "pins.jsonl"
        ledger.write_text(json.dumps({
            "session_id": "sess-a", "scope": "homelab", "ts": "2026-08-10T09:00:00Z",
        }) + "\n")
        assert cursor_transcripts.discover(log, projects, ledger)[0].scope == "qe"

    def test_the_pin_ledger_supplies_a_field_and_never_discovers_a_session(self, tmp_path):
        """The ledger records Claude Code and Cursor sessions in the same rows with
        nothing to tell them apart, so discovering from it would sweep every Claude
        session on the box into the Cursor extractor."""
        ledger = tmp_path / "pins.jsonl"
        ledger.write_text(json.dumps({
            "session_id": "a-claude-session", "scope": "main", "ts": "2026-08-10T09:00:00Z",
        }) + "\n")
        assert cursor_transcripts.discover(tmp_path / "nolog.jsonl", tmp_path / "nope", ledger) == []

    def test_the_earliest_ledger_row_gives_the_launch_scope(self, tmp_path, monkeypatch):
        """Later `engaged` rows restate the scope rather than revising it, and the
        ledger is not guaranteed append-ordered, so the earliest dated row wins."""
        projects, chats = _cursor_tree(tmp_path, [("home-u-work", "sess-a", "/home/u/work")])
        monkeypatch.setattr(cursor_transcripts, "CURSOR_CHATS", chats)
        ledger = tmp_path / "pins.jsonl"
        ledger.write_text("\n".join(json.dumps(r) for r in [
            {"session_id": "sess-a", "scope": "engaged-later", "event": "engaged",
             "ts": "2026-08-10T11:00:00Z"},
            {"session_id": "sess-a", "scope": "homelab", "ts": "2026-08-10T09:00:00Z"},
        ]) + "\n")
        assert cursor_transcripts.discover(
            tmp_path / "nolog.jsonl", projects, ledger)[0].scope == "homelab"

    def test_the_newest_hook_row_wins_by_timestamp_not_by_file_order(self, tmp_path):
        """An out-of-order log must not elect the wrong scope. Position was the
        implicit tie-break, and it holds only while the log is append-ordered."""
        log = tmp_path / "log.jsonl"
        log.write_text("\n".join(json.dumps(r) for r in [
            {"session_id": "a", "scope": "homelab", "transcript_path": "/t.jsonl",
             "ts": "2026-07-29T10:00:00Z"},
            {"session_id": "a", "scope": "main", "transcript_path": "/t.jsonl",
             "ts": "2026-07-29T09:00:00Z"},
        ]) + "\n")
        assert [s.scope for s in cursor_transcripts.discover(log, tmp_path / "nope")] == ["homelab"]

    def test_an_undated_row_does_not_displace_a_dated_one(self, tmp_path):
        log = tmp_path / "log.jsonl"
        log.write_text("\n".join(json.dumps(r) for r in [
            {"session_id": "a", "scope": "homelab", "transcript_path": "/t.jsonl",
             "ts": "2026-07-29T10:00:00Z"},
            {"session_id": "a", "scope": "main", "transcript_path": "/t.jsonl"},
        ]) + "\n")
        assert [s.scope for s in cursor_transcripts.discover(log, tmp_path / "nope")] == ["homelab"]


class TestClaimUnresolved:
    """An unmade routing decision is refused, never defaulted.

    A scope is written into vertex IDs, so distilling an unattested session into
    `main` is not a mistake an operator can walk back later.
    """

    def _sessions(self):
        return [
            cursor_transcripts.EndedSession(
                session_id="attested", scope="homelab",
                transcript_path=Path("/t.jsonl"), ended_at=None),
            cursor_transcripts.EndedSession(
                session_id="globbed", scope=cursor_transcripts.UNRESOLVED_SCOPE,
                transcript_path=Path("/u.jsonl"), ended_at=None),
        ]

    def test_without_an_assignment_the_unresolved_one_is_refused_not_defaulted(self):
        ready, refused = cursor_transcripts.claim_unresolved(self._sessions())
        assert [s.session_id for s in ready] == ["attested"]
        # Returned, not dropped: the caller has to be able to name it, or the
        # operator can never learn there is anything to assign.
        assert [s.session_id for s in refused] == ["globbed"]

    def test_an_assignment_claims_only_the_unresolved_one(self):
        ready, refused = cursor_transcripts.claim_unresolved(self._sessions(), "literature")
        assert refused == []
        assert {s.session_id: s.scope for s in ready} == {
            "attested": "homelab",     # a resolved scope is never overwritten
            "globbed": "literature",
        }

    def test_an_empty_assignment_cannot_stand_in_for_main(self):
        _ready, refused = cursor_transcripts.claim_unresolved(self._sessions(), "")
        assert len(refused) == 1


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
