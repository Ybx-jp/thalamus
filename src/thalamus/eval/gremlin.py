"""Gremlin fluency metrics — the guards, the recipe store, and their evals.

The fluency layer (gremlin-python skill, RECIPES.md store, terminal-step guard
hook, memory_query dialect guard) ships with its measurement, per the
eval-methodology consultation (exchange 918ddb8ddf094a29): block counts are
activity, not effectiveness, so this module computes the metrics that grade the
layer honestly:

- **Rescue rate** — a guard block followed by a passing gremlin command in the
  same session is a save; a repeat block is friction. Read from the guard event
  log (~/.thalamus/guards/, written by gremlin-guard.sh).
- **Rejection classes** on memory_query — dialect vs mutation vs server
  failure, counted from the existing trace tap (the rejection text is the
  tool_response; no parallel log).
- **Reuse tagging** — recipe-derived vs from-scratch, by traversal-shape
  fingerprint (the ordered step sequence, dialect-folded), with success rates
  per arm. Question+query example stores earn their keep through reuse
  (DAIL-SQL, arXiv 2308.15363); reuse must be measured, not assumed.
- **Recipe smoke run** — every RECIPES.md entry re-executed read-only, turning
  the one-shot "Validated" date into a rolling freshness signal. A recipe that
  stops executing is an eviction candidate, not documentation.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from thalamus.eval.traces import TraceEvent, load_events
from thalamus.substrate.query import run_query

GUARDS_DIR = Path.home() / ".thalamus" / "guards"
RECIPES_PATH = (
    Path(__file__).parents[1] / "harness" / "skills" / "gremlin-python" / "RECIPES.md"
)
RECALL_STRATEGY_PATH = (
    Path(__file__).parents[1] / "harness" / "skills" / "recall-strategy" / "SKILL.md"
)

# A fingerprint shorter than this matches half of all traversals; it carries no
# reuse signal and is skipped.
_MIN_FINGERPRINT_STEPS = 3

# Mutating tokens a recipe must never contain — the smoke run refuses to execute
# a stored recipe that drifted onto the write path (docs/05: ad-hoc is read-only).
# Checked on an underscore-folded compact view, so both dialects are caught
# (add_v and addV inside a submitted string alike — the memory_query guard's
# deny list, plus the writer's own entry points, which recipes can import).
_SMOKE_DENIED = (
    "addv(",
    "adde(",
    "mergev(",
    "mergee(",
    "drop(",
    "property(",
    "sideeffect(",
    "io(",
    "call(",
    "program(",
    "writetrace(",
    "memorize(",
    "ensureedge(",
    "ensurevertex(",
    "writesession(",
)

# The recall-strategy recipes predate per-entry Validated dates; the skill
# shipped 2026-07-16, which bounds their admission for temporal reuse tagging.
_RECALL_STRATEGY_ADMITTED = datetime.fromisoformat("2026-07-16T00:00:00+00:00")

_STEP_RE = re.compile(r"\.\s*([A-Za-z_]+)\s*\(")
_VALIDATED_RE = re.compile(r"\*\*Validated:\*\*\s*(\d{4}-\d{2}-\d{2})")


@dataclass
class GuardEvent:
    ts: datetime
    session_id: str
    verdict: str  # "block" | "pass"
    command_hash: str = ""
    # what satisfied a pass: "terminal" | "wrapper" | "textedit" | "no-traversal"
    # ("no-traversal" = the trigger fired on an import but no traversal was built)
    branch: str = ""
    fingerprint: tuple[str, ...] = ()


def load_guard_events(base: Path | None = None) -> list[GuardEvent]:
    directory = base or GUARDS_DIR
    if not directory.is_dir():
        return []
    events: list[GuardEvent] = []
    for path in sorted(directory.glob("*.jsonl")):
        with path.open(errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    ts = datetime.fromisoformat(
                        str(record.get("ts", "")).replace("Z", "+00:00")
                    )
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(record, dict) or not record.get("session_id"):
                    continue
                verdict = record.get("verdict")
                if verdict not in ("block", "pass"):
                    continue
                fingerprint = tuple(
                    s for s in str(record.get("fingerprint", "")).split(",") if s
                )
                events.append(
                    GuardEvent(
                        ts=ts,
                        session_id=str(record["session_id"]),
                        verdict=verdict,
                        command_hash=str(record.get("command_hash", "")),
                        branch=str(record.get("branch", "")),
                        fingerprint=fingerprint,
                    )
                )
    events.sort(key=lambda e: e.ts)
    return events


def step_fingerprint(text: str) -> tuple[str, ...]:
    """The ordered gremlin step sequence, dialect-folded.

    `has_label` and `hasLabel` fold to the same token, so a fingerprint matches
    across the gremlin-python / gremlin-lang split. Quoting, arguments, and
    whitespace are invisible — reuse is shape reuse (adapting a recipe's
    arguments is still reuse; DAIL-SQL's example selection matches on query
    skeletons for the same reason).
    """
    return tuple(m.lower().replace("_", "") for m in _STEP_RE.findall(text))


@dataclass(frozen=True)
class Recipe:
    fingerprint: tuple[str, ...]
    admitted: datetime | None  # None: unknown — matches without a time bound


def recipe_fingerprints() -> dict[str, Recipe]:
    """Fingerprints of every stored recipe, from both stores, with admission dates.

    RECIPES.md (fenced blocks, per-entry Validated dates) and recall-strategy's
    seven memory_query recipes (indented blocks; admitted when the skill
    shipped) — reuse of either arm counts. The admission date matters: tagging
    a trace recipe-derived when it *predates* the recipe credits the store with
    the successes that created it (selection on success — verification
    8f6ad2d6f4024b2c finding 3).
    """
    prints: dict[str, Recipe] = {}
    for path in (RECIPES_PATH, RECALL_STRATEGY_PATH):
        if not path.is_file():
            continue
        default_admitted = (
            _RECALL_STRATEGY_ADMITTED if path == RECALL_STRATEGY_PATH else None
        )
        for index, (name, code, validated) in enumerate(_dated_blocks(path.read_text())):
            fp = step_fingerprint(code)
            if len(fp) >= _MIN_FINGERPRINT_STEPS:
                # Index-suffixed: several recipes can share one section heading
                # (recall-strategy's seven live under a single ##).
                prints[f"{path.stem}:{index}:{name}"] = Recipe(
                    fp, validated or default_admitted
                )
    return prints


def is_recipe_derived(
    query: str, prints: dict[str, Recipe], ts: datetime | None = None
) -> str | None:
    """The recipe this query's shape reuses, or None if written from scratch.

    With `ts`, only recipes already admitted at that time match — a query older
    than the recipe it resembles was the recipe's *source*, not its reuse.
    """
    fp = step_fingerprint(query)
    for name, recipe in prints.items():
        if ts is not None and recipe.admitted is not None and ts < recipe.admitted:
            continue
        if _contains(fp, recipe.fingerprint):
            return name
    return None


def _shares_intent(blocked: tuple[str, ...], retry: tuple[str, ...]) -> bool:
    """Whether a later pass plausibly retries the blocked traversal.

    Pre-v3 guard events carry no fingerprint; without one the join cannot be
    tightened and falls back to any-terminal-pass.
    """
    if not blocked:
        return True
    overlap = set(blocked) & set(retry)
    return len(overlap) >= min(2, len(blocked))


def _contains(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    if len(needle) > len(haystack):
        return False
    return any(
        haystack[i : i + len(needle)] == needle
        for i in range(len(haystack) - len(needle) + 1)
    )


def _dated_blocks(markdown: str) -> list[tuple[str, str, datetime | None]]:
    """(section name, code, Validated date) for fenced and 4-space-indented blocks."""
    blocks: list[tuple[str, str, datetime | None]] = []
    section = ""
    validated: datetime | None = None
    fence: list[str] | None = None
    indent: list[str] = []
    for line in markdown.splitlines():
        if fence is not None:
            if line.strip().startswith("```"):
                blocks.append((section, "\n".join(fence), validated))
                fence = None
            else:
                fence.append(line)
            continue
        if line.startswith("#"):
            if indent:
                blocks.append((section, "\n".join(indent), validated))
                indent = []
            section = line.lstrip("# ").strip()
            validated = None
            continue
        match = _VALIDATED_RE.search(line)
        if match:
            validated = datetime.fromisoformat(match.group(1) + "T00:00:00+00:00")
        if line.strip().startswith("```"):
            fence = []
            continue
        if line.startswith("    ") and line.strip():
            indent.append(line.strip())
            continue
        if indent and line.strip():
            blocks.append((section, "\n".join(indent), validated))
            indent = []
    if indent:
        blocks.append((section, "\n".join(indent), validated))
    return blocks


@dataclass
class GremlinReport:
    blocks: int = 0
    passes: int = 0
    rescued: int = 0
    repeat_blocks: int = 0
    mq_total: int = 0
    mq_ok: int = 0
    mq_miss: int = 0
    mq_dialect: int = 0
    mq_mutation: int = 0
    mq_failed: int = 0
    bash_total: int = 0
    bash_errored: int = 0
    reuse: dict[str, dict[str, int]] = field(default_factory=dict)  # arm -> {n, ok}

    def render(self) -> str:
        lines = ["Gremlin fluency report", ""]
        lines.append(
            f"Guard (terminal-step): {self.blocks} block(s), {self.passes} pass(es)"
        )
        if self.blocks:
            lines.append(
                f"  rescue rate: {self.rescued}/{self.blocks} blocks followed by a "
                f"pass in-session; {self.repeat_blocks} repeat block(s) (friction)"
            )
        lines.append(
            f"memory_query: {self.mq_total} call(s) — {self.mq_ok} returned data, "
            f"{self.mq_miss} empty, {self.mq_dialect} dialect-rejected, "
            f"{self.mq_mutation} mutation-rejected, {self.mq_failed} server-failed"
        )
        lines.append(
            f"bash_gremlin: {self.bash_total} execution(s) — "
            f"{self.bash_errored} errored"
        )
        for arm in ("recipe-derived", "from-scratch"):
            stats = self.reuse.get(arm)
            if stats and stats["n"]:
                lines.append(
                    f"  {arm}: {stats['ok']}/{stats['n']} first-shot success"
                )
        if not (self.blocks or self.passes or self.mq_total or self.bash_total):
            lines.append("")
            lines.append("No gremlin events yet — instrumentation pending, unmeasured.")
        return "\n".join(lines)


def gremlin_report(
    traces_base: Path | None = None, guards_base: Path | None = None
) -> GremlinReport:
    report = GremlinReport()

    guard_events = load_guard_events(guards_base)
    by_session: dict[str, list[GuardEvent]] = {}
    for event in guard_events:
        by_session.setdefault(event.session_id, []).append(event)
    for events in by_session.values():
        for i, event in enumerate(events):
            if event.verdict == "pass":
                report.passes += 1
                continue
            report.blocks += 1
            later = events[i + 1 :]
            # A rescue is a corrected retry, not "any later pass" — wrapper and
            # text-edit passes fire constantly in an active session and would
            # saturate the metric (verification 8f6ad2d6f4024b2c finding 1).
            # The join is on traversal intent: a later terminal-branch pass
            # sharing the blocked command's step fingerprint.
            if any(
                e.verdict == "pass"
                and e.branch in ("terminal", "")
                and _shares_intent(event.fingerprint, e.fingerprint)
                for e in later
            ):
                report.rescued += 1
            # Friction is re-submitting the *same* doomed traversal, not any
            # adjacent block.
            if any(
                e.verdict == "block"
                and (
                    (event.command_hash and e.command_hash == event.command_hash)
                    or (event.fingerprint and e.fingerprint == event.fingerprint)
                )
                for e in later
            ):
                report.repeat_blocks += 1

    prints = recipe_fingerprints()
    events = load_events(traces_base, tools=frozenset({"memory_query", "bash_gremlin"}))
    for event in events:
        succeeded = _succeeded(event)
        if event.tool == "memory_query":
            report.mq_total += 1
            response = event.tool_response.strip()
            if event.is_miss():
                report.mq_miss += 1
            elif "gremlin-python dialect" in response:
                report.mq_dialect += 1
            elif "mutating or side-effect" in response:
                report.mq_mutation += 1
            elif response.startswith("Query failed:"):
                report.mq_failed += 1
            elif succeeded:
                report.mq_ok += 1
            query = str(event.tool_input.get("query", ""))
        else:
            report.bash_total += 1
            if not succeeded:
                report.bash_errored += 1
            query = str(event.tool_input.get("command", ""))

        arm = (
            "recipe-derived"
            if is_recipe_derived(query, prints, ts=event.ts)
            else "from-scratch"
        )
        stats = report.reuse.setdefault(arm, {"n": 0, "ok": 0})
        stats["n"] += 1
        stats["ok"] += int(succeeded)

    return report


def _succeeded(event: TraceEvent) -> bool:
    """Execution accuracy's first half: the query *executed* correctly.

    An empty result is an execution success — it is often the right answer to
    an existence question, and calling it a failure conflates the query running
    with the answer being non-empty (the fact-itself vs downstream-consequence
    split; verification 8f6ad2d6f4024b2c finding 4). The second half — was the
    output *used* — is the standard used/evidence verdict on the landed Trace
    (`thalamus eval report`), not recomputed here.
    """
    if event.tool == "memory_query":
        return event.tool_response.strip().startswith("Query result") or event.is_miss()
    return (
        bool(event.tool_response.strip())
        and "Traceback (most recent call last)" not in event.tool_response
    )


@dataclass
class SmokeResult:
    name: str
    ok: bool
    detail: str = ""


def smoke_recipes(url: str, path: Path | None = None) -> list[SmokeResult]:
    """Re-execute every stored recipe read-only against the live graph.

    Python blocks run in-process (they carry their own connect/close); plain
    blocks run through the memory_query validator+executor, so a recipe that
    would be rejected on the live surface fails its smoke too.
    """
    recipes_path = path or RECIPES_PATH
    results: list[SmokeResult] = []
    text = recipes_path.read_text() if recipes_path.is_file() else ""
    seen: set[str] = set()
    for name, code in _python_blocks(text):
        if name in seen or not name or name.lower().startswith(("gremlin recipe", "entry")):
            continue
        seen.add(name)
        compact = re.sub(r"\s+", "", code).lower().replace("_", "")
        if any(denied in compact for denied in _SMOKE_DENIED):
            results.append(SmokeResult(name, False, "mutating step in stored recipe"))
            continue
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                exec(compile(code, f"<recipe:{name}>", "exec"), {"__name__": "__smoke__"})
            results.append(SmokeResult(name, True))
        except Exception:
            results.append(
                SmokeResult(name, False, traceback.format_exc(limit=1).strip())
            )
    for name, code in _lang_blocks(text):
        if name in seen:
            continue
        seen.add(name)
        outcome = run_query(url, code.strip())
        ok = not outcome.startswith(("Rejected:", "Query failed:", "Query must", "Query exceeds"))
        results.append(SmokeResult(name, ok, "" if ok else outcome.splitlines()[0]))
    return results


def render_smoke(results: list[SmokeResult]) -> str:
    if not results:
        return "No recipes found to smoke."
    lines = [f"Recipe smoke run — {sum(r.ok for r in results)}/{len(results)} OK"]
    for result in results:
        mark = "OK " if result.ok else "FAIL"
        lines.append(f"  [{mark}] {result.name}" + (f" — {result.detail}" if result.detail else ""))
    return "\n".join(lines)


def _python_blocks(markdown: str) -> list[tuple[str, str]]:
    return _fenced(markdown, "python")


def _lang_blocks(markdown: str) -> list[tuple[str, str]]:
    return [
        (name, code)
        for lang, name, code in _fenced_with_lang(markdown)
        if lang in ("", "groovy", "gremlin") and code.lstrip().startswith("g.")
    ]


def _fenced(markdown: str, language: str) -> list[tuple[str, str]]:
    return [(name, code) for lang, name, code in _fenced_with_lang(markdown) if lang == language]


def _fenced_with_lang(markdown: str) -> list[tuple[str, str, str]]:
    blocks: list[tuple[str, str, str]] = []
    section = ""
    fence: list[str] | None = None
    lang = ""
    for line in markdown.splitlines():
        if fence is not None:
            if line.strip().startswith("```"):
                blocks.append((lang, section, "\n".join(fence)))
                fence = None
            else:
                fence.append(line)
            continue
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        stripped = line.strip()
        if stripped.startswith("```"):
            fence = []
            lang = stripped[3:].strip().lower()
    return blocks
