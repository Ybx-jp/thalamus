"""A text `/api/send` cannot deliver is refused, not acknowledged and then submitted.

Issue #327. `/api/send` (`console/server.py`) types the posted `text` with one
`tmux send-keys -t <target> -l -- <text>` and never reads its return code. tmux refuses a
command whose argv is longer than about 16,340 bytes (`command too long`, rc 1) and types
nothing. The handler answers `{"ok": true}` all the same and, with `submit` on (the
default), goes on to send `Enter` into a composer that never received the text.
`dispatch._send` builds the same argv and reports the failure; this endpoint does not.

The property: a text posted over the limit either reaches the pane intact, or the response
is non-2xx; and when it did not reach the pane, no `Enter` does either.

**The oracle is real tmux.** The case drives the real `/api/send` handler over HTTP with
`console.tmux` replaced by a shim that answers `list-windows` itself and runs every other
call on a **private tmux socket** (`tmux -L qe-...`, torn down in a `finally`; nothing
here names the operator's socket or a session called `thalamus`), rewriting only the
`-t` target. The pane runs `stty raw -echo; cat > FILE`, so what it received is
byte-exact and an `Enter` shows up as a `\\r`. Each call's return code and stderr are
recorded, so the witness can say tmux itself refused the text.

**Controls.**

1. *Delivery.* A text under the limit, posted the same way with `submit` on, must arrive
   followed by one `\\r`; otherwise "nothing arrived" over the limit is a harness artifact.
2. *Limit.* The over-limit `send-keys` must be seen failing with `command too long` on the
   tmux the handler called, which attributes the loss to tmux's refusal and not to the
   replay.

Measured on tmux 3.4: 16,340 bytes or less is delivered; 17,000 to 70,000 gets rc 1.
Drive it green by having the handler check the `send-keys` return code, skip the `Enter`
and answer non-2xx, or by delivering long text through a tmux buffer.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import tempfile
import threading
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier
from .console_send_text_is_data_not_argv import _WINDOWS, _PrivateTmux

_SITE = "src/thalamus/console/server.py"
_SELF = "tests/qe/cases/console_send_oversize_text.py"


def _text(n: int) -> str:
    """`n` bytes of ASCII with no short period, so a truncation cannot pass unnoticed."""
    unit = "0123456789abcdefghijklmnopqrstuvwxyz"
    return "".join(unit[(i * 7 + i // 36) % 36] for i in range(n))


class _PrivateShim:
    """`console.tmux` that runs on the private socket and records rc and stderr."""

    def __init__(self, private: _PrivateTmux) -> None:
        self.private = private
        self.calls: list[tuple[tuple[str, ...], int, str]] = []

    def __call__(self, *args: str) -> subprocess.CompletedProcess:
        if args and args[0] == "list-windows":
            return subprocess.CompletedProcess(list(args), 0, _WINDOWS, "")
        argv = list(args)
        for i, a in enumerate(argv):
            if a == "-t" and i + 1 < len(argv):
                argv[i + 1] = "t:0"
                break
        r = subprocess.run(["tmux", "-L", self.private.socket, *argv],
                           capture_output=True, text=True, timeout=10)
        self.calls.append((args, r.returncode, r.stderr.strip()))
        return r


@contextlib.contextmanager
def _serving(console, cfg, shim):
    real = console.tmux
    console.tmux = shim
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), console.Handler)
    httpd.config = cfg
    thread = threading.Thread(target=httpd.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        console.tmux = real


def _post_send(port: int, text: str) -> tuple[int, str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        conn.request("POST", "/api/send",
                     json.dumps({"index": 0, "text": text, "submit": True}),
                     {"Content-Type": "application/json"})
        resp = conn.getresponse()
        return resp.status, resp.read().decode("utf-8", "replace")
    finally:
        conn.close()


def _settle(private: _PrivateTmux, want: int) -> bytes:
    """Pane bytes once `want` have arrived, or after a grace period if they never do."""
    deadline = time.monotonic() + 0.6
    while time.monotonic() < deadline:
        if len(private.out[0].read_bytes()) >= want:
            break
        time.sleep(0.01)
    time.sleep(0.05)
    return private.out[0].read_bytes()


def run() -> Finding | None:
    from thalamus.console import server as console  # noqa: PLC0415

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
                    site=_SELF,
                )
            root = Path(tmp) / "checkout"
            (root / ".git").mkdir(parents=True)
            cfg = console.Config(session="qe-send-oversize", project_root=root)
            shim = _PrivateShim(private)

            bad: list[str] = []
            refused_seen = False
            with _serving(console, cfg, shim) as port:
                # CONTROL 1: an under-limit text, submit on, arrives and is submitted.
                small = _text(8000)
                private.reset()
                status, _ = _post_send(port, small)
                got = _settle(private, len(small) + 1)
                if status != 200 or got != small.encode() + b"\r":
                    return Finding(
                        failure_class=FailureClass.COLLAPSED_SENTINEL,
                        summary="an 8000-byte text posted to /api/send did not reach the "
                                "private pane followed by Enter, so this case cannot "
                                "observe delivery and every loss below is its own artifact",
                        witness=f"status={status}; pane held {len(got)} bytes "
                                f"(want {len(small) + 1})",
                        site=_SELF,
                    )

                for n in (17000, 40000, 70000):
                    text = _text(n)
                    private.reset()
                    shim.calls.clear()
                    status, body = _post_send(port, text)
                    got = _settle(private, len(text) + 1)
                    sends = [c for c in shim.calls if c[0][:1] == ("send-keys",)]
                    tmux_said = next((err for a, rc, err in sends
                                      if rc != 0 and "-l" in a), "")
                    refused_seen = refused_seen or "too long" in tmux_said
                    delivered = got.startswith(text.encode())
                    enter = b"\r" in got[len(text) if delivered else 0:]
                    held = (f"{len(got)} byte(s) ({got!r})" if len(got) < 16
                            else f"{len(got)} bytes")
                    if not delivered and status // 100 == 2:
                        bad.append(
                            f"{n}-byte text: HTTP {status} {body.strip()} while the "
                            f"pane held {held}{' including an Enter' if enter else ''}; "
                            f"tmux said {tmux_said!r}")
                    elif not delivered and enter:
                        bad.append(f"{n}-byte text: HTTP {status} but an Enter still "
                                   f"reached the pane; tmux said {tmux_said!r}")

            # CONTROL 2: the loss must be tmux's own refusal of the handler's call.
            if not refused_seen:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="no over-limit send-keys was seen failing with "
                            "`command too long`, so the loss (if any) is not attributable "
                            "to tmux's argv limit",
                    witness=f"last send-keys calls: {[(rc, err) for _, rc, err in sends]}",
                    site=_SELF,
                )

            if bad:
                return Finding(
                    failure_class=FailureClass.INVARIANT_FALSIFIED,
                    summary="/api/send does not check tmux's return code: text over "
                            "tmux's command-length limit is dropped, the response is "
                            "success, and Enter is still sent",
                    witness="; ".join(bad),
                    site=_SITE,
                )
        finally:
            private.stop()
    return None


CASE = Case(
    name="send-oversize-text-is-delivered-or-refused-and-never-submitted",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="text over tmux's command limit posted to /api/send must reach the pane or "
            "be refused with a non-2xx, and no Enter may follow an undelivered text",
    run=run,
    issue=327,
    fixed=False,
)
