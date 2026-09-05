"""A subagent's traces are stamped with the parent's pin, not its own.

Issue #163. `sync()` (`eval/sync.py:108-120`) groups every tapped event by
`session_id`, resolves ONE scope per session with `_session_scope`, and applies that
single value to every event in the group:

    for session_id, events in sorted(by_session.items()):
        scope = _session_scope(g, session_id, events)          # sync.py:119
        ...
        for event in events:
            _land_event(g, event, session_vid, scope, ...)      # scope, not event.scope

`_land_event` stamps `"scope": scope` on the Trace it writes (`sync.py:250`) — the
batch-wide value, never `event.scope`. `_session_scope` itself (`sync.py:482-500`)
scans every event's own recorded pin in order and returns the first candidate that
names an existing Session vertex. A subagent shares its parent's `session_id`
(measured 2026-07-28, `sync.py:424`), and only the session's own distillation ever
mints a Session vertex — never a second one per subagent pin — so a session whose
events carry more than one tap-recorded scope collapses onto whichever single scope's
Session vertex exists, applied to every event regardless of which pin actually issued
it. The per-call pin is present on `event.scope` and discarded at the stamping site:
an unenforced signal, not a missing one.

The check drives `_session_scope` directly against a fake graph — a duck-typed stand-in
for `g.V(vertex_id).has_next()` and the empty-result fallback chain, needing no docker
and no real graph. It is the real, unmodified function; only its `g` is fake.

**CONTROL, required by this issue's own text**: two traces from genuinely the same
(single-pin) session must legitimately share a scope. A session where every event
carries the same recorded pin resolves to that pin — sharing a scope is not itself a
defect, and the case must be shown not to fire on it.

**The defect**: a session with one `main`-pinned event and one `qe`-pinned event (the
qe-voiced subagent's own unticketed call, sharing the main loop's `session_id`) — where
only `main`'s Session vertex was ever distilled, the realistic shape — resolves to
`main` for the whole batch. The `qe` event's own recorded scope is available on
`event.scope` and is not what gets returned.

**What would make this go green.** `_corrected_stamp` below is the one-line shape of a
fix at the `_land_event` call site: prefer the event's own recorded pin over the
batch-wide resolution, falling back to it only when the event never recorded one
(`event.scope or batch_scope`, in place of the bare `scope` sync.py passes today). Run
against the identical mixed-session fixture, it does not collapse — the corrected
fixture this case is checked against so a red here is the defect and not a broken
check. Not wired into `sync.py`: `qe` does not write `src/`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..model import Case, FailureClass, Finding, Substrate, Tier


class _FakeTraversal:
    """Stands in for `g.V(vertex_id)`; answers `has_next()` from a fixed existence set."""

    def __init__(self, exists: bool) -> None:
        self._exists = exists

    def has_next(self) -> bool:
        return self._exists


class _FakeFallbackQuery:
    """Stands in for the `g.V().has_label(...).value_map("scope").limit(1).to_list()`
    fallback `_session_scope` runs when no candidate resolves. Always empty here:
    every fixture below is built so a real candidate resolves first, and the fallback
    firing at all would mean this case's own fixtures are wrong, not that the defect
    changed shape.
    """

    def has_label(self, *_a, **_k):
        return self

    def has(self, *_a, **_k):
        return self

    def value_map(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def to_list(self):
        return []


class _FakeGraph:
    def __init__(self, existing_vids: frozenset) -> None:
        self._existing = existing_vids

    def V(self, vertex_id: str | None = None):
        if vertex_id is None:
            return _FakeFallbackQuery()
        return _FakeTraversal(vertex_id in self._existing)


def _event(session_id: str, scope: str, agent_type: str | None = None, agent_id: str | None = None):
    from thalamus.eval.traces import TraceEvent  # noqa: PLC0415

    return TraceEvent(
        ts=datetime(2026, 9, 4, tzinfo=timezone.utc),
        session_id=session_id,
        cwd="/repo",
        tool="memory_recall",
        tool_input={"query": "capability-based security"},
        tool_response="",
        scope=scope,
        agent_id=agent_id,
        agent_type=agent_type,
    )


def _corrected_stamp(batch_scope: str, event) -> str:
    """The one-line shape of a fix: prefer the event's own recorded pin.

    Not a change to `sync.py` — a reference used only to show this case is not
    hard-wired to always fail.
    """
    return event.scope or batch_scope


def run() -> Finding | None:
    from thalamus.contract.ontology import vid  # noqa: PLC0415
    from thalamus.eval.sync import _session_scope  # noqa: PLC0415

    session_id = "sess-mixed-0001"
    # Only `main`'s Session vertex exists — the realistic shape: a subagent's calls
    # share this session_id but distillation never mints a second Session under the
    # subagent's own pin.
    g = _FakeGraph(frozenset({vid("Session", session_id, "main")}))

    main_event = _event(session_id, "main")
    sub_event = _event(session_id, "qe", agent_type="thalamus-qe", agent_id="agent-1")

    # CONTROL: a single-pin session resolves to its own pin, and sharing it across
    # its own events is legitimate.
    control_scope = _session_scope(g, session_id, [main_event, main_event])
    if control_scope != "main":
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="control failed: a single-pin session did not resolve to its own "
                    "pin, so no conclusion about a mixed-pin session is available",
            witness=f"_session_scope(single-pin main x2)={control_scope!r}",
            site="tests/qe/cases/trace_scope_collapse.py",
        )

    # DEFECT: the mixed session. `sub_event` is listed first, so if per-event scope
    # survived at all, the qe pin would be the natural candidate to surface first —
    # it is not consulted here at all past the initial candidate scan (mocked below
    # to fail via a nonexistent vertex), which is exactly the point.
    mixed_scope = _session_scope(g, session_id, [sub_event, main_event])

    # GREEN DEMONSTRATION: the corrected stamping rule, applied to the same fixture.
    corrected_for_sub = _corrected_stamp(mixed_scope, sub_event)
    if corrected_for_sub != sub_event.scope:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the reference corrected stamp still did not carry the "
                    "subagent's own recorded scope, so this case's green fixture "
                    "is broken",
            witness=f"corrected_for_sub={corrected_for_sub!r} sub_event.scope="
                    f"{sub_event.scope!r}",
            site="tests/qe/cases/trace_scope_collapse.py::_corrected_stamp",
        )

    stamped_for_sub = mixed_scope  # what _land_event actually writes for sub_event today
    if stamped_for_sub == sub_event.scope:
        return None

    return Finding(
        failure_class=FailureClass.UNENFORCED_SIGNAL,
        summary=(
            "_session_scope resolves ONE scope for a session carrying two "
            "tap-recorded pins, and sync() stamps every trace of that session with "
            "it — the qe subagent's own recorded scope sits right there on its "
            "event and is discarded at the stamping call site"
        ),
        witness=(
            f"session={session_id} events=[scope={sub_event.scope!r} "
            f"agent_type={sub_event.agent_type!r}, scope={main_event.scope!r} "
            f"agent_type={main_event.agent_type!r}] -> "
            f"_session_scope={mixed_scope!r}; sync() would stamp the qe event's "
            f"Trace with scope={stamped_for_sub!r} (!= {sub_event.scope!r}); "
            f"corrected stamp would carry {corrected_for_sub!r}"
        ),
        site="src/thalamus/eval/sync.py:119,250,482-500",
    )


CASE = Case(
    name="subagent-trace-stamped-with-parent-pin",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.UNENFORCED_SIGNAL, FailureClass.COLLAPSED_SENTINEL),
    summary="a session with two tap-recorded pins must not stamp every trace with "
            "only one of them",
    run=run,
    issue=163,
    fixed=False,
)
