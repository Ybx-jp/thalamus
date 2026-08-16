"""
Control-plane tests: the window projection, the spawn whitelist, the key allowlist.

Interfaces: thalamus.console.server
Infrastructure: a stubbed `tmux` callable and tmp_path directories — no tmux
server, no claude, no graph.
Scope: the two things the client trusts blind and the one thing a client must not
be able to widen. The projection (`parse_windows`) decides which window is the
anchor, and the anchor is the window the UI refuses to close; the spawn picker's
directory list is simultaneously the whitelist a spawn request is checked against,
so "what the client was offered" and "what the server will accept" have to be the
same computation. Driving a real pinned session is verified live — a bridge can
only be tested by the tmux it bridges to.
"""

import json
import subprocess
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from thalamus.console import server
from thalamus.console.server import Config, Handler, parse_windows, spawn_dirs

WINDOW_FIELDS = "0\tmain\t1\tclaude\t60\t50\t0\t/home/op/code/thalamus"


def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    return path


def _pin():
    """The real `harness.pin`, which the console imports lazily rather than holding.

    Tests patch the module the console resolves at call time, not an attribute on
    the console — there is deliberately no `server.pin` to reach for.
    """
    return server.pin_module()


# ---- the projection the client renders ----


def test_the_lowest_indexed_window_is_the_anchor():
    """Not the first line, not the one named `main` — the lowest index.

    tmux's base-index is an operator setting, and several windows can carry the
    same scope name once the same expert is spawned in two directories. Index
    ordering is the one property that survives both: the anchor can't be closed,
    so nothing can ever take an index below it.
    """
    raw = "\n".join([
        "3\thomelab\t1\tclaude\t60\t50\t0\t/home/op/code/other",
        "1\tmain\t0\tclaude\t60\t50\t0\t/home/op/code/thalamus",
        "2\tmain\t0\tclaude\t60\t50\t0\t/home/op/code/other",
    ])
    windows = parse_windows(raw)

    assert [w["index"] for w in windows] == [3, 1, 2]
    assert [w["anchor"] for w in windows] == [False, True, False]


def test_a_window_carries_its_own_directory_not_the_rosters():
    """Two sessions of one expert are told apart by cwd, so cwd is projected three
    ways: raw (identity), basename (the tab's second line), tilded (the tooltip)."""
    home = str(Path.home())
    raw = f"0\thomelab\t1\tclaude\t60\t50\t0\t{home}/code/some-project"
    (window,) = parse_windows(raw)

    assert window["cwd"] == f"{home}/code/some-project"
    assert window["cwd_label"] == "some-project"
    assert window["cwd_short"] == "~/code/some-project"


def test_an_unparseable_line_is_dropped_not_guessed():
    """A line tmux didn't format as expected yields no window rather than one with
    an invented index — an index is a send-keys target."""
    raw = "\n".join(["not a window line", WINDOW_FIELDS])

    assert [w["index"] for w in parse_windows(raw)] == [0]


def test_a_lifecycle_flag_is_a_start_stamp_not_a_bare_yes():
    """The two operations that can lose work are the two the operator cannot time.

    `RECYCLE_GRACE_S` lives inside the worker thread, so a bare boolean renders a
    word with no duration while the worker silently races a clock. The stamp is also
    what makes a leaked flag self-reporting: the entry is dropped in the worker's
    `finally`, so a worker that dies leaves the row saying "restarting…" forever with
    nothing to contradict it — unless the row can say *how long* forever has been.
    """
    server.RECYCLING.clear()
    server.CLOSING.clear()
    try:
        server.RECYCLING[4] = 1_000_000.0
        server.CLOSING[7] = 2_000_000.0
        raw = "\n".join([
            "4\tmain\t0\tclaude\t60\t50\t0\t/home/op",
            "7\tqe\t0\tclaude\t60\t50\t0\t/home/op",
            "9\tdesigner\t0\tclaude\t60\t50\t0\t/home/op",
        ])

        by_index = {w["index"]: w for w in parse_windows(raw)}

        assert by_index[4]["recycling"] == 1_000_000.0
        assert by_index[7]["closing"] == 2_000_000.0
        # Absent, not False-with-a-zero: a zero stamp would render as 1970 and a
        # reader asking only "is this in flight" must still get a falsy answer.
        assert by_index[9]["recycling"] is None
        assert by_index[4]["closing"] is None
    finally:
        server.RECYCLING.clear()
        server.CLOSING.clear()


def test_a_second_restart_request_does_not_reset_the_clock():
    """`already` suppresses the duplicate worker; it must suppress the stamp too.

    Otherwise a phone and a desktop polling the same row, or an impatient double
    tap, silently restart the elapsed time the operator is using to decide whether
    the window has hung — the one number the stamp exists to provide.
    """
    server.RECYCLING.clear()
    try:
        server.RECYCLING.setdefault(3, 111.0)
        server.RECYCLING.setdefault(3, 999.0)

        assert server.RECYCLING[3] == 111.0
    finally:
        server.RECYCLING.clear()


def test_an_unobservable_session_is_not_reported_as_unblocked(monkeypatch):
    """The distinction the whole row exists to draw, on the row's own indicator.

    Session descriptors are partitioned by config dir (lab/045), so a console can be
    structurally unable to see a window's descriptor. Calling that window "not
    stuck" states a fact on evidence that says nothing — so `observed` is False and
    `blocked` is None, and neither is the same pixel as a session that was read and
    found healthy.
    """
    class _Session:
        def __init__(self, session_id, status, stamp):
            self.session_id, self.status, self.status_updated_at = (
                session_id, status, stamp)

    class _Dispatch:
        WAITING_STATUS = "waiting"
        BUSY_STATUS = "busy"
        DELIVERABLE_STATUSES = ("idle", "busy")

        class quick:
            @staticmethod
            def live_sessions():
                return [_Session("seen-blocked", "waiting", 1_700_000_000_000),
                        _Session("seen-fine", "idle", 1_700_000_000_000)]

    monkeypatch.setattr(server, "dispatch_module", lambda: _Dispatch)
    windows = [{"session_id": "seen-blocked"}, {"session_id": "seen-fine"},
               {"session_id": "in-another-config-dir"}, {"session_id": ""}]

    server.attach_blocked(windows)

    assert (windows[0]["observed"], windows[0]["blocked"]) == (True, True)
    assert windows[0]["blocked_since"] == 1_700_000_000.0
    assert (windows[1]["observed"], windows[1]["blocked"]) == (True, False)
    assert windows[1]["blocked_since"] is None
    # The two that could not be read. Not False — None. And no state word either:
    # without a descriptor `idle` and `busy` are equally unknown, so observability
    # stays one fact about the row instead of an absence spelled per field.
    for row in (windows[2], windows[3]):
        assert row["observed"] is False
        assert row["blocked"] is None
        assert row["blocked_since"] is None
        assert row["activity"] == ""
        assert row["activity_since"] is None


