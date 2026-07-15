"""Stage 2 of the bootstrap: model-extracted Claims and Threads.

Stage 1 (transcripts.py) recovers everything a transcript records exactly — which files
were touched, when, by which tool calls. This module handles the half that genuinely
needs judgement: decisions, problems, solutions, and open threads.

Three design commitments, all inherited from docs/10:

1. **Extraction reads the archive, not ~/.claude.** The digest is rendered from the
   retained, content-addressed bytes — the same Source vertex the session's DERIVED_FROM
   edge points at. Claude Code rotates its own transcripts; the archive does not.

2. **Extraction is disposable.** Claims are content-addressed and the transcript is
   retained, so a re-run with a better model or prompt converges or supersedes — it never
   migrates. Nothing here is precious.

3. **The deterministic layer wins on facts.** The model's output is merged INTO the
   stage-1 graph: session identity, sources, and anchored touches come from the record;
   the model contributes only what cannot be recorded — judgement.

The model is invoked through `claude -p` (headless Claude Code), which rides whatever
authentication the operator's own sessions use. No API key handling here.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass

import yaml

from thalamus.substrate.schema import SessionGraph

DEFAULT_MODEL = "sonnet"

# Character budgets for the rendered digest. ~4 chars/token, so 240k chars ≈ 60k tokens —
# comfortably inside context while leaving room for instructions and output.
_DIGEST_BUDGET = 240_000
_TEXT_CAP = 2_000
_TOOL_RESULT_CAP = 400
_COMMAND_CAP = 300


# ---------------------------------------------------------------------------
# Digest rendering — archived JSONL -> something a model can actually read
# ---------------------------------------------------------------------------


def render_digest(payload: bytes, *, budget: int = _DIGEST_BUDGET) -> str:
    """Render archived transcript bytes into a compact, readable exchange log.

    Keeps user prompts, assistant prose, tool calls (name + salient input), and heavily
    truncated tool results. Drops sidechains, meta records, and system-injected noise —
    the extractor needs the *conversation*, not the plumbing.

    If the result exceeds the budget, the middle is elided rather than the tail: openings
    state intent and endings state outcomes, and both matter more than the grind between.
    """
    lines: list[str] = []
    for record in _records(payload):
        if record.get("isSidechain") or record.get("isMeta"):
            continue
        record_type = record.get("type")
        content = (record.get("message") or {}).get("content")

        if record_type == "user":
            if isinstance(content, str):
                text = content.strip()
                if text and not text.startswith("<"):
                    lines.append(f"USER: {_clip(text, _TEXT_CAP)}")
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        text = _tool_result_text(block)
                        if text:
                            lines.append(f"  result: {_clip(text, _TOOL_RESULT_CAP)}")
        elif record_type == "assistant":
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text", "").strip():
                    lines.append(f"ASSISTANT: {_clip(block['text'].strip(), _TEXT_CAP)}")
                elif block.get("type") == "tool_use":
                    lines.append(f"  tool: {_tool_use_line(block)}")

    digest = "\n".join(lines)
    if len(digest) <= budget:
        return digest
    return _elide_middle(lines, budget)


def _tool_use_line(block: dict) -> str:
    name = block.get("name", "?")
    tool_input = block.get("input") or {}
    for key in ("file_path", "notebook_path", "path", "pattern", "url"):
        if tool_input.get(key):
            return f"{name} {tool_input[key]}"
    if tool_input.get("command"):
        return f"{name} $ {_clip(str(tool_input['command']), _COMMAND_CAP)}"
    if tool_input.get("description"):
        return f"{name} — {_clip(str(tool_input['description']), _COMMAND_CAP)}"
    rendered = json.dumps(tool_input, default=str)
    return f"{name} {_clip(rendered, _COMMAND_CAP)}"


def _tool_result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        ]
        return " ".join(p.strip() for p in parts if p.strip())
    return ""


def _clip(text: str, cap: int) -> str:
    text = " ".join(text.split())
    if len(text) <= cap:
        return text
    return text[:cap] + " …[truncated]"


def _elide_middle(lines: list[str], budget: int) -> str:
    """Keep the head and tail of the conversation; elide the middle."""
    head_budget = budget // 2
    tail_budget = budget - head_budget

    head: list[str] = []
    used = 0
    head_end = 0
    for index, line in enumerate(lines):
        if used + len(line) > head_budget:
            head_end = index
            break
        head.append(line)
        used += len(line) + 1

    tail: list[str] = []
    used = 0
    tail_start = len(lines)
    for index in range(len(lines) - 1, head_end - 1, -1):
        line = lines[index]
        if used + len(line) > tail_budget:
            tail_start = index + 1
            break
        tail.append(line)
        used += len(line) + 1
    tail.reverse()

    elided = tail_start - head_end
    if elided <= 0:
        return "\n".join(head + tail)
    marker = f"\n[... {elided} messages elided for length ...]\n"
    return "\n".join(head) + marker + "\n".join(tail)


def _records(payload: bytes):
    for line in payload.decode(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


# ---------------------------------------------------------------------------
# The extraction prompt — the batch adaptation of skills/extract-session
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are extracting graph memory from the transcript of a PAST coding session. The \
deterministic facts (which files were edited, when, by which tool calls) are already \
recorded exactly — do NOT re-derive them. Your job is judgement: what was decided and \
why, what went wrong, how it was fixed, and what was left open.

Output ONLY a fenced YAML block conforming to the schema below. Be terse but precise — \
1-3 sentences per description. Capture what a future agent would need to quickly \
understand what happened and why.

### Rules

1. **summary** — 1-3 sentences: the goal and what was achieved.
2. **decisions** — choices made WITH rationale. A decision without a rationale is not \
worth recording.
3. **problems** — what blocked progress, confused, or required debugging.
4. **solutions** — how problems were resolved; link via problem_ref (0-indexed into \
problems).
5. **threads** — work left open, next steps, follow-ups. Use stable lowercase-hyphenated \
ids. Threads are the primary entrypoint for future agents.
6. **thread_refs** — if this session continued or resolved one of the EXISTING OPEN \
THREADS listed below, reference it by its exact id with the new status. Prefer \
resolving an existing thread over spawning a duplicate.
7. **artifacts** — only list artifacts you reference from a decision/problem/solution/\
thread. Every artifact you list MUST appear in at least one such reference, or it will \
be rejected as an orphan. Use exact file paths as they appear in the transcript.
8. Claims are content-addressed on (kind, description): identical descriptions converge \
on one node — that is how "this keeps coming up" becomes a graph fact. If this session \
re-asserts one of the KNOWN CLAIMS listed below, copy its description EXACTLY and put \
what is new in the other fields (rationale, outcome, approach). Only word a claim \
differently when the assertion itself is genuinely different.
9. Do NOT emit session_id, timestamp, tool, project, scope, sources, or touched — those \
are stamped from the record.

### Schema

```yaml
summary: "<1-3 sentence summary>"
artifacts:
  - identifier: "<exact file path or qualified name>"
    type: "file|class|function|module|dependency|config|endpoint"
decisions:
  - description: "<what was decided>"
    rationale: "<why>"
    outcome: "<what resulted, if known>"
    artifacts: ["<identifiers>"]
problems:
  - description: "<what went wrong>"
    category: "bug|performance|design|integration|configuration|dependency|understanding"
    artifacts: ["<identifiers>"]
solutions:
  - description: "<what fixed it>"
    approach: "<how>"
    worked: true
    problem_ref: 0
    artifacts: ["<identifiers>"]
threads:
  - id: "<stable-slug>"
    title: "<short actionable title>"
    description: "<what needs to happen and why>"
    status: "open"
    artifacts: ["<identifiers>"]
thread_refs:
  - id: "<existing thread id>"
    status: "in_progress|resolved|abandoned"
    notes: "<progress made>"
```

### Existing open threads in this project
{open_threads}

### Known claims in this project (re-assert by copying the description exactly)
{known_claims}

### Session metadata
Project: {project}
Session title: {title}

### Transcript digest
{digest}
"""


