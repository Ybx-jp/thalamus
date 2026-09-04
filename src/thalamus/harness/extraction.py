"""Stage 2 of the bootstrap: model-extracted Claims and Threads.

Stage 1 (transcripts.py) recovers everything a transcript records exactly — which files
were touched, when, by which tool calls. This module handles the half that genuinely
needs judgement: decisions, problems, solutions, and open threads.

Three design commitments:

1. **Extraction reads the archive, not ~/.claude.** The digest is rendered from the
   retained, content-addressed bytes — the same Source vertex the session's DERIVED_FROM
   edge points at. Claude Code rotates its own transcripts; the archive does not.

2. **Extraction is disposable.** Claims are content-addressed and the transcript is
   retained, so a re-run with a better model or prompt converges or supersedes — it never
   migrates. Nothing here is precious.

3. **The deterministic layer wins on facts.** The model's output is merged INTO the
   stage-1 graph: session identity, sources, and anchored touches come from the record;
   the model contributes only what cannot be recorded — judgement.

The model is invoked through a headless coding-agent CLI chosen by harness
(`harness/agents.py`): `claude -p` for Claude Code sessions, Cursor's `agent -p`
for Cursor ones. Either rides whatever authentication the operator's own sessions
already use, so there is no API key handling here — and a Cursor-only machine
never needs Claude Code installed to turn its sessions into memory.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any

import yaml

# Re-exported: extraction is their main caller, and `cli.py` and the suite reach
# them through this module rather than through `agents`. The noqa markers are
# load-bearing — a lint autofix strips these and breaks those callers, not this one.
from thalamus.harness.agents import (
    AGENT_CLIS,  # noqa: F401
    CLAUDE_DEFAULT_MODEL,
    CURSOR_DEFAULT_MODEL,  # noqa: F401
    AgentCLI,  # noqa: F401
    UnknownHarness,
    cli_for,
    sandbox_env,
)
from thalamus.harness.transcripts import EXTERNAL_INGRESS_TOOLS
from thalamus.substrate.reader import (
    MIN_MATCHED_RATIO,
    MIN_MATCHED_TERMS,
    STOPWORDS,
)
from thalamus.substrate.schema import (
    Artifact,
    Claim,
    Decision,
    Problem,
    Provenance,
    SessionGraph,
    Solution,
    Thread,
    ThreadRef,
    Tier,
)

_TOKEN_RE = re.compile(r"[a-z0-9_./-]+")
_WORD_RE = re.compile(r"[a-z0-9]+")

DEFAULT_MODEL = CLAUDE_DEFAULT_MODEL

# Character budgets for the rendered digest. ~4 chars/token, so 240k chars ≈ 60k tokens —
# comfortably inside context while leaving room for instructions and output.
_DIGEST_BUDGET = 240_000
_TEXT_CAP = 2_000
_TOOL_RESULT_CAP = 400
_COMMAND_CAP = 300


# ---------------------------------------------------------------------------
# Digest rendering — archived JSONL -> something a model can actually read
# ---------------------------------------------------------------------------


def render_digest(
    payload: bytes, *, budget: int = _DIGEST_BUDGET, harness: str = "claude",
) -> str:
    """Render archived transcript bytes into a compact, readable exchange log.

    Keeps user prompts, assistant prose, tool calls (name + salient input), and heavily
    truncated tool results. Drops sidechains, meta records, and system-injected noise —
    the extractor needs the *conversation*, not the plumbing.

    Harness-tolerant where the harnesses are alike and dispatched where they are not.
    Claude Code discriminates rows with `type`, Cursor with `role` and nothing else
    (harness/cursor_transcripts.py), but the *block* vocabulary is the same in both, so
    one renderer serves them and a Cursor digest simply contains no `result:` lines —
    that format carries no tool outputs to render. Codex shares none of that vocabulary:
    its rows are `{timestamp, type, payload}` and its tool calls are JavaScript
    programs, so it gets its own renderer rather than a widened one. Widening this one
    to swallow a third grammar is how a renderer comes to produce a plausible digest of
    a format it does not understand.

    If the result exceeds the budget, the middle is elided rather than the tail: openings
    state intent and endings state outcomes, and both matter more than the grind between.
    """
    if harness == "codex":
        return _render_codex_digest(payload, budget=budget)
    lines: list[str] = []
    external_tool_uses: set[str] = set()
    for record in _records(payload):
        if record.get("isSidechain") or record.get("isMeta"):
            continue
        record_type = record.get("type") or record.get("role")
        content = (record.get("message") or {}).get("content")
        tag = _anchor_tag(record)

        if record_type == "user":
            if isinstance(content, str):
                text = content.strip()
                if text and not text.startswith("<"):
                    lines.append(f"{tag}USER: {_clip(text, _TEXT_CAP)}")
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    # Cursor writes user prompts as text blocks rather than a bare
                    # string; without this a Cursor digest holds no user turns at all.
                    if block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text and not text.startswith("<"):
                            lines.append(f"{tag}USER: {_clip(text, _TEXT_CAP)}")
                    elif block.get("type") == "tool_result":
                        text = _tool_result_text(block)
                        if text:
                            # External-ingress results are labelled so the extractor
                            # can apply the external-origin rule; the label
                            # is data about the segment, decided here, not by the model.
                            label = (
                                "result [EXTERNAL CONTENT]"
                                if block.get("tool_use_id") in external_tool_uses
                                else "result"
                            )
                            lines.append(f"{tag}  {label}: {_clip(text, _TOOL_RESULT_CAP)}")
        elif record_type == "assistant":
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text", "").strip():
                    lines.append(
                        f"{tag}ASSISTANT: {_clip(block['text'].strip(), _TEXT_CAP)}"
                    )
                elif block.get("type") == "tool_use":
                    if block.get("name") in EXTERNAL_INGRESS_TOOLS and block.get("id"):
                        external_tool_uses.add(block["id"])
                    lines.append(f"{tag}  tool: {_tool_use_line(block)}")

    digest = "\n".join(lines)
    if len(digest) <= budget:
        return digest
    return _elide_middle(lines, budget)


_CODEX_CALL_RE = re.compile(r"tools\.([A-Za-z0-9_]+)\(")

# Codex APIs whose call is also reported as a semantic `event_msg`, so the protocol
# row is redundant in a digest. Deliberately a short measured list rather than a rule:
# an API added here that stops emitting its event would vanish from the digest, and
# the safe direction is a call rendered twice rather than one rendered never.
_CODEX_EVENT_BACKED = frozenset({"apply_patch", "web__run"})


def _render_codex_digest(payload: bytes, *, budget: int) -> str:
    """The same exchange log, from codex's rollout grammar.

    Codex writes the conversation twice — once as protocol `response_item` rows and
    once as semantic `event_msg` rows — and this reads the second, because that is the
    layer where a patch is a set of paths rather than a program that produced them
    (harness/codex_transcripts.py). The exception is tool *output*, which only the
    protocol layer carries.

    The tool line names the declared API the program called (`tools.apply_patch(` →
    `apply_patch`) rather than the wrapper `exec` every codex call shares. Naming the
    wrapper would render every call in the session identically, which is a digest that
    costs tokens and says nothing.
    """
    lines: list[str] = []
    ingress_calls: set[str] = set()

    for record in _records(payload):
        payload_row = record.get("payload")
        payload_row = payload_row if isinstance(payload_row, dict) else {}
        kind, item = record.get("type"), payload_row.get("type")

        if kind == "event_msg":
            if item == "user_message":
                text = str(payload_row.get("message") or "").strip()
                if text:
                    lines.append(f"USER: {_clip(text, _TEXT_CAP)}")
            elif item == "agent_message":
                text = str(payload_row.get("message") or "").strip()
                if text:
                    lines.append(f"ASSISTANT: {_clip(text, _TEXT_CAP)}")
            elif item == "patch_apply_end":
                changes = payload_row.get("changes")
                paths = sorted(changes) if isinstance(changes, dict) else []
                if paths:
                    lines.append(f"  tool: apply_patch {_clip(', '.join(paths), _COMMAND_CAP)}")
            elif item == "web_search_end":
                query = str(payload_row.get("query") or "").strip()
                lines.append(f"  tool: web_search {_clip(query, _COMMAND_CAP)}")
            continue

        if kind != "response_item":
            continue

        if item == "custom_tool_call":
            program = payload_row.get("input")
            program = program if isinstance(program, str) else ""
            called = _CODEX_CALL_RE.search(program)
            name = called.group(1) if called else str(payload_row.get("name") or "?")
            call_id = str(payload_row.get("call_id") or "")
            if call_id and "web__run" in program:
                ingress_calls.add(call_id)
            if name in _CODEX_EVENT_BACKED:
                # Codex describes this call twice, and the `event_msg` says it better:
                # a list of paths beats the patch program that produced them, and a
                # query beats the search call. Rendering both spends the budget saying
                # one thing twice.
                continue
            # For everything else the program is the only description of the call
            # there is, so a clipped line of it goes in — the same role the `command`
            # field plays in the Claude Code renderer.
            lines.append(f"  tool: {name} {_clip(' '.join(program.split()), _COMMAND_CAP)}")
        elif item == "custom_tool_call_output":
            text = _codex_output_text(payload_row.get("output"))
            if text:
                # External-ingress results are labelled so the extractor can apply the
                # external-origin rule; the label is data about the segment, decided
                # here, not by the model.
                label = (
                    "result [EXTERNAL CONTENT]"
                    if str(payload_row.get("call_id") or "") in ingress_calls
                    else "result"
                )
                lines.append(f"  {label}: {_clip(text, _TOOL_RESULT_CAP)}")

    digest = "\n".join(lines)
    if len(digest) <= budget:
        return digest
    return _elide_middle(lines, budget)


def _codex_output_text(output) -> str:
    if isinstance(output, str):
        return output.strip()
    if not isinstance(output, list):
        return ""
    parts = [
        block.get("text", "")
        for block in output
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ]
    return "\n".join(part for part in parts if part).strip()


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
    # A question put to the operator carries its own summary. Without this the
    # fallback below dumps the whole option tree as escaped JSON, which is the
    # least readable line in the feed and the one most worth reading — it is the
    # session saying it is blocked on a human.
    asked = _questions(tool_input)
    if asked:
        more = f" (+{len(asked) - 1} more)" if len(asked) > 1 else ""
        return f"{name} — {_clip(asked[0]['question'], _COMMAND_CAP)}{more}"
    rendered = json.dumps(tool_input, default=str)
    return f"{name} {_clip(rendered, _COMMAND_CAP)}"


def _questions(tool_input: dict) -> list[dict]:
    """The questions in an `AskUserQuestion` input, normalised, or []."""
    raw = tool_input.get("questions")
    if not isinstance(raw, list):
        return []
    out = []
    for q in raw:
        if not isinstance(q, dict):
            continue
        text = str(q.get("question") or "").strip()
        if not text:
            continue
        options = [
            str(o.get("label") or "").strip()
            for o in (q.get("options") or [])
            if isinstance(o, dict) and str(o.get("label") or "").strip()
        ]
        out.append({
            "question": text,
            "header": str(q.get("header") or "").strip(),
            "options": options,
            "multi": bool(q.get("multiSelect")),
        })
    return out


# How many characters of a message UUID the digest shows. Eight is what the
# extractor is asked to copy back as an anchor; `resolve_anchors` expands it to the
# full UUID before the write, so the graph carries the `TOUCHES.anchors` shape and
# the digest spends 11 characters a line rather than 39.
_ANCHOR_PREFIX = 8


def _anchor_tag(record: dict) -> str:
    """`[a8202b5a] ` for a record carrying a message UUID, empty for one that does not.

    The tag is what lets the extractor anchor an outcome — a `worked: false`, an
    `outcome_kind`, a refused alternative — to the message that shows it, the way the
    deterministic layer anchors a touch to the tool call that made it. Without a
    handle in the digest the model can only assert an outcome; with one it can cite.
    """
    uuid = record.get("uuid")
    if not isinstance(uuid, str) or not uuid:
        return ""
    return f"[{uuid[:_ANCHOR_PREFIX]}] "


def resolve_anchors(data: dict, payload: bytes) -> dict:
    """Expand the digest's UUID prefixes in every `anchors` list to full message UUIDs.

    An anchor that resolves to no message in the transcript is dropped, not kept: the
    model was asked to copy a handle it saw, and one that matches nothing is either
    invented or mistyped, and a fabricated anchor is worse than none — it reads
    exactly like evidence. A prefix matching more than one message is dropped for the
    same reason. Returns a new dict; `data` is not modified.
    """
    by_prefix: dict[str, list[str]] = {}
    for record in _records(payload):
        uuid = record.get("uuid")
        if isinstance(uuid, str) and uuid:
            by_prefix.setdefault(uuid[:_ANCHOR_PREFIX], [])
            if uuid not in by_prefix[uuid[:_ANCHOR_PREFIX]]:
                by_prefix[uuid[:_ANCHOR_PREFIX]].append(uuid)

    def resolve(anchors: object) -> list[str]:
        if not isinstance(anchors, list):
            return []
        resolved: list[str] = []
        for anchor in anchors:
            handle = str(anchor).strip().strip("[]")
            candidates = by_prefix.get(handle[:_ANCHOR_PREFIX], [])
            matches = [u for u in candidates if u.startswith(handle)]
            if len(matches) == 1 and matches[0] not in resolved:
                resolved.append(matches[0])
        return resolved

    out = dict(data)
    solutions = data.get("solutions")
    if isinstance(solutions, list):
        out["solutions"] = [
            {**s, "anchors": resolve(s.get("anchors"))} if isinstance(s, dict) else s
            for s in solutions
        ]
    decisions = data.get("decisions")
    if isinstance(decisions, list):
        out["decisions"] = []
        for decision in decisions:
            if isinstance(decision, dict) and isinstance(decision.get("alternatives"), list):
                decision = {
                    **decision,
                    "alternatives": [
                        {**a, "anchors": resolve(a.get("anchors"))} if isinstance(a, dict) else a
                        for a in decision["alternatives"]
                    ],
                }
            out["decisions"].append(decision)
    return out


# How many characters of a reference handle the served-memory list shows, and the
# extractor copies back. Same length as an anchor handle and the same job.
_REFERENCE_PREFIX = 8


def reference_handle(vid: str) -> str:
    """The short handle the extractor copies in place of a vertex ID.

    A digest of the whole ID rather than a prefix of it, which is where this departs
    from `_anchor_tag`: every passage of one document shares a single 64-character
    source hash in its ID (`scope:x:chunk:<source>-0007`), so an 8-character prefix
    would be identical across every chunk of that document and could name none of
    them. Hashing the ID collides for nothing and costs the same eight characters.
    """
    return hashlib.sha256(vid.encode()).hexdigest()[:_REFERENCE_PREFIX]


def resolve_references(data: dict, served: list[str]) -> dict:
    """Expand every `references` handle to the vertex ID it names; drop what does not.

    The counterpart of `resolve_anchors`, over the served-memory list instead of the
    transcript. `served` is what this session's retrievals actually returned, so it is
    also the set of legal references: a handle outside it was invented or mistyped,
    and a fabricated reference is worse than none — it reads exactly like evidence,
    and the write path would hang a `USES {role: reason}` edge off whatever it named.

    A model that pastes a full vertex ID from the list instead of its handle is taken
    at its word, since that ID is served too. Returns a new dict; `data` is unmodified.
    """
    by_handle = {reference_handle(vid): vid for vid in served}
    known = set(served)

    def resolve(references: object) -> list[str]:
        if not isinstance(references, list):
            return []
        resolved: list[str] = []
        for reference in references:
            token = str(reference).strip().strip("[]`")
            # Exact match on the handle, never a prefix: a handle is a digest, so a
            # near-miss carries no evidence that it meant the entry it happens to
            # share eight characters with.
            target = token if token in known else by_handle.get(token)
            if target is not None and target not in resolved:
                resolved.append(target)
        return resolved

    out = dict(data)
    solutions = data.get("solutions")
    if isinstance(solutions, list):
        out["solutions"] = [
            {**s, "references": resolve(s.get("references"))} if isinstance(s, dict) else s
            for s in solutions
        ]
    decisions = data.get("decisions")
    if isinstance(decisions, list):
        out["decisions"] = []
        for decision in decisions:
            if isinstance(decision, dict):
                decision = {**decision, "references": resolve(decision.get("references"))}
                if isinstance(decision.get("alternatives"), list):
                    decision["alternatives"] = [
                        {**a, "references": resolve(a.get("references"))}
                        if isinstance(a, dict)
                        else a
                        for a in decision["alternatives"]
                    ]
            out["decisions"].append(decision)
    return out


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
worth recording. Record the **alternatives** the session considered and turned down, \
each with the reason it lost: the reason an option was refused is often the most \
reusable thing in a session, and it is what a later session needs to avoid re-arguing \
the same choice. An alternative the operator refused counts, even if it was never \
tried.
3. **problems** — what blocked progress, confused, or required debugging.
4. **solutions** — how problems were addressed; link via problem_ref (0-indexed into \
problems). `worked` is a finding, not a default: set `false` when the fix did not \
hold, and say how it ended with `outcome_kind` — `unresolved` (tried, did not fix it), \
`reversed` (worked, later undone), `rejected` (the operator refused it), `residual` \
(held, with a known remaining defect). A failed attempt with its reason is worth as \
much as a fix: both outcomes are wanted, symmetrically. Anchor every `worked: false` \
and every `outcome_kind` with the digest handles of the messages that show it (the \
`[a8202b5a]` tags), copied exactly.
5. **threads** — a continuation point a *different* session could pick up **cold**. \
Use stable lowercase-hyphenated ids. Threads are served into the next session's \
entrypoint and into consultation briefs, so each one spends context in sessions that \
did not ask for it — the bar is what someone would act on, not what was left over.

   The test: could a session with no access to this transcript act on it? If reading \
it requires knowing what happened here, it is not a thread — put it in the summary. \
These specifically do NOT earn one: something this session finished; an observation \
about current state ("the store has zero open threads" was minted from a probe's \
return value, was wrong, and rode 43 consultation briefs); a defect or gap the \
*operator* should queue rather than an agent resume, which belongs in the tracker; a \
restatement of a decision, which is already a decision.

   Measured on this graph: 542 threads from 192 sessions, and **93% of the 359 open \
ones were touched by exactly one session and never revisited**. They are not \
duplicates — the highest pairwise similarity any two reach is 0.39 — so the cost is \
not repetition but volume: distinct work nobody returns to, served forever. Most \
sessions justify 0-2. If you are writing a fourth, you are recording rather than \
continuing.
6. **thread_refs** — if this session continued or resolved one of the EXISTING OPEN \
THREADS listed below, reference it by its exact id with the new status. Prefer \
resolving an existing thread over spawning a duplicate. `open` is a status you may \
set: a thread this session found was closed prematurely — the work was not actually \
done, or it came back — is **reopened**, not respawned under a new id. A duplicate id \
hides the reopening, and how often a close does not hold is the only check on closes \
being made too easily.
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
10. Any claim whose substance rests on content the transcript FETCHED from outside \
(segments labelled `result [EXTERNAL CONTENT]` — web pages, search results) must carry \
`external: true`. What a web page asserts is that page's claim, not this session's \
lived experience — it keeps third-party trust even when quoted first-hand. Claims about \
what the agent DID with such content (edited a file, ran a command) stay first-party.
11. **references** — when a decision, solution or rejected alternative rested on \
something recalled from memory, name it under `references` by its **handle**: the \
8-character code in brackets in "Memory served into this session" below. Copy the \
handle, not the description and not a vertex id. Only handles from that list — it is \
everything this session's retrievals actually returned, so a handle that is not in it \
names nothing and is dropped. Leave `references` empty when the reasoning drew on \
nothing recalled; an empty list is a true statement.

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
    references: ["<handle from the served-memory list, if any>"]
    alternatives:
      - description: "<an option considered and turned down>"
        reason: "<why it lost>"
        references: ["<handle, if the reason rested on one>"]
        anchors: ["<digest handle of the message that raised or refused it>"]
    artifacts: ["<identifiers>"]
    external: false
problems:
  - description: "<what went wrong>"
    category: "bug|performance|design|integration|configuration|dependency|understanding"
    artifacts: ["<identifiers>"]
    external: false
solutions:
  - description: "<what was tried>"
    approach: "<how>"
    worked: "<true only if it held; false otherwise>"
    outcome_kind: "<unresolved|reversed|rejected|residual — omit when it simply held>"
    anchors: ["<digest handle of the message that shows the outcome>"]
    references: ["<handle from the served-memory list, if any>"]
    problem_ref: 0
    artifacts: ["<identifiers>"]
    external: false
threads:
  - id: "<stable-slug>"
    title: "<short actionable title>"
    description: "<what needs to happen and why>"
    status: "open"
    artifacts: ["<identifiers>"]
thread_refs:
  - id: "<existing thread id>"
    status: "open|in_progress|resolved|abandoned"
    notes: "<progress made>"
```

### Existing open threads in this project
{open_threads}

### Known claims in this project (re-assert by copying the description exactly)
{known_claims}

### Memory served into this session (cite one under `references` by its handle)
{served_nodes}

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
    served_nodes: list[dict] | None = None,
) -> str:
    if open_threads:
        rendered = "\n".join(
            f"- {t['id']} [{t['status']}]: {t['title']}" for t in open_threads
        )
    else:
        rendered = "(none)"
    # The convergence feed: the same mechanism as open threads, pointed at
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
        served_nodes=render_served_nodes(served_nodes),
        project=project,
        title=title,
        digest=digest,
    )


_SERVED_TEXT_CAP = 160


def render_served_nodes(served_nodes: list[dict] | None) -> str:
    """The reference feed: what this session's retrievals put in front of the model.

    The digest cannot carry this. A tool result is clipped at 400 characters and a
    recall renders its first node's ID some 150 characters in, so result #1's ID
    survives and every later one is truncated away — asking the model to copy an ID
    out of the digest asks for something that is usually not there. The feed names
    the same nodes in one line each, by a handle short enough that no clip reaches it.

    Ordered as the session met them, so the list reads like the session's own memory
    of what it was told, and each entry is one line: handle, label, scope, and enough
    text to tell two recalls apart.
    """
    if not served_nodes:
        return "(nothing recalled)"
    lines = []
    for node in served_nodes:
        scope = node.get("scope") or "?"
        label = node.get("label") or "node"
        text = _clip(str(node.get("text") or ""), _SERVED_TEXT_CAP)
        lines.append(f"- [{reference_handle(node['vid'])}] {label} · {scope} — {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Model invocation — headless, one dialect per harness
# ---------------------------------------------------------------------------

@dataclass
class ExtractionRun:
    text: str
    # None means the CLI does not report cost — not that the call was free.
    cost_usd: float | None = None
    # Same rule, and it took a third harness to notice the field was breaking it: a
    # `0` here read as "this run took no time" where codex means "the CLI does not
    # report a duration". `turn.completed` carries usage and nothing else, and the
    # rollout row that does carry `duration_ms` is never written, because the
    # extraction sandbox runs `--ephemeral`.
    duration_ms: int | None = None
    # Tokens are reported separately from price, because one CLI reports each.
    # Claude Code prices the call and Cursor counts the tokens, so a run that
    # carries no `cost_usd` is not an uninstrumented run — reading "no price" as
    # "no data" is what threw Cursor's counts away on every extraction.
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None


class ExtractionError(RuntimeError):
    pass


def run_extraction(
    prompt: str,
    *,
    model: str | None = None,
    harness: str = "claude",
    timeout: int = 900,
) -> ExtractionRun:
    """Run the extraction prompt through a headless coding-agent CLI.

    A session distills through **its own harness's** CLI: a Cursor session on a
    machine where only Cursor is installed must not need Claude Code present and
    authenticated to become memory. It also keeps each harness's traffic on the
    vendor the operator already chose for that machine, which is a policy question
    on a work box and not only a convenience one.

    The subprocess runs in an empty temp directory: the digest is already in the
    prompt, so the model has no reason to touch a filesystem — and now it couldn't
    find anything interesting if it tried.

    It also runs marked (`agents.sandbox_env`). The headless CLI is a full session
    to its own harness — transcript on disk, SessionEnd fired, hooks armed at user
    scope — so without the marker distillation distills itself, and the graph fills
    with memory about the act of remembering (measured 2026-07-29: 307 of 445
    Session nodes).
    """
    try:
        cli = cli_for(harness)
    except UnknownHarness as exc:
        raise ExtractionError(str(exc)) from None
    model = model or cli.default_model

    with tempfile.TemporaryDirectory(prefix="thalamus-extract-") as workdir:
        try:
            proc = subprocess.run(
                cli.argv(model),
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
                env=sandbox_env(),
            )
        except FileNotFoundError as exc:
            raise ExtractionError(
                f"`{cli.binary}` CLI not found on PATH — required to distill "
                f"{cli.harness} sessions"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ExtractionError(f"extraction timed out after {timeout}s") from exc

    if proc.returncode != 0:
        stderr = (proc.stderr.strip() or proc.stdout.strip())[:500]
        # The model hint only applies to a failure about the model. Appending it to
        # every non-zero exit sent a workspace-trust refusal out advising
        # `agent --list-models`, which points the reader at the one thing that was
        # not wrong. Cursor also writes this class of refusal to stdout rather than
        # stderr, so an empty stderr must fall back rather than report nothing.
        hint = f" ({cli.model_hint})" if cli.model_hint and "model" in stderr.lower() else ""
        raise ExtractionError(
            f"{' '.join(cli.argv(model))} exited {proc.returncode}{hint}: {stderr}"
        )

    try:
        reader = _ENVELOPE_READERS[cli.envelope]
    except KeyError:
        raise ExtractionError(
            f"no envelope reader for dialect `{cli.envelope}` declared by "
            f"harness `{cli.harness}`; known: {', '.join(sorted(_ENVELOPE_READERS))}"
        ) from None
    return reader(proc.stdout, cli)


def _usage_counts(usage, *keys: str) -> list[int | None]:
    """The named counts, absent ones staying None rather than becoming 0.

    An absent count means "not reported" and a zero means "none were used"; the two
    are different answers and collapsing them is how Cursor's token counts came to be
    thrown away on every extraction.
    """
    usage = usage if isinstance(usage, dict) else {}
    return [
        int(usage[key]) if isinstance(usage.get(key), (int, float)) else None
        for key in keys
    ]


def _read_object_envelope(stdout: str, cli) -> ExtractionRun:
    """One JSON object on stdout — Claude Code and Cursor."""
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ExtractionError(
            f"unparseable {cli.binary} -p output: {stdout[:200]}"
        ) from exc

    if envelope.get("is_error"):
        raise ExtractionError(
            f"{cli.binary} -p reported an error: {envelope.get('result', '')[:300]}"
        )

    cost = float(envelope.get("total_cost_usd") or 0.0) if cli.reports_cost else None
    # Read regardless of `reports_cost`: the two are different measurements and the
    # flag governs only the price.
    tokens = _usage_counts(
        envelope.get("usage"),
        "inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens",
    )
    return ExtractionRun(
        text=envelope.get("result", ""),
        cost_usd=cost,
        duration_ms=int(envelope.get("duration_ms") or 0),
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        cache_read_tokens=tokens[2],
        cache_write_tokens=tokens[3],
    )


def _read_jsonl_events(stdout: str, cli) -> ExtractionRun:
    """A line per event, terminated by `turn.completed` — codex.

    The answer is not in one place. The text is the last `item.completed` whose item
    is an `agent_message`, and the counts are on the terminal `turn.completed`, so
    both are accumulated across the stream rather than read off a single object
    (measured 2026-08-17, codex-cli 0.147.0).

    **A stream with no terminal event is an error, not an empty result.** `codex exec`
    can exit 0 having printed `turn.failed` — a 401, a rate limit, a refusal — and
    returning the empty string there would file a session with a blank summary and
    call it distilled. Unparseable lines are skipped rather than fatal for the
    opposite reason: a future codex adding an event kind must not stop extraction,
    and the terminal event is what says the turn actually finished.
    """
    text = ""
    usage = None
    failure = ""
    completed = False

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text") or text
        elif kind == "turn.completed":
            usage = event.get("usage")
            completed = True
        elif kind == "turn.failed":
            error = event.get("error")
            if isinstance(error, dict):
                failure = str(error.get("message") or "")

    if failure:
        raise ExtractionError(f"{cli.binary} exec reported an error: {failure[:300]}")
    if not completed:
        raise ExtractionError(
            f"{cli.binary} exec printed no turn.completed event: {stdout[-200:]}"
        )

    tokens = _usage_counts(
        usage,
        "input_tokens", "output_tokens", "cached_input_tokens", "cache_write_input_tokens",
    )
    return ExtractionRun(
        text=text,
        # Not a price. Codex carries no dollar figure anywhere in its stream, and a
        # 0.0 here would read as "this call was free".
        cost_usd=None,
        # Nor a duration, and `None` for the same reason: `turn.completed` reports
        # usage only. The rollout's `task_complete` row does carry `duration_ms`, but
        # the sandbox runs `--ephemeral` and writes no rollout, so it is genuinely
        # unavailable on this path rather than zero.
        duration_ms=None,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        cache_read_tokens=tokens[2],
        cache_write_tokens=tokens[3],
    )


_ENVELOPE_READERS = {
    "object": _read_object_envelope,
    "jsonl-events": _read_jsonl_events,
}


# ---------------------------------------------------------------------------
# Parsing and merging
# ---------------------------------------------------------------------------

_YAML_FENCE = re.compile(r"```ya?ml\s*\n(.*?)```", re.DOTALL)

# A block-mapping line whose value is a bare scalar: optional list dash, a plain
# identifier key, then the rest of the line. Free-text fields (description,
# citation, ...) match this; structure openers (`claims:`) don't reach the value
# branch because they have nothing after the colon.
_KEYED_LINE_RE = re.compile(r"^(\s*(?:-\s+)?[A-Za-z_][A-Za-z0-9_]*: )(\S.*?)\s*$")

# Characters that cannot open a plain scalar. `#` is the dangerous one: it fails
# silently by starting a comment, so the claim is dropped rather than reported.
_RESERVED_HEADS = ("@", "`", "%", "!", "#")


def _requote_scalars(raw: str) -> str:
    """Quote bare scalar values that break YAML block-mapping parsing.

    The extraction prompts show free-text fields unquoted (`description: ...`),
    so the model legitimately emits prose after the key — and prose containing
    ": " reads as a nested mapping key, which is a scanner error mid-line.

    Two failure shapes are rewritten. The second is the leading character: YAML
    reserves `@` and a backtick as indicators and lets neither open a plain scalar,
    `%` opens a directive and `!` a tag, and a leading `#` starts a comment that
    swallows the value into `None` without erroring at all. Prose legitimately
    begins with each of them — `@supports`, `!important`, `#hashtag` — so the value
    is quoted rather than lost. Already-quoted values and flow/block openers pass
    through untouched.
    """
    lines = []
    for line in raw.splitlines():
        match = _KEYED_LINE_RE.match(line)
        if match:
            value = match.group(2)
            if not value.startswith(('"', "'", "[", "{", "|", ">", "&", "*")) and (
                ": " in value or value.endswith(":") or value.startswith(_RESERVED_HEADS)
            ):
                line = match.group(1) + json.dumps(value, ensure_ascii=False)
        lines.append(line)
    return "\n".join(lines)


def _close_unterminated_quotes(raw: str) -> str:
    """Close a double-quoted scalar the model left open at end of line.

    A long value emitted without its closing quote does not fail on its own line —
    the scalar runs on and swallows following lines until the next `"`, so the
    scanner reports a block-mapping error several lines down and the whole document
    is lost. Every quoted value in the extraction schema is single-line, so a keyed
    line that opens a quote and ends with an odd number of unescaped ones is missing
    exactly one, and appending it recovers the value the model meant to write.
    """
    lines = []
    for line in raw.splitlines():
        match = _KEYED_LINE_RE.match(line)
        if match and match.group(2).startswith('"'):
            value, escaped, quotes = match.group(2), False, 0
            for ch in value:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    quotes += 1
            if quotes % 2:
                line = match.group(1) + value + '"'
        lines.append(line)
    return "\n".join(lines)


_VALID_ESCAPES = set('"\\/bfnrtu0abevNLP_ \t\n\rx')


def _repair_escapes(raw: str) -> str:
    """Neutralize invalid backslash escapes inside double-quoted scalars.

    Citations are verbatim quotes, so whatever notation the source uses rides into
    the value — arXiv HTML renders math as literal `\\sim`, `\\times`, `\\rightarrow`
    beside the glyph. YAML rejects an unknown escape in a double-quoted scalar
    outright, which fails the whole document over one character in one quote. A lone
    backslash is doubled so it survives as the literal the source actually contained.
    """
    out, in_quote, i = [], False, 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\n":
            in_quote = False
        elif ch == '"' and (not out or out[-1] != "\\"):
            in_quote = not in_quote
        elif ch == "\\" and in_quote:
            nxt = raw[i + 1] if i + 1 < len(raw) else ""
            if nxt in _VALID_ESCAPES:
                out.append(raw[i : i + 2])
                i += 2
                continue
            out.append("\\\\")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_extraction(text: str) -> dict:
    """Pull the YAML block out of the model's response."""
    match = _YAML_FENCE.search(text)
    raw = match.group(1) if match else text
    data = None
    for repair in (lambda s: s, _requote_scalars, _repair_escapes,
                   lambda s: _repair_escapes(_requote_scalars(s)),
                   _close_unterminated_quotes,
                   lambda s: _repair_escapes(_requote_scalars(_close_unterminated_quotes(s)))):
        try:
            data = yaml.safe_load(repair(raw))
            break
        except yaml.YAMLError as exc:
            last = exc
    if data is None:
        raise ExtractionError(f"unparseable extraction YAML: {last}")
    if not isinstance(data, dict):
        raise ExtractionError(f"extraction is not a mapping: {str(data)[:200]}")
    return data


