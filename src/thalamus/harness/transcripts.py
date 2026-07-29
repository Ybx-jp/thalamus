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

# Tools whose results are external content crossing into the transcript — the ingress
# half of the transcript-mediated laundering channel (docs/05). Deliberately short and
# conservative: Read/Bash outputs are tier-1 observations of the operator's own machine
# (the docs/index Artifact argument), while these fetch from origins nobody curated.
# Bash *can* curl the web — that residual is documented in docs/05, not papered over
# with shell parsing this layer exists to avoid.
EXTERNAL_INGRESS_TOOLS = frozenset({"WebFetch", "WebSearch"})


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
    # Verbatim texts of tool results from EXTERNAL_INGRESS_TOOLS — the third-party
    # content embedded in this first-party transcript. The laundering floor (docs/05)
    # judges extracted claims against these.
    external_texts: list[str] = field(default_factory=list)

    # Which harness wrote the transcript these facts came from.
    harness: str = "claude-code"
    # Whether `external_texts` is *evidence* or merely *empty*. Claude Code embeds
    # tool results, so an empty list there means nothing was fetched. Cursor omits
    # tool outputs from transcripts entirely (harness/cursor_transcripts.py), so an
    # empty list there means we cannot know — and the mechanical half of the
    # laundering floor, the half no prompt content can lift, has nothing to run
    # against. Collapsing the two would delete that defence while appearing to
    # apply it, so the distinction is carried rather than inferred downstream.
    ingress_verifiable: bool = True
    # Count of external-ingress tool *calls* seen. Present even when their results
    # are not, so an unverifiable session can still say whether it fetched at all.
    ingress_detected: int = 0
    # Records the reader could not classify at all. A parser written against a
    # format it has never observed must not absorb surprises quietly: silent
    # tolerance turns "the vendor changed the format" into "this session had fewer
    # turns", which is the failure this project keeps rediscovering. Recognition is
    # kept complete and separate from processing, and what falls outside it is
    # counted and surfaced rather than repaired (RFC 9413's virtuous intolerance;
    # LangSec, Momot et al., IEEE SecDev 2016 — both explicitly reject Postel's law
    # outside pre-declared extension points).
    unrecognized: int = 0

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


def tool_result_text(block: dict) -> str:
    """The text of a tool_result content block, whichever shape the harness wrote."""
    content = block.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        ]
        return " ".join(p.strip() for p in parts if p.strip())
    return ""


def parse(path: Path) -> TranscriptFacts:
    """Read a transcript and recover every fact that needs no inference."""
    facts = TranscriptFacts(session_id=path.stem, path=path)
    external_tool_uses: set[str] = set()

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
            if isinstance(content, str):
                text = content
                stripped = text.lstrip()
                # A "<"-prefixed record is harness scaffolding (caveats, system
                # reminders), not the user speaking — except a slash-command
                # invocation, which is a deliberate user turn. Without this, a
                # session driven purely by slash commands (/teach lessons) has
                # zero countable turns and silently never distills (measured:
                # ef3e3d6a, 87 assistant messages, ineligible).
                is_command = stripped.startswith("<command-name>") or (
                    stripped.startswith("<") and "<command-name>" in stripped[:200]
                )
                if text and (not stripped.startswith("<") or is_command):
                    facts.user_turns += 1
                    if not facts.first_prompt:
                        facts.first_prompt = text.strip()
                continue
            # Tool results ride in user-type records. Results of external-ingress
            # tools are third-party content inside a first-party transcript —
            # collected verbatim so the laundering floor can judge claims against
            # them (docs/05).
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                if block.get("tool_use_id") not in external_tool_uses:
                    continue
                text = tool_result_text(block)
                if text:
                    facts.external_texts.append(text)
            continue

        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            facts.tool_calls += 1
            if block.get("name") in EXTERNAL_INGRESS_TOOLS and block.get("id"):
                external_tool_uses.add(block["id"])
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
