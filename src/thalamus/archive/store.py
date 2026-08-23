"""Content-addressed storage for retained primary evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ARCHIVE_DIR = Path.home() / ".thalamus" / "archive"

ARCHIVE_SCHEME = "archive://"


@dataclass(frozen=True)
class ArchiveEntry:
    content_hash: str
    path: Path
    byte_size: int
    already_present: bool

    @property
    def uri(self) -> str:
        return f"{ARCHIVE_SCHEME}{self.content_hash}"


def archive_dir() -> Path:
    """Where retained evidence lives. Outside the repo, deliberately."""
    override = os.environ.get("THALAMUS_ARCHIVE_DIR")
    return Path(override) if override else DEFAULT_ARCHIVE_DIR


def index_dir() -> Path:
    """Where mutable indexes over the archive live — beside it, never inside it.

    Derived from `archive_dir()` rather than given its own override, because an index
    of content hashes is worthless against a different archive: point the archive
    somewhere else and the index that belongs to it follows. Kept outside because
    `arch.growth` walks the archive root and counts everything unreferenced by a Source
    as stray retained bytes, which an index file is not.
    """
    return archive_dir().parent / "index"


FETCH_INDEX = "fetched.jsonl"


@dataclass(frozen=True)
class FetchRecord:
    """One verified fetch, keyed by the address that was asked for.

    Not content addressing and deliberately not immutable: the same URL serves
    different bytes over time, so this is last-writer-wins and every read carries `at`
    so the caller can decide whether the record is still worth anything.
    """

    location: str
    origin: str
    content_hash: str
    suffix: str
    content_type: str
    at: datetime

    def age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.at).total_seconds()


def record_fetch(
    *,
    location: str,
    origin: str,
    content_hash: str,
    suffix: str,
    content_type: str,
    base: Path | None = None,
) -> Path | None:
    """Index a fetch so a later run can ingest the bytes that were verified.

    Append-only, one row per fetch. An unwritable index costs a re-fetch and nothing
    else, so it never takes down the run that was retaining evidence.
    """
    path = (base or index_dir()) / FETCH_INDEX
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "location": location,
                        "origin": origin,
                        "content_hash": content_hash,
                        "suffix": suffix,
                        "content_type": content_type,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        return None
    return path


def recall_fetch(location: str, *, base: Path | None = None) -> FetchRecord | None:
    """The most recent indexed fetch of `location`, or None.

    Last row wins: a URL re-fetched today is not the URL fetched last month, and the
    older rows are kept only so the sequence is auditable. A malformed row is skipped
    rather than raised on — the index is an optimization, and a corrupt line must cost
    a re-fetch, never an ingest.
    """
    path = (base or index_dir()) / FETCH_INDEX
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for line in reversed(lines):
        try:
            row = json.loads(line)
            if row.get("location") != location:
                continue
            return FetchRecord(
                location=location,
                origin=str(row["origin"]),
                content_hash=str(row["content_hash"]),
                suffix=str(row.get("suffix") or ""),
                content_type=str(row.get("content_type") or ""),
                at=datetime.strptime(row["at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                ),
            )
        except (ValueError, KeyError, TypeError):
            continue
    return None


def archive_bytes(payload: bytes, *, suffix: str = "", base: Path | None = None) -> ArchiveEntry:
    """Retain bytes under their sha256. Idempotent, and never overwrites.

    Content addressing does three jobs at once: re-archiving the same transcript is a
    no-op, tampering is detectable, and the hash is a stable node identity that does not
    depend on where the file happened to sit on disk.
    """
    root = base or archive_dir()
    content_hash = hashlib.sha256(payload).hexdigest()

    # Shard by the first two chars — one flat directory of thousands of files ages badly.
    destination = root / content_hash[:2] / f"{content_hash}{suffix}"
    if destination.exists():
        return ArchiveEntry(content_hash, destination, len(payload), already_present=True)

    destination.parent.mkdir(parents=True, exist_ok=True)
    # Write-then-rename: a crash mid-write must not leave a corrupt file at a hash that
    # claims to describe it.
    staging = destination.with_suffix(destination.suffix + ".partial")
    staging.write_bytes(payload)
    staging.rename(destination)
    return ArchiveEntry(content_hash, destination, len(payload), already_present=False)


def read_archived(content_hash: str, *, suffix: str = "", base: Path | None = None) -> bytes:
    """Read retained bytes back, verifying they still hash to their name."""
    root = base or archive_dir()
    path = root / content_hash[:2] / f"{content_hash}{suffix}"
    payload = path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != content_hash:
        raise ValueError(
            f"Archive corruption: {path} hashes to {actual}, not {content_hash}. "
            "Retained evidence is supposed to be immutable."
        )
    return payload


# Deliberately coarse. This reports; it does not redact — the archive is *evidence*, and
# evidence that has been quietly rewritten is not evidence. The operator decides.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9]{32,}")),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("hf-token", re.compile(r"hf_[A-Za-z0-9]{34,}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("wireguard-key", re.compile(r"(?i)privatekey\s*=\s*[A-Za-z0-9+/]{42,44}=")),
    # Signed licence files for commercial databases. The marker is the header
    # line, not the key body, so this fires on the file even when the signature
    # itself has been trimmed out of a transcript.
    ("license-feature-key", re.compile(r"feature-key-version")),
    ("generic-bearer", re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9\-._~+/]{20,}")),
)


def scan_for_secrets(payload: bytes) -> dict[str, int]:
    """Report likely credentials in retained evidence. Returns pattern -> hit count.

    Transcripts contain whatever was on screen, which is why this exists. It is a warning
    surface, not a gate: the archive is local-only and outside the repo, and silently
    rewriting evidence would defeat the purpose of retaining it.
    """
    try:
        text = payload.decode("utf-8", errors="ignore")
    except Exception:  # pragma: no cover - decode with errors='ignore' does not raise
        return {}

    findings: dict[str, int] = {}
    for name, pattern in _SECRET_PATTERNS:
        hits = len(pattern.findall(text))
        if hits:
            findings[name] = hits
    return findings


# Where a finding goes when nobody is watching the terminal. Session-end distillation is
# detached and its stderr is nobody's tail, so a warning that only printed would be a
# warning only the interactive paths ever got — and the recurring path is the one that
# archives on every session.
SECRET_LOG = Path.home() / ".thalamus" / "logs" / "secret-scan.log"


def report_secrets(findings: dict[str, int], subject: str, *,
                   log_path: Path | None = None) -> str:
    """Surface a scan's findings. Returns the one-line summary, empty when clean.

    The scan reports and never redacts (see `scan_for_secrets`), so its entire value is
    that a person is told — which makes "computed and dropped" the same as not scanning.
    Every path that archives bytes calls this with what it found, and the call is the
    consumer: it writes a dated row to `SECRET_LOG` and prints to stderr, so an
    interactive run says it now and a detached one leaves it where `subject` can be
    matched back to the archived bytes.

    Clean input writes nothing. A log that also recorded the silences would bury the
    rows worth reading, and the archive itself already records what was retained.
    """
    if not findings:
        return ""
    detail = ", ".join(f"{name}×{hits}" for name, hits in sorted(findings.items()))
    line = f"⚠ possible credentials in retained bytes — {subject}: {detail}"

    path = log_path or SECRET_LOG
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {subject}: {detail}\n")
    except OSError:
        # An unwritable log must not take down the archiving path it rides on. The
        # stderr line below is still delivered, so the finding is never lost silently.
        pass

    print(line, file=sys.stderr)
    return line


# Rejected extraction objects, retained beside the batch they left. A rejection is the
# one part of a paid extraction that used to leave no trace at all, which is what made
# "is the claim-kind vocabulary adequate?" a question with no data behind it. One file
# across every scope, deliberately: all nine manifests declare an identical claim-kind
# pair today, so a schema weakness would appear identically in nine unjoined logs and
# the dominant signal would be the one thing per-scope files hide.
REJECT_LOG = Path.home() / ".thalamus" / "logs" / "rejected-claims.jsonl"


def record_rejections(
    rows: list[dict],
    *,
    scope: str,
    content_hash: str,
    origin: str,
    log_path: Path | None = None,
) -> Path | None:
    """Append rejected extraction objects to the ledger. Returns the path, or None.

    Rows are plain dicts so this stays below the contract — the archive knows bytes and
    provenance, not claim kinds. `content_hash` joins a row back to the retained
    document, so a re-read of what was rejected never depends on the graph having
    accepted anything.

    An unwritable ledger must not take down the ingest riding on it: the CLI reports
    every rejection to the operator either way, and this is the durable copy rather
    than the only one.
    """
    if not rows:
        return None
    path = log_path or REJECT_LOG
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(
                    json.dumps(
                        {
                            "at": stamp,
                            "scope": scope,
                            "content_hash": content_hash,
                            "origin": origin,
                            **row,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    except OSError:
        return None
    return path