def apply_ingress_floor(
    graph: SessionGraph,
    external_texts: list[str],
    *,
    ingress_verifiable: bool = True,
) -> SessionGraph:
    """Down-tier everything that rests on external content the transcript embedded.

    The laundering defense's write-path half: a session transcript is
    tier-1 evidence, but the pages it fetched are not — a claim distilled from them
    must keep third-party trust or recall will later serve a stranger's assertion as
    the agent's own lived experience.

    Coverage is every enumerated list whose type carries provenance (`_TIERED_LISTS`),
    not the three claim lists alone: a Thread or an Artifact minted out of a fetched
    page carries a tier just as a Decision does, and a seventh claim type added to
    `_CLAIM_LISTS` tomorrow is floored the day it is added. `ThreadRef` is the one
    enumerated type left out, because it has no provenance to down-tier.

    Two layers, deliberately unequal:
    - the extractor's `external: true` marks are honored (good recall, but a poisoned
      page can talk the model out of marking);
    - claims whose distinctive terms echo the external texts are forced external
      **regardless of the mark** — no instruction reaches this layer, and `_tokens`
      makes it read through a claim rewritten to spell the page's words differently.
      Same dials as used-vs-ignored attribution: crude, cheap, honest.

    It is lexical, so the residual is vocabulary: a claim that restates the page in
    words the page does not use is not caught. Paraphrase is the bar, not spelling.

    Down-tier is the only direction: nothing here ever raises trust, so the worst
    failure is first-party memory rendering as tier 2 — which informs, and costs
    nothing but emphasis.

    `ingress_verifiable=False` says the transcript format cannot carry tool results
    at all, so an empty `external_texts` is ignorance rather than evidence — the
    Cursor case (harness/cursor_transcripts.py). The mechanical layer then has
    nothing to run against, and honoring only the extractor's self-marks would
    leave exactly the liftable half of the defence standing. So the whole session
    is floored instead. That is heavy-handed by design: it is the same trade the
    docstring above already prices, taken at the one moment the cheap mechanical
    check is unavailable, and it makes capturing tool outputs out-of-band the way
    to earn tier-1 back rather than something to remember to do.
    """
    if not ingress_verifiable:
        if not any(getattr(graph, attr) for attr in _TIERED_LISTS):
            return graph
    elif not external_texts and not any(c.external for c in graph.claims()):
        return graph

    corpus_tokens = _tokens(" ".join(external_texts))

    reason = "transcript-ingress" if ingress_verifiable else "transcript-ingress-unverifiable"
    floored = Provenance(
        tier=Tier.CURATED,
        source=f"session:{graph.session_id}#{reason}",
        ingested_at=graph.timestamp,
    )

    def floor(items: list) -> list:
        out = []
        for item in items:
            marked = getattr(item, "external", False)
            if not ingress_verifiable or marked or _echoes(item, corpus_tokens):
                update: dict = {"provenance": floored}
                # `external` is a Claim field; Thread and Artifact carry the tier and
                # nothing else, so the provenance is the whole of the down-tier there.
                if "external" in type(item).model_fields:
                    update["external"] = True
                item = item.model_copy(update=update)
            out.append(item)
        return out

    return graph.model_copy(
        update={attr: floor(getattr(graph, attr)) for attr in _TIERED_LISTS}
    )