def test_the_reduction_reads_only_fields_the_real_descriptor_has():
    """The liveness tests hand `attach_blocked` a fake session, which is the right
    shape for testing its logic and the wrong shape for catching a rename.

    A fake grows whatever attribute the code asks for, so the suite stayed green
    while `server.py` read `status_updated_at` from a descriptor that did not carry
    it — an AttributeError on every poll that could read a descriptor at all, which
    is the common case in production and the impossible case under a fake.

    So this binds the reduction to the real type. It fails on a rename in either
    file rather than at runtime on the phone.

    The names are *derived from the reduction's own source*, not listed here. A list
    is a second owner: it is maintained by hand alongside the code it describes, so
    the day the reduction reads a fourth attribute the fake grows it, the list never
    hears about it, and the binding is decorative again — the original defect with
    one more name in front of it. Reading them out of the source means a new read is
    covered the moment it is written.
    """
    import dataclasses
    import re

    from thalamus.harness.quick import LiveSession

    reads = _attribute_reads(server.attach_blocked, "session")
    assert "status_updated_at" in reads, (
        "the source scan found no `session.status_updated_at` — either the reduction "
        "stopped reading it or this scan has stopped seeing reads, and the second "
        "would make every assertion below vacuous")

    carried = {f.name for f in dataclasses.fields(LiveSession)}
    for field in sorted(reads):
        assert field in carried, (
            f"attach_blocked reads session.{field}; the descriptor no longer carries "
            f"it. LiveSession has: {sorted(carried)}")


def _attribute_reads(fn, receiver: str) -> set[str]:
    """Every `<receiver>.<name>` read in a function's own source.

    Deliberately syntactic. The alternative — call the reduction and see what it
    touches — is what the fake already does, and what cannot see an attribute the
    code never reaches on the one input the test happened to construct.
    """
    import inspect
    import re
    import textwrap

    source = textwrap.dedent(inspect.getsource(fn))
    return set(re.findall(rf"\b{re.escape(receiver)}\.([A-Za-z_][A-Za-z0-9_]*)", source))


def test_the_reduction_reads_only_module_constants_the_real_module_has():
    """The same binding for the *module* the reduction reads, not just the session.

    `attach_blocked` reads three constants off `harness.dispatch`, and the liveness
    tests hand it a hand-written `_Dispatch` class that re-declares all three. That
    class is a fake in exactly the sense the descriptor was: it grows whatever the
    code asks it for, so a rename in `dispatch.py` leaves the suite green and takes
    out `/api/panes` on the first busy session.

    Measured 2026-08-15: `DELIVERABLE_STATUSES` and `WAITING_STATUS` are pinned to
    the real module by `test_console_js.py`, and `BUSY_STATUS` is pinned nowhere but
    inside the fake. One identifier over from the defect that shipped.

    Derived from source for the same reason as above — a fourth constant is covered
    the day it is read, not the day someone remembers to add it here.
    """
    from thalamus.harness import dispatch as dispatch_mod

    reads = _attribute_reads(server.attach_blocked, "dispatch")
    # `dispatch.quick` is the module's own import, reached for `live_sessions()`.
    assert "BUSY_STATUS" in reads, (
        "the source scan found no `dispatch.BUSY_STATUS` — see the vacuity note above")

    for name in sorted(reads):
        assert hasattr(dispatch_mod, name), (
            f"attach_blocked reads dispatch.{name}, which the real module does not "
            f"have. The `_Dispatch` fake in the liveness tests would still supply it.")


def test_the_source_scan_can_actually_fail():
    """The two guards above rest entirely on the scan seeing what a reduction reads.

    A scan that silently returns nothing turns both of them into assertions about an
    empty set, which pass forever. So the scan is pointed at a known shape and must
    find exactly the reads in it — and must not invent one that is not there.
    """
    def sample(session, dispatch):
        if session.status == dispatch.WAITING_STATUS:
            return session.session_id
        return session.status_updated_at, dispatch.BUSY_STATUS

    assert _attribute_reads(sample, "session") == {
        "status", "session_id", "status_updated_at"}
    assert _attribute_reads(sample, "dispatch") == {"WAITING_STATUS", "BUSY_STATUS"}
    assert _attribute_reads(sample, "nobody") == set()


def test_the_poll_composes_the_ledger_join_and_the_descriptor_read(tmp_path,
                                                                   monkeypatch):
    """
    Scenario: `/api/panes` served once, over HTTP, with a real pin-ledger row and a
    real session descriptor on disk — no fake session, no fake dispatch module.

    Verifications:
    - the ledger join supplies `session_id`, `project`, `repo_root`
    - the descriptor read keys on that `session_id` and reports `blocked`
    - a window with no ledger row is `observed is False`, not "not stuck"

    This is the composition, and the composition is what broke. `attach_ledger_facts`
    supplies the session id; `attach_blocked` keys on it; the defect that shipped an
    AttributeError on every poll lived precisely in that seam, and both halves were
    only ever tested apart — each against a hand-written stand-in that could not
    disagree with the real thing. Before this test `/api/panes` had no coverage at
    any level, which is why a human reading a diff was the control.

    The descriptor carries no `procStart`, which skips the `/proc` liveness check —
    the same trick `test_dispatch.py` uses. No tmux, no claude, no graph.
    """
    from thalamus.console import transcript as tr

    config = tmp_path / "config"
    (config / "sessions").mkdir(parents=True)
    # A real descriptor, in the shape the harness writes. `status: waiting` is the
    # one the roster must not render as healthy.
    (config / "sessions" / "4242.json").write_text(json.dumps({
        "sessionId": "sess-blocked", "pid": 4242, "cwd": "/home/op/code/thalamus",
        "agent": "thalamus-qe", "name": "alpha-qe", "status": "waiting",
        "updatedAt": 1_700_000_000_000,
    }))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))

    pins = tmp_path / "pins.jsonl"
    pins.write_text(json.dumps({
        "session_id": "sess-blocked", "scope": "qe", "tmux_pane": "%7",
        "cwd": "/home/op/code/thalamus", "project": "thalamus",
        "repo_root": "/home/op/code/thalamus", "ts": "2026-08-15T10:00:00Z",
    }) + "\n")
    monkeypatch.setattr(tr, "PINS", pins)
    # The index is a module-global cached across polls, so a stale one from another
    # test would answer this one. Rebuilt rather than reused.
    monkeypatch.setattr(server, "_LEDGER", None)
    monkeypatch.setattr(server, "_FEEDS", None)

    joined = ("3\tqe\t1\tclaude\t60\t50\t0\t/home/op/code/thalamus\tclaude\t%7\t4242")
    orphan = ("4\tmain\t0\tclaude\t60\t50\t0\t/home/op/code/other\tclaude\t%9\t4243")

    cfg = Config(project_root=tmp_path, scan_roots=[tmp_path])
    with _serving(cfg, windows="\n".join([joined, orphan])) as post:
        body = post.get("/api/panes")

    rows = {w["index"]: w for w in body["windows"]}

    # The join: launch facts tmux cannot know, carried by the ledger row.
    assert rows[3]["session_id"] == "sess-blocked"
    assert rows[3]["project"] == "thalamus"
    assert rows[3]["repo_root"] == "/home/op/code/thalamus"

    # The read that depends on it. `blocked` is True only if the session id from the
    # ledger reached the descriptor lookup — which is the seam.
    assert rows[3]["observed"] is True
    assert rows[3]["blocked"] is True
    assert rows[3]["blocked_since"] == 1_700_000_000.0

    # And the window the ledger has never heard of states a non-observation rather
    # than an absence of trouble.
    assert rows[4]["session_id"] == ""
    assert rows[4]["observed"] is False
    assert rows[4]["blocked"] is None

    # The rest of what the payload promises the client, beside the rows.
    assert "grace_s" in body and "distill" in body


