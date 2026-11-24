"""Hypothesis, bounded and turned into a witness, for the console's property arm.

Not a case. The `console_api_*` cases all share one shape: a generated input is driven
at a REAL console (`_console_rig`), a stated invariant is checked on the reply, and the
suite needs *the shrunk counterexample and the observed reply* as a `Finding.witness` —
not a pytest traceback. `hunt()` is the one place that conversion happens.

**What it does that a bare `@given` does not**

- *Deterministic and bounded.* `derandomize=True`, no example database, no deadline,
  every health check suppressed (a server round trip is slower than the health checks
  assume, and a suppressed check is not a silent pass — the property still runs
  `max_examples` times), `report_multiple_bugs=False`.
- *One counterexample per distinct defect, not one per run.* A property that fails on
  the first crash shape reports that shape and hides every other one. `hunt()` runs the
  property, takes the shrunk failure, adds its *signature* to an exclusion set, and runs
  again — so the report names each distinct way the surface breaks, each at its minimal
  input. The signature is chosen by the case (route + exception type, say); two inputs
  with the same signature are one defect.
- *A shrink budget.* Shrinking re-drives the server for every candidate. Once the first
  violation has been found, the check stops *reporting* after `shrink_budget_s`, which
  makes every further candidate look passing and lets the shrinker finish; the failure
  Hypothesis then cannot replay is recovered from the last violation the check recorded,
  which is the smallest one it saw. That recovery is the only place a `Flaky*` error is
  caught, and it is caught only when a violation was recorded — a Flaky with nothing
  recorded is a real error and propagates (MALFORMED), never a pass.
- *No internal error becomes a pass.* Anything that is not the case's own violation
  propagates.
"""

from __future__ import annotations

import http.client
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hypothesis import HealthCheck, Phase, given, settings
from hypothesis import errors as hyp_errors


class _Violation(Exception):
    """Raised inside the property to make Hypothesis treat the example as failing."""


@dataclass
class Hit:
    signature: Any
    example: Any
    detail: str


def hunt(strategy, check: Callable[[Any], tuple[Any, str] | None], *, max_examples: int,
         rounds: int = 5, budget_s: float = 35.0,
         shrink_budget_s: float = 5.0) -> tuple[list[Hit], bool]:
    """Distinct shrunk counterexamples to `check`, at most `rounds` of them.

    `check(example)` returns None when the invariant holds, or `(signature, detail)`.
    Returns `(hits, truncated)`: `truncated` is True when the loop stopped on its round or
    time budget rather than on a clean pass, i.e. more distinct defects may remain.
    """
    import warnings  # noqa: PLC0415

    known: set = set()
    hits: list[Hit] = []
    started = time.monotonic()
    truncated = True
    for _ in range(rounds):
        remaining = budget_s - (time.monotonic() - started)
        if remaining <= 2:
            break
        last: dict[str, Hit] = {}
        first_seen: list[float] = []
        cut: list[bool] = []

        @settings(derandomize=True, database=None, max_examples=max_examples,
                  deadline=None, suppress_health_check=list(HealthCheck),
                  report_multiple_bugs=False, print_blob=False,
                  phases=(Phase.generate, Phase.shrink))
        @given(strategy)
        def prop(example):
            now = time.monotonic()
            if first_seen and now - first_seen[0] > shrink_budget_s:
                return  # shrink budget spent: let the shrinker finish on the best so far
            if now - started > budget_s:
                cut.append(True)
                return
            verdict = check(example)
            if verdict is None:
                return
            sig, detail = verdict
            if sig in known:
                return
            if not first_seen:
                first_seen.append(now)
            last["hit"] = Hit(sig, example, detail)
            raise _Violation(detail)

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", hyp_errors.HypothesisWarning)
                prop()
        except _Violation:
            pass
        except hyp_errors.Flaky:
            if "hit" not in last:
                raise
        else:
            truncated = bool(cut)  # clean pass, unless the time budget cut it short
            break
        hit = last["hit"]
        hits.append(hit)
        known.add(hit.signature)
    return hits, truncated


# ---- a tiny HTTP client that never raises -------------------------------------------

@dataclass
class Resp:
    status: int | None
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    error: str = ""

    def obj(self):
        try:
            return json.loads(self.body)
        except ValueError:
            return None


def http_call(port: int, method: str, path: str, body: bytes | None = None,
              headers: dict[str, str] | None = None, timeout: float = 10.0) -> Resp:
    """One request on a fresh connection. A dropped connection, a reset or a timeout is
    a `Resp` with `status=None` and `error` naming it — never an exception."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body, headers or {})
        r = conn.getresponse()
        return Resp(r.status, r.read(), dict(r.getheaders()))
    except (http.client.HTTPException, OSError) as exc:
        return Resp(None, error=f"{type(exc).__name__}: {exc}")
    finally:
        conn.close()


def post_raw(port: int, path: str, raw: bytes, headers: dict[str, str] | None = None,
             timeout: float = 10.0) -> Resp:
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    return http_call(port, "POST", path, raw, h, timeout)


# `_answered` formats a caught crash as "<ExceptionType>: <message>".
_CRASH_RE = re.compile(r"^[A-Za-z_][\w.]*(Error|Exception|Exit|Interrupt|Overflow)\b:?")


def crash_type(resp: Resp) -> str | None:
    """A normalised key for the crash when this reply is `_answered` catching one.

    `"<ExceptionType>: <message>"` with quoted spans and digit runs collapsed, so two
    inputs that die on the same line share a key and two that die for different reasons
    (`int('--5')` vs the 4300-digit limit, both `ValueError`) do not.
    """
    if resp.status != 500:
        return None
    obj = resp.obj()
    if isinstance(obj, dict) and isinstance(obj.get("error"), str):
        if _CRASH_RE.match(obj["error"]):
            text = re.sub(r"'[^']*'", "''", obj["error"])
            return re.sub(r"\d+", "N", text)[:70]
    return None


def reply_shape_problem(resp: Resp) -> str | None:
    """Why this reply breaks the console's own answer contract, or None.

    A reply must arrive. An error status carries a JSON object with a string `error`;
    the one other shape the console uses for a route-level failure is
    `{"ok": false, "output": "..."}` (spawn, shell, roster), which is accepted as well.
    """
    if resp.status is None:
        return f"no response ({resp.error})"
    if resp.status < 400:
        return None
    obj = resp.obj()
    if isinstance(obj, dict):
        if isinstance(obj.get("error"), str):
            return None
        if obj.get("ok") is False and isinstance(obj.get("output"), str):
            return None
    return f"{resp.status} reply is not a JSON object with a string `error`: {resp.body[:120]!r}"


def short(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= limit else f"{text[:limit]}…(len={len(text)})"
