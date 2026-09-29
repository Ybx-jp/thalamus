"""What the operator types is what the pane receives — tmux must read it as data.

Issue #152, fixed. `/api/send` (`console/server.py`) and `dispatch._send`
(`harness/dispatch.py`) hand caller text to `tmux send-keys -l`. `-l` stops tmux reading
the text as key names, but two layers under it still parse the text element as tmux
syntax:

**Option parsing.** Text beginning with `-` is read as flags. `-n` and `--help` are usage
errors and nothing is typed; `-t <pane>` is worse, because tmux accepts it and the
keystrokes address a pane of the payload's choosing. Only `--` ends option scanning.

**The command separator.** An argv token that ends with `;` has that one `;` consumed as
a command separator, so `echo hi;` arrives as `echo hi`. A `;` anywhere else in the token
arrives as data, and `\\;` is unescaped to `;`. The console posts each 24 ms burst of
typing as its own `text` (`flushKeys`, `app.js`), so a `-` or `;` lands at a chunk edge
in ordinary typing. Neither call site chunks server-side: one request, one `send-keys`.

**The oracle is real tmux, not a model of one.** The case drives the real `/api/send`
handler over HTTP and the real `dispatch._send`, each with its `tmux` replaced by a
recorder that executes nothing, then replays the recorded argv against a **private tmux
socket** (`tmux -L qe-...`, torn down in a `finally`; nothing here names the operator's
socket) and reads back the bytes the pane process received. The pane runs
`stty raw -echo; cat > FILE`, so the record is byte-exact: no terminal echo, no line
discipline, newlines and control bytes as sent. Only the `-t` target is rewritten on
replay, which keeps the text element under test untouched. A second window is a decoy
whose receiving file must stay empty: keystrokes must never reach a pane the request did
not name.

Payloads cover leading dashes and flag look-alikes (`-t 0`, `-t t:1 ...`, `-l`, `--`),
runs of trailing backslashes before a final `;`, a `;` followed by whitespace or a
newline, whitespace-only and multi-line text, tmux `{ }` blocks, `#{...}` and `%`
formats, `~` and `$VAR`, unicode, ESC and the word `Enter`.

**Controls.**

1. *Replay.* An ordinary payload must arrive; otherwise every "did not arrive" below is
   an artifact of the replay harness. Reported as a collapsed sentinel.
2. *Repair.* Each payload is sent a second time through an argv this case builds itself
   from the *posted* text (`-l -- <text with a final ; escaped>`), independent of what the
   server recorded. All must arrive, which attributes any loss in the shipped argv to how
   it was built and lets the control express both the broken and the fixed state.
3. *`/api/key`.* Built from the `KEYMAP` whitelist, it must not put dash-leading data
   where tmux reads keys.

Measured limits, not asserted here: tmux rejects an argv over about 16340 bytes with
`command too long` (rc 1), the same as before the fix, and `/api/send` does not read the
return code.

**Driven red** against the parent of the fix (21a385b): the shipped argv is bare
`-l <text>`, and the property fails on `-n`, `--help`, `-t 0`, `-t t:1 leaked` and every trailing-`;`
payload; the decoy stays empty there, because tmux consumes the whole element as a
target rather than typing it. Repeat it by checking out
`src/thalamus/console/server.py` and `src/thalamus/harness/dispatch.py` from 21a385b.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
import threading
import time
import uuid
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_WINDOWS = "0\tmain\t1\tclaude\t80\t24\t0\t/tmp\tclaude\t%0\t991"

_BS = "\\"

# Texts an operator (or another agent, via dispatch) sends. Each is sent alone, exactly
# as `flushKeys` posts a chunk. The first entry is not padding: it separates "tmux dropped
# this payload" from "the replay never typed anything at all".
_PAYLOADS = (
    ("plain", "an ordinary chunk"),
    ("a;b", "an embedded semicolon, which is NOT a separator"),
    ("-n", "a chunk starting with a dash: read as a flag"),
    ("--help", "a chunk starting with two dashes"),
    ("--", "the option terminator itself"),
    ("-l", "a flag look-alike of the one already passed"),
    ("-t 0", "a chunk that retargets the send to a pane of its own choosing"),
    ("-t t:1 leaked", "a retarget to the decoy window, which must stay empty"),
    ("echo hi;", "a chunk ending in a semicolon: the `;` is eaten"),
    ("a;;", "two trailing semicolons: exactly one is eaten"),
    (";", "a lone semicolon"),
    ("a" + _BS + ";", "a backslash before the final semicolon"),
    ("a" + _BS * 2 + ";", "two backslashes before the final semicolon"),
    ("a" + _BS * 3 + ";", "three backslashes before the final semicolon"),
    (_BS + ";", "a lone escaped semicolon"),
    ("a; ", "a semicolon followed by a space: not final, so data"),
    ("a;\n", "a semicolon followed by a newline"),
    ("line1\nline2;", "multi-line text ending in a semicolon"),
    ("   ", "whitespace only"),
    ("{", "a tmux command-block brace"),
    ("a }", "a closing brace"),
    ("{;", "an opening brace then a separator"),
    ("#{pane_id}", "a tmux format string"),
    ("%1", "a percent sequence"),
    ("~", "a tilde"),
    ("$HOME", "a shell variable"),
    ("héllo ✓ 日本語;", "unicode ending in a semicolon"),
    ("\x1b[A;", "an escape sequence ending in a semicolon"),
    ("Enter;", "a key name: `-l` must keep it text"),
)


def _oracle_args(text: str) -> list[str]:
    """`send-keys` tail that types `text` verbatim, built here from the text alone.

    `--` ends option parsing. tmux consumes exactly one trailing `;` of the element as a
    command separator, and unescapes `\;` to `;`; a `;` elsewhere in the element is
    data. Measured on tmux 3.4: `a;;` -> `a;`, `a\;\;` -> `a\;;`, `a;\;` -> `a;;`.
    """
    if text.endswith(";"):
        text = text[:-1] + _BS + ";"
    return ["-l", "--", text]


class _RecordingTmux:
    """Records argv and answers `list-windows`. Executes nothing, ever."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> subprocess.CompletedProcess:
        self.calls.append(args)
        out = _WINDOWS if args and args[0] == "list-windows" else ""
        return subprocess.CompletedProcess(args=list(args), returncode=0,
                                           stdout=out, stderr="")

    @property
    def sends(self) -> list[tuple[str, ...]]:
        return [c for c in self.calls if c and c[0] == "send-keys"]


