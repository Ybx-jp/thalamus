"""
Typed text reaches the pane as data (harness/tmux.py literal_text_args).

Interfaces: thalamus.harness.tmux.literal_text_args, dispatch._send
Infrastructure: a private tmux server (`-L`, never the roster's) whose pane runs `stty raw -echo; cat > FILE`, read
back from FILE once a trailing sentinel arrives; skipped when tmux is absent
Scope: `send-keys -l` still parses its text argument as tmux syntax — a leading `-` is
flags (`-t 0` retargets the send) and a trailing `;` is a command separator.
"""

import os
import shutil
import subprocess
import time
import uuid

import pytest

from thalamus.harness import dispatch
from thalamus.harness.tmux import literal_text_args

PAYLOADS = ["-t 0", "-X", "--", "a;", "a\\;", ";", "\\;", "a;;", "x; y", "x ;y",
            "-", "", "a;b;", ";;", "; ;", "\\\\;"]

needs_tmux = pytest.mark.skipif(not shutil.which("tmux"), reason="tmux not installed")


SENTINEL = "\x01"


class _Pane:
    """A private tmux server's one pane, running `stty raw -echo; cat > FILE`."""

    def __init__(self, sock, tmp):
        self.sock = sock
        self.out = tmp / "out.bin"
        self.ready = tmp / "ready"

    def tmux(self, *args):
        return subprocess.run(["tmux", "-L", self.sock, "-f", "/dev/null", *args],
                              capture_output=True, text=True, timeout=30)

    def _cmd(self):
        return (f"stty raw -echo; : > {self.out}; touch {self.ready}; "
                f"exec cat >> {self.out}")

    def start(self):
        self.tmux("new-session", "-d", "-s", "s", "-x", "200", "-y", "20", "sh", "-c", self._cmd())

    def typed(self, args, deadline_s=60.0):
        """The bytes the pane's process received from `send-keys args`.

        The pane records raw bytes (no echo, no line discipline) and a sentinel is sent
        in a separate `send-keys` after `args`; the pty delivers in order, so the
        sentinel's arrival means everything sent before it has arrived or was lost.
        Nothing is timed against a screen."""
        self.ready.unlink(missing_ok=True)
        self.tmux("respawn-pane", "-k", "-t", "s:0.0", "sh", "-c", self._cmd())
        self._wait(lambda: self.ready.exists(), deadline_s)
        self.tmux("send-keys", "-t", "s:0.0", *args)
        self.tmux("send-keys", "-t", "s:0.0", "-l", "--", SENTINEL)
        self._wait(lambda: self.out.read_bytes().endswith(SENTINEL.encode()), deadline_s)
        return self.out.read_bytes()[:-1].decode()

    @staticmethod
    def _wait(cond, deadline_s):
        deadline = time.monotonic() + deadline_s
        while not cond():
            assert time.monotonic() < deadline, "the pane never reached the expected state"
            time.sleep(0.02)


@pytest.fixture(scope="module")
def pane(tmp_path_factory):
    """One private server per module, on a socket no other worker or run shares."""
    p = _Pane(f"thalamus-test-literal-{os.getpid()}-{uuid.uuid4().hex[:8]}",
              tmp_path_factory.mktemp("literal"))
    try:
        p.start()
        yield p
    finally:
        p.tmux("kill-server")


@needs_tmux
@pytest.mark.parametrize("text", PAYLOADS)
def test_text_arrives_byte_for_byte(pane, text):
    """
    Scenario: text that tmux would read as an option or a command separator.

    Verification: the pane shows exactly the text. Without `--` and the `;` escape
    `-t 0`, `-X`, `--`, `a;`, `;` and `a;;` are lost, retargeted or truncated.
    """
    assert pane.typed(literal_text_args(text)) == text


@needs_tmux
def test_the_bare_argv_loses_these_payloads(pane):
    """The control: the argv without the helper (`-l` alone) drops or mangles the
    payloads, so the parametrized test above measures the helper and not a permissive
    tmux."""
    lost = [t for t in PAYLOADS if pane.typed(["-l", t]) != t]
    assert {"-t 0", "--", "a;", ";"} <= set(lost)


def test_dispatch_send_passes_the_literal_tail(monkeypatch):
    calls = []

    def fake(*args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(dispatch, "_tmux", fake)
    assert dispatch._send("%3", "-t 0;", submit=False) == ""
    assert calls == [("send-keys", "-t", "%3", "-l", "--", "-t 0\\;")]