def test_screen_rev_moves_with_the_pane_text_and_only_with_it(tmp_path, monkeypatch):
    """The token the rail pulses on, over two polls of the real handler.

    Both halves are the contract, and each fails differently. A token that misses a
    change makes the pulse lie — the window worked and the rail said nothing. A token
    that moves on its own (a capture timestamp, a counter bumped per poll) makes every
    window pulse forever, which is the same as no pulse at all.

    It is not asserted to be a hash of anything. The client compares it to the previous
    poll's for equality and never parses it, so the format is free to change without
    the client changing with it.
    """
    from thalamus.console import transcript as tr

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(tr, "PINS", tmp_path / "pins.jsonl")
    monkeypatch.setattr(server, "_LEDGER", None)
    monkeypatch.setattr(server, "_FEEDS", None)

    busy = ("3\tqe\t1\tclaude\t60\t50\t0\t/home/op/code/thalamus\tclaude\t%7\t4242")
    quiet = ("4\tmain\t0\tclaude\t60\t50\t0\t/home/op/code/other\tclaude\t%9\t4243")

    cfg = Config(project_root=tmp_path, scan_roots=[tmp_path])
    screens = {3: "$ pytest\n", 4: "$ pytest\n"}
    with _serving(cfg, windows="\n".join([busy, quiet]), screens=screens) as post:
        first = {w["index"]: w for w in post.get("/api/panes")["windows"]}
        # Only window 3 moves. Window 4 is captured again and holds its text, which
        # is the case a timestamp or a per-poll counter would get wrong.
        post.fake.screens[3] = "$ pytest\n2 passed\n"
        second = {w["index"]: w for w in post.get("/api/panes")["windows"]}

    assert first[3]["screen_rev"] != second[3]["screen_rev"]
    assert first[4]["screen_rev"] == second[4]["screen_rev"]

    # Every row carries one, in a type the client can compare. Nothing further is
    # asserted about the value: two windows showing the same screen are free to
    # hold equal tokens or not, since a per-window counter is as valid an answer
    # as a digest and a test that pinned either would forbid the other.
    for row in list(first.values()) + list(second.values()):
        assert isinstance(row["screen_rev"], (str, int))


def test_the_poll_join_is_by_pane_and_a_mismatch_does_not_borrow_a_row(tmp_path,
                                                                      monkeypatch):
    """The join key is the pane id, and a wrong one must yield nothing.

    Borrowing another window's row is worse than having none: `project` and
    `repo_root` are what the roster groups on, so a mis-join silently files a
    session under someone else's project and looks identical to a correct one.
    Under-grouping is honest; over-grouping asserts a relation that does not hold.
    """
    from thalamus.console import transcript as tr

    config = tmp_path / "config"
    (config / "sessions").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))

    pins = tmp_path / "pins.jsonl"
    pins.write_text(json.dumps({
        "session_id": "sess-elsewhere", "scope": "qe", "tmux_pane": "%7",
        "cwd": "/home/op/code/thalamus", "project": "thalamus",
        "repo_root": "/home/op/code/thalamus", "ts": "2026-08-15T10:00:00Z",
    }) + "\n")
    monkeypatch.setattr(tr, "PINS", pins)
    monkeypatch.setattr(server, "_LEDGER", None)
    monkeypatch.setattr(server, "_FEEDS", None)

    # Same scope, same cwd, different pane — and pane_pid 0, so the legacy fallback
    # has no start time to match on and must decline rather than guess.
    mismatched = ("3\tqe\t1\tclaude\t60\t50\t0\t/home/op/code/thalamus\tclaude\t%99\t0")

    cfg = Config(project_root=tmp_path, scan_roots=[tmp_path])
    with _serving(cfg, windows=mismatched) as post:
        body = post.get("/api/panes")

    (row,) = body["windows"]
    assert row["session_id"] == ""
    assert row["project"] == "" and row["repo_root"] == ""


def test_the_row_says_nothing_about_liveness_when_the_harness_is_absent(monkeypatch):
    """A console running without the harness package must disclaim, not reassure."""
    monkeypatch.setattr(server, "dispatch_module", lambda: None)
    windows = [{"session_id": "anything"}]

    server.attach_blocked(windows)

    assert windows[0]["observed"] is False
    assert windows[0]["blocked"] is None
    assert windows[0]["activity"] == ""
    assert windows[0]["activity_since"] is None


def test_the_state_word_is_composed_here_and_only_busy_earns_a_clock(monkeypatch):
    """The word the state slot draws, and the stamp that decides whether it ticks.

    The client prints `activity` and draws an elapsed exactly when `activity_since`
    is non-null. Both decisions therefore live here: a client that re-derived either
    from a status value would be a second reader of the field this reduction exists
    to consume, and two readers drift.

    `busy` earns a clock because `busy 14:32` on a session thought finished is a
    finding. `idle` does not — an elapsed on every idle row is motion on most rows at
    once, which spends the attention the terminal states need.
    """
    class _Session:
        def __init__(self, session_id, status, stamp):
            self.session_id, self.status, self.status_updated_at = (
                session_id, status, stamp)

    class _Dispatch:
        WAITING_STATUS = "waiting"
        BUSY_STATUS = "busy"
        DELIVERABLE_STATUSES = ("idle", "busy")

        class quick:
            @staticmethod
            def live_sessions():
                return [_Session("busy-one", "busy", 1_700_000_000_000),
                        _Session("idle-one", "idle", 1_700_000_000_000),
                        _Session("blocked-one", "waiting", 1_700_000_000_000),
                        _Session("odd-one", "compacting", 1_700_000_000_000)]

    monkeypatch.setattr(server, "dispatch_module", lambda: _Dispatch)
    windows = [{"session_id": s} for s in
               ("busy-one", "idle-one", "blocked-one", "odd-one")]

    server.attach_blocked(windows)

    busy, idle, blocked, odd = windows
    assert (busy["activity"], busy["activity_since"]) == ("busy", 1_700_000_000.0)
    assert (idle["activity"], idle["activity_since"]) == ("idle", None)

    # A blocked row's word is the pill, so the slot holds no activity word to compete
    # with it. `blocked` and `activity` are set from one branch and cannot both speak.
    assert (blocked["blocked"], blocked["activity"]) == (True, "")

    # A status the vocabulary does not cover draws nothing rather than the likelier
    # word. The row was read — `observed` is True and `blocked` is a real False — so
    # an empty slot here means "read, not stopped, and no word for it", which is not
    # the same pixel as the unobserved row's *not in reach*.
    assert (odd["observed"], odd["blocked"]) == (True, False)
    assert (odd["activity"], odd["activity_since"]) == ("", None)


