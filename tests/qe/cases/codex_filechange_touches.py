"""A file a codex session writes must reach the session's touched files.

codex-cli 0.148.0 moved its events under one `item_completed` envelope, and
`harness/codex_transcripts.py` reads that grammar for `UserMessage`, `AgentMessage`,
`CommandExecution`, `Reasoning` and `Extension`. By 0.154.0 a patch no longer writes a
`patch_apply_end` event at all: the structured record of a file write is an
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
reports the changed path in `touched`. The row is the live one, with the path made
generic.

**Control.** The same `changes` map in the older grammar's `patch_apply_end` event must
reach `touched` — otherwise a parse that read nothing at all (a moved file, a changed
signature) would make this case look like the defect.

**Shown capable of going red.** Red on the tree as it stands; handling `FileChange` the
way `patch_apply_end` is handled (`_record_touches` on the item) turns it green.
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
    got = _touched([_meta(), _filechange()])
    if _PATH in got:
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
)
