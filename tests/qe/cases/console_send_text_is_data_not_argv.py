"""What the operator types is what the pane receives — tmux must read it as data.

Issue #152, open. `/api/send` hands the posted text to tmux as a bare argv element
(`console/server.py:2165`):

    tmux("send-keys", "-t", target, "-l", text)

`-l` is there on purpose and both call sites document why: without it tmux reads the
payload as key *names*, so a message containing the word `Enter` submits itself early
(`harness/dispatch.py:534`). What `-l` does not do is stop the two layers underneath it.

**Option parsing.** `text` is the last argv element, and tmux's option scan is still in
flag position when it reaches it, so text beginning with `-` is read as flags. `-n` and
`--help` are usage errors and nothing is typed. `-t <pane>` is worse than an error: tmux
accepts the flag and takes the rest as a target, so the keystrokes address a pane of the
payload's choosing rather than the one the request named.

**The command separator.** An argv token that *is* `;` or *ends with* `;` has the
semicolon consumed as a tmux command separator. `a;b` arrives whole; a lone `;` never
arrives; `echo hi;` arrives as `echo hi`.

Every one of those calls returns rc 0 or is never checked — `server.py:2165` does not
read the return code at all, so `/api/send` answers `200 {"ok": true}` either way, and
the client swallows failures wholesale (`static/app.js:876`, `catch (e) {}`). The
operator sees characters silently missing from the pane and nothing anywhere says so.

**Why the two console surfaces disagree, which is the reported symptom.** `flushKeys`
(`app.js:2708`) cuts the typed stream at 24 ms boundaries (`KEY_COALESCE_MS`,
`app.js:2685`) and posts each chunk as its own `text`. A `-` or a `;` anywhere in what is
being typed can therefore land at the *start* or the *end* of a chunk, so ordinary
typing — `--dangerously-skip-permissions`, a `- ` bullet, any line ending in `;` — hits
this constantly. The composer posts the whole string as one element, so only a string
that itself begins with `-` or ends with `;` is affected. Same endpoint, same absent
escaping (`sendMessage`, `app.js:883`); only the chunking differs.

`dispatch.py:537` carries the identical defect over text composed by *another agent*,
which is where the retarget stops being a typo and becomes a write outside the room the
message was addressed to.

**The oracle is real tmux, not a model of one.** A case that asserted "the argv contains
`--`" would be pinning a fix rather than the property, and would go green on a repair
that inserted `--` and still lost the semicolon. So this drives the real `/api/send`
handler over real HTTP, captures the argv the server actually built, replays that argv
against a **private tmux socket** (`tmux -L qe-…`), and reads the pane back. The property
is the one the operator cares about: the characters posted are the characters that
arrive.

**It cannot reach the operator's control plane.** The socket name is unique per run and
the server is torn down in a `finally`. Nothing here goes near `tmux -L thalamus`: the
console's own `tmux` is replaced by a recorder that executes nothing, and the replay
rewrites the target to the private pane this case created. The recorded argv is used
verbatim otherwise — rewriting only the target is what keeps the text element, which is
the thing under test, untouched.

**Three controls, all running.**

1. *The replay control.* A benign text must arrive in the pane. If it does not, the
   replay harness is pointed at the wrong pane or socket and every "text did not arrive"
   below is an artifact of this case rather than a fact about the product. Reported as a
   collapsed sentinel, never as a finding.
2. *The repair control.* Every probe argv is replayed a second time in repaired form —
   `--` inserted before the text, and `;` escaped as `\\;`. All of them must arrive. This
   is what makes the finding attributable to the argv construction: it shows the same
   text, the same tmux, and the same pane accept the payload once the argv is built
   correctly, so the failures above are not tmux refusing the characters themselves.
3. *Discrimination on `/api/key`.* The named-key route builds its argv from `KEYMAP`
   (`server.py:553`), a strict whitelist, and must not be affected. A case that reported
   both routes broken would more likely have a broken replay than have found a second
   defect, and `tests/test_console.py:1047` already pins the whitelist's shape.

**Shown capable of going red** — it is red now, against the defect as it ships. Control 2
is the green direction, run every time rather than described: it replays the repaired
argv through the same oracle and requires every payload to land.
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

# Texts an operator types. Each is posted alone, exactly as `flushKeys` posts a chunk.
# The two benign entries are not padding: they are what separates "tmux dropped this
# payload" from "the replay never typed anything at all".
_PAYLOADS = (
    ("plain", "an ordinary chunk"),
    ("a;b", "an embedded semicolon, which is NOT a separator"),
    ("-n", "a chunk starting with a dash: read as a flag"),
    ("--help", "a chunk starting with two dashes"),
    ("-t 0", "a chunk that retargets the send to a pane of its own choosing"),
    ("echo hi;", "a chunk ending in a semicolon: the `;` is eaten"),
    ("a;;", "two trailing semicolons: exactly one is eaten"),
)


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

    `-L` with a per-run name, and `kill-server` in the caller's `finally`. The console's
    own socket is never named here and this case never calls `harness.tmux.argv`.
    """

    def __init__(self) -> None:
        self.socket = f"qe-sendkeys-{os.getpid()}-{uuid.uuid4().hex[:8]}"

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["tmux", "-L", self.socket, *args],
                              capture_output=True, text=True, timeout=10)

    def start(self) -> None:
        # `cat` echoes what is typed, so the pane content is a faithful record of what
        # arrived — and it execs nothing that could outlive the socket.
        self._run("new-session", "-d", "-s", "t", "-x", "80", "-y", "24", "cat")

    def replay(self, argv: tuple[str, ...]) -> None:
        """Run one recorded send-keys argv, retargeted to this private pane."""
        args = list(argv)
        for i, a in enumerate(args):
            if a == "-t" and i + 1 < len(args):
                args[i + 1] = "t:0"
                break
        self._run(*args)

    def pane(self) -> str:
        return self._run("capture-pane", "-p", "-t", "t:0").stdout

    def clear(self) -> None:
        self._run("send-keys", "-t", "t:0", "-X", "cancel")
        self._run("clear-history", "-t", "t:0")
        self._run("respawn-pane", "-k", "-t", "t:0", "cat")
        time.sleep(0.15)

    def stop(self) -> None:
        with contextlib.suppress(Exception):
            self._run("kill-server")