def test_an_unparseable_start_stamp_is_absent_rather_than_now():
    """A fabricated start time is indistinguishable on the wire from a recorded one.

    The row renders identity partly from `started`, so inventing one would make two
    sessions look equally well-known when only one is.
    """
    # Parsed as UTC, not as local time: the ledger writes `date -u` and a naive
    # parse would skew every stamp by the box's offset.
    assert server._ledger_epoch("2026-08-15T16:17:41Z") == 1786810661.0
    assert server._ledger_epoch("") is None
    assert server._ledger_epoch("not a timestamp") is None
    assert server._ledger_epoch("2026-08-15 16:17:41") is None


def test_pane_state_flags_survive_the_projection():
    dead = "4\tmain\t0\tbash\t80\t24\t1\t/home/op"
    (window,) = parse_windows(dead)

    assert window["dead"] is True
    assert window["active"] is False
    assert window["width"] == 80 and window["height"] == 24


# ---- the spawn picker IS the whitelist ----


def test_the_picker_offers_favorites_first_and_scans_for_repos(tmp_path):
    code = tmp_path / "code"
    _repo(code / "alpha")
    _repo(code / "beta")
    (code / "not-a-repo").mkdir()

    cfg = Config(project_root=_repo(code / "alpha"), scan_roots=[code])
    dirs, allowed = spawn_dirs(cfg)

    assert dirs[0]["favorite"] is True and dirs[0]["label"] == "alpha"
    assert [d["label"] for d in dirs] == ["alpha", "beta"]  # deduped; no plain dirs
    assert allowed == {str(code / "alpha"), str(code / "beta")}


def test_a_directory_the_picker_never_offered_cannot_be_spawned_into(tmp_path):
    """The whitelist is recomputed from the same function that built the picker, so
    a request naming any other path is refused — including one reached by climbing
    out of an offered directory."""
    code = tmp_path / "code"
    _repo(code / "alpha")
    secret = _repo(tmp_path / "elsewhere")
    cfg = Config(project_root=code / "alpha", scan_roots=[code])

    with _serving(cfg) as post:
        status, body = post("/api/spawn", {"scope": "main", "dir": str(secret)})
        assert status == 400 and "allowed list" in body["error"]

        status, body = post(
            "/api/spawn", {"scope": "main", "dir": str(code / "alpha" / ".." / "elsewhere")}
        )
        assert status == 400 and "allowed list" in body["error"]


def test_a_window_reports_the_room_it_was_created_in(tmp_path):
    """
    Scenario: tmux lists a member window whose start command carries the room

    Verifications:
    - the room is projected onto the window
    - a window created without one reports no room

    Read from `#{pane_start_command}` rather than the window name: the launcher
    puts the room in an `env` prefix on the window's argv, which is what a
    `respawn-window` re-executes, so the start command agrees with the process even
    after the recycle button drops tmux's `-e`. The window name stays the bare
    scope — the room is a second dimension over the roster, not a renaming of it.
    """
    member = ("2\thomelab\t1\tclaude\t60\t50\t0\t/home/op/code/thalamus\t"
              "env THALAMUS_ROOM=alpha CLAUDE_CONFIG_DIR=/home/op/.thalamus/rooms/alpha "
              "claude --agent thalamus-homelab --name alpha-homelab")
    solo = "1\tmain\t0\tclaude\t60\t50\t0\t/home/op/code/thalamus\tclaude"

    rooms = {w["index"]: w["room"] for w in parse_windows("\n".join([member, solo]))}

    assert rooms == {2: "alpha", 1: ""}


def test_a_room_name_that_is_not_a_room_name_is_refused(tmp_path):
    """
    Scenario: a spawn request naming a room with a path or regex metacharacter

    Verifications:
    - it is refused before anything is created

    Naming a room IS creating it (the launcher provisions the dir on the way in),
    so this field is the one place a client's string reaches both a filesystem path
    under ROOMS_DIR and the pattern `room-guard.sh` interpolates to decide who a
    member may message.
    """
    code = tmp_path / "code"
    cfg = Config(project_root=_repo(code / "alpha"), scan_roots=[code])

    with _serving(cfg) as post:
        for bad in ("../escape", "a/b", "Alpha", "a|b"):
            status, body = post("/api/spawn",
                                {"scope": "main", "dir": str(code / "alpha"), "room": bad})
            assert status == 400 and body["error"] == "invalid room name", bad


def test_the_spawn_endpoint_names_the_room_and_never_inherits_one(tmp_path, monkeypatch):
    """
    Scenario: the console spawns into a room, and then spawns solo

    Verifications:
    - the room from the request reaches `pin.spawn`
    - a request with no room passes "" — not None, which would mean "read the env"

    The console is a long-lived server process. If it left the room to
    `resolve_room()`, every session spawned from the phone would silently join
    whatever room the *server* was started in, and the phone would have no way to
    say otherwise.
    """
    code = tmp_path / "code"
    cfg = Config(project_root=_repo(code / "alpha"), scan_roots=[code])
    seen: list[dict] = []
    monkeypatch.setattr(_pin(), "spawn",
                        lambda scope, cwd, **kw: seen.append({"scope": scope, **kw}))

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        post("/api/spawn", {"scope": "main", "dir": str(code / "alpha"), "room": "alpha"})
        post("/api/spawn", {"scope": "main", "dir": str(code / "alpha")})

    assert [s["room"] for s in seen] == ["alpha", ""]
    # And the harness the request did not name is the default, never the last one
    # some other request asked for.
    assert [s["harness"] for s in seen] == ["claude", "claude"]


def test_a_spawn_whose_window_died_is_reported_failed(tmp_path, monkeypatch):
    """
    Scenario: `pin.spawn` reports the window it made did not survive its settle

    Verifications:
    - the response is a failure, not the success every layer below it reported
    - what the window printed on the way out reaches the phone
    - the operator is told to check PATH, which is the cause in almost every case

    `tmux new-window` returns 0 as soon as it has forked — before the command it
    was given has execed. A window whose command cannot be executed at all dies
    instantly and is reaped, while tmux, `pin`, and the console all still see
    success. Measured 2026-08-08: with `claude` off the server's PATH every spawn
    answered ok and produced nothing, which reads on a phone as a button that does
    nothing at all. The verdict is `pin`'s, since it is the only layer holding the
    id of the window it made; the console's job is that it reaches the operator.
    """
    code = tmp_path / "code"
    cfg = Config(project_root=_repo(code / "alpha"), scan_roots=[code])
    pin = _pin()

    def died(*a, **k):
        raise pin.WindowDied("the window was created and its command exited (exit 1) "
                             "— it printed: Not logged in.")

    monkeypatch.setattr(pin, "spawn", died)

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        status, body = post("/api/spawn", {"scope": "main", "dir": str(code / "alpha")})

    assert status == 500 and body["ok"] is False
    assert "Not logged in." in body["output"]
    assert "PATH" in body["output"]