@contextlib.contextmanager
def _serving(console, cfg):
    """The real handler on an ephemeral port, with tmux replaced by a recorder."""
    recorder = _RecordingTmux()
    real = console.tmux
    console.tmux = recorder
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), console.Handler)
    httpd.config = cfg
    thread = threading.Thread(target=httpd.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1], recorder
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        console.tmux = real


def _post(port: int, path: str, payload: dict) -> None:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("POST", path, json.dumps(payload),
                     {"Content-Type": "application/json"})
        conn.getresponse().read()
    finally:
        conn.close()


class _PrivateTmux:
    """A tmux server on a socket name nothing else can be holding.

    `-L` with a per-run name, and `kill-server` in the caller's `finally`. Window 0 is
    the target and window 1 a decoy; each runs `cat` in raw mode into its own file, so
    what a pane received is read back byte-exact.
    """

    def __init__(self, tmp: Path) -> None:
        self.socket = f"qe-sendkeys-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.out = {0: tmp / "target.bin", 1: tmp / "decoy.bin"}
        self.ready = {0: tmp / "target.ready", 1: tmp / "decoy.ready"}

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["tmux", "-L", self.socket, *args],
                              capture_output=True, text=True, timeout=10)

    def _cmd(self, n: int) -> str:
        return (f"stty raw -echo; : > {self.out[n]}; touch {self.ready[n]}; "
                f"exec cat >> {self.out[n]}")

    def _wait_ready(self, n: int) -> bool:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.ready[n].exists():
                return True
            time.sleep(0.01)
        return False

    def start(self) -> bool:
        for n in (0, 1):
            self.out[n].write_bytes(b"")
        self._run("new-session", "-d", "-s", "t", "-x", "80", "-y", "24",
                  "sh", "-c", self._cmd(0))
        self._run("new-window", "-d", "-t", "t:1", "sh", "-c", self._cmd(1))
        return self._wait_ready(0) and self._wait_ready(1)

    def reset(self) -> bool:
        for n in (0, 1):
            self.ready[n].unlink(missing_ok=True)
            self._run("respawn-pane", "-k", "-t", f"t:{n}", "sh", "-c", self._cmd(n))
        return self._wait_ready(0) and self._wait_ready(1)

    def replay(self, argv: tuple[str, ...]) -> None:
        """Run one recorded send-keys argv, retargeted to the private target pane."""
        args = list(argv)
        for i, a in enumerate(args):
            if a == "-t" and i + 1 < len(args):
                args[i + 1] = "t:0"
                break
        self._run(*args)

    def received(self, n: int, want: bytes) -> bytes:
        """What pane `n` got, waiting for `want`'s length (a lost payload times out)."""
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            if len(self.out[n].read_bytes()) >= len(want):
                break
            time.sleep(0.01)
        time.sleep(0.03)
        return self.out[n].read_bytes()

    def stop(self) -> None:
        with contextlib.suppress(Exception):
            self._run("kill-server")


def _arrived(private: _PrivateTmux, argv: tuple[str, ...], text: str) -> tuple[bytes, bytes]:
    """(target bytes, decoy bytes) after replaying `argv`."""
    private.reset()
    private.replay(argv)
    want = text.encode()
    return private.received(0, want), private.received(1, b"")


