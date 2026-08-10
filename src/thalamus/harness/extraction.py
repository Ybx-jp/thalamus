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

The model is invoked through a headless coding-agent CLI chosen by harness
(`harness/agents.py`): `claude -p` for Claude Code sessions, Cursor's `agent -p`
for Cursor ones. Either rides whatever authentication the operator's own sessions
already use, so there is no API key handling here — and a Cursor-only machine
never needs Claude Code installed to turn its sessions into memory.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass

import yaml

from thalamus.eval.attribution import MIN_MATCHED_RATIO, MIN_MATCHED_TERMS
from thalamus.harness.agents import (  # re-exported: extraction is their main caller
    AGENT_CLIS,
    CLAUDE_DEFAULT_MODEL,
    CURSOR_DEFAULT_MODEL,
    AgentCLI,
    UnknownHarness,
    cli_for,
    sandbox_env,
)
from thalamus.harness.transcripts import EXTERNAL_INGRESS_TOOLS
from thalamus.substrate.reader import _extract_keywords
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


def render_digest(payload: bytes, *, budget: int = _DIGEST_BUDGET) -> str:
    """Render archived transcript bytes into a compact, readable exchange log.

    Keeps user prompts, assistant prose, tool calls (name + salient input), and heavily
    truncated tool results. Drops sidechains, meta records, and system-injected noise —
    the extractor needs the *conversation*, not the plumbing.

    Harness-tolerant on purpose: Claude Code discriminates rows with `type`, Cursor with
    `role` and nothing else (harness/cursor_transcripts.py). The block vocabulary is the
    same in both, so one renderer serves both and a Cursor digest simply contains no
    `result:` lines — the format carries no tool outputs to render.

    If the result exceeds the budget, the middle is elided rather than the tail: openings
    state intent and endings state outcomes, and both matter more than the grind between.
    """
    lines: list[str] = []
    external_tool_uses: set[str] = set()
    for record in _records(payload):
        if record.get("isSidechain") or record.get("isMeta"):
            continue
        record_type = record.get("type") or record.get("role")
        content = (record.get("message") or {}).get("content")

        if record_type == "user":
            if isinstance(content, str):
                text = content.strip()
                if text and not text.startswith("<"):
                    lines.append(f"USER: {_clip(text, _TEXT_CAP)}")
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    # Cursor writes user prompts as text blocks rather than a bare
                    # string; without this a Cursor digest holds no user turns at all.
                    if block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text and not text.startswith("<"):
                            lines.append(f"USER: {_clip(text, _TEXT_CAP)}")
                    elif block.get("type") == "tool_result":
                        text = _tool_result_text(block)
                        if text:
                            # External-ingress results are labelled so the extractor
                            # can apply the external-origin rule (docs/05); the label
                            # is data about the segment, decided here, not by the model.
                            label = (
                                "result [EXTERNAL CONTENT]"
                                if block.get("tool_use_id") in external_tool_uses
                                else "result"
                            )
                            lines.append(f"  {label}: {_clip(text, _TOOL_RESULT_CAP)}")
        elif record_type == "assistant":
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text", "").strip():
                    lines.append(f"ASSISTANT: {_clip(block['text'].strip(), _TEXT_CAP)}")
                elif block.get("type") == "tool_use":
                    if block.get("name") in EXTERNAL_INGRESS_TOOLS and block.get("id"):
                        external_tool_uses.add(block["id"])
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
10. Any claim whose substance rests on content the transcript FETCHED from outside \
(segments labelled `result [EXTERNAL CONTENT]` — web pages, search results) must carry \
`external: true`. What a web page asserts is that page's claim, not this session's \
lived experience — it keeps third-party trust even when quoted first-hand. Claims about \
what the agent DID with such content (edited a file, ran a command) stay first-party.

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
    external: false
problems:
  - description: "<what went wrong>"
    category: "bug|performance|design|integration|configuration|dependency|understanding"
    artifacts: ["<identifiers>"]
    external: false
solutions:
  - description: "<what fixed it>"
    approach: "<how>"
    worked: true
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
# Model invocation — headless, one dialect per harness
# ---------------------------------------------------------------------------

