"""
Typed text reaches the pane as data (harness/tmux.py literal_text_args).

Interfaces: thalamus.harness.tmux.literal_text_args, dispatch._send
Infrastructure: a private tmux server (`-L`, never the roster's) running `sleep` (the tty echoes what it is sent), read
back with capture-pane; skipped when tmux is absent
Scope: `send-keys -l` still parses its text argument as tmux syntax — a leading `-` is
flags (`-t 0` retargets the send) and a trailing `;` is a command separator.
"""

import os
import shutil
import subprocess
import time

import pytest

from thalamus.harness import dispatch
from thalamus.harness.tmux import literal_text_args

PAYLOADS = ["-t 0", "-X", "--", "a;", "a\\;", ";", "\\;", "a;;", "x; y", "x ;y",
            "-", "", "a;b;", ";;", "; ;", "\\\\;"]

needs_tmux = pytest.mark.skipif(not shutil.which("tmux"), reason="tmux not installed")


@pytest.fixture
def pane():
    sock = f"thalamus-test-literal-{os.getpid()}"

    def tmux(*args):
        return subprocess.run(["tmux", "-L", sock, "-f", "/dev/null", *args],
                              capture_output=True, text=True, timeout=5)

    tmux("new-session", "-d", "-s", "s", "-x", "200", "-y", "20", "echo READY; sleep 300")
    try:
        yield tmux
    finally:
        tmux("kill-server")


def _screen(tmux):
    """The pane's first two lines, padded — capture-pane trims trailing blanks."""
    return [*tmux("capture-pane", "-p", "-J", "-t", "s:0.0").stdout.split("\n"), "", ""][:2]


def _typed(tmux, args, want):
    """What the pane shows after `send-keys args`, polled until it equals `want` or a
    few seconds pass. The pane prints READY first so keys are never sent before its shell
    is reading."""
    tmux("respawn-pane", "-k", "-t", "s:0.0", "echo READY; sleep 300")
    deadline = time.time() + 5.0
    while _screen(tmux)[0] != "READY" and time.time() < deadline:
        time.sleep(0.02)
    tmux("send-keys", "-t", "s:0.0", *args)
    deadline = time.time() + 5.0
    while True:
        shown = _screen(tmux)[1]
        if shown == want or time.time() > deadline:
            return shown
        time.sleep(0.05)


@needs_tmux
@pytest.mark.parametrize("text", PAYLOADS)
def test_text_arrives_byte_for_byte(pane, text):
    """
    Scenario: text that tmux would read as an option or a command separator.

    Verification: the pane shows exactly the text. Without `--` and the `;` escape
    `-t 0`, `-X`, `--`, `a;`, `;` and `a;;` are lost, retargeted or truncated.
    """
    assert _typed(pane, literal_text_args(text), text) == text


@needs_tmux
def test_the_bare_argv_loses_these_payloads(pane):
    """The control: the argv without the helper (`-l` alone) drops or mangles the
    payloads, so the parametrized test above measures the helper and not a permissive
    tmux."""
    lost = [t for t in PAYLOADS if _typed(pane, ["-l", t], t) != t]
    assert {"-t 0", "--", "a;", ";"} <= set(lost)


def test_dispatch_send_passes_the_literal_tail(monkeypatch):
    calls = []

    def fake(*args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(dispatch, "_tmux", fake)
    assert dispatch._send("%3", "-t 0;", submit=False) == ""
    assert calls == [("send-keys", "-t", "%3", "-l", "--", "-t 0\\;")]
