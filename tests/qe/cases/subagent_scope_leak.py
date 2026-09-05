"""An unticketed recall is served the parent session's scope, whoever actually asked.

Issue #165. `SCOPE` (`harness/mcp_server.py:67`) is resolved once at process start from
`resolve_pin()`, and every unticketed call is served it:

    def _granted_scope(g, ticket: str) -> tuple[str, list[str]] | str:
        if not ticket:
            return SCOPE, knowledge_scopes()      # mcp_server.py:117-118

A subagent shares its parent's MCP process (measured 2026-07-28, cited in `sync.py:424`
and in this issue), so a `thalamus-qe` subagent's own `memory_recall` call reaches this
same function, in this same process, with this same `SCOPE`. The ticket is the only
per-call signal `_granted_scope` reads at all — its signature is `(g, ticket)`, and
none of the twelve `@mcp.tool` functions in `mcp_server.py` accept anything that names
the caller (no `agent_id`, `agent_type`, or session field anywhere on the surface a
model can call). So the function is not merely biased toward the parent's scope for a
subagent's call — it has no parameter through which a subagent's call could be shaped
any differently from the main loop's own. "A subagent's unticketed call" and "the main
loop's own unticketed call" are the identical function invocation.

The check drives `_granted_scope` directly, three ways:

1. **Structural** — `inspect.signature` on the live function has exactly `(g, ticket)`.
   No identity parameter exists to read, so nothing downstream of this function could
   ever recover which agent actually asked.
2. **Behavioural, unticketed** — call it twice with `ticket=""`, once standing for the
   main loop's own call and once for a `thalamus-qe` subagent's. Nothing distinguishes
   the two calls (there is no parameter to distinguish them with), so both return the
   same value: `SCOPE`. For the main-loop call this is correct — that IS the CONTROL
   this issue's own text asks for, a genuinely parent-scoped call correctly served the
   parent's scope. For the subagent call it is the defect: an unticketed recall from a
   `thalamus-qe` persona is served under `main`, indistinguishably from the session
   that spawned it.
3. **Behavioural, ticketed** — call it a third time with a real (stubbed) ticket grant.
   This one DOES return a different scope than `SCOPE`, which is the point: the
   mechanism is not a resolver that always returns one constant no matter what it is
   given — it reads the ticket and branches on it. It simply has no equivalent signal
   for the unticketed path, which is exactly what the issue's "Adjacent" section names
   as unbuilt: "a per-call scope signal the server can trust."

`consultation.ticket_grant` is monkeypatched rather than called for real, so step 3
needs no graph — the same monkeypatch shape `mcp_tool_arg_sweep.py` uses for
`mcp_server.SCOPE`/`GRAPH_URL`, restored in `finally`. `mcp_server` is imported directly
per that case's own precedent: `record_ranker` at its import top level is idempotent
against an unchanged fingerprint and writes nothing else, and nothing in this run
opens a graph connection or writes a trace or Session.

**What would make this go green.** A fix gives the unticketed path a per-call signal —
concretely, an `agent_type` the harness could thread through (the same field the tap
already records independently, per issue #163). `_reference_fixed_granted_scope` below
is that shape: it reads an `agent_type` argument and, when it names a real expert
manifest, serves that scope instead of the process-global `SCOPE`. Run against the
identical subagent-shaped call, it returns `qe`, not `main` — the corrected fixture this
case is checked against so a red here is the defect and not a broken check.
"""

from __future__ import annotations

import inspect

from ..model import Case, FailureClass, Finding, Substrate, Tier

_EXPECTED_SIG = ("g", "ticket")


def _reference_fixed_granted_scope(
    scope: str, knowledge_scopes: list[str], agent_type: str | None, real_scopes: set[str]
) -> str:
    """The shape of a fix: read the one per-call signal a subagent's call already
    carries in the tap (`agent_type`, issue #163) and prefer it over the process
    global when it names a real expert. Not wired into `mcp_server.py` — `qe` does not
    write `src/` — this exists only so the case can show what green looks like.
    """
    if agent_type and agent_type.startswith("thalamus-"):
        candidate = agent_type[len("thalamus-"):]
        if candidate in real_scopes:
            return candidate
    return scope


