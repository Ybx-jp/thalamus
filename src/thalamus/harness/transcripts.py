"""Claude Code transcript discovery, retention, and deterministic extraction.

Claude Code persists every session as JSONL under
`~/.claude/projects/<abs-cwd with '/' replaced by '-'>/<session-id>.jsonl`.

This module does the half of memory extraction that **needs no model at all**. Which
files a session edited, when, on which branch, with which tools, and in which messages —
that is all recorded exactly. An LLM would only be *worse* at it: it is ground truth, and
inference could only add error. What genuinely needs a model (decisions, problems,
solutions, threads — the *claims*) is left to the extraction skill.

The split matters beyond convenience. The deterministic layer gives every artifact a
real, anchored edge back to the exact tool call that touched it — so `docs/03`'s
provenance inspector works on bootstrapped data with no model in the loop, and the eval
loop gets a corpus it can trust to be free of extraction error.

One constraint worth knowing: **assistant reasoning is not persisted in plaintext.** A
thinking block on disk is an empty string plus an encrypted signature. Retained
transcripts carry user prompts, assistant prose, tool calls, and tool results — not the
private chain of thought.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from thalamus.archive import archive_bytes, scan_for_secrets
from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.substrate.schema import (
    Artifact,
    ArtifactType,
    SessionGraph,
    Source,
    SourceKind,
    Tool,
    Touch,
)

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"

# Tool inputs that name a file. Bash commands are deliberately NOT parsed for paths:
# guessing which words in a shell line are files is exactly the kind of inference this
# layer exists to avoid.
_PATH_INPUTS = ("file_path", "notebook_path")


@dataclass
class TranscriptFacts:
    """Everything recoverable from a transcript without a model."""

    session_id: str
    path: Path
    cwd: str = ""
    git_branch: str = ""
    title: str = ""
    first_prompt: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    message_count: int = 0
    user_turns: int = 0
    tool_calls: int = 0
    # artifact identifier -> message UUIDs of the tool calls that touched it
    touched: dict[str, list[str]] = field(default_factory=dict)

    @property
    def project(self) -> str:
        return Path(self.cwd).name if self.cwd else ""


def discover(projects_dir: Path | None = None) -> dict[str, list[Path]]:
    """Map project directory name -> its transcript files."""
    root = projects_dir or CLAUDE_PROJECTS
    if not root.is_dir():
        return {}
    found: dict[str, list[Path]] = {}
    for project_dir in sorted(root.iterdir()):
        if not project_dir.is_dir():
            continue
        transcripts = sorted(project_dir.glob("*.jsonl"))
        if transcripts:
            found[project_dir.name] = transcripts
    return found


def parse(path: Path) -> TranscriptFacts:
    """Read a transcript and recover every fact that needs no inference."""
    facts = TranscriptFacts(session_id=path.stem, path=path)

    for record in _records(path):
        record_type = record.get("type")

        # Claude Code writes its own session title. Free, and better than a first-line
        # heuristic — no reason to make a model regenerate what is already on disk.
        if record_type == "ai-title" and record.get("aiTitle"):
            facts.title = record["aiTitle"]
            continue

        if record.get("cwd"):
            facts.cwd = record["cwd"]
        if record.get("gitBranch"):
            facts.git_branch = record["gitBranch"]

        timestamp = _timestamp(record.get("timestamp"))
        if timestamp:
            facts.started_at = min(facts.started_at or timestamp, timestamp)
            facts.ended_at = max(facts.ended_at or timestamp, timestamp)

        if record_type not in ("user", "assistant"):
            continue
        if record.get("isSidechain") or record.get("isMeta"):
            continue  # subagent sidechains are their own episodes, not this one

        facts.message_count += 1
        content = (record.get("message") or {}).get("content")

        if record_type == "user":
            text = content if isinstance(content, str) else ""
            if text and not text.lstrip().startswith("<"):
                facts.user_turns += 1
                if not facts.first_prompt:
                    facts.first_prompt = text.strip()
            continue

        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            facts.tool_calls += 1
            tool_input = block.get("input") or {}
            for key in _PATH_INPUTS:
                identifier = tool_input.get(key)
                if not identifier:
                    continue
                anchors = facts.touched.setdefault(str(identifier), [])
                uuid = record.get("uuid")
                if uuid and uuid not in anchors:
                    anchors.append(uuid)

    return facts


def retain(path: Path, *, archive_base: Path | None = None):
    """Copy a transcript into the immutable archive. Returns (entry, secret findings).

    Thalamus owns the bytes from here on. Claude Code rotates and compacts its own
    transcripts, so a pointer into ~/.claude/projects would rot — and evidence that can
    disappear is not evidence.
    """
    payload = path.read_bytes()
    entry = archive_bytes(payload, suffix=".jsonl", base=archive_base)
    return entry, scan_for_secrets(payload)


def to_session_graph(
    facts: TranscriptFacts,
    *,
    content_hash: str,
    uri: str,
    byte_size: int,
    scope: str = MAIN_SCOPE,
) -> SessionGraph:
    """Build the deterministic half of a session's memory. No model involved.

    Produces: the Source (its own transcript), the Session, every Artifact it touched, and
    the anchored TOUCHES edges between them. Claims and Threads are left empty — those need
    judgement, and this layer refuses to guess.
    """
    identifiers = sorted(facts.touched)
    timestamp = facts.ended_at or facts.started_at or datetime.now()

    source = Source(
        content_hash=content_hash,
        kind=SourceKind.TRANSCRIPT,
        title=facts.title or f"Session {facts.session_id[:8]}",
        uri=uri,
        origin=str(facts.path),
        byte_size=byte_size,
        message_count=facts.message_count,
    )

    return SessionGraph(
        session_id=facts.session_id,
        timestamp=timestamp,
        tool=Tool.CLAUDE_CODE,
        scope=scope,
        project=facts.project or None,
        summary=_summary(facts),
        sources=[source],
        artifacts=[
            Artifact(
                identifier=identifier,
                type=ArtifactType.FILE,
                project=facts.project or None,
            )
            for identifier in identifiers
        ],
        touched=[
            Touch(identifier=identifier, anchors=facts.touched[identifier])
            for identifier in identifiers
        ],
    )


def _summary(facts: TranscriptFacts) -> str:
    """A summary we can stand behind without a model.

    Claude Code's own `ai-title` is the headline; the opening prompt supplies the intent.
    Honest and cheap. A real distillation is the extraction skill's job, and when it runs,
    it overwrites this — the transcript is retained, so re-extraction is always available.
    """
    title = facts.title or f"Session {facts.session_id[:8]}"
    if facts.first_prompt:
        opening = " ".join(facts.first_prompt.split())[:180]
        return f"{title} — opened with: {opening}"
    return title


def _records(path: Path):
    with path.open(errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
