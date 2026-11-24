"""The write gate must answer a malformed `Origin` with the refusal, not with a crash.

Issue #132's gate (`Handler._origin_ok`, `same_origin`, `origin_key`) compares the request's
`Origin`/`Referer` with the `Host` it was addressed to. `console_write_origin` drives it with
well-formed foreign origins and proves a refusal reaches no pane. Neither it nor the unit
tests feed the parser what a hostile page or a broken proxy can actually put in the header:
a port that is not a number, out of range, signed or hex, an unterminated IPv6 literal, a
stack of colons. `urlsplit(...).port` raises `ValueError` on every one of those, nothing in
`_origin_ok` catches it, and the route's `_answered` wrapper turns the exception into
`500 {"error": "ValueError: Port could not be cast to integer value as '...'"}`.

It fails closed — the exception fires before the route runs, so nothing is typed — but by
accident, and the accident has three costs. The status is wrong for the caller (a 500 reads
as a console fault and is retried or reported as one, where the answer is "this origin is
refused"). The refusal is not in the refusal's shape, so a client that branches on the 403
the gate documents never sees it. And the property "every request the gate cannot place is
refused" is held by an exception rather than by the gate: a later change that guards the
parse with a bare `except: pass` — the obvious repair for a 500 — turns the same input into
an accepted write.

**Property.** For `Origin` and, separately, `Referer` set to each of a fixed set of
malformed values, `POST /api/send` answers `403`, nothing is typed into the pane, and the
console process is still serving.

**Controls.** The request with the console's own origin must be accepted and must type the
probe text into the pane (so "nothing typed" can be seen); a well-formed foreign origin must
be 403 (so the gate is on); a request with neither header is accepted (the documented
allowance), so a console that refused everything is not what passes.

**Shown capable of going red.** Current tree: red, e.g. `Origin: http://127.0.0.1:54321.evil.example`
-> `500 ValueError: Port could not be cast to integer value`. Green: in a copy of
`Handler._origin_ok` (`QE_CONSOLE_SRC`) wrap the two comparisons in `try/except ValueError:
return False` and the case passes. A copy that wraps them in `except ValueError: return
True` reports `failed-open` with the probe text in the pane.
"""

from __future__ import annotations

import json
import uuid

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_rig import console_rig

_SITE = "packages/thalamus-console/src/thalamus_console/server.py::Handler._origin_ok"

_MALFORMED = (
    "http://127.0.0.1:{port}.evil.example",   # port that is not a number
    "http://127.0.0.1:99999",                  # port out of range
    "http://127.0.0.1:-1",
    "http://127.0.0.1:0x10",
    "http://[::1",                             # unterminated IPv6 literal
    "http://[::1]:x",
    "http://a:b:c",
)


def run() -> Finding | None:
    with console_rig() as rig:
        def send(token, **headers):
            body = json.dumps({"index": 0, "text": token, "submit": False}).encode()
            h = {"Content-Type": "text/plain", **headers}
            r = rig.request("POST", "/api/send", body, h)
            typed = token in rig.capture(0)
            return r.status, typed

        # controls
        t = "QE-OWN-" + uuid.uuid4().hex[:8]
        status, typed = send(t, Origin=rig.base)
        if status != 200 or not rig.wait_for(lambda: t in rig.capture(0), timeout=5):
            return Finding(FailureClass.COLLAPSED_SENTINEL,
                           "a same-origin send did not land, so 'nothing typed' cannot be "
                           "seen", witness=f"status={status} typed={typed}", site=_SITE)
        t = "QE-FOREIGN-" + uuid.uuid4().hex[:8]
        status, typed = send(t, Origin="https://evil.example")
        if status != 403 or typed:
            return Finding(FailureClass.COLLAPSED_SENTINEL,
                           "the gate did not refuse a well-formed foreign origin",
                           witness=f"status={status} typed={typed}", site=_SITE)
        t = "QE-NONE-" + uuid.uuid4().hex[:8]
        status, typed = send(t)
        if status != 200:
            return Finding(FailureClass.COLLAPSED_SENTINEL,
                           "a request with no Origin or Referer was refused — the "
                           "documented allowance is gone, or the fixture is broken",
                           witness=f"status={status}", site=_SITE)

        for header in ("Origin", "Referer"):
            for template in _MALFORMED:
                value = template.format(port=rig.port)
                t = "QE-BAD-" + uuid.uuid4().hex[:8]
                status, typed = send(t, **{header: value})
                if typed:
                    return Finding(FailureClass.FAILED_OPEN,
                                   "a malformed origin was accepted and its text typed "
                                   "into a pane",
                                   witness=f"{header}: {value!r} -> {status}, "
                                           f"{t} in pane 0", site=_SITE)
                if status != 403:
                    return Finding(
                        FailureClass.INVARIANT_FALSIFIED,
                        "a malformed Origin/Referer is not refused with the gate's 403: "
                        "the parse raises and the route answers 500, so the request is "
                        "refused by accident and in the wrong shape",
                        witness=f"POST /api/send {header}: {value!r} -> {status} "
                                f"(want 403)", site=_SITE)
        if not rig.alive():
            return Finding(FailureClass.INVARIANT_FALSIFIED,
                           "the console died serving a malformed origin",
                           witness=rig.log_tail(300), site=_SITE)
    return None


CASE = Case(
    name="console-write-gate-answers-403-to-a-malformed-origin",
    issue=418,
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.FAILED_OPEN,
             FailureClass.COLLAPSED_SENTINEL),
    summary="an Origin or Referer the gate cannot parse is refused with 403 and types "
            "nothing, rather than raising into a 500",
    run=run,
)
