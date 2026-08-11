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
    monkeypatch.setattr(server, "SPAWN_SETTLE_S", 0)

    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        post("/api/spawn", {"scope": "main", "dir": str(code / "alpha"), "room": "alpha"})
        post("/api/spawn", {"scope": "main", "dir": str(code / "alpha")})

    assert [s["room"] for s in seen] == ["alpha", ""]


def test_a_spawn_that_produced_no_living_window_is_reported_failed(tmp_path, monkeypatch):
    """
    Scenario: `pin.spawn` returns cleanly, but the window it made is already dead

    Verifications:
    - the response is a failure, not the success every layer below it reported
    - the operator is told to check PATH, which is the cause in almost every case

    `tmux new-window` returns 0 as soon as it has forked — before the command it
    was given has execed. A window whose command cannot be executed at all dies
    instantly and is reaped, while tmux, `pin`, and the console all still see
    success. Measured 2026-08-08: with `claude` off the server's PATH every spawn
    answered ok and produced nothing, which reads on a phone as a button that does
    nothing at all. Only the window list can tell the difference.
    """
    code = tmp_path / "code"
    cfg = Config(project_root=_repo(code / "alpha"), scan_roots=[code])
    monkeypatch.setattr(_pin(), "spawn", lambda *a, **k: None)
    monkeypatch.setattr(server, "SPAWN_SETTLE_S", 0)

    # The window list never gains a live window: exactly what an exec failure leaves.
    with _serving(cfg, windows=WINDOW_FIELDS) as post:
        status, body = post("/api/spawn", {"scope": "main", "dir": str(code / "alpha")})

    assert status == 500 and body["ok"] is False
    assert "PATH" in body["output"]


def test_a_dead_window_does_not_count_as_a_spawn(tmp_path, monkeypatch):
    """A *new* window is not enough — tmux keeps reporting one whose pane has died.

    The confirmation asks whether a new window is alive, not whether one appeared,
    because the failure being caught produces a window either way.
    """
    code = tmp_path / "code"
    cfg = Config(project_root=_repo(code / "alpha"), scan_roots=[code])
    monkeypatch.setattr(server, "SPAWN_SETTLE_S", 0)
    live = "0\tmain\t1\tclaude\t60\t50\t0\t/home/op/code/thalamus\t"
    # index 1 is new since the spawn, and its pane_dead flag is set.
    dead = live + "\n1\tmain\t0\tclaude\t60\t50\t1\t/home/op/code/alpha\t"

    serving = _serving(cfg, windows=live)
    monkeypatch.setattr(_pin(), "spawn",
                        lambda *a, **k: setattr(serving.fake, "windows", dead))
    with serving as post:
        status, body = post("/api/spawn", {"scope": "main", "dir": str(code / "alpha")})

    assert status == 500 and body["ok"] is False


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

    def __init__(self, windows: str = ""):
        self.windows = windows
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> subprocess.CompletedProcess:
        self.calls.append(args)
        out = self.windows if args and args[0] == "list-windows" else ""
        return subprocess.CompletedProcess(args=list(args), returncode=0, stdout=out, stderr="")


class _serving:
    """A live console on an ephemeral port, with tmux stubbed out.

    The refusals under test live in the request handler, not in a pure function,
    so they are exercised over real HTTP.
    """

    def __init__(self, cfg: Config, windows: str = ""):
        self.cfg = cfg
        self.fake = _FakeTmux(windows)

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
