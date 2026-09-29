"""A file a codex session writes must reach the session's touched files.

codex-cli 0.148.0 moved its events under one `item_completed` envelope, and
`harness/codex_transcripts.py` reads that grammar for `UserMessage`, `AgentMessage`,
`CommandExecution`, `Reasoning` and `Extension`. In that grammar (measured in 0.148.0 and
0.154.0 rollouts) a patch writes no `patch_apply_end` event at all: the structured record of a file write is an
`item_completed` whose item is `FileChange`, carrying the same
`changes: {"<absolute path>": {"type": "add", ...}}` map. `FileChange` is not in
`_COMPLETED_ITEMS`, so it is counted as unrecognised and its paths are dropped. A codex
session that writes files distills with no `TOUCHES` edge to any of them, and
`recall_by_artifact` cannot find it from the file.

Found by the live tier (`tests/qe/live/`, config `codex-luna`): a real codex 0.154.0
session wrote `notes/codex.md` through `apply_patch`, the file landed, the rollout
carried the `FileChange` row, and the distilled Session touched 0 Artifacts while the
SessionEnd log said "5 record(s) … did not match the expected codex shape".

The property: `codex_transcripts.parse` over a rollout holding a `FileChange` item
reports the changed path in `touched`, anchored on the `call_id` of the tool call that
wrote it. The item's own `id` ("exec-<uuid>") appears in no other row of a rollout (0 of
29 recorded FileChange items), so it joins to nothing; the call is the single tool call
open (issued, output not yet seen) when the item arrives. With two calls open the owner
is ambiguous and the anchor must be empty, never either call's id. The row is the live
one, with the path made generic.

**Control.** The same `changes` map in the older grammar's `patch_apply_end` event must
reach `touched` — otherwise a parse that read nothing at all (a moved file, a changed
signature) would make this case look like the defect.

**Shown capable of going red.** Against the parent of the fix (`FileChange` absent from
`_COMPLETED_ITEMS`) the path is missing from `touched`; against the first fix, which
anchored on the item's `id`, the anchor assertion fails.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Tier

_SID = "01a0d7d6-749b-77f0-b627-8effe1031ee7"
_PATH = "/work/project/notes/codex.md"
_CHANGES = {_PATH: {"type": "add", "content": "probe\n"}}


def _meta() -> dict:
    return {"timestamp": "2026-09-25T09:12:30.000Z", "type": "session_meta",
            "payload": {"id": _SID, "session_id": _SID, "cwd": "/work/project",
                        "timestamp": "2026-09-25T09:12:30.000Z", "cli_version": "0.154.0",
                        "originator": "codex_exec", "source": "exec"}}


def _filechange() -> dict:
    # The live row from codex-cli 0.154.0, path made generic.
    return {"timestamp": "2026-09-25T09:12:41.043Z", "type": "event_msg", "payload": {
        "type": "item_completed", "thread_id": _SID,
        "turn_id": "01a0d7d6-74ee-7d21-80ba-926c53ad743d",
        "item": {"type": "FileChange", "id": "exec-9b7dd9f7-875b-40f7-b424-cb57e4bd6be9",
                 "changes": _CHANGES, "status": "completed",
                 "stdout": f"Success. Updated the following files:\nA {_PATH}\n",
                 "stderr": ""},
        "started_at_ms": 1790327561043, "completed_at_ms": 1790327561043}}


def _patch_apply_end() -> dict:
    return {"timestamp": "2026-09-25T09:12:41.043Z", "type": "event_msg", "payload": {
        "type": "patch_apply_end", "call_id": "call_probe", "success": True,
        "changes": _CHANGES}}


def _call(call_id: str = "call_probe_exec") -> dict:
    # The real shape: the exec call that wrote the patch sits directly before the
    # FileChange row, and its output directly after; only the call carries a call_id.
    return {"timestamp": "2026-09-25T09:12:40.900Z", "type": "response_item", "payload": {
        "type": "custom_tool_call", "id": f"ctc_{call_id}", "status": "completed",
        "call_id": call_id, "name": "exec", "input": "apply_patch"}}


def _touched(rows: list[dict]) -> dict:
    from thalamus.harness import codex_transcripts

    with tempfile.TemporaryDirectory(prefix="qe-codex-rollout-") as tmp:
        path = Path(tmp) / f"rollout-2026-09-25T09-12-30-{_SID}.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        facts = codex_transcripts.parse(path, session_id=_SID)
    return dict(facts.touched)


def run() -> Finding | None:
    control = _touched([_meta(), _patch_apply_end()])
    if _PATH not in control:
        return Finding(
            FailureClass.COLLAPSED_SENTINEL,
            "the older grammar's patch_apply_end did not reach touched either, so a "
            "missing FileChange path would prove nothing",
            witness=f"touched={control!r}",
            site="tests/qe/cases/codex_filechange_touches.py")
    got = _touched([_meta(), _call(), _filechange()])
    if _PATH in got:
        if "call_probe_exec" not in got[_PATH]:
            return Finding(
                FailureClass.INVARIANT_FALSIFIED,
                "a FileChange's touch is anchored on an id that joins to no row in the "
                "rollout; the call that wrote the file is the open custom_tool_call",
                witness=f"anchors={got[_PATH]!r}, call_id in rollout='call_probe_exec'",
                site="src/thalamus/harness/codex_transcripts.py (_record_completed_item "
                     "FileChange anchor)")
        ambiguous = _touched([_meta(), _call(), _call("call_probe_other"), _filechange()])
        if ambiguous.get(_PATH) != []:
            return Finding(
                FailureClass.INVARIANT_FALSIFIED,
                "with two tool calls open a FileChange is anchored on a guess instead of "
                "being left unanchored",
                witness=f"two open calls -> anchors={ambiguous.get(_PATH)!r}, expected []",
                site="src/thalamus/harness/codex_transcripts.py (_record_completed_item)")
        return None
    return Finding(
        FailureClass.INVARIANT_FALSIFIED,
        "a file codex 0.154 wrote (an item_completed FileChange) is dropped from the "
        "session's touched files, so the distilled Session TOUCHES no Artifact for it",
        witness=f"FileChange changes={list(_CHANGES)} -> touched={got!r}; "
                f"patch_apply_end control -> touched={list(control)}",
        site="src/thalamus/harness/codex_transcripts.py (_COMPLETED_ITEMS lacks FileChange)")


CASE = Case(
    name="codex-filechange-reaches-touched",
    tier=Tier.FAST,
    substrate=(),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a file a codex 0.154 session writes must reach the session's touched files",
    run=run,
    issue=302,
    fixed=True,
)