def _tokens(text: str) -> set[str]:
    """Every form of every word in `text` that either side could spell it as.

    One tokenizer, run over the page and over the claim, emitting a compound token
    **and** its separator-delimited parts: `tool-calls` yields `tool-calls`, `tool`,
    `calls`, and so does `tool calls` minus the compound. That redundancy is the whole
    mechanism. A single tokenizer is not enough on its own — the claim's spelling is
    attacker-chosen, so a page saying `tool calls` and a claim saying `tool-calls`
    share no token however identically the two sides tokenize, and joining a claim's
    words with any of `_TOKEN_RE`'s in-class separators lifted the floor outright.
    Emitting both forms makes the match invariant to which separator, if any, the
    claim used; characters outside `_TOKEN_RE`'s class (`~`, `,`, `|`, U+200B) split
    on both sides and never survived a shared tokenizer anyway.

    The cost is a coarser signal — `docs/concepts.md` also contributes `docs` and
    `concepts` — which lands as more first-party claims read as tier 2. That is
    the direction this whole layer is allowed to fail in.
    """
    found: set[str] = set()
    for token in _TOKEN_RE.findall(text.lower()):
        found.add(token)
        parts = _WORD_RE.findall(token)
        if len(parts) > 1:
            found.update(parts)
    return found


