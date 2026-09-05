"""Every `@mcp.tool` function must survive hostile arguments, called directly.

Corpus record: issue #75. `tool_write_freedom.py` walks the AST of `mcp_server.py`
and proves no *retrieval* tool reaches a mutation step, but it invokes nothing — no
case in this tree ever calls a tool, and no case ever hands one an argument it did
not expect. The 12 tools take scope, project, ticket, topic, thread, and limit
arguments from free text a model composes, with no coverage of absent, empty,
wrong-typed, oversized, or injection-shaped values.

**Generated, not enumerated by hand.** The tool list is read off the same AST walk
`tool_write_freedom._tool_names` uses — `@mcp.tool` decorated functions in
`mcp_server.py` — so a tool added later without a case here shows up as a coverage
gap the first time this runs, rather than a silent absence nobody notices (the
`_KNOWN_TOOL_COUNT` control below). The hostile values swept per parameter are
derived from each function's own `inspect.signature`, keyed only by annotation
(`str` or `int` — the only two this surface uses), so a new tool's parameters are
swept the same way without anyone writing a per-tool case.

**Deterministically hermetic.** FastMCP's `@mcp.tool` decorator returns the original
function (confirmed: `mcp_server.memory_recall` is a plain `function`, not a
wrapper), so this sweep calls the same callables the server dispatches to, with no
FastMCP transport in between — an exception here is the tool's own, not a framework
artifact. `GRAPH_URL` is pinned to a dead port for the run (`test_mcp_server.py`'s own
`TestTheGraphIsDown` precedent) rather than trusted to whatever the executing box
happens to have: ten of the twelve tools open with `g = _connect()` and every one of
those returns the connect-down diagnostic verbatim before touching a single
argument, and that fact must hold on a CI runner with no docker exactly as it holds
on a dev box with a live graph on :8182 — a case whose green/red depended on which
box ran it would be reporting on the box, not the code. `SCOPE` is likewise pinned to
`MAIN_SCOPE` so `memory_query` (the one tool that does not gate on a live connection —
`run_query` calls `validate_query` before ever touching a `Client`) is actually
exercised regardless of which scope pins the session running this suite.

**What this does not cover, and why.** Past the connect gate, `_granted_scope`,
`recall()`, and friends are where a hostile `limit` or forged `ticket` would have to
misbehave to widen scope or crash on a real graph, and none of that runs when
`GRAPH_URL` is dead by construction. Probing it needs a graph this suite controls
well enough to assert facts about, which is exactly the seam issue #60 is for; until
it lands, that half is left out rather than shipped as a case that would SKIP on
every CI run forever (no workflow here invokes `run.py --all-tiers`, so a
`Substrate.NEEDS_GRAPH` case in `cases/` — as opposed to `install/`, which
`qe-linux.yml` does drive to the graph phases — would never be exercised by CI at
all). `query_guard_evasion.py` is the sibling case for `memory_query`'s own
step-filter and scope gate.

**"Does not silently widen scope"**, concretely: `mcp_server`'s own module docstring
states no tool accepts a scope argument, scope being resolved server-side from the
pin. That is checked directly and cheaply, without a graph: no swept tool's signature
may declare a parameter literally named `scope`.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SRC = Path(__file__).resolve().parents[3] / "src" / "thalamus"
_SERVER = _SRC / "harness" / "mcp_server.py"

# From issue #75's own audit against 5ce2004: 10 read tools + 2 write tools
# (consult_request, consult_answer). A count below this is a shrunk surface; the
# check does not require exactly this number because growth is not a defect, only
# a coverage gap the sweep already handles generically.
_KNOWN_TOOL_COUNT = 12

_DEAD_GRAPH_URL = "ws://localhost:9/gremlin"

# The diagnostic every connect-gated tool returns verbatim, from
# `substrate.writer.graph_down_detail` — asserted literally, not just "no exception",
# because sameness across every hostile argument is the positive evidence that the
# argument never reached anything past the gate.
_GRAPH_DOWN_MARKER = "docker compose up -d"

# Hostile values, keyed by the only two annotations this tool surface uses. Each
# entry is (label, value) so a failure witness names which value broke it.
_HOSTILE_STR: tuple[tuple[str, object], ...] = (
    ("empty", ""),
    ("none", None),
    ("wrong-type-int", 12345),
    ("wrong-type-list", ["a", "b"]),
    ("oversized", "x" * 200_000),
    ("null-byte", "abc\x00def"),
    ("path-traversal", "../../../../etc/passwd"),
    ("format-string-attr-walk", "{0.__class__.__mro__[1].__subclasses__()}"),
    ("percent-format", "%s%s%s%s%s"),
    ("gremlin-shaped", "g.V().addV('x')"),
    ("script-tag", "<script>alert(1)</script>"),
    ("rtl-override", "abc‮ cba"),
    ("control-chars", "line1\nline2\r\x07\x1b[31m"),
)

_HOSTILE_INT: tuple[tuple[str, object], ...] = (
    ("negative", -1),
    ("zero", 0),
    ("huge", 10**9),
    ("wrong-type-str", "five"),
    ("wrong-type-float", 3.7),
    ("none", None),
)

# A benign placeholder per annotation, for holding every OTHER parameter steady
# while one is swept — never itself asserted on, just needed to make the call.
_BENIGN: dict[type, object] = {str: "benign", int: 1}


def _tool_names() -> set[str]:
    """Functions the server decorates with `@mcp.tool`.

    Same AST walk as `tool_write_freedom._tool_names` — deliberately re-read here
    rather than imported, so this case's enumeration does not depend on that one's
    module staying importable, and drifts identically if the decorator's spelling
    ever changes.
    """
    tree = ast.parse(_SERVER.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for deco in node.decorator_list:
            target = deco.func if isinstance(deco, ast.Call) else deco
            if isinstance(target, ast.Attribute) and target.attr == "tool":
                names.add(node.name)
    return names


def _looks_like_traceback(text: str) -> bool:
    markers = ("Traceback (most recent call last)", 'File "', "line ")
    return sum(m in text for m in markers) >= 2


def _hostile_values(annotation: object) -> tuple[tuple[str, object], ...]:
    return _HOSTILE_INT if annotation is int else _HOSTILE_STR


def _baseline_kwargs(sig: inspect.Signature) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    for name, param in sig.parameters.items():
        if param.default is not inspect.Parameter.empty:
            kwargs[name] = param.default
        else:
            kwargs[name] = _BENIGN.get(param.annotation, "benign")
    return kwargs


def run() -> Finding | None:  # noqa: C901
    from thalamus.contract.ontology import MAIN_SCOPE  # noqa: PLC0415
    from thalamus.harness import mcp_server  # noqa: PLC0415

    tools = sorted(_tool_names())
    if len(tools) < _KNOWN_TOOL_COUNT:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                f"enumeration found {len(tools)} `@mcp.tool` functions, fewer than "
                f"the {_KNOWN_TOOL_COUNT} known from issue #75's audit — a shrunk "
                "surface, or the decorator match no longer fires, and either way "
                "the sweep below covers less than it claims"
            ),
            witness=f"tools={tools}",
            site=str(_SERVER),
        )

    scope_leaks = [name for name in tools if "scope" in inspect.signature(
        getattr(mcp_server, name)).parameters]
    if scope_leaks:
        return Finding(
            failure_class=FailureClass.BOUNDARY_LEAK,
            summary=(
                "a tool declares a parameter literally named `scope`, against the "
                "server's own stated contract that scope is never a tool argument "
                "and is resolved server-side from the pin"
            ),
            witness=f"tools: {scope_leaks}",
            site=str(_SERVER),
        )

    original_url = mcp_server.GRAPH_URL
    original_scope = mcp_server.SCOPE
    violations: list[str] = []
    try:
        mcp_server.GRAPH_URL = _DEAD_GRAPH_URL
        mcp_server.SCOPE = MAIN_SCOPE

        for name in tools:
            fn = getattr(mcp_server, name, None)
            if not callable(fn):
                violations.append(f"{name}: enumerated but not a callable attribute")
                continue
            sig = inspect.signature(fn)
            baseline = _baseline_kwargs(sig)

            for param_name, param in sig.parameters.items():
                for label, hostile in _hostile_values(param.annotation):
                    kwargs = dict(baseline)
                    kwargs[param_name] = hostile
                    witness = f"{name}({param_name}={label})"
                    try:
                        result = fn(**kwargs)
                    except Exception as exc:  # noqa: BLE001
                        violations.append(
                            f"{witness} raised {type(exc).__name__}: {exc}"
                        )
                        continue
                    if not isinstance(result, str):
                        violations.append(
                            f"{witness} returned {type(result).__name__}, not str"
                        )
                        continue
                    if _looks_like_traceback(result):
                        violations.append(
                            f"{witness} returned what looks like a traceback: "
                            f"{result[:200]!r}"
                        )
                        continue
                    # DISCRIMINATION CONTROL for the ten connect-gated tools: with
                    # the graph dead, the diagnostic must be the SAME for every
                    # hostile argument, because the argument never reached
                    # anything that could vary it. `memory_query` is exempt — it
                    # does not gate on a connection and answers from
                    # `validate_query` or a real (if capped) query failure instead.
                    if name != "memory_query" and _GRAPH_DOWN_MARKER not in result:
                        violations.append(
                            f"{witness} returned a message that is not the "
                            f"connect-down diagnostic, though the graph is dead: "
                            f"{result[:200]!r}"
                        )
    finally:
        mcp_server.GRAPH_URL = original_url
        mcp_server.SCOPE = original_scope

    if not violations:
        return None

    return Finding(
        failure_class=FailureClass.BOUNDARY_LEAK,
        summary=(
            "a hostile argument to an MCP tool, called directly, raised, returned "
            "something other than a string, leaked a traceback, or (for the "
            "connect-gated tools) produced a message that varied though the graph "
            "was unreachable and the argument should never have been read"
        ),
        witness="; ".join(violations[:20])
        + (f" (+{len(violations) - 20} more)" if len(violations) > 20 else ""),
        site=str(_SERVER),
    )


CASE = Case(
    name="mcp-tool-argument-sweep",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.COLLAPSED_SENTINEL, FailureClass.BOUNDARY_LEAK),
    summary=(
        "every MCP tool, called directly with hostile arguments derived from its "
        "own signature, must not raise, must not return a non-string or a "
        "traceback, and must not accept a scope parameter"
    ),
    run=run,
    # memory_query(query=<non-str>) raises AttributeError from validate_query's
    # unguarded `query.strip()`. Filed rather than fixed — this scope may not write
    # src/. See issue #173.
    issue=173,
    fixed=False,
)
