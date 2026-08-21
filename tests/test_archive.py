"""
Evidence-archive tests.

Interfaces: thalamus.archive.store.archive_bytes, read_archived, scan_for_secrets,
  report_secrets
Infrastructure: none; a tmp_path archive and a tmp_path findings log
Scope: immutability, content addressing, and the secret-warning surface — including
that a finding reaches a reader, since a scan that reports and never redacts is worth
exactly what its report is read on.
"""

import pytest

from thalamus.archive import (
    archive_bytes,
    read_archived,
    report_secrets,
    scan_for_secrets,
)


def test_archiving_is_content_addressed_and_idempotent(tmp_path):
    """
    Scenario: Archive the same transcript twice

    Verifications:
    - both calls land on the same hash and path
    - the second is reported as already present rather than rewritten

    Content addressing does three jobs at once: re-archiving is a no-op, tampering is
    detectable, and the hash is a stable node identity that does not depend on where the
    file happened to sit on disk.
    """
    payload = b'{"type":"user","message":{"content":"hello"}}\n'

    first = archive_bytes(payload, suffix=".jsonl", base=tmp_path)
    second = archive_bytes(payload, suffix=".jsonl", base=tmp_path)

    # Verifies: identity is the content, so re-archiving cannot duplicate or clobber
    assert first.content_hash == second.content_hash
    assert first.path == second.path
    assert not first.already_present
    assert second.already_present
    assert first.uri == f"archive://{first.content_hash}"


def test_reading_back_verifies_the_evidence_was_not_tampered_with(tmp_path):
    """
    Scenario: Retained evidence is modified on disk

    Verifications:
    - reading it back raises rather than silently returning altered evidence

    The archive is the floor of the provenance chain. Evidence that can be quietly
    rewritten is not evidence, so the read path re-hashes rather than trusting the name.
    """
    entry = archive_bytes(b"original evidence", suffix=".jsonl", base=tmp_path)
    assert read_archived(entry.content_hash, suffix=".jsonl", base=tmp_path) == b"original evidence"

    entry.path.write_bytes(b"tampered evidence")

    # Verifies: corruption surfaces loudly instead of poisoning the graph
    with pytest.raises(ValueError, match="Archive corruption"):
        read_archived(entry.content_hash, suffix=".jsonl", base=tmp_path)


def test_secret_scan_reports_credentials_without_redacting_them(tmp_path):
    """
    Scenario: A transcript contains what looks like a credential

    Verifications:
    - the scan names the pattern and counts the hits
    - the archived bytes are untouched

    This is a warning surface, not a gate. The archive is local and outside the repo, and
    silently rewriting evidence would defeat the point of retaining it — so the operator is
    told, and the operator decides.
    """
    payload = b"here is a key: AKIAIOSFODNN7EXAMPLE and another: ghp_" + b"a" * 36

    findings = scan_for_secrets(payload)
    entry = archive_bytes(payload, suffix=".jsonl", base=tmp_path)

    # Verifies: it names what it found
    assert findings["aws-access-key"] == 1
    assert findings["github-token"] == 1
    # Verifies: and changed nothing
    assert entry.path.read_bytes() == payload


def test_clean_content_reports_nothing():
    """
    Scenario: A transcript with no credentials in it

    Verifications:
    - the scan is quiet
    """
    # Verifies: no false alarm on ordinary prose
    assert scan_for_secrets(b"just some ordinary session text about graphs") == {}


def test_a_finding_reaches_both_surfaces(tmp_path, capsys):
    """
    Scenario: bytes with a credential in them, reported

    Verifications:
    - the summary names the subject and what was found
    - it goes to stderr, for a run someone is watching
    - and to the log, for the session-end path, which is detached and watched by nobody

    The scan reports and never redacts, so being told is the entire value of running
    it: findings computed and dropped are the same as no scan at all.
    """
    log = tmp_path / "secret-scan.log"

    line = report_secrets({"aws-access-key": 2}, "session abc12345 transcript",
                          log_path=log)

    assert "aws-access-key×2" in line
    assert "session abc12345 transcript" in line
    assert line in capsys.readouterr().err
    assert "session abc12345 transcript: aws-access-key×2" in log.read_text()


def test_a_clean_scan_writes_no_row(tmp_path, capsys):
    """The control, and the reason the log is worth reading.

    A log that also recorded every silence would bury the rows that matter under one
    per session, and the archive already records what was retained.
    """
    log = tmp_path / "secret-scan.log"

    assert report_secrets({}, "session def transcript", log_path=log) == ""
    assert not log.exists()
    assert capsys.readouterr().err == ""


def test_an_unwritable_log_does_not_take_down_the_archiving_path(tmp_path, capsys):
    """Reporting rides on paths that must complete. It degrades to stderr alone."""
    blocked = tmp_path / "not-a-dir" / "secret-scan.log"
    (tmp_path / "not-a-dir").write_text("this is a file, not a directory")

    line = report_secrets({"openai-key": 1}, "ingested document https://x/y",
                          log_path=blocked)

    assert "openai-key×1" in line
    assert line in capsys.readouterr().err