# The free-text fields the echo check reads, across every tier-carrying type. Read by
# `getattr`, so a type contributes whichever of them it has: a Claim's
# description/rationale/approach/outcome, a Thread's title and description, an
# Artifact's identifier and notes. An Artifact's identity *is* its identifier — a
# dependency named only by the fetched page has nothing else to echo with — so it
# counts as content here rather than as an address.
_ECHO_FIELDS = (
    "description", "rationale", "approach", "outcome", "title", "notes", "identifier",
)


def _echoes(item: Claim | Thread | Artifact, corpus_tokens: set[str]) -> bool:
    """Does this item's content lexically echo the external texts?"""
    if not corpus_tokens:
        return False
    text = " ".join(
        str(value)
        for field_name in _ECHO_FIELDS
        if (value := getattr(item, field_name, None))
    )
    terms = sorted(t for t in _tokens(text) if len(t) > 2 and t not in STOPWORDS)
    if not terms:
        return False
    matched = [term for term in terms if term in corpus_tokens]
    needed = min(len(terms), MIN_MATCHED_TERMS)
    return len(matched) >= needed and len(matched) / len(terms) >= MIN_MATCHED_RATIO


_CLAIM_LISTS: tuple[tuple[str, type], ...] = (
    ("decisions", Decision),
    ("problems", Problem),
    ("solutions", Solution),
    ("threads", Thread),
    ("thread_refs", ThreadRef),
    ("artifacts", Artifact),
)