def test_only_a_dead_window_gets_the_path_hint(tmp_path, monkeypatch):
    """A launch that refused itself already said why, and PATH is not it.

    The hint is a guess — a good one for a window that died silently, noise on top
    of a refusal that named its own reason, and misleading if the operator acts on
    it.
    """
    code = tmp_path / "code"
    cfg = Config(project_root=_repo(code / "alpha"), scan_roots=[code])

    def refused(*a, **k):
        raise ValueError("not a directory: /home/op/code/gone")

    monkeypatch.setattr(_pin(), "spawn", refused)

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        status, body = post("/api/spawn", {"scope": "main", "dir": str(code / "alpha")})

    assert status == 500 and body["ok"] is False
    assert "not a directory" in body["output"]
    assert "PATH" not in body["output"]


def test_the_harness_the_phone_picked_is_the_one_that_launches(tmp_path, monkeypatch):
    """
    Scenario: the sheet's harness chip is tapped over to Cursor and a session spawned

    Verifications:
    - the harness from the request reaches `pin.spawn`
    - the picker offers exactly the harnesses that can be pinned, and says which of
      them carries a persona

    The sheet cannot hold its own harness list: `LAUNCH_SHAPES` is what a spawn is
    validated against, so a chip the client invented would be refused after the tap.
    `persona` rides along because the two choices are not the same object — a Cursor
    pin routes and is bounded and has no charter — and the sheet is the only place
    that difference is visible before the window exists.
    """
    code = tmp_path / "code"
    cfg = Config(project_root=_repo(code / "alpha"), scan_roots=[code])
    seen: list[dict] = []
    monkeypatch.setattr(_pin(), "spawn",
                        lambda scope, cwd, **kw: seen.append({"scope": scope, **kw}))

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        options = post.get("/api/spawn-options")
        post("/api/spawn", {"scope": "main", "dir": str(code / "alpha"),
                            "harness": "cursor"})

    assert [s["harness"] for s in seen] == ["cursor"]
    assert options["harnesses"] == [{"harness": "claude", "persona": True},
                                    {"harness": "cursor", "persona": False}]


def test_a_harness_with_no_launch_shape_is_refused(tmp_path):
    """A harness that cannot be pinned is refused before anything is created.

    `launch_argv` raises for it, which would otherwise reach the phone as the last
    line of a stack trace instead of a reason.
    """
    code = tmp_path / "code"
    cfg = Config(project_root=_repo(code / "alpha"), scan_roots=[code])

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        status, body = post("/api/spawn", {"scope": "main", "dir": str(code / "alpha"),
                                           "harness": "codex"})

    assert status == 400 and body["error"] == "unknown harness"


def test_the_console_runs_with_no_thalamus_around_it(tmp_path, monkeypatch):
    """
    Scenario: `server.py` run by a bare python3, with the package unimportable

    Verifications:
    - the tmux bridge still serves — panes, keys, input are unaffected
    - the expert controls report themselves unavailable instead of raising

    The bridge is stdlib-only on purpose; only the expert layer (scopes, spawn,
    roster, rooms) needs the package. Keeping that seam real is what lets the
    console be run without a checkout, and what keeps a missing dependency from
    taking down the surface an operator reaches for when something is already wrong.
    """
    monkeypatch.setattr(server, "_pin_cache", None)
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"), session="s")

    assert server.has_experts() is False
    assert server.known_scopes() == []
    assert server.spawn_harnesses() == []

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        spawned, body = post("/api/spawn", {"scope": "main", "dir": str(tmp_path)})
        keyed, _ = post("/api/key", {"index": 0, "key": "enter"})

    assert spawned == 503 and "unavailable" in body["error"]
    assert keyed == 200  # the bridge is untouched by the package being absent


def test_a_held_key_replays_in_one_tmux_call(tmp_path):
    """Holding a key must cost one process launch, not one per repeat.

    The client coalesces a run of the same key into a single request carrying its
    count; this is the other half — `send-keys -N` replays it inside tmux instead
    of the console spawning a process per keystroke.
    """
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"), session="s")

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        status, _ = post("/api/key", {"index": 0, "key": "backspace", "count": 12})
        sends = [c for c in post.fake.calls if c[0] == "send-keys"]

    assert status == 200
    assert len(sends) == 1, "a counted repeat must not fan out into many calls"
    assert "-N" in sends[0] and sends[0][sends[0].index("-N") + 1] == "12"
    assert sends[0][-1] == "BSpace"


def test_a_single_key_does_not_use_the_repeat_flag(tmp_path):
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"), session="s")

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        post("/api/key", {"index": 0, "key": "enter"})
        sends = [c for c in post.fake.calls if c[0] == "send-keys"]

    assert len(sends) == 1 and "-N" not in sends[0]


@pytest.mark.parametrize(
    "count,expected",
    [(10_000, "64"), (-5, None), (0, None), ("nonsense", None), (None, None)],
)
def test_the_repeat_count_is_clamped_whatever_the_client_sends(tmp_path, count, expected):
    """The count is client-supplied and this server has no authentication, so
    nothing reachable here may ask it for an unbounded amount of work."""
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"), session="s")

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        status, _ = post("/api/key", {"index": 0, "key": "backspace", "count": count})
        sends = [c for c in post.fake.calls if c[0] == "send-keys"]

    assert status == 200
    assert len(sends) == 1
    if expected is None:
        assert "-N" not in sends[0]          # clamped to a single press
    else:
        assert sends[0][sends[0].index("-N") + 1] == expected


def test_an_unknown_scope_is_refused_before_any_directory_check(tmp_path):
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"))

    with _serving(cfg) as post:
        status, body = post("/api/spawn", {"scope": "../../etc", "dir": str(tmp_path)})

    assert status == 400 and body["error"] == "unknown scope"


def test_defaults_describe_one_machine_and_nothing_is_hardcoded_elsewhere(tmp_path):
    """An operator who passes no flags still gets a usable picker — their checkout,
    starred, plus its neighbours — and an admin sheet that manages no units."""
    cfg = Config(project_root=_repo(tmp_path / "code" / "thalamus"))

    assert cfg.favorites == [tmp_path / "code" / "thalamus"]
    assert cfg.scan_roots == [tmp_path / "code"]
    assert cfg.services == []


# ---- frame themes ----


def _frames_file(tmp_path: Path, entries: str) -> Path:
    f = tmp_path / "frames.lua"
    f.write_text(entries)
    return f


def _frame_entry(name: str, path: Path) -> str:
    return (f'{{ name = "{name}", path = "{path}", '
            'panel = { left = 0.1, right = 0.2, top = 0.05, bottom = 0.3 } },')


