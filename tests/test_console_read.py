"""The console's read view: resolution, tailing, and the display projection.

The invariant worth holding onto here is that resolution **refuses rather than
guesses**. Showing one session's transcript under another session's tab is a
worse failure than showing nothing, because nothing is visibly nothing and the
wrong feed looks exactly like the right one.
"""

from __future__ import annotations

import json

import pytest

from thalamus.console import transcript as tr


def write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def append_jsonl(path, records):
    with path.open("a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def assistant(*blocks, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"content": list(blocks)}}


def ledger_row(sid, scope="main", cwd="/repo", pane="", ts="2026-08-09T00:00:00Z"):
    return {"session_id": sid, "scope": scope, "cwd": cwd,
            "tmux_pane": pane, "ts": ts, "agent": "", "room": "", "forked_from": ""}


# ---- the project-directory flattening ----

@pytest.mark.parametrize("cwd,slug", [
    ("/home/ybx/code/thalamus", "-home-ybx-code-thalamus"),
    ("/home/ybx/.claude/plugins", "-home-ybx--claude-plugins"),        # `.` and `/` both
    ("/home/ybx/Documents/resume-workbench", "-home-ybx-Documents-resume-workbench"),
    ("/tmp/a__b", "-tmp-a--b"),                                        # `_` too
])
def test_project_slug_matches_claude_codes_flattening(cwd, slug):
    assert tr.project_slug(cwd) == slug


def test_transcript_path_falls_back_to_a_glob(tmp_path, monkeypatch):
    """The filename is the session id, so a session is findable even when the
    recorded cwd does not reproduce its directory name."""
    monkeypatch.setattr(tr, "CLAUDE_PROJECTS", tmp_path)
    proj = tmp_path / "-somewhere-else"
    proj.mkdir()
    (proj / "sid-1.jsonl").write_text("")
    assert tr.transcript_path("sid-1", "/wrong/place") == proj / "sid-1.jsonl"
    assert tr.transcript_path("sid-missing", "/wrong/place") is None


# ---- the ledger index ----

def test_ledger_indexes_by_pane_and_tails(tmp_path):
    pins = tmp_path / "pins.jsonl"
    write_jsonl(pins, [ledger_row("s1", pane="%1"), ledger_row("s2", pane="%2")])
    idx = tr.LedgerIndex(pins)
    idx.refresh()
    assert idx.by_pane("%1")["session_id"] == "s1"

    # Appended rows are picked up without re-reading the file from the start.
    before = idx._offset
    append_jsonl(pins, [ledger_row("s3", pane="%3")])
    idx.refresh()
    assert idx._offset > before
    assert idx.by_pane("%3")["session_id"] == "s3"


def test_recycled_pane_resolves_to_the_newest_session(tmp_path):
    """A recycle respawns the window and preserves its pane id, so the
    replacement session appends a fresher row under the same key."""
    pins = tmp_path / "pins.jsonl"
    write_jsonl(pins, [ledger_row("old", pane="%7", ts="2026-08-09T00:00:00Z"),
                       ledger_row("new", pane="%7", ts="2026-08-09T01:00:00Z")])
    idx = tr.LedgerIndex(pins)
    idx.refresh()
    assert idx.by_pane("%7")["session_id"] == "new"


def test_event_rows_never_shadow_a_launch_row(tmp_path):
    """`engaged` events share the session id but carry no launch facts."""
    pins = tmp_path / "pins.jsonl"
    write_jsonl(pins, [ledger_row("s1", pane="%1"),
                       {"event": "engaged", "session_id": "s1", "scope": "main",
                        "ts": "2026-08-09T00:00:01Z"}])
    idx = tr.LedgerIndex(pins)
    idx.refresh()
    assert idx.by_pane("%1")["cwd"] == "/repo"


def test_partial_final_line_is_not_parsed_until_complete(tmp_path):
    pins = tmp_path / "pins.jsonl"
    pins.write_text(json.dumps(ledger_row("s1", pane="%1")) + "\n" + '{"session_id": "s2"')
    idx = tr.LedgerIndex(pins)
    idx.refresh()
    assert idx.by_pane("%1") is not None
    with pins.open("a") as fh:
        fh.write(', "tmux_pane": "%2", "scope": "main", "cwd": "/repo"}\n')
    idx.refresh()
    assert idx.by_pane("%2")["cwd"] == "/repo"


# ---- the legacy fallback ----

def test_legacy_match_resolves_a_unique_launch(tmp_path):
    pins = tmp_path / "pins.jsonl"
    write_jsonl(pins, [ledger_row("s1", scope="homelab", ts="2026-08-09T00:00:01Z")])
    idx = tr.LedgerIndex(pins)
    idx.refresh()
    start = tr._row_epoch({"ts": "2026-08-09T00:00:00Z"})
    assert idx.legacy_match("homelab", "/repo", start)["session_id"] == "s1"


def test_legacy_match_refuses_when_two_sessions_share_scope_and_cwd(tmp_path):
    """The live roster really does hold two `main` windows in one checkout, so
    this is the normal case, not a corner."""
    pins = tmp_path / "pins.jsonl"
    write_jsonl(pins, [ledger_row("s1", ts="2026-08-09T00:00:01Z"),
                       ledger_row("s2", ts="2026-08-09T00:00:20Z")])
    idx = tr.LedgerIndex(pins)
    idx.refresh()
    start = tr._row_epoch({"ts": "2026-08-09T00:00:00Z"})
    assert idx.legacy_match("main", "/repo", start) is None


def test_legacy_match_ignores_a_later_session_in_the_same_place(tmp_path):
    """An unbounded 'newest row at or after start' would drift onto a successor."""
    pins = tmp_path / "pins.jsonl"
    write_jsonl(pins, [ledger_row("mine", ts="2026-08-09T00:00:01Z"),
                       ledger_row("someone-elses", ts="2026-08-09T06:00:00Z")])
    idx = tr.LedgerIndex(pins)
    idx.refresh()
    start = tr._row_epoch({"ts": "2026-08-09T00:00:00Z"})
    assert idx.legacy_match("main", "/repo", start)["session_id"] == "mine"


# ---- identified vs identifiable ----

def test_resolve_reports_a_known_session_with_no_transcript_yet(tmp_path, monkeypatch):
    """A freshly spawned window is the normal case here, not an edge one.

    Claude Code writes the JSONL on the first turn, so between spawn and the first
    message the session is fully identified and has no transcript. That must not
    read as the ambiguity refusal — the console knows exactly which session it is.
    """
    monkeypatch.setattr(tr, "CLAUDE_PROJECTS", tmp_path / "projects")
    pins = tmp_path / "pins.jsonl"
    write_jsonl(pins, [ledger_row("fresh", pane="%42")])
    idx = tr.LedgerIndex(pins)
    idx.refresh()

    got = tr.resolve("%42", "main", "/repo", 0, idx)
    assert got is not None, "an identified session must not resolve to None"
    session_id, path, launch_cwd = got
    assert session_id == "fresh"
    assert path is None          # nothing written yet
    assert launch_cwd == "/repo"


def test_resolve_returns_none_only_when_the_window_is_unidentifiable(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "CLAUDE_PROJECTS", tmp_path / "projects")
    pins = tmp_path / "pins.jsonl"
    write_jsonl(pins, [ledger_row("s1", pane="%1")])
    idx = tr.LedgerIndex(pins)
    idx.refresh()
    # No row for this pane and no pid to fall back on: genuinely unknown.
    assert tr.resolve("%99", "main", "/repo", 0, idx) is None


def test_resolve_finds_the_transcript_once_the_first_turn_lands(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    monkeypatch.setattr(tr, "CLAUDE_PROJECTS", projects)
    proj = projects / tr.project_slug("/repo")
    proj.mkdir(parents=True)
    (proj / "fresh.jsonl").write_text("")
    pins = tmp_path / "pins.jsonl"
    write_jsonl(pins, [ledger_row("fresh", pane="%42")])
    idx = tr.LedgerIndex(pins)
    idx.refresh()

    session_id, path, _ = tr.resolve("%42", "main", "/repo", 0, idx)
    assert session_id == "fresh"
    assert path == proj / "fresh.jsonl"


def test_row_epoch_reads_timestamps_as_utc():
    # 1970-01-02T00:00:00Z is exactly one day. mktime would skew this by the
    # box's offset and the assertion would fail anywhere but UTC.
    assert tr._row_epoch({"ts": "1970-01-02T00:00:00Z"}) == 86400


# ---- the feed projection ----

def test_feed_projects_prose_tools_and_pairs_results(tmp_path):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"type": "user", "message": {"content": "do the thing"}},
        assistant({"type": "text", "text": "Working on it."},
                  {"type": "tool_use", "id": "t1", "name": "Edit",
                   "input": {"file_path": "/repo/a.py"}}),
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "line one\nline two"}]}},
    ])
    feed = tr.Feed(session_id="s", path=path, cwd="/repo")
    feed.refresh()
    kinds = [i["kind"] for i in feed.items]
    assert kinds == ["user", "prose", "tool"]
    tool = feed.items[-1]
    assert tool["summary"] == "Edit a.py"       # cwd stripped
    assert tool["status"] == "done"
    assert tool["result"] == "line one\nline two"


