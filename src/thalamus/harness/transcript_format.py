"""Checking a Claude Code transcript against what distillation's readers assume of it.

Claude Code's transcript is not a documented format, and the readers in
`transcripts.py` and `extraction.py` rest on a dozen facts about it that nothing in this
repository keeps true: which record types carry turns, which shapes content takes, which
flags mark a record as the harness talking rather than the operator, how compaction
lays the file out. A release that changes one of them does not fail anything. The
readers skip what they do not recognise, so a renamed field is a session that distils
thinner, and a new kind of user record is the operator credited with words the harness
wrote — which is what the compaction summary was until `is_compaction_summary` existed.

So this module states those facts as rules and checks a transcript against them. Each
rule is a reader's dependence, named for what breaks when it fails, and nothing else is
checked: a field no reader touches can change freely without a finding, because a
validator that reports every change trains its reader to stop reading it. Alerting on
broad difference measures is the documented failure of data validation at scale
(Shankar et al., arXiv:2303.06094, after Breck et al.); the rules here are the
consumer's declared expectations instead, the narrower check.

What that leaves out is the case the compaction summary was: a field the readers never
read *added* to a record they do read, changing what it means. A check of the consumed
fields passes it by construction. `operator-voice` covers it the only way it can be
covered, as a closed world: every record a reader would take for the operator's words
is checked for discriminators — origin values and true boolean flags — outside the set
measured as meaning "the operator said this", so a new one is a finding until someone
decides what it means and updates the set or the readers.

The sets are measured, not documented. They were taken from every transcript under
`~/.claude/projects` on 2026-10-18, Claude Code 2.1.263 to 2.1.302.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from thalamus.harness.transcripts import archived_snapshots, is_compaction_summary

FORMAT_LOG = Path.home() / ".thalamus" / "logs" / "transcript-format.log"

# Block types a user or assistant record's content list carries. The readers consume
# `text`, `tool_use` and `tool_result`, and drop the rest on purpose: `thinking` is not
# the conversation, and `fallback` (2.1.211) records only a model switch, `from` and
# `to`. A type outside these is content every reader drops without having decided to.
KNOWN_BLOCK_TYPES = {
    "user": frozenset({"text", "tool_result", "image", "document"}),
    "assistant": frozenset({"text", "tool_use", "thinking", "redacted_thinking", "fallback"}),
}

# Values Claude Code writes on a record of the operator speaking. `origin.kind` and
# `turnOrigin` say who produced the turn, `promptSource` how it was entered. Records
# from a peer session or a task notification carry other values and are `isMeta` or
# open with a tag, so the readers already skip them.
VOICE_ORIGIN_KINDS = frozenset({"human"})
VOICE_TURN_ORIGINS = frozenset({"human", "sdk"})
VOICE_PROMPT_SOURCES = frozenset({"typed", "suggestion_accepted", "queued", "sdk"})

# True boolean flags measured on records the readers take for the operator, and which
# do not change that reading. The queue flags describe how a queued prompt was
# delivered; `stackedExpansion` (2.1.204) rides on a slash command the operator typed
# with its arguments.
VOICE_NEUTRAL_FLAGS = frozenset({
    # With these sets the rules find nothing on the corpus they were measured on, and
    # find every compaction summary when the readers' skip of it is removed
    # (A0232, cites-as-live).
    "queueSkipSlashCommands", "queueSkipAttachments", "stackedExpansion",
})

# A rule's name says which dependence it checks, so a finding names what it breaks.
RULES = {
    "content-shape": "a turn record's message content is a string or a list",
    "block-type": "every content block is of a type the readers have decided about",
    "tool-fields": "tool_use carries id, name and input; tool_result carries tool_use_id",
    "tool-linkage": "a tool_result answers a tool_use earlier in the same file",
    "envelope": "a turn record carries a uuid and a parseable timestamp",
    "operator-voice": "a record read as the operator carries only operator discriminators",
    "compaction": "a compaction appends: its boundary's parent and kept turns precede it, "
                  "and the summary that follows it is flagged",
}


@dataclass(frozen=True)
class Finding:
    """One record that breaks one rule."""

    rule: str
    line: int
    version: str
    detail: str


@dataclass
class FileReport:
    """What checking one transcript found, with the denominator beside it."""

    path: Path
    records: int = 0
    versions: set[str] = field(default_factory=set)
    findings: list[Finding] = field(default_factory=list)


def _skipped(record: dict) -> bool:
    """What every reader skips before treating a record as a turn."""
    return bool(record.get("isSidechain") or record.get("isMeta")
                or is_compaction_summary(record))


def _operator_text(record: dict) -> str:
    """The text a reader would take for the operator's words, empty when there is none.

    The readers' own test: a user record not skipped above, whose string content (or
    text block) does not open with a tag — tags are harness scaffolding — except a
    slash-command invocation, which `parse` counts as the operator's turn.
    """
    if record.get("type") != "user" or _skipped(record):
        return ""
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        texts = [content]
    elif isinstance(content, list):
        texts = [block.get("text", "") for block in content
                 if isinstance(block, dict) and block.get("type") == "text"]
    else:
        texts = []
    for text in texts:
        stripped = text.strip() if isinstance(text, str) else ""
        if stripped and (not stripped.startswith("<") or "<command-name>" in stripped[:200]):
            return stripped
    return ""


def _parses(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _voice_findings(record: dict) -> list[str]:
    problems = []
    origin = record.get("origin")
    if isinstance(origin, dict) and origin.get("kind") not in VOICE_ORIGIN_KINDS:
        problems.append(f"origin.kind {origin.get('kind')!r}")
    elif origin is not None and not isinstance(origin, dict):
        problems.append(f"origin {origin!r}")
    if "turnOrigin" in record and record["turnOrigin"] not in VOICE_TURN_ORIGINS:
        problems.append(f"turnOrigin {record['turnOrigin']!r}")
    if "promptSource" in record and record["promptSource"] not in VOICE_PROMPT_SOURCES:
        problems.append(f"promptSource {record['promptSource']!r}")
    flags = sorted(key for key, value in record.items()
                   if value is True and key not in VOICE_NEUTRAL_FLAGS)
    problems += [f"flag {key}" for key in flags]
    return problems


def check_records(lines: Iterable[str]) -> FileReport:
    """Check one transcript's lines. `check_transcript` is the entry from a path."""
    report = FileReport(path=Path())
    uuids_before: set[str] = set()
    tool_uses: set[str] = set()
    # A boundary's kept turns must not be written again after it; the set is filled
    # when a boundary is read and checked against every later record's uuid.
    preserved: set[str] = set()
    expect_summary_at: int | None = None

    for number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        report.records += 1
        version = record.get("version") if isinstance(record.get("version"), str) else ""
        if version:
            report.versions.add(version)

        def find(rule: str, detail: str) -> None:
            report.findings.append(Finding(rule, number, version, detail))

        kind = record.get("type")
        uuid = record.get("uuid") if isinstance(record.get("uuid"), str) else ""

        if uuid and uuid in preserved:
            find("compaction", f"kept turn {uuid[:8]} written again after its boundary")

        if expect_summary_at is not None and kind == "user":
            if not is_compaction_summary(record):
                find("compaction", f"the first user record after the boundary on line "
                                   f"{expect_summary_at} is not flagged isCompactSummary")
            expect_summary_at = None

        # The boundary's `logicalParentUuid` is not checked: after a manual /compact on
        # 2.1.302 it named a record the file never held, while the file before the
        # compaction was a byte prefix of the file after it.
        if kind == "system" and record.get("subtype") == "compact_boundary":
            kept = ((record.get("compactMetadata") or {}).get("preservedMessages") or {})
            for kept_uuid in kept.get("uuids") or []:
                if isinstance(kept_uuid, str) and kept_uuid not in uuids_before:
                    find("compaction", f"kept turn {kept_uuid[:8]} is not earlier "
                                       "in the file")
                preserved.add(kept_uuid)
            expect_summary_at = number

        if uuid:
            uuids_before.add(uuid)

        if kind not in ("user", "assistant") or record.get("isSidechain"):
            continue

        if not uuid:
            find("envelope", f"{kind} record has no uuid")
        if not _parses(record.get("timestamp")):
            find("envelope", f"{kind} record's timestamp {record.get('timestamp')!r} "
                             "does not parse")

        content = (record.get("message") or {}).get("content")
        if not isinstance(content, (str, list)):
            find("content-shape", f"{kind} content is {type(content).__name__}")
            continue

        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                find("block-type", f"{kind} content block is {type(block).__name__}")
                continue
            block_type = block.get("type")
            if block_type not in KNOWN_BLOCK_TYPES[kind]:
                find("block-type", f"{kind} block type {block_type!r}")
            elif block_type == "tool_use":
                if not (isinstance(block.get("id"), str) and isinstance(block.get("name"), str)
                        and isinstance(block.get("input"), dict)):
                    find("tool-fields", "tool_use lacks a string id, a string name or a "
                                        "dict input")
                elif not record.get("isMeta"):
                    tool_uses.add(block["id"])
            elif block_type == "tool_result":
                use_id = block.get("tool_use_id")
                if not isinstance(use_id, str):
                    find("tool-fields", "tool_result lacks a string tool_use_id")
                elif use_id not in tool_uses:
                    find("tool-linkage", f"tool_result for {use_id[:16]} answers no "
                                         "earlier tool_use")

        if _operator_text(record):
            for problem in _voice_findings(record):
                find("operator-voice", f"a record read as the operator carries {problem}")

    return report