def build_prompt(
    digest: str,
    *,
    project: str,
    title: str,
    open_threads: list[dict] | None = None,
    known_claims: list[dict] | None = None,
) -> str:
    if open_threads:
        rendered = "\n".join(
            f"- {t['id']} [{t['status']}]: {t['title']}" for t in open_threads
        )
    else:
        rendered = "(none)"
    # The convergence feed (docs/10): the same mechanism as open threads, pointed at
    # claims. The model can only converge on wording it can see.
    if known_claims:
        rendered_claims = "\n".join(
            f"- [{c['kind']}] {c['description']}" for c in known_claims
        )
    else:
        rendered_claims = "(none)"
    return _PROMPT_TEMPLATE.format(
        open_threads=rendered,
        known_claims=rendered_claims,
        project=project,
        title=title,
        digest=digest,
    )


# ---------------------------------------------------------------------------
# Model invocation — claude -p, headless
# ---------------------------------------------------------------------------


@dataclass
class ExtractionRun:
    text: str
    cost_usd: float = 0.0
    duration_ms: int = 0


class ExtractionError(RuntimeError):
    pass


def run_extraction(
    prompt: str, *, model: str = DEFAULT_MODEL, timeout: int = 900
) -> ExtractionRun:
    """Run the extraction prompt through headless Claude Code.

    The subprocess runs in an empty temp directory: the digest is already in the prompt,
    so the model has no reason to touch a filesystem — and now it couldn't find anything
    interesting if it tried.
    """
    with tempfile.TemporaryDirectory(prefix="thalamus-extract-") as workdir:
        try:
            proc = subprocess.run(
                ["claude", "-p", "--model", model, "--output-format", "json"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
            )
        except FileNotFoundError as exc:
            raise ExtractionError("`claude` CLI not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise ExtractionError(f"extraction timed out after {timeout}s") from exc

    if proc.returncode != 0:
        stderr = proc.stderr.strip()[:500]
        raise ExtractionError(f"claude -p exited {proc.returncode}: {stderr}")

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"unparseable claude -p output: {proc.stdout[:200]}") from exc

    if envelope.get("is_error"):
        raise ExtractionError(f"claude -p reported an error: {envelope.get('result', '')[:300]}")

    return ExtractionRun(
        text=envelope.get("result", ""),
        cost_usd=float(envelope.get("total_cost_usd") or 0.0),
        duration_ms=int(envelope.get("duration_ms") or 0),
    )


# ---------------------------------------------------------------------------
# Parsing and merging
# ---------------------------------------------------------------------------

_YAML_FENCE = re.compile(r"```ya?ml\s*\n(.*?)```", re.DOTALL)


def parse_extraction(text: str) -> dict:
    """Pull the YAML block out of the model's response."""
    match = _YAML_FENCE.search(text)
    raw = match.group(1) if match else text
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ExtractionError(f"extraction is not a mapping: {str(data)[:200]}")
    return data


def merge_extraction(base: SessionGraph, data: dict) -> SessionGraph:
    """Merge model judgement into the deterministic stage-1 graph.

    Identity, provenance, sources, and anchored touches come from the record; the model
    contributes summary, claims, and threads. Fields the model was told not to emit are
    overridden even if it emitted them anyway.
    """
    extracted = SessionGraph(
        **{
            **data,
            "session_id": base.session_id,
            "timestamp": base.timestamp,
            "tool": base.tool,
            "scope": base.scope,
            "project": base.project,
            "summary": data.get("summary") or base.summary,
            "sources": [],
            "touched": [],
        }
    )

    artifacts = {artifact.identifier: artifact for artifact in base.artifacts}
    for artifact in extracted.artifacts:
        artifacts.setdefault(artifact.identifier, artifact)

    return base.model_copy(
        update={
            "summary": extracted.summary,
            "artifacts": list(artifacts.values()),
            "decisions": extracted.decisions,
            "problems": extracted.problems,
            "solutions": extracted.solutions,
            "threads": extracted.threads,
            "thread_refs": extracted.thread_refs,
        }
    )