def test_a_tool_awaiting_its_result_stays_pending(tmp_path):
    """The state the read view cannot interpret on its own: a call with no
    result is either running or blocked on an approval prompt that the
    transcript never records."""
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [assistant({"type": "tool_use", "id": "t1", "name": "Bash",
                                  "input": {"command": "sleep 100"}})])
    feed = tr.Feed(session_id="s", path=path)
    feed.refresh()
    assert feed.items[-1]["status"] == "pending"


def test_error_results_are_marked(tmp_path):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        assistant({"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "x"}}),
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "boom", "is_error": True}]}},
    ])
    feed = tr.Feed(session_id="s", path=path)
    feed.refresh()
    assert feed.items[-1]["status"] == "error"


def test_feed_reads_only_what_was_appended(tmp_path):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [assistant({"type": "text", "text": "first"})])
    feed = tr.Feed(session_id="s", path=path)
    feed.refresh()
    first_seq = feed.seq
    feed.refresh()                                   # nothing new
    assert feed.seq == first_seq
    assert feed.since(first_seq) == []
    append_jsonl(path, [assistant({"type": "text", "text": "second"})])
    feed.refresh()
    fresh = feed.since(first_seq)
    assert [i["text"] for i in fresh] == ["second"]


def test_a_late_result_re_delivers_an_old_item(tmp_path):
    """The reason `seq` is per-item and not just a cursor: a tool emitted many
    records ago resolves later and the client has to hear about it."""
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [assistant({"type": "tool_use", "id": "t1", "name": "Bash",
                                  "input": {"command": "x"}})])
    feed = tr.Feed(session_id="s", path=path)
    feed.refresh()
    caught_up = feed.seq
    append_jsonl(path, [{"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "done"}]}}])
    feed.refresh()
    changed = feed.since(caught_up)
    assert [i["id"] for i in changed] == [1]
    assert changed[0]["status"] == "done"


def test_state_records_are_captured_not_rendered(tmp_path):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"type": "mode", "mode": "normal"},
        {"type": "permission-mode", "permissionMode": "auto"},
        {"type": "agent-setting", "agentSetting": "thalamus-homelab"},
        {"type": "system", "subtype": "turn_duration", "durationMs": 5},
    ])
    feed = tr.Feed(session_id="s", path=path)
    feed.refresh()
    assert feed.mode == "normal"
    assert feed.permission_mode == "auto"
    assert feed.agent == "thalamus-homelab"
    assert list(feed.items) == []


