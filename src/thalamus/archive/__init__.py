"""The evidence archive: immutable, content-addressed primary sources.

Thalamus **owns the bytes**. It does not reference a file it does not control — Claude
Code rotates and compacts its own transcripts, so `~/.claude/projects/` is not durable
storage and a pointer into it would rot.

Why this exists at all, in one line each:

- **It gives the provenance chain a floor.** A tier-1 claim's source is a Session, whose
  stored content is a *summary* — a distillation of itself. The provenance inspector has
  to land on evidence, not on another summary.
- **It makes extraction reversible.** Forgetting must be "archival, never deletion —
  reversible and auditable", but *extraction* is today lossy and irreversible.
  With the archive, the graph becomes a materialized view over an immutable log: if the
  view is wrong — bad skill, better model, changed schema — rebuild it.
- **The eval loop needs it.** Layer 1 defines used-vs-ignored as matching
  retrieved content against *the session's outputs*. The session's outputs are the
  transcript. Without it, layer 1 cannot be computed at all.

The archive lives OUTSIDE the repository (`~/.thalamus/archive/` by default). Transcripts
are the highest-risk artifact in the project — they contain whatever was on screen,
including credentials — and a `.gitignore` is one `git add -f` away from a bad day.
"""

from thalamus.archive.store import (
    DEFAULT_ARCHIVE_DIR,
    REJECT_LOG,
    SECRET_LOG,
    ArchiveEntry,
    archive_bytes,
    archive_dir,
    read_archived,
    record_rejections,
    report_secrets,
    scan_for_secrets,
)

__all__ = [
    "DEFAULT_ARCHIVE_DIR",
    "REJECT_LOG",
    "SECRET_LOG",
    "ArchiveEntry",
    "archive_bytes",
    "archive_dir",
    "read_archived",
    "record_rejections",
    "report_secrets",
    "scan_for_secrets",
]
