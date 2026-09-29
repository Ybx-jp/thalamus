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

The property: every recorded shape of one thalamus MCP response parses to the same text,
so a miss is a miss and a hit yields the same node ids. Shapes driven: Claude's list, the
codex result object, that object JSON-encoded, the server's bare `{"result": ...}` (dict
and encoded), several text blocks, an image block mixed in, and an empty `content` list
with `structuredContent.result` set. `content` text wins over `structuredContent` when
they disagree, plain strings pass through untouched, and a text block whose text is null
must not raise out of `_parse_line` (`load_events` does not catch it, so one such line
would end `eval sync`).

**Control.** The same text in Claude Code's shape must parse as a miss / yield the ids.
Otherwise a changed miss pattern would make this case look like the defect.

**Shown capable of going red.** Against 21a385b (before the dict unwrap) the miss parses
as legacy and the case reports "codex shape -> miss=False legacy=True"; against e2c4d0c
the empty-content and null-text arms go red. Repeat by restoring
`tool_response = json.dumps(tool_response)` for a dict response in `_parse_line`.
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


_V1 = "scope:live-codex:claim:aaa1"
_V2 = "scope:live-codex:thread:bbb2"
_HIT = f"**c** `{_V1}`\nbody\n\n---\n\n**t** `{_V2}`"


def _codex(text):
    return {"content": [{"type": "text", "text": text}],
            "structuredContent": {"result": text}, "isError": False, "_meta": {}}


def _fail(message, witness):
    return Finding(FailureClass.INVARIANT_FALSIFIED, message, witness=witness,
                   site="src/thalamus/eval/traces.py (_parse_line / _render_mcp_result)")


def _hit_ids(response):
    event = _parse(response)
    return None if event is None else event.returned_node_ids()


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
    if not (event is not None and event.is_miss() and not event.is_legacy()):
        return Finding(
            FailureClass.INVARIANT_FALSIFIED,
            "a thalamus MCP miss recorded from codex parses as a legacy trace, so eval sync "
            "skips it and no codex recall ever lands as a Trace",
            witness=(f"codex shape -> miss={getattr(event, 'is_miss', lambda: None)()} "
                     f"legacy={getattr(event, 'is_legacy', lambda: None)()}; "
                     f"claude shape -> miss=True"),
            site="src/thalamus/eval/traces.py (_parse_line: dict tool_response)")

    # A hit carries the same node ids in every shape the harnesses record it in.
    want = _hit_ids([{"type": "text", "text": _HIT}])
    if want != [_V1, _V2]:
        return Finding(FailureClass.COLLAPSED_SENTINEL,
                       "the Claude-shaped hit did not yield its vertex ids",
                       witness=repr(want), site="tests/qe/cases/codex_trace_envelope.py")
    shapes = {
        "codex dict": _codex(_HIT),
        "codex dict JSON-encoded": json.dumps(_codex(_HIT)),
        "bare {result} envelope": {"result": _HIT},
        "bare {result} JSON-encoded": json.dumps({"result": _HIT}),
        "two text blocks": {"content": [{"type": "text", "text": f"`{_V1}`"},
                                        {"type": "text", "text": f"`{_V2}`"}]},
        "image block mixed in": {"content": [{"type": "image", "data": "AA=="},
                                             {"type": "text", "text": _HIT}]},
        "content empty, structuredContent.result set":
            {"content": [], "structuredContent": {"result": _HIT}},
    }
    for label, response in shapes.items():
        got = _hit_ids(response)
        if got != want:
            return _fail(f"a hit recorded as {label} does not yield the same node ids as "
                         "the Claude list shape", f"{label} -> {got!r}; claude -> {want!r}")
    for label, response in {
        "content text beats structuredContent":
            {"content": [{"type": "text", "text": _TEXT}],
             "structuredContent": {"result": _HIT}},
    }.items():
        got = _parse(response)
        if got is None or not got.is_miss():
            return _fail(f"{label}: the rendered content is what the model saw",
                         repr(got))
    only_image = _parse({"content": [{"type": "image", "data": "AA=="}],
                         "structuredContent": ["not", "a", "dict"]})
    if only_image is None or only_image.tool_response != "":
        return _fail("a result with no text and no usable structured form must render "
                     "empty", repr(only_image))
    for text in ("No matching memories found.", "plain string with `no` ids"):
        plain = _parse(text)
        if plain is None or plain.tool_response != text:
            return _fail("a plain string response changed", repr(plain))

    # Hostile: a text block whose text is null must not take the whole tap down.
    try:
        _parse({"content": [{"type": "text", "text": None}]})
    except Exception as exc:  # noqa: BLE001 - the point is that nothing escapes
        return _fail("one malformed dict tap line raises out of _parse_line, which "
                     "load_events does not catch, so eval sync dies on it",
                     f"{type(exc).__name__}: {exc}")
    return None


CASE = Case(
    name="codex-trace-envelope-parses",
    tier=Tier.FAST,
    substrate=(),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a thalamus MCP call recorded from codex must parse like the same call from Claude",
    run=run,
    issue=306,
    fixed=True,
)