def run() -> Finding | None:
    from thalamus.contract.ontology import MAIN_SCOPE  # noqa: PLC0415
    from thalamus.harness import consultation  # noqa: PLC0415
    from thalamus.harness import mcp_server  # noqa: PLC0415

    sig = tuple(inspect.signature(mcp_server._granted_scope).parameters)
    if sig != _EXPECTED_SIG:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "_granted_scope's signature changed from (g, ticket), so this case's "
                "premise — that no per-call identity parameter exists — no longer "
                "describes the code and needs re-reading before it means anything"
            ),
            witness=f"inspect.signature(_granted_scope)={sig!r}",
            site="src/thalamus/harness/mcp_server.py::_granted_scope",
        )

    original_scope = mcp_server.SCOPE
    original_grant = consultation.ticket_grant
    try:
        mcp_server.SCOPE = MAIN_SCOPE
        # Stubbed so step 3 needs no graph: a real cross-scope grant, exactly the
        # shape `ticket_grant` returns for an open Exchange (`consultation.py:203`).
        consultation.ticket_grant = lambda g, ticket: (  # noqa: ARG005
            {"tk-cross": ("qe", MAIN_SCOPE)}.get(ticket)
        )

        g = object()  # the shared connection; unused by every branch driven here

        # Same call, twice: nothing in the arguments below differs, because nothing
        # in _granted_scope's signature COULD differ between "the main loop asked"
        # and "a thalamus-qe subagent asked".
        main_loop_grant = mcp_server._granted_scope(g, "")
        subagent_grant = mcp_server._granted_scope(g, "")
        ticketed_grant = mcp_server._granted_scope(g, "tk-cross")

        if isinstance(main_loop_grant, str) or isinstance(ticketed_grant, str):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="_granted_scope returned an error string for a call this "
                        "case expects to succeed, so no conclusion about served "
                        "scope is available",
                witness=f"main_loop={main_loop_grant!r} ticketed={ticketed_grant!r}",
                site="tests/qe/cases/subagent_scope_leak.py",
            )

        main_loop_scope = main_loop_grant[0]
        subagent_scope = subagent_grant[0]
        ticketed_scope = ticketed_grant[0]

        # CONTROL: a genuinely parent-scoped call must be served the parent's scope,
        # or "the subagent was served main" cannot be told apart from "this resolver
        # always returns main". Required by the issue's own reproduction.
        if main_loop_scope != MAIN_SCOPE:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="control failed: the main loop's own unticketed call was not "
                        "served its own pin, so no conclusion about a subagent's "
                        "call is available",
                witness=f"main_loop_scope={main_loop_scope!r} expected={MAIN_SCOPE!r}",
                site="tests/qe/cases/subagent_scope_leak.py",
            )

        # CONTROL: the mechanism must be shown capable of differing from SCOPE at
        # all, or "the subagent was served the wrong scope" cannot be told apart
        # from "this resolver returns one constant no matter what".
        if ticketed_scope == MAIN_SCOPE:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="control failed: a ticketed call granting a different scope "
                        "still returned the process pin, so this resolver cannot be "
                        "shown to read any per-call signal at all",
                witness=f"ticketed_scope={ticketed_scope!r} SCOPE={MAIN_SCOPE!r}",
                site="tests/qe/cases/subagent_scope_leak.py",
            )

        # GREEN DEMONSTRATION: the corrected shape, given the same subagent-shaped
        # call plus the one signal a fix would need, does NOT collapse.
        fixed_scope = _reference_fixed_granted_scope(
            main_loop_scope, [], "thalamus-qe", {"qe", "main", "literature"}
        )
        if fixed_scope != "qe":
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the reference fixed resolver did not serve the subagent's "
                        "own scope either, so this case's green fixture is broken",
                witness=f"reference_fixed_scope={fixed_scope!r}",
                site="tests/qe/cases/subagent_scope_leak.py::_reference_fixed_granted_scope",
            )

        if subagent_scope != "qe":
            return Finding(
                failure_class=FailureClass.BOUNDARY_LEAK,
                summary=(
                    "an unticketed recall shaped exactly like a thalamus-qe "
                    "subagent's own call is served the parent session's scope: "
                    "_granted_scope has no parameter through which the two calls "
                    "could differ, so both return the process-global SCOPE"
                ),
                witness=(
                    f"SCOPE={MAIN_SCOPE!r} sig={sig!r} "
                    f"main_loop_call->scope={main_loop_scope!r} "
                    f"qe_subagent_call->scope={subagent_scope!r} "
                    f"(ticketed control->scope={ticketed_scope!r}, "
                    f"reference-fixed->scope={fixed_scope!r})"
                ),
                site="src/thalamus/harness/mcp_server.py:67,117-118",
            )
        return None
    finally:
        mcp_server.SCOPE = original_scope
        consultation.ticket_grant = original_grant


CASE = Case(
    name="subagent-unticketed-recall-served-parent-scope",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="a thalamus-qe subagent's unticketed memory_recall must not be served "
            "under the parent session's scope",
    run=run,
    issue=165,
    fixed=False,
)