def test_no_frames_are_configured_by_default(tmp_path):
    """A shipped package reads no other application's config directory unasked, so
    the feature is off until a path is named. Off means empty, never an error."""
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"))

    assert cfg.frames_file is None
    assert server.frames(cfg) == []
    assert server.frame_bytes(cfg, "anything") == (None, None)


def test_a_frame_whose_image_is_missing_is_dropped_not_offered(tmp_path):
    """A stale frame file degrades to fewer frames, never to a broken background.

    The file names absolute paths on one machine; images move and are deleted. The
    client must only ever be offered frames that can actually be served.
    """
    art = tmp_path / "real.png"
    art.write_bytes(b"\x89PNG\r\n\x1a\n")
    entries = (_frame_entry("real.png", art)
               + _frame_entry("gone.png", tmp_path / "gone.png")
               + _frame_entry("notanimage.txt", tmp_path / "notanimage.txt"))
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"),
                 frames_file=_frames_file(tmp_path, entries))

    assert [f["name"] for f in server.frames(cfg)] == ["real.png"]


def test_a_malformed_panel_fraction_is_dropped_not_raised(tmp_path):
    """The regex is looser than `float()`, and this function promises never to raise.

    `[-\\d.]+` happily matches `1.2.3` and a bare `-`. Converting one of those
    would raise out of `frames()`, out of `do_GET` — which has no blanket handler
    — and 500 the endpoint, taking down the surface an operator reaches for when
    something else is already wrong. A typo'd fraction is a dropped frame, exactly
    like a missing image is.
    """
    art = tmp_path / "real.png"
    art.write_bytes(b"\x89PNG\r\n\x1a\n")
    bad = (f'{{ name = "bad.png", path = "{art}", '
           'panel = { left = 1.2.3, right = 0.2, top = 0.05, bottom = 0.3 } },')
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"),
                 frames_file=_frames_file(tmp_path, bad + _frame_entry("real.png", art)))

    assert [f["name"] for f in server.frames(cfg)] == ["real.png"]


def test_a_frame_is_addressed_by_name_and_never_by_path(tmp_path):
    """
    Scenario: a client asks for a frame, and then asks for a file it names itself

    Verifications:
    - a known name serves the bytes the frame file recorded
    - a path-shaped request matches no name, so it is a 404 rather than a read

    The request contributes only a name, matched for equality against the parsed
    list; the path served is always the one on record. Traversal is not expressible
    even though the art lives outside the package.
    """
    art = tmp_path / "real.png"
    art.write_bytes(b"\x89PNG\r\n\x1a\nDATA")
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"\x89PNG\r\n\x1a\nSECRET")
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"),
                 frames_file=_frames_file(tmp_path, _frame_entry("real.png", art)))

    blob, ctype = server.frame_bytes(cfg, "real.png")
    assert blob == b"\x89PNG\r\n\x1a\nDATA" and ctype == "image/png"
    assert server.frame_bytes(cfg, f"../../{secret}") == (None, None)
    assert server.frame_bytes(cfg, str(secret)) == (None, None)


def test_the_frame_list_never_leaks_a_path_from_this_machine(tmp_path):
    """The client addresses frames by name, so the absolute paths stay server-side —
    they describe one operator's disk and the client has no use for them."""
    art = tmp_path / "real.png"
    art.write_bytes(b"\x89PNG\r\n\x1a\n")
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"),
                 frames_file=_frames_file(tmp_path, _frame_entry("real.png", art)))

    with _serving(cfg) as post:
        body = post.get("/api/frames")

    assert body["frames"] == [{"name": "real.png",
                               "panel": {"left": 0.1, "right": 0.2,
                                         "top": 0.05, "bottom": 0.3}}]
    assert str(tmp_path) not in json.dumps(body)


# ---- input the client names, never composes ----


def test_every_forwardable_key_is_a_tmux_key_name_not_an_argument():
    """The client sends `ctrl-c`, never `C-c` and never a tmux flag. Anything not
    in the map is refused, so a request can't reach send-keys with an option."""
    for name, key in server.KEYMAP.items():
        assert name == name.lower()
        assert not key.startswith("-"), f"{name} maps to something tmux reads as a flag"
    assert server.KEYMAP["ctrl-c"] == "C-c"
    assert server.KEYMAP["shift-tab"] == "BTab"


def test_an_unnamed_key_is_refused(tmp_path):
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"))

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        status, body = post("/api/key", {"index": 0, "key": "kill-session"})

    assert status == 400 and body["error"] == "unknown key"


def test_input_to_a_window_that_does_not_exist_is_refused(tmp_path):
    """Indexes are validated against the live window list, so a stale tab in a
    phone left open for a day can't type into whatever now holds that index."""
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"))

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        status, body = post("/api/send", {"index": 9, "text": "hello"})

    assert status == 400 and body["error"] == "unknown window"


def test_the_anchor_cannot_be_closed(tmp_path):
    """Closing it would leave the plane with no reference cwd and no way back."""
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"))

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        status, body = post("/api/close", {"index": 0})

    assert status == 400 and "anchor" in body["error"]


def test_only_configured_units_are_restartable(tmp_path):
    cfg = Config(project_root=_repo(tmp_path / "code" / "alpha"),
                 services=["thalamus-console.service"])

    with _serving(cfg) as post:
        status, body = post("/api/service", {"unit": "sshd.service"})

    assert status == 400 and body["error"] == "unknown unit"


# ---- harness ----


class _FakeTmux:
    """Records argv lists and answers `list-windows` from a fixed screenful.

    Recording rather than executing is the point: a test that let these through
    would drive the operator's real roster.
    """

    def __init__(self, windows: str = "", screens: dict[int, str] | None = None):
        self.windows = windows
        # `capture-pane` answers from here, keyed by window index. Mutable, so a
        # test can move one window's screen between two polls.
        self.screens = screens if screens is not None else {}
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> subprocess.CompletedProcess:
        self.calls.append(args)
        out = ""
        if args and args[0] == "list-windows":
            out = self.windows
        elif args and args[0] == "capture-pane":
            target = args[-1].rpartition(":")[2]
            out = self.screens.get(int(target), "") if target.isdigit() else ""
        return subprocess.CompletedProcess(args=list(args), returncode=0, stdout=out, stderr="")


# ---- launch posture ----

# A Cursor pin as `pin` really builds it: the room `env -u` prefix wraps a second `env`
# carrying the scope, so the binary is the third `env`-ish token in. Copied from a live
# roster rather than composed here, since the nesting is the part that breaks parsers.
CURSOR_START = ("1\thomelab\t0\tagent\t60\t50\t0\t/home/op/code/thalamus\t"
                "env -u THALAMUS_ROOM -u CLAUDE_CONFIG_DIR env THALAMUS_SCOPE=homelab "
                "agent --trust\t%84\t990")
