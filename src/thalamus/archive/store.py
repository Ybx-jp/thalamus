"""Content-addressed storage for retained primary evidence."""

from __future__ import annotations

import hashlib
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
