"""Graph memory schema definitions and YAML validation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Tool(str, Enum):
    CURSOR = "cursor"
    CLAUDE_CODE = "claude_code"


class ArtifactType(str, Enum):
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    MODULE = "module"
    DEPENDENCY = "dependency"
    CONFIG = "config"
    ENDPOINT = "endpoint"


class ProblemCategory(str, Enum):
    BUG = "bug"
    PERFORMANCE = "performance"
    DESIGN = "design"
    INTEGRATION = "integration"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    UNDERSTANDING = "understanding"


class Artifact(BaseModel):
    identifier: str = Field(description="Unique path or qualified name")
    type: ArtifactType
    project: Optional[str] = None
    notes: Optional[str] = None


class Decision(BaseModel):
    description: str
    rationale: str
    outcome: Optional[str] = None
    artifacts: list[str] = Field(default_factory=list, description="Artifact identifiers touched")


class Problem(BaseModel):
    description: str
    category: ProblemCategory
    artifacts: list[str] = Field(default_factory=list, description="Artifact identifiers involved")


class Solution(BaseModel):
    description: str
    approach: str
    worked: bool = True
    problem_ref: Optional[int] = Field(None, description="Index into problems list")
    artifacts: list[str] = Field(default_factory=list, description="Artifact identifiers touched")


class ThreadStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


class Thread(BaseModel):
    """An open thread of work — a continuation point, next step, or unfinished line of inquiry.

    Threads persist across sessions until resolved. They serve as entrypoints into
    the session subgraph and operationalize the memory trace.
    """

    id: str = Field(description="Stable slug identifier (e.g. 'build-linking-workflow')")
    title: str = Field(description="Short actionable title")
    description: str = Field(description="What needs to happen, why it matters")
    status: ThreadStatus = ThreadStatus.OPEN
    artifacts: list[str] = Field(default_factory=list, description="Artifact identifiers involved")
    blocks: list[str] = Field(default_factory=list, description="Thread IDs this blocks")
    blocked_by: list[str] = Field(default_factory=list, description="Thread IDs blocking this")


class ThreadRef(BaseModel):
    """Reference to an existing thread being continued or resolved in this session."""

    id: str = Field(description="Thread ID being referenced")
    status: ThreadStatus = Field(description="New status after this session's work")
    notes: Optional[str] = Field(None, description="What progress was made")


class SessionGraph(BaseModel):
    """Schema for a single session's extracted graph. This is what the extraction skill outputs."""

    session_id: str = Field(description="Unique session/conversation ID")
    timestamp: datetime = Field(default_factory=datetime.now)
    tool: Tool
    project: Optional[str] = Field(None, description="Primary project/repo if identifiable")
    summary: str = Field(description="1-3 sentence summary of the session")

    artifacts: list[Artifact] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    problems: list[Problem] = Field(default_factory=list)
    solutions: list[Solution] = Field(default_factory=list)
    threads: list[Thread] = Field(default_factory=list, description="New threads opened in this session")
    thread_refs: list[ThreadRef] = Field(default_factory=list, description="Existing threads continued/resolved")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "abc123-def456",
                "timestamp": "2025-11-15T14:30:00",
                "tool": "cursor",
                "project": "thalamus",
                "summary": "Designed and scaffolded graph-based memory system for agentic tools.",
                "artifacts": [
                    {"identifier": "src/thalamus/schema.py", "type": "file", "project": "thalamus"},
                    {"identifier": "gremlinpython", "type": "dependency"},
                ],
                "decisions": [
                    {
                        "description": "Use TinkerGraph for storage",
                        "rationale": "Already have infra, real traversal semantics",
                        "outcome": "Proceeding with local Docker setup",
                        "artifacts": ["docker-compose.yml"],
                    }
                ],
                "problems": [],
                "solutions": [],
                "threads": [
                    {
                        "id": "build-linking-workflow",
                        "title": "Build cluster/summarization workflow",
                        "description": "Once 5-10 sessions accumulate, group related subgraphs behind summary nodes",
                        "status": "open",
                        "artifacts": ["src/thalamus/writer.py"],
                    }
                ],
                "thread_refs": [],
            }
        }
