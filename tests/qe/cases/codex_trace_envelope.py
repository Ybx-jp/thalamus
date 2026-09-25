"""A thalamus MCP call made from codex must land as a Trace, like the same call from Claude.

The trace tap records `tool_response` as each harness hands it over. Claude Code hands
over `[{"type": "text", "text": …}]`, which `eval/traces._parse_line` joins into the
rendered text. codex-cli 0.154.0 hands over the MCP result object —
`{"content": [{"type": "text", "text": …}], "structuredContent": {"result": …},
"isError": false, "_meta": …}`. That dict is JSON-dumped, and the only envelope the
parser then unwraps is a top-level `{"result": …}`. The rendered text stays buried in
JSON, so a miss is not recognised as a miss and a response with no backticked vertex id
reads as a pre-node-level `legacy` trace. `eval sync` skips it. No codex recall ever
becomes a Trace or a `QUERIES` edge.

Found by the live tier (`tests/qe/live/`, config `codex-luna`): a codex session called
`mcp__thalamus__memory_recall`, the tap recorded it with the right session id and scope,
the Session distilled, and eval sync reported "2 legacy traces skipped (pre-node-level
rendering)" and landed 0. A Claude session calling the same tool in the same kind of
cell landed its Trace.

The property: the codex-shaped record of a miss parses as a miss, not as legacy. The
record is the live one.

**Control.** The same text in Claude Code's shape must parse as a miss. Otherwise a
changed miss pattern would make this case look like the defect.

**Shown capable of going red.** Red on the tree as it stands. Unwrapping
`content[].text` (or `structuredContent.result`) from a dict response turns it green.
"""

from __future__ import annotations

import json

from ..model import Case, FailureClass, Finding, Tier

_TEXT = "No matching memories found."
_BASE = {"ts": "2026-09-25T09:29:28Z", "session_id": "01a0d7e5-ddac-7751-b538-8733da7cf9f4",
         "scope": "live-codex", "cwd": "/work/project",
         "tool_name": "mcp__thalamus__memory_recall",
         "tool_input": {"query": "live tier probe"}, "agent_id": "", "agent_type": ""}
_CODEX = {"content": [{"type": "text", "text": _TEXT}],
          "structuredContent": {"result": _TEXT}, "isError": False,
          "_meta": {"fastmcp": {"wrap_result": True}}}
_CLAUDE = [{"type": "text", "text": _TEXT}]


def _parse(response):
    from thalamus.eval.traces import _parse_line

    return _parse_line(json.dumps({**_BASE, "tool_response": response}))


def run() -> Finding | None:
    control = _parse(_CLAUDE)
    if control is None or not control.is_miss():
        return Finding(
            FailureClass.COLLAPSED_SENTINEL,
            "the Claude-shaped miss did not parse as a miss, so a codex-shaped one "
            "failing to would prove nothing",
            witness=repr(control),
            site="tests/qe/cases/codex_trace_envelope.py")
    event = _parse(_CODEX)
    if event is not None and event.is_miss() and not event.is_legacy():
        return None
    return Finding(
        FailureClass.INVARIANT_FALSIFIED,
        "a thalamus MCP miss recorded from codex parses as a legacy trace, so eval sync "
        "skips it and no codex recall ever lands as a Trace",
        witness=(f"codex shape -> miss={getattr(event, 'is_miss', lambda: None)()} "
                 f"legacy={getattr(event, 'is_legacy', lambda: None)()}; "
                 f"claude shape -> miss=True"),
        site="src/thalamus/eval/traces.py (_parse_line: dict tool_response)")


CASE = Case(
    name="codex-trace-envelope-parses",
    tier=Tier.FAST,
    substrate=(),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a thalamus MCP call recorded from codex must parse like the same call from Claude",
    run=run,
    issue=306,
)
