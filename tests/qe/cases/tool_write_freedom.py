"""No tool the eval loop counts as retrieval may reach a graph write.

Corpus record: `memorize-let-session-write-own-memory` (`fe5d440`). A live `memorize`
MCP tool let a session write its own memory: claims are content-addressed on
(kind, description), so a rephrased decision minted a second node instead of converging,
and threads arrived with fresh ids leaving both open in `memory_open_threads` — the
surface a new session reads first. It also left a named eval residual: a memory-on arm
could write memory through it, against the rule that no arm writes memory.

Deleting the tool fixed the instance. The residual it left is a *policy* — "the retrieval
tools happen not to write" — held in place by nobody, on a surface that grows. The record
names the structural form: enumerate the tools and assert write-freedom, so the rule
survives the next tool without anyone remembering it. `tests/test_eval.py`'s roster
invariant enumerates the memory tools and checks the roster, not what they reach.

The surface under test is the intersection of two lists the code already keeps: the
functions decorated `@mcp.tool` in the server, and `eval/traces.RETRIEVAL_TOOLS`, which
is what the eval loop scores as retrieval. Intersecting them is deliberate — a name in
the roster with no tool behind it is not a hole in the defense, and a tool nobody scores
as retrieval is allowed to write.

The control runs in the same pass, over the same walker: the MCP tools that are *not*
retrieval — `consult_request` and `consult_answer` — must be found reaching a write,
because minting an exchange record is exactly what they are for. A walker reporting the
whole surface clean is reporting on itself.

Reachability is by call name across the package, which over-approximates (two functions
sharing a name are both followed). For a case whose finding is "this reaches a write",
over-approximation is the safe direction: it can raise a question that turns out to be
answerable, and it cannot quietly miss one.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SRC = Path(__file__).resolve().parents[3] / "src" / "thalamus"
_SERVER = _SRC / "harness" / "mcp_server.py"

# Gremlin's mutation steps, plus the writer's own entry point. A traversal that reaches
# any of these is writing, whatever the function around it is called.
_MUTATIONS = frozenset(
    {"add_v", "addV", "add_e", "addE", "merge_v", "mergeV", "property", "drop",
     "write_session_graph"}
)
_WALK_LIMIT = 4000


def _index() -> dict[str, list[ast.AST]]:
    index: dict[str, list[ast.AST]] = defaultdict(list)
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                index[node.name].append(node)
    return index


def _callees(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name:
                out.add(name)
    return out


def _reaches_write(entry: str, index: dict[str, list[ast.AST]]) -> str:
    """The first call path from `entry` to a mutation step, or "" if none exists.

    The path is the witness. "This tool can write" is a claim; "consult_answer ->
    close_exchange -> property" is something a reader can check in a minute.
    """
    seen: set[str] = {entry}
    queue: list[tuple[str, list[str]]] = [(entry, [entry])]
    while queue and len(seen) < _WALK_LIMIT:
        current, path = queue.pop()
        for callee in sorted({c for node in index.get(current, []) for c in _callees(node)}):
            if callee in _MUTATIONS:
                return " -> ".join([*path, callee])
            if callee in index and callee not in seen:
                seen.add(callee)
                queue.append((callee, [*path, callee]))
    return ""


def _tool_names() -> set[str]:
    """Functions the server decorates with `@mcp.tool` — the live surface, not a list."""
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


def run() -> Finding | None:
    from thalamus.eval.traces import RETRIEVAL_TOOLS  # noqa: PLC0415

    if not _SERVER.is_file():
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the MCP server module was not found, so 'no tool writes' means "
                    "'no tool was read'",
            witness=str(_SERVER),
            site="src/thalamus/harness/mcp_server.py",
        )

    index = _index()
    tools = _tool_names()
    retrieval = sorted(tools & set(RETRIEVAL_TOOLS))
    others = sorted(tools - set(RETRIEVAL_TOOLS))

    if not retrieval:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no MCP tool matched the eval loop's retrieval roster, so this case "
                    "would clear a surface it never identified",
            witness=f"tools={sorted(tools)}; roster={sorted(RETRIEVAL_TOOLS)}",
            site="src/thalamus/eval/traces.py::RETRIEVAL_TOOLS",
        )

    # CONTROL: the same walker, on the tools that exist in order to write. If it cannot
    # find the exchange mint, it cannot be trusted to find an accidental one.
    writers = {name: path for name in others if (path := _reaches_write(name, index))}
    if not writers:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the walker found no write path from any tool, including the ones "
                    "that exist to mint exchange records — so a clean retrieval surface "
                    "is a statement about the walker",
            witness=f"non-retrieval tools checked: {others}",
            site="tests/qe/cases/tool_write_freedom.py::_reaches_write",
        )

    violations = {
        name: path for name in retrieval if (path := _reaches_write(name, index))
    }
    if not violations:
        return None

    return Finding(
        failure_class=FailureClass.BOUNDARY_LEAK,
        summary=(
            "a tool the eval loop scores as retrieval can reach a graph write, so a "
            "memory-on arm could write memory through the read surface and the rule "
            "that no arm writes memory would hold only by nobody having tried"
        ),
        witness="; ".join(f"{name}: {path}" for name, path in sorted(violations.items())),
        site="src/thalamus/harness/mcp_server.py",
    )


CASE = Case(
    name="retrieval-tools-reach-no-write",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="every MCP tool scored as retrieval must be structurally unable to write",
    run=run,
)