def _repaired(argv: tuple[str, ...]) -> list[str]:
    """The same send, built so tmux reads the text as data.

    Two separate rules, and conflating them is a bug this case caught in its own first
    draft: escaping every `;` types a literal backslash for the embedded ones.

    `--` ends option parsing, which covers the leading dash. The separator is a lexical
    rule `--` does not reach, and it consumes exactly **one trailing** semicolon —
    measured against tmux 3.4, 2026-08-31, sending each payload and reading the pane:

        a;b        -> a;b       embedded, untouched
        a;;        -> a;        one trailing `;` eaten, not both
        \\;         -> ;         an escaped one arrives
        a\\;\\;      -> a\\;;      escaping a non-final one types the backslash
        a;\\;       -> a;;       so escape the final one only

    """
    args = list(argv)
    text = args[-1]
    if text.endswith(";"):
        text = text[:-1] + r"\;"
    return [*args[:-1], "--", text]


def _arrived(private: _PrivateTmux, argv, repair: bool) -> str:
    private.clear()
    private.replay(tuple(_repaired(argv)) if repair else argv)
    time.sleep(0.3)
    return private.pane().strip()


def run() -> Finding | None:
    from thalamus.console import server as console  # noqa: PLC0415

    private = _PrivateTmux()
    try:
        private.start()
        if "t:0" not in private._run("list-windows", "-t", "t",
                                     "-F", "t:#{window_index}").stdout:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the private tmux session this case needs did not start, so "
                        "nothing below could observe a keystroke arriving or failing "
                        "to arrive",
                witness=f"tmux -L {private.socket} new-session produced no window",
                site="tests/qe/cases/console_send_text_is_data_not_argv.py",
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "checkout"
            (root / ".git").mkdir(parents=True)
            cfg = console.Config(session="qe-send-probe", project_root=root)

            # Capture the argv the real handler builds, one POST per payload, exactly
            # as `flushKeys` posts a chunk: submit false, so no Enter is appended.
            captured: list[tuple[str, str, tuple[str, ...]]] = []
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
                            site="src/thalamus/console/server.py:2165",
                        )
                    captured.append((text, why, new[0]))

                # CONTROL 3: the named-key route must build its argv from the
                # whitelist, with nothing dash-leading reaching tmux as data.
                before = len(recorder.sends)
                _post(port, "/api/key", {"index": 0, "key": "enter"})
                key_argv = recorder.sends[before:]

            # CONTROL 1, before any verdict: a benign payload must reach the pane.
            plain = next(c for c in captured if c[0] == "plain")
            if _arrived(private, plain[2], repair=False) != "plain":
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="an ordinary chunk did not reach the private pane, so the "
                            "replay harness cannot observe a keystroke arriving and "
                            "every missing payload below would be its own artifact",
                    witness=f"posted 'plain', pane held "
                            f"{_arrived(private, plain[2], repair=False)!r}",
                    site="tests/qe/cases/console_send_text_is_data_not_argv.py",
                )

            # CONTROL 2: repaired argv must deliver every payload, including the ones
            # the shipped argv loses. This is what attributes the finding to the argv.
            for text, why, argv in captured:
                got = _arrived(private, argv, repair=True)
                if got != text:
                    return Finding(
                        failure_class=FailureClass.COLLAPSED_SENTINEL,
                        summary="a payload did not arrive even with the argv repaired, "
                                "so this case cannot show the argv construction is "
                                "what loses it and its findings are not attributable",
                        witness=f"repaired argv for {text!r} ({why}) left the pane "
                                f"holding {got!r}",
                        site="tests/qe/cases/console_send_text_is_data_not_argv.py",
                    )

            if key_argv and any(a.startswith("-") for a in key_argv[0][4:]):
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="/api/key put a dash-leading element where tmux reads keys, "
                            "which the KEYMAP whitelist should make impossible — the "
                            "probe is more likely wrong than the whitelist",
                    witness=f"/api/key argv={key_argv[0]}",
                    site="src/thalamus/console/server.py:2185",
                )

            # THE PROPERTY, over the argv as it ships.
            lost = []
            for text, why, argv in captured:
                got = _arrived(private, argv, repair=False)
                if got != text:
                    lost.append(f"{text!r} ({why}) -> pane held {got!r}")

            if lost:
                return Finding(
                    failure_class=FailureClass.BOUNDARY_LEAK,
                    summary="text posted to /api/send is parsed by tmux as arguments "
                            "rather than typed as data, so chunks beginning with a dash "
                            "set flags or retarget the pane and a trailing semicolon is "
                            "dropped — and /api/send answers 200 ok for every one",
                    witness="; ".join(lost) + " — the same payloads all arrive when the "
                            "argv is repaired with `--` and an escaped `;`",
                    site="src/thalamus/console/server.py:2165",
                )
    finally:
        private.stop()
    return None


CASE = Case(
    name="typed-text-reaches-the-pane-as-data-not-as-tmux-arguments",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="text posted to /api/send must arrive in the pane verbatim, not be read by "
            "tmux as flags, a retarget, or a command separator",
    run=run,
    issue=152,
)