CLAUDE_START = ("0\tmain\t1\tclaude\t60\t50\t0\t/home/op/code/thalamus\t"
                "env -u THALAMUS_ROOM -u CLAUDE_CONFIG_DIR claude --agent thalamus-qe "
                "--permission-mode auto\t%0\t991")


@pytest.mark.parametrize("start, harness", [
    ("claude", "claude"),
    ("env -u THALAMUS_ROOM -u CLAUDE_CONFIG_DIR claude --permission-mode auto", "claude"),
    ("env -u THALAMUS_ROOM env THALAMUS_SCOPE=homelab agent --trust", "cursor"),
    ("/usr/local/bin/claude --agent x", "claude"),
    ("bash", ""),
    ("", ""),
])
def test_the_harness_is_read_from_the_start_command(start, harness):
    """`pane_current_command` shows whatever is in the foreground, so a window shelling
    out reads as `bash`. The creation command is the one field that cannot disagree
    with what was launched — and its `env` prefix nests, which is what a one-`env`
    parser gets wrong on every room-launched Cursor window."""
    assert server.window_harness(start) == harness


def test_a_window_launched_under_an_older_posture_is_marked():
    """A flag rides the argv and the argv is fixed at window creation, so a posture
    change cannot reach a running session. Unmarked, that divergence is silent."""
    windows = parse_windows(CLAUDE_START, {"claude": ("--permission-mode", "auto")})
    assert windows[0]["harness"] == "claude" and windows[0]["policy_stale"] is False

    windows = parse_windows(CLAUDE_START, {"claude": ("--permission-mode", "acceptEdits")})
    assert windows[0]["policy_stale"] is True


def test_a_flag_and_a_value_must_appear_together_to_count():
    """Checking that every token is present somewhere would pass a window carrying the
    flag with a *different* value, which is exactly the drift worth catching."""
    scrambled = CLAUDE_START.replace("--permission-mode auto", "auto --permission-mode")
    assert parse_windows(scrambled, {"claude": ("--permission-mode", "auto")})[0][
        "policy_stale"] is True


def test_a_window_running_no_known_harness_is_never_stale():
    """A shell in a pane has no posture to be out of date with, and guessing one would
    badge it against some other harness's flags."""
    plain = "2\tshell\t0\tbash\t60\t50\t0\t/home/op\tbash\t%2\t992"
    assert parse_windows(plain, {"claude": ("--permission-mode", "auto")})[0][
        "policy_stale"] is False


def test_the_start_command_never_reaches_the_client():
    """It carries the launch environment. The projection ships the two facts derived
    from it and not the string itself."""
    window = parse_windows(CURSOR_START, {"cursor": ()})[0]
    assert window["harness"] == "cursor"
    assert "start" not in window and "THALAMUS_SCOPE" not in json.dumps(window)


def _own_store(tmp_path, monkeypatch):
    """Point the posture store at tmp_path.

    These cases all refuse, so none of them writes today — but the endpoint reaches
    the module defaults, and a test that starts passing is a test that starts editing
    the operator's real launch posture.
    """
    from thalamus.harness import launch_policy
    monkeypatch.setattr(launch_policy, "STORE", tmp_path / "policy.json")
    monkeypatch.setattr(launch_policy, "LEDGER", tmp_path / "policy.jsonl")


def test_the_posture_panel_serves_options_with_their_costs(tmp_path):
    cfg = Config(project_root=_repo(tmp_path / "alpha"))
    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        body = post.get("/api/launch-policy")

    harnesses = {h["harness"]: h for h in body["harnesses"]}
    assert set(harnesses) == {"claude", "cursor"}
    cursor = harnesses["cursor"]["capabilities"][0]
    assert cursor["value"] == cursor["default"] == "manual"
    loose = [o for o in cursor["options"] if o["above_default"]]
    assert loose and all(o["drops"] for o in loose)


def test_a_refused_posture_reaches_the_phone_as_its_reason(tmp_path, monkeypatch):
    """The refusal prose is written for the person mid-decision and is the whole
    argument for the rule, so it is not flattened into a status code."""
    cfg = Config(project_root=_repo(tmp_path / "alpha"))
    _own_store(tmp_path, monkeypatch)
    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        # Tightening is the case that still refuses a lifetime: a posture reverting
        # toward *more* permission on a timer is the forgotten-setting failure inverted.
        status, body = post("/api/launch-policy",
                            {"harness": "claude", "capability": "permission_posture",
                             "value": "manual", "ttl_hours": 24})

    assert status == 409 and "does not take a lifetime" in body["error"]


def test_an_unknown_posture_is_a_refusal_not_a_crash(tmp_path, monkeypatch):
    cfg = Config(project_root=_repo(tmp_path / "alpha"))
    _own_store(tmp_path, monkeypatch)
    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        status, body = post("/api/launch-policy",
                            {"harness": "cursor", "capability": "permission_posture",
                             "value": "sudo-everything"})

    assert status == 409 and "not a posture" in body["error"]


class _serving:
    """A live console on an ephemeral port, with tmux stubbed out.

    The refusals under test live in the request handler, not in a pure function,
    so they are exercised over real HTTP.
    """

    def __init__(self, cfg: Config, windows: str = "", screens: dict[int, str] | None = None):
        self.cfg = cfg
        self.fake = _FakeTmux(windows, screens)

    def __enter__(self):
        self._real_tmux = server.tmux
        server.tmux = self.fake
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.config = self.cfg
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        port = self.httpd.server_address[1]

        def post(path: str, payload: dict) -> tuple[int, dict]:
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("POST", path, json.dumps(payload),
                         {"Content-Type": "application/json"})
            response = conn.getresponse()
            body = json.loads(response.read() or "{}")
            conn.close()
            return response.status, body

        def get(path: str) -> dict:
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", path)
            response = conn.getresponse()
            body = json.loads(response.read() or "{}")
            conn.close()
            return body

        post.get = get
        # The recorded argv is the only place some behaviour is observable — a
        # counted key repeat has no response body that differs from a single press.
        post.fake = self.fake
        return post

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        server.tmux = self._real_tmux
        return False


@pytest.fixture(autouse=True)
def _no_leaked_state():
    """In-flight recycle/close sets are module state; a leak between tests would
    make a window report `restarting…` forever."""
    yield
    server.RECYCLING.clear()
    server.CLOSING.clear()


# ---- the room dialogue, as a thin client over the dispatch verb ----


def test_the_dialogue_refuses_a_room_name_that_could_reach_a_path(tmp_path):
    """The room name reaches `room_config_dir` as a path segment and the guard's
    roommate pattern as a regex, so the console validates it with `pin.valid_room`
    before it reaches either — the same check `/api/spawn` already makes."""
    cfg = Config(project_root=tmp_path, scan_roots=[tmp_path])
    with _serving(cfg) as post:
        for bad in ("../escape", "Room", "a b", ""):
            status, body = post("/api/dispatch", {"room": bad, "message": "hi"})
            assert status == 400, bad
            assert "room name" in body["error"] or "dispatch" in body["error"]