def test_harness_meta_turns_are_dropped_but_sidechains_are_kept(tmp_path):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [
        {"type": "user", "isMeta": True, "message": {"content": "harness chatter"}},
        assistant({"type": "text", "text": "subagent speaking"}, sidechain=True),
    ])
    feed = tr.Feed(session_id="s", path=path)
    feed.refresh()
    assert [i["kind"] for i in feed.items] == ["prose"]
    assert feed.items[0]["sidechain"] is True


def test_truncation_preserves_lines_and_flags_itself():
    body, truncated = tr._cap_result("\n".join(f"line {i}" for i in range(200)))
    assert truncated
    assert body.count("\n") == tr.RESULT_LINE_CAP - 1
    assert "\n" in body, "line structure must survive — this is a diff, not a summary"


def test_wire_splits_bodies_off_and_caps_the_summary():
    long_cmd = "Bash $ " + "x" * 500
    items = [{"kind": "tool", "id": 1, "seq": 1, "name": "Bash", "summary": long_cmd,
              "result": "a\nb", "status": "done", "truncated": False, "sidechain": False},
             {"kind": "prose", "id": 2, "seq": 2, "text": "hello"}]
    out = tr.wire(items)
    assert "result" not in out[0]
    assert out[0]["preview"] == "a b"          # single line, for the collapsed row
    assert out[0]["has_body"] is True
    assert len(out[0]["summary"]) <= tr.SUMMARY_CAP + 2
    assert out[1] == items[1]                   # non-tool items pass through


def test_cold_open_is_bounded_and_keeps_the_newest(tmp_path):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [assistant({"type": "text", "text": f"m{i}"}) for i in range(100)])
    feed = tr.Feed(session_id="s", path=path)
    feed.refresh()
    tail = feed.since(0, limit=10)
    assert len(tail) == 10
    assert tail[-1]["text"] == "m99"            # truncating the head, never the tail


def test_feed_store_evicts_least_recently_used(tmp_path):
    store = tr.FeedStore(cap=2)
    for name in ("a", "b", "c"):
        p = tmp_path / f"{name}.jsonl"
        p.write_text("")
        store.get(name, p)
    assert set(store._feeds) == {"b", "c"}


def test_shorten_leaves_a_summary_alone_without_a_cwd():
    assert tr.shorten("Edit /repo/a.py", "") == "Edit /repo/a.py"
    assert tr.shorten("Bash $ cd /repo; ls", "/repo") == "Bash $ ls"
