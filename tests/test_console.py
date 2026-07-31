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