@dataclass
class ExtractionRun:
    text: str
    # None means the CLI does not report cost — not that the call was free.
    cost_usd: float | None = None
    duration_ms: int = 0


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
        stderr = proc.stderr.strip()[:500]
        hint = f" ({cli.model_hint})" if cli.model_hint else ""
        raise ExtractionError(
            f"{cli.binary} -p --model {model} exited {proc.returncode}{hint}: {stderr}"
        )

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ExtractionError(
            f"unparseable {cli.binary} -p output: {proc.stdout[:200]}"
        ) from exc

    if envelope.get("is_error"):
        raise ExtractionError(
            f"{cli.binary} -p reported an error: {envelope.get('result', '')[:300]}"
        )

    cost = float(envelope.get("total_cost_usd") or 0.0) if cli.reports_cost else None
    return ExtractionRun(
        text=envelope.get("result", ""),
        cost_usd=cost,
        duration_ms=int(envelope.get("duration_ms") or 0),
    )


# ---------------------------------------------------------------------------
# Parsing and merging
# ---------------------------------------------------------------------------

_YAML_FENCE = re.compile(r"```ya?ml\s*\n(.*?)```", re.DOTALL)

# A block-mapping line whose value is a bare scalar: optional list dash, a plain
# identifier key, then the rest of the line. Free-text fields (description,
# citation, ...) match this; structure openers (`claims:`) don't reach the value
# branch because they have nothing after the colon.
_KEYED_LINE_RE = re.compile(r"^(\s*(?:-\s+)?[A-Za-z_][A-Za-z0-9_]*: )(\S.*?)\s*$")


def _requote_scalars(raw: str) -> str:
    """Quote bare scalar values that break YAML block-mapping parsing.

    The extraction prompts show free-text fields unquoted (`description: ...`),
    so the model legitimately emits prose after the key — and prose containing
    ": " reads as a nested mapping key, which is a scanner error mid-line.
    Only bare values with that failure shape are rewritten; already-quoted
    values and flow/block openers pass through untouched.
    """
    lines = []
    for line in raw.splitlines():
        match = _KEYED_LINE_RE.match(line)
        if match:
            value = match.group(2)
            if not value.startswith(('"', "'", "[", "{", "|", ">", "&", "*")) and (
                ": " in value or value.endswith(":")
            ):
                line = match.group(1) + json.dumps(value, ensure_ascii=False)
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
                   lambda s: _repair_escapes(_requote_scalars(s))):
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
    """Down-tier claims that rest on external content the transcript embedded.

    The laundering defense's write-path half (docs/05): a session transcript is
    tier-1 evidence, but the pages it fetched are not — a claim distilled from them
    must keep third-party trust or recall will later serve a stranger's assertion as
    the agent's own lived experience.

    Two layers, deliberately unequal:
    - the extractor's `external: true` marks are honored (good recall, but a poisoned
      page can talk the model out of marking);
    - claims whose distinctive terms echo the external texts are forced external
      **regardless of the mark** — the mechanical floor no prompt content can lift.
      Same dials as used-vs-ignored attribution: crude, cheap, honest (docs/04).

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
        if not graph.claims():
            return graph
    elif not external_texts and not any(c.external for c in graph.claims()):
        return graph

    corpus = " ".join(external_texts).lower()
    corpus_tokens = set(_TOKEN_RE.findall(corpus))

    reason = "transcript-ingress" if ingress_verifiable else "transcript-ingress-unverifiable"
    floored = Provenance(
        tier=Tier.CURATED,
        source=f"session:{graph.session_id}#{reason}",
        ingested_at=graph.timestamp,
    )

    def floor(claims: list) -> list:
        out = []
        for claim in claims:
            if not ingress_verifiable or claim.external or _echoes(claim, corpus_tokens):
                claim = claim.model_copy(update={"external": True, "provenance": floored})
            out.append(claim)
        return out

    return graph.model_copy(
        update={
            "decisions": floor(graph.decisions),
            "problems": floor(graph.problems),
            "solutions": floor(graph.solutions),
        }
    )


def _echoes(claim: Claim, corpus_tokens: set[str]) -> bool:
    """Does this claim's content lexically echo the external texts?"""
    if not corpus_tokens:
        return False
    text = " ".join(
        str(value)
        for field_name in ("description", "rationale", "approach", "outcome")
        if (value := getattr(claim, field_name, None))
    )
    terms = sorted(set(_extract_keywords(text)))
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
    whole value is that its claims are traceable (docs/05).

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
