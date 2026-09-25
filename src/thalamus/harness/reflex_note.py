"""The agentic plan's note — checked before it may be delivered, and delivered as an arm.

Every other line the reflex delivers is quoted: a digest line is built from a row the
graph holds, and the pointer file renders records through the reader's own formatters.
The note is the exception, a few sentences the local model wrote about what the kept
records establish, and it is held to what makes a model-written summary checkable
rather than trusted (ALCE's citation discipline, docs/14 §5):

- at most `NOTE_CHAR_CAP` characters;
- every sentence cites at least one handle, `[R4.2]`;
- every cited handle is one the digest serves, so the agent can open what the note
  rests on;
- nothing in it addresses the reader as an instruction (`reflex.imperative_voice`).

A note that fails any of these is not delivered and the records go out without it; the
failure is recorded by name. Whether each sentence is entailed by what it cites is not
checked here; it is measured on a sample.

A note that passes is an arm of its own. Whether a digest carries it is assigned in
balanced blocks within the session — one `shown`, one `withheld`, in an order drawn from
the session id and the block's index — over the same served records, so the note's
effect on use is read apart from which records the plan chose. A withheld note is kept
in the trace for the analysis and never reaches the agent.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from thalamus.harness.reflex import imperative_voice
from thalamus.harness.reflex_queue import _append_line

NOTE_CHAR_CAP = 500

SHOWN = "shown"
WITHHELD = "withheld"
NOTE_ARMS = (SHOWN, WITHHELD)

# A cited handle: `R4.2`, bracketed or not.
HANDLE_RE = re.compile(r"\bR\d+\.\d+\b")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class NoteCheck:
    # valid | absent | too_long | uncited_sentence | unknown_handle | imperative
    status: str
    cited: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.status == "valid"


def check_note(note: str, served: set[str]) -> NoteCheck:
    """Whether `note` may be delivered beside a digest serving the handles in `served`."""
    note = note.strip()
    if not note:
        return NoteCheck("absent")
    if len(note) > NOTE_CHAR_CAP:
        return NoteCheck("too_long")
    cited = list(dict.fromkeys(HANDLE_RE.findall(note)))
    sentences = [s for s in _SENTENCE_RE.split(note) if s.strip()]
    if any(not HANDLE_RE.search(sentence) for sentence in sentences):
        return NoteCheck("uncited_sentence", cited)
    if any(handle not in served for handle in cited):
        return NoteCheck("unknown_handle", cited)
    if imperative_voice(note):
        return NoteCheck("imperative", cited)
    return NoteCheck("valid", cited)


def _arms_path(root: Path, session_id: str) -> Path:
    return root / "note_arms" / f"{session_id}.jsonl"


def assign_note_arm(root: Path, session_id: str, firing_id: str) -> str:
    """The next slot of this session's note blocks, recorded before it is returned.

    Only notes that passed `check_note` are assigned, so the count is of valid notes
    and each block splits them evenly. The worker runs one job at a time under its
    global lock, so two assignments never read the same count.
    """
    path = _arms_path(root, session_id)
    assigned = 0
    if path.is_file():
        with path.open(errors="ignore") as handle:
            for line in handle:
                try:
                    if json.loads(line).get("arm") in NOTE_ARMS:
                        assigned += 1
                except (json.JSONDecodeError, AttributeError):
                    continue
    block, slot = divmod(assigned, len(NOTE_ARMS))
    arm = random.Random(f"{session_id}:note:{block}").sample(NOTE_ARMS, len(NOTE_ARMS))[slot]
    _append_line(path, {"firing_id": firing_id, "arm": arm})
    return arm
