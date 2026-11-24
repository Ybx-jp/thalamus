"""A real `thalamus console` on a tmux server and a HOME that are not the operator's.

Not a case. The integration, browser and fuzz arms over the console all need the same
expensive thing — the real server process, importing the real core and every installed
plugin, driving a real tmux — and every one of them needs it to be unable to reach the
live control plane. This module is the one place that promise is kept.

**Why a subprocess, not `Handler` in-process.** The cases under `console_*` that predate
this rig stub `tmux` and drive `Handler` on a thread; that is the right instrument for a
property of one route. It is the wrong one for a property that crosses into the core:
`launch_policy.LEDGER`, `FAVORITES_STORE`, the pin ledger and the launcher all bind
`Path.home()` at import, so an in-process probe would write the operator's real files
under any patch list that missed one. A child with `HOME` set moves all of them at once
and needs no list — the premise `home-redirection-moves-every-path` keeps true.

**What `HOME` does not contain, and how each is closed here:**

- *tmux.* It finds its server through `/tmp/tmux-<uid>/`, never `HOME`. Every tmux argv in
  `src/` goes through `thalamus_console.tmux.argv`, which reads `THALAMUS_TMUX_SOCKET`,
  so the child gets a socket name unique to this rig. The rig refuses to start if that
  name is the default (`thalamus`) and, once up, asserts the server reports the same
  name back on `/api/panes` — the containment's positive control, read off the surface
  rather than assumed from the environment.
- *the agent CLIs.* `claude` and `codex` on the child's `PATH` are stand-ins that print
  their argv once and then `exec cat`, so a window stays alive past the launcher's
  settle deadline (the console treats a window that dies as a failed spawn) and typed
  text is echoed back by the pane's tty. No model is reachable from a rig.
- *inherited environment.* The child starts from an empty environment plus a short
  allowlist. This session is itself pinned (`THALAMUS_SCOPE`, `TMUX`, `CLAUDE_*`), and a
  console that inherited those would spawn into the caller's room — the defect
  `do_spawn`'s explicit `room=""` exists to prevent, which a rig must not reintroduce.

**Never driven from a rig**, because no redirection contains them: `/api/deploy`
(`git pull` on the checkout the code is served from, then a unit restart),
`/api/service` (a real `systemctl --user` / `launchctl` call), `/api/roster` (`thalamus
roster` against the checkout), and `/api/cursor-sweep` (extraction over transcripts).
`UNDRIVABLE_POSTS` names them for the fuzz arm, which derives its route list from
`do_POST` and must subtract these by name.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
# `QE_CONSOLE_SRC` points the whole console arm — the arming probes in `_console_spec`
# and the rig's child process alike — at another tree's `packages/thalamus-console/src`,
# so the oracle can be run against a branch still being built in another worktree
# without merging it first. Unset, it is this checkout's.
CONSOLE_SRC = Path(os.environ.get("QE_CONSOLE_SRC")
                   or REPO_ROOT / "packages" / "thalamus-console" / "src")
CONSOLE_PKG = CONSOLE_SRC / "thalamus_console"
SERVER_PY = CONSOLE_PKG / "server.py"
STATIC_DIR = CONSOLE_PKG / "static"

UNDRIVABLE_POSTS = frozenset({"/api/deploy", "/api/service", "/api/roster",
                              "/api/cursor-sweep"})

STUB_AGENT = """#!/bin/sh
# qe rig stand-in for a harness CLI: say what we were asked to run, then hold the pane.
printf 'STUB-AGENT %s\\n' "$(basename "$0")"
exec cat
"""

# Inherited by the child; everything else is dropped. LANG so tmux and Python agree on
# UTF-8 — a C locale makes tmux replace non-ASCII with `_`, and the send properties
# would then be measuring the locale.
_PASSED_ENV = ("LANG", "LC_ALL", "TERM", "TZ", "USER", "LOGNAME", "SHELL")


class RigFailed(RuntimeError):
    """The rig could not stand up. A case lets this raise: it is MALFORMED, not red."""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def thalamus_bin() -> Path:
    """The `thalamus` console script of the interpreter running this suite."""
    here = Path(sys.executable).parent / "thalamus"
    if here.exists():
        return here
    found = shutil.which("thalamus")
    if not found:
        raise RigFailed("no `thalamus` entry point beside the running interpreter")
    return Path(found)


@dataclass
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self):
        return json.loads(self.body or b"null")


@dataclass
class Rig:
    root: Path
    home: Path
    projects: Path
    socket: str
    session: str
    port: int
    proc: subprocess.Popen
    log: Path
    repos: list[Path] = field(default_factory=list)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # ---- HTTP ----

    def request(self, method: str, path: str, body: bytes | None = None,
                headers: dict[str, str] | None = None, timeout: float = 20.0) -> Reply:
        req = urllib.request.Request(self.base + path, data=body, method=method,
                                     headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return Reply(r.status, dict(r.headers.items()), r.read())
        except urllib.error.HTTPError as e:
            return Reply(e.code, dict(e.headers.items()), e.read())

    def get(self, path: str, **kw) -> Reply:
        return self.request("GET", path, **kw)

    def post(self, path: str, obj=None, *, raw: bytes | None = None,
             origin: str | None = None, timeout: float = 20.0) -> Reply:
        body = raw if raw is not None else json.dumps(obj if obj is not None else {}).encode()
        headers = {"Content-Type": "application/json"}
        if origin is not None:
            headers["Origin"] = origin
        return self.request("POST", path, body, headers, timeout=timeout)

    # ---- tmux on this rig's server only ----

    def tmux(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["tmux", "-L", self.socket, *args], capture_output=True,
                              text=True, timeout=15)

    def window_names(self) -> list[tuple[int, str]]:
        r = self.tmux("list-windows", "-t", self.session, "-F",
                      "#{window_index}\t#{window_name}")
        out = []
        for line in r.stdout.splitlines():
            i, _, name = line.partition("\t")
            out.append((int(i), name))
        return out

    def capture(self, index: int) -> str:
        return self.tmux("capture-pane", "-p", "-J", "-t",
                         f"{self.session}:{index}", "-S", "-200").stdout

    def wait_for(self, predicate, timeout: float = 10.0, interval: float = 0.1):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = predicate()
            if last:
                return last
            time.sleep(interval)
        return last

    def alive(self) -> bool:
        return self.proc.poll() is None

    def log_tail(self, n: int = 2000) -> str:
        try:
            return self.log.read_text(errors="replace")[-n:]
        except OSError:
            return ""


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(path.parent),
           "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "init", "-q", "-b", "master", str(path)], check=True, env=env,
                   capture_output=True)
    (path / "README.md").write_text(f"# {path.name}\n")
    for args in (["add", "README.md"],
                 ["-c", "user.name=qe", "-c", "user.email=qe@invalid",
                  "commit", "-q", "-m", "seed"]):
        subprocess.run(["git", "-C", str(path), *args], check=True, env=env,
                       capture_output=True)
    return path


@dataclass
class SourceRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes


@dataclass
class JobsSource:
    """A stand-in for the program that runs the operator's jobs (board note N1).

    It records every request it receives and answers from `responder`, which maps a
    `SourceRequest` to `(status, headers, body)`. The default answers 200 with a JSON
    echo of what arrived, so a case can read off the reply what the console forwarded
    — and, separately, off `requests`, what reached the source at all.
    """

    port: int
    token: str
    token_file: Path
    requests: list[SourceRequest] = field(default_factory=list)
    responder: object = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def _echo(req: SourceRequest) -> tuple[int, dict[str, str], bytes]:
    return 200, {"Content-Type": "application/json"}, json.dumps(
        {"method": req.method, "path": req.path}).encode()


@contextlib.contextmanager
def jobs_source(root: Path | None = None, responder=None) -> Iterator[JobsSource]:
    """Serve a recording jobs source on a free loopback port for the block's length."""
    import http.server
    import threading

    root = root or Path(tempfile.mkdtemp(prefix="qe-jobs-source-"))
    token = "qe-token-" + uuid.uuid4().hex
    token_file = root / "jobs-token"
    token_file.write_text(token + "\n")
    src = JobsSource(port=0, token=token, token_file=token_file,
                     responder=responder or _echo)

    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):  # quiet
            pass

        def _serve(self):
            n = int(self.headers.get("Content-Length") or 0)
            req = SourceRequest(self.command, self.path, dict(self.headers.items()),
                                self.rfile.read(n) if n else b"")
            src.requests.append(req)
            status, headers, body = src.responder(req)
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = do_PUT = do_DELETE = _serve

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    src.port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield src
    finally:
        httpd.shutdown()
        httpd.server_close()