# What the ingress floor rewrites: every enumerated list whose type carries a tier.
# Derived rather than listed, so a claim type added above is floored on arrival.
# `ThreadRef` falls out here — it has no provenance, so it has nothing to down-tier.
_TIERED_LISTS: tuple[str, ...] = tuple(
    attr for attr, model in _CLAIM_LISTS if "provenance" in model.model_fields
)


def _validation_reason(exc: Exception) -> str:
    """`field — message`, from a pydantic ValidationError or anything else.

    The operator reads this in a detached log to decide whether a dropped claim was
    worth recovering, so it has to name the field *and* what was wrong with it.
    """
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            parts = [
                f"{'.'.join(str(p) for p in err.get('loc', ())) or '?'} — {err.get('msg', '')}"
                for err in errors()
            ]
            if parts:
                return "; ".join(parts)[:160]
        except Exception:
            pass
    return str(exc).replace("\n", " ")[:160]


def partition_valid(data: dict) -> tuple[dict, list[str]]:
    """Split a parsed extraction into the items that validate and the ones that don't.

    One malformed list item used to discard the whole run: a `SessionGraph(**data)`
    raising on `solutions.2.approach` threw away the other forty claims the model got
    right, and the session stayed out of the graph until someone re-ran it by hand and
    paid again. The digest pass had *succeeded*; only a downstream check failed.

    So items are validated individually and the bad ones are dropped by name. This is
    deliberately not a repair: nothing is invented to satisfy a required field. A
    validator is ground truth about conformance, never about content — a missing
    `approach` means the model recorded no approach, and inventing one would convert a
    loud failure into a fabricated memory, which is strictly worse for a store whose
    whole value is that its claims are traceable.

    Returns the surviving data and a human-readable list of what was dropped and why.
    Losing one claim is a cost; losing the session is an outage.
    """
    kept = dict(data)
    dropped: list[str] = []
    # old index -> new index, per list. `problem_ref` is positional, so dropping a
    # problem renumbers every later one: without this remap a surviving solution
    # would silently attach its SOLVED_BY edge to the wrong problem, which is worse
    # than the failure being fixed here — a wrong link reads exactly like a right one.
    remap: dict[str, dict[int, int]] = {}
    for field_name, model in _CLAIM_LISTS:
        items = data.get(field_name)
        if not isinstance(items, list):
            continue
        survivors = []
        index_map: dict[int, int] = {}
        for index, item in enumerate(items):
            try:
                model(**(item if isinstance(item, dict) else dict(item)))
            except Exception as exc:
                dropped.append(f"{field_name}[{index}]: {_validation_reason(exc)}")
                continue
            index_map[index] = len(survivors)
            survivors.append(item)
        kept[field_name] = survivors
        remap[field_name] = index_map

    problem_map = remap.get("problems")
    if problem_map is not None and len(problem_map) != len(data.get("problems") or []):
        rebuilt = []
        for solution in kept.get("solutions") or []:
            if not isinstance(solution, dict):
                rebuilt.append(solution)
                continue
            ref = solution.get("problem_ref")
            if isinstance(ref, int):
                solution = dict(solution)
                # Pointed at a dropped problem: unlink rather than guess. An
                # unlinked solution is still true; a mislinked one is not.
                solution["problem_ref"] = problem_map.get(ref)
            rebuilt.append(solution)
        kept["solutions"] = rebuilt
    return kept, dropped


def merge_extraction(base: SessionGraph, data: dict[str, Any]) -> SessionGraph:
    """Merge model judgement into the deterministic stage-1 graph.

    Identity, provenance, sources, and anchored touches come from the record; the model
    contributes summary, claims, and threads. Fields the model was told not to emit are
    overridden even if it emitted them anyway.
    """
    payload: dict[str, Any] = {
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
    extracted = SessionGraph(**payload)

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