def check_transcript(path: Path) -> FileReport:
    """Check one transcript file against every rule."""
    with path.open(errors="ignore") as handle:
        report = check_records(handle)
    report.path = path
    return report


def check_snapshots(archive_base: Path | None = None) -> tuple[int, list[str]]:
    """The append-only rule tested directly, where the archive holds the evidence.

    One file cannot show that nothing was removed from it. Two retained snapshots of
    one session can: the earlier must be a byte prefix of the later, or the harness
    rewrote what it had written. Returns how many pairs were compared, beside the
    sessions whose pair was not a prefix.
    """
    pairs = 0
    broken: list[str] = []
    for session_id, paths in archived_snapshots(archive_base).items():
        for earlier, later in zip(paths, paths[1:]):
            pairs += 1
            if not later.read_bytes().startswith(earlier.read_bytes()):
                broken.append(f"session {session_id[:8]}: {earlier.name[:12]} is not a "
                              f"prefix of {later.name[:12]}")
    return pairs, broken


def summarise(findings: list[Finding]) -> list[str]:
    """One line per distinct finding, with its count and the first line it was on."""
    grouped: dict[tuple[str, str], list[Finding]] = {}
    for finding in findings:
        grouped.setdefault((finding.rule, finding.detail), []).append(finding)
    return [
        f"{rule}: {detail} ({len(hits)}×, first on line {hits[0].line}"
        f"{', ' + hits[0].version if hits[0].version else ''})"
        for (rule, detail), hits in grouped.items()
    ]


def report_findings(report: FileReport, subject: str, *, log_path: Path | None = None) -> str:
    """Surface one transcript's findings on the distillation path. Empty when clean.

    The same shape as `report_secrets`: a dated row per finding in `FORMAT_LOG` and the
    summary on stderr, so a detached SessionEnd run leaves the record where `thalamus
    contract check --transcripts` points. It reports and never refuses: a finding says
    a reader may have misread the session, not that the session is unusable, and a
    distillation it stopped would be lost to the same release it detected
    (A0231, cites-as-live).
    """
    if not report.findings:
        return ""
    lines = summarise(report.findings)
    path = log_path or FORMAT_LOG
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with path.open("a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(f"{stamp} {subject} {report.path}: {line}\n")
    except OSError:
        # An unwritable log must not take down the distillation it rides on; the stderr
        # lines below still carry every finding.
        pass
    summary = (f"⚠ transcript format — {subject}: {len(report.findings)} record(s) break "
               f"an assumption distillation reads them by")
    print(summary, file=sys.stderr)
    for line in lines:
        print(f"    {line}", file=sys.stderr)
    return summary