def dead_port() -> int:
    """A loopback port nothing listens on, for a source that does not answer."""
    return _free_port()


@contextlib.contextmanager
def console_rig(*, repos: tuple[str, ...] = ("alpha", "beta"),
                extra_args: tuple[str, ...] = (), env: dict[str, str] | None = None,
                start_timeout: float = 30.0, session: str = "roster") -> Iterator[Rig]:
    """Stand up one console, yield it, and tear down everything it started."""
    if shutil.which("tmux") is None:
        raise RigFailed("tmux is not installed — declare Substrate.NEEDS_TMUX")
    root = Path(tempfile.mkdtemp(prefix="qe-console-rig-"))
    sock = f"qe-rig-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    if sock == "thalamus":  # unreachable by construction; stated because it is the point
        raise RigFailed("refusing to address the default tmux server")
    home, binp, projects = root / "home", root / "bin", root / "projects"
    for d in (home, binp, projects):
        d.mkdir()
    for name in ("claude", "codex"):
        p = binp / name
        p.write_text(STUB_AGENT)
        p.chmod(0o755)
    made = [_git_repo(projects / r) for r in repos]
    port = _free_port()
    # Named for no scope. tmux resolves `new-window -t <session>` to a *window* whose
    # name starts with it, so a roster session sharing a scope's name breaks every spawn
    # after that scope's (`console-spawn-survives-a-scope-named-like-its-session`).
    log = root / "console.log"
    child_env = {k: os.environ[k] for k in _PASSED_ENV if k in os.environ}
    child_env.setdefault("LANG", "C.UTF-8")
    child_env.update({
        "HOME": str(home),
        "PATH": os.pathsep.join([str(binp), str(Path(sys.executable).parent),
                                 "/usr/local/bin", "/usr/bin", "/bin"]),
        "THALAMUS_TMUX_SOCKET": sock,
        "PYTHONUNBUFFERED": "1",
    })
    if os.environ.get("QE_CONSOLE_SRC"):
        child_env["PYTHONPATH"] = str(CONSOLE_SRC)
    child_env.update(env or {})
    argv = [str(thalamus_bin()), "console", "--port", str(port), "--session", session,
            "--project-root", str(made[0] if made else projects),
            "--scan", str(projects), "--fetch-interval", "0", *extra_args]
    with open(log, "wb") as fh:
        proc = subprocess.Popen(argv, env=child_env, stdout=fh, stderr=subprocess.STDOUT,
                                cwd=str(root), start_new_session=True)
    rig = Rig(root=root, home=home, projects=projects, socket=sock, session=session,
              port=port, proc=proc, log=log, repos=made)
    try:
        deadline = time.monotonic() + start_timeout
        while True:
            if not rig.alive():
                raise RigFailed(f"console exited {proc.returncode}: {rig.log_tail()}")
            try:
                if rig.get("/api/build", timeout=2).status == 200:
                    break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                pass
            if time.monotonic() > deadline:
                raise RigFailed(f"console did not answer in {start_timeout}s: "
                                f"{rig.log_tail()}")
            time.sleep(0.2)
        # The containment's positive control, read off the surface.
        served = rig.get("/api/panes").json().get("tmux_socket")
        if served != sock:
            raise RigFailed(f"console reports tmux socket {served!r}, rig set {sock!r} — "
                            f"refusing to drive a server this rig did not scope")
        yield rig
    finally:
        with contextlib.suppress(Exception):
            os.killpg(proc.pid, signal.SIGTERM)
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)
        with contextlib.suppress(Exception):
            os.killpg(proc.pid, signal.SIGKILL)
        subprocess.run(["tmux", "-L", sock, "kill-server"], capture_output=True)
        shutil.rmtree(root, ignore_errors=True)