def test_the_dialogue_refuses_an_empty_message(tmp_path):
    cfg = Config(project_root=tmp_path, scan_roots=[tmp_path])
    with _serving(cfg) as post:
        status, body = post("/api/dispatch", {"room": "alpha", "message": "   "})
        assert status == 400 and "nothing to dispatch" in body["error"]


def test_a_room_refusal_is_409_and_carries_the_reason(tmp_path, monkeypatch):
    """
    Scenario: the verb refuses — here, a room with no live members.

    Verification: 409 rather than 400, and the refusal text survives to the client.
    The request was well-formed; the room said no, and the reason names what the
    operator has to fix. Flattening it to 400 would make a room that cannot be
    reached indistinguishable from a malformed request.
    """
    cfg = Config(project_root=tmp_path, scan_roots=[tmp_path])
    with _serving(cfg) as post:
        status, body = post("/api/dispatch", {"room": "alpha", "message": "hello"})
        assert status == 409
        assert "no live members" in body["error"]


def test_the_dispatch_endpoint_never_inherits_the_room_it_was_started_in(tmp_path,
                                                                        monkeypatch):
    """
    Scenario: the console server's own process is in a room — it was started from a
    member's shell, or a unit inherited the variable — and the operator dispatches
    from the phone to a *different* room.

    Verification: the refusal names the room's own state ("no live members"), never
    the caller's. `authenticate` refuses a caller that is in a different room than
    the one it addresses, and it reads that caller's room from `THALAMUS_ROOM` when
    nobody tells it otherwise. The console is the operator's broadcast path — the
    one caller that is definitionally roomless — so it has to say so.

    This is the sibling of the spawn endpoint's `..._never_inherits_one`, and the
    same argument: a long-lived server that leaves a room to the environment adopts
    whatever room it happened to be launched in and holds it for its whole life.
    Here the consequence is worse than a mis-parented window — *every* dispatch to
    every other room is refused, and the reason names a room the operator is not in
    and cannot see.
    """
    monkeypatch.setenv("THALAMUS_ROOM", "beta")
    cfg = Config(project_root=tmp_path, scan_roots=[tmp_path])
    with _serving(cfg) as post:
        status, body = post("/api/dispatch", {"room": "alpha", "message": "hello"})

    assert status == 409
    assert "cannot dispatch into room" not in body["error"], (
        "the console authenticated as a member of the room its own process was "
        "launched in — it is the operator's roomless broadcast path and must pass "
        "caller_room explicitly, the way /api/spawn passes room"
    )
    assert "no live members" in body["error"]


def test_the_dispatch_endpoint_declares_its_roomlessness_to_the_real_signature():
    """
    Scenario: the guard above, pinned at the seam instead of through a refusal.

    Verification: `harness.dispatch.dispatch` really accepts `caller_room`, and the
    console really passes `""` for it.

    Bound against the *real* function via `inspect.signature`, not a spy. The test
    that should have caught this passes `fake_dispatch(room, message, **kwargs)`,
    and `**kwargs` accepts every argument including the ones the real function does
    not have — so it cannot see the console omit a parameter, nor see the parameter
    be absent from the callee. A fake grows whatever the caller hands it, which is
    the same reason a hand-written descriptor could not see a field go missing.

    `""` and `None` are different claims here: `None` means "read my environment",
    which is right for the CLI, where the invocation is the session.
    """
    import inspect

    from thalamus.harness import dispatch as dispatch_mod

    parameters = inspect.signature(dispatch_mod.dispatch).parameters
    assert "caller_room" in parameters, (
        "dispatch() offers no way for a caller to state the room it is in, so every "
        "caller is at the mercy of THALAMUS_ROOM. authenticate() has the seam; it "
        "was never plumbed through the public entry point."
    )

    seen: dict = {}

    def spy(room, text, **kwargs):
        # Bind against the real signature so this stand-in cannot silently accept an
        # argument the real function would reject, nor hide one it requires.
        inspect.signature(dispatch_mod.dispatch).bind(room, text, **kwargs)
        seen.update(kwargs)
        raise dispatch_mod.DispatchRefused("stop here — the call is the assertion")

    cfg = Config(project_root=Path("/nonexistent"), scan_roots=[])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dispatch_mod, "dispatch", spy)
        with _serving(cfg) as post:
            post("/api/dispatch", {"room": "alpha", "message": "hello"})

    assert seen.get("caller_room") == "", (
        f"console passed caller_room={seen.get('caller_room')!r}; it must pass '' — "
        "None means 'read my environment', which for a long-lived server is whatever "
        "room it was started in"
    )


def test_the_dialogue_delegates_rather_than_reimplementing_the_preflight(tmp_path,
                                                                        monkeypatch):
    """
    Scenario: a dispatch that the verb accepts.

    Verification: the console calls `harness.dispatch.dispatch` and renders what it
    returns — it does not decide anything about `waiting` itself. A second
    implementation here, however small, would be a second policy about when it is
    safe to type into somebody's session, and the two would drift.
    """
    from thalamus.harness import dispatch as dispatch_mod

    seen = {}

    def fake_dispatch(room, message, **kwargs):
        seen["room"] = room
        seen["message"] = message
        seen["kwargs"] = kwargs
        target = dispatch_mod.Target(
            scope="qe", session_id="sid", name="alpha-qe", pane="%1",
            status="idle", updated_at=1,
        )
        return dispatch_mod.DispatchResult(
            room=room, sender=kwargs.get("sender", ""), handle="abcd1234",
            deliveries=(dispatch_mod.Delivery(target=target, performed=True),),
            undelivered=(),
        )

    monkeypatch.setattr(dispatch_mod, "dispatch", fake_dispatch)
    cfg = Config(project_root=tmp_path, scan_roots=[tmp_path])
    with _serving(cfg) as post:
        status, body = post("/api/dispatch", {
            "room": "alpha", "message": "stand up", "to": ["qe"], "partial": True,
        })

    assert status == 200 and body["ok"] is True
    assert body["handle"] == "abcd1234" and body["delivered"] == 1
    assert body["targets"][0]["name"] == "alpha-qe"
    assert seen["room"] == "alpha" and seen["message"] == "stand up"
    assert seen["kwargs"]["scopes"] == ["qe"] and seen["kwargs"]["partial"] is True


def test_send_keeps_no_waiting_preflight_because_the_operator_can_see_it(tmp_path):
    """
    Scenario: the composer types into the one window the operator is watching.

    Verification: it goes through with no status check. This is the line between the
    two send paths — `/api/dispatch` refuses a `waiting` target because the sender
    cannot see it, while answering a permission prompt through the composer is a
    primary use of the console. Gating this on `waiting` would break the case the
    console exists for, so the asymmetry is deliberate and tested.
    """
    cfg = Config(project_root=tmp_path, scan_roots=[tmp_path])
    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        status, body = post("/api/send", {"index": 0, "text": "1"})
        assert status == 200 and body["ok"] is True
    sent = [args for args in post.fake.calls if "send-keys" in args]
    assert any("1" in args for args in sent)