def run() -> Finding | None:
    from thalamus.console import server as console  # noqa: PLC0415
    from thalamus.harness import dispatch  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        private = _PrivateTmux(Path(tmp))
        try:
            if not private.start():
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="the private tmux session this case needs did not start, so "
                            "nothing below could observe a keystroke arriving or "
                            "failing to arrive",
                    witness=f"tmux -L {private.socket} produced no ready panes",
                    site="tests/qe/cases/console_send_text_is_data_not_argv.py",
                )

            root = Path(tmp) / "checkout"
            (root / ".git").mkdir(parents=True)
            cfg = console.Config(session="qe-send-probe", project_root=root)

            # Capture the argv each real call site builds, one send per payload.
            # (surface, text, why, argv)
            captured: list[tuple[str, str, str, tuple[str, ...]]] = []
            with _serving(console, cfg) as (port, recorder):
                for text, why in _PAYLOADS:
                    before = len(recorder.sends)
                    _post(port, "/api/send",
                          {"index": 0, "text": text, "submit": False})
                    new = recorder.sends[before:]
                    if not new:
                        return Finding(
                            failure_class=FailureClass.COLLAPSED_SENTINEL,
                            summary="/api/send built no send-keys argv for a payload, "
                                    "so this case has nothing to replay and cannot "
                                    "report on what tmux would do with it",
                            witness=f"text={text!r} ({why}) produced no send-keys call",
                            site="src/thalamus/console/server.py",
                        )
                    captured.append(("/api/send", text, why, new[0]))

                # CONTROL 3: the named-key route must build its argv from the
                # whitelist, with nothing dash-leading reaching tmux as data.
                before = len(recorder.sends)
                _post(port, "/api/key", {"index": 0, "key": "enter"})
                key_argv = recorder.sends[before:]

            dispatch_rec = _RecordingTmux()
            real_dispatch_tmux = dispatch._tmux
            dispatch._tmux = dispatch_rec
            try:
                for text, why in _PAYLOADS:
                    before = len(dispatch_rec.sends)
                    dispatch._send("%0", text, submit=False)
                    new = dispatch_rec.sends[before:]
                    if not new:
                        return Finding(
                            failure_class=FailureClass.COLLAPSED_SENTINEL,
                            summary="dispatch._send built no send-keys argv for a "
                                    "payload, so this case cannot report on it",
                            witness=f"text={text!r} ({why}) produced no send-keys call",
                            site="src/thalamus/harness/dispatch.py",
                        )
                    captured.append(("dispatch._send", text, why, new[0]))
            finally:
                dispatch._tmux = real_dispatch_tmux

            # CONTROL 1, before any verdict: a benign payload must reach the pane.
            plain = next(c for c in captured if c[1] == "plain")
            got, _ = _arrived(private, plain[3], "plain")
            if got != b"plain":
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="an ordinary chunk did not reach the private pane, so the "
                            "replay harness cannot observe a keystroke arriving and "
                            "every missing payload below would be its own artifact",
                    witness=f"sent 'plain', pane held {got!r}",
                    site="tests/qe/cases/console_send_text_is_data_not_argv.py",
                )

            # CONTROL 2: an argv built here from the text alone must deliver every
            # payload, so a loss in the shipped argv is attributable to its construction.
            for text, why in _PAYLOADS:
                oracle = ("send-keys", "-t", "t:0", *_oracle_args(text))
                got, decoy = _arrived(private, oracle, text)
                if got != text.encode() or decoy:
                    return Finding(
                        failure_class=FailureClass.COLLAPSED_SENTINEL,
                        summary="a payload did not arrive even through the oracle's own "
                                "argv, so this case cannot show the argv construction "
                                "is what loses it and its findings are not attributable",
                        witness=f"oracle argv for {text!r} ({why}) left the pane "
                                f"holding {got!r} and the decoy {decoy!r}",
                        site="tests/qe/cases/console_send_text_is_data_not_argv.py",
                    )

            if key_argv and any(a.startswith("-") for a in key_argv[0][4:]):
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="/api/key put a dash-leading element where tmux reads keys, "
                            "which the KEYMAP whitelist should make impossible — the "
                            "probe is more likely wrong than the whitelist",
                    witness=f"/api/key argv={key_argv[0]}",
                    site="src/thalamus/console/server.py",
                )

            # THE PROPERTY, over each argv as it ships.
            lost = []
            for surface, text, why, argv in captured:
                got, decoy = _arrived(private, argv, text)
                if got != text.encode() or decoy:
                    lost.append(f"{surface} {text!r} ({why}) -> pane held {got!r}"
                                + (f", decoy held {decoy!r}" if decoy else ""))

            if lost:
                return Finding(
                    failure_class=FailureClass.BOUNDARY_LEAK,
                    summary="text sent to tmux send-keys is parsed by tmux as arguments "
                            "rather than typed as data, so chunks beginning with a dash "
                            "set flags or retarget the pane and a trailing semicolon is "
                            "dropped",
                    witness="; ".join(lost) + " — the same payloads all arrive through "
                            "an argv built as `-l -- <text, final ; escaped>`",
                    site="src/thalamus/console/server.py, src/thalamus/harness/dispatch.py",
                )
        finally:
            private.stop()
    return None


CASE = Case(
    name="typed-text-reaches-the-pane-as-data-not-as-tmux-arguments",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="text sent through /api/send or dispatch must arrive in the pane verbatim, "
            "not be read by tmux as flags, a retarget, or a command separator",
    run=run,
    issue=152,
    fixed=True,
)
