"""Tests for the artifact-snapshot vocabulary.

Interfaces: thalamus.snapshotting.check_name, digest_and_size, check_digest, git_ref,
Registry.

The module owns no artifact kind, so every test here is about the vocabulary each
kind borrows: what a name may be, what a digest pairs with, what a duplicate costs,
and what a mismatch says.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from thalamus import snapshotting


@dataclass(frozen=True)
class Row:
    name: str
    taken_at: str
    sha256: str
    note: str = ""


def a_row(name: str, sha: str = "a" * 64) -> Row:
    return Row(name=name, taken_at=snapshotting.now(), sha256=sha)


# --- names ------------------------------------------------------------------


@pytest.mark.parametrize("name", ["exp008-wave1", "abc", "a" * 64, "a1-b2-c3"])
def test_accepts_a_citable_name(name):
    snapshotting.check_name(name)


@pytest.mark.parametrize("name", ["", "ab", "a" * 65, "Exp008", "exp 008", "exp/008",
                                  "-leading", "exp_008", "exp.008"])
def test_refuses_a_name_that_would_be_quoted_wrong_somewhere(name):
    with pytest.raises(snapshotting.SnapshotError, match="invalid snapshot name"):
        snapshotting.check_name(name)


def test_the_message_names_the_kind_the_caller_asked_about():
    """A vocabulary that says 'snapshot name' to someone asking about a VM image
    makes them translate."""
    with pytest.raises(snapshotting.SnapshotError, match="invalid image name"):
        snapshotting.check_name("NOPE", noun="image")


# --- digests ----------------------------------------------------------------


def test_check_digest_passes_when_the_bytes_are_unchanged():
    snapshotting.check_digest("wave1", "a" * 64, "a" * 64)


def test_check_digest_reports_both_hashes_not_just_that_they_differ():
    with pytest.raises(snapshotting.SnapshotError) as excinfo:
        snapshotting.check_digest("wave1", "a" * 64, "b" * 64)
    message = str(excinfo.value)
    assert "aaaaaaaaaaaa" in message and "bbbbbbbbbbbb" in message


def test_check_digest_says_what_the_mismatch_means_for_this_operation():
    with pytest.raises(snapshotting.SnapshotError, match="refusing to restore it"):
        snapshotting.check_digest("wave1", "a" * 64, "b" * 64, noun="snapshot",
                             consequence="refusing to restore it")


# --- the registry -----------------------------------------------------------


def test_an_absent_ledger_reads_as_empty_not_as_an_error(tmp_path):
    reg = snapshotting.Registry(tmp_path / "nothing-here.jsonl", Row)
    assert reg.rows() == [] and reg.names() == []


def test_append_then_read_round_trips(tmp_path):
    reg = snapshotting.Registry(tmp_path / "snapshots.jsonl", Row)
    reg.append(a_row("one"))
    reg.append(a_row("two", sha="b" * 64))
    assert reg.names() == ["one", "two"]
    assert reg.find("two").sha256 == "b" * 64


def test_append_creates_the_parent_directory(tmp_path):
    reg = snapshotting.Registry(tmp_path / "deep" / "down" / "snapshots.jsonl", Row)
    reg.append(a_row("one"))
    assert reg.path.is_file()


def test_the_ledger_is_one_json_object_per_line(tmp_path):
    """Append-only in the literal sense: a crashed write costs the last row, never
    the file."""
    reg = snapshotting.Registry(tmp_path / "snapshots.jsonl", Row)
    reg.append(a_row("one"))
    reg.append(a_row("two"))
    lines = reg.path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["name"] == "one"


def test_blank_lines_in_the_ledger_are_skipped(tmp_path):
    path = tmp_path / "snapshots.jsonl"
    reg = snapshotting.Registry(path, Row)
    reg.append(a_row("one"))
    path.write_text(path.read_text() + "\n\n")
    assert reg.names() == ["one"]


def test_a_duplicate_name_is_refused_before_the_artifact_is_made(tmp_path):
    reg = snapshotting.Registry(tmp_path / "snapshots.jsonl", Row)
    reg.append(a_row("one"))
    with pytest.raises(snapshotting.SnapshotError, match="already exists; snapshots are immutable"):
        reg.refuse_duplicate("one")


def test_the_duplicate_refusal_uses_the_kind_s_own_plural(tmp_path):
    reg = snapshotting.Registry(tmp_path / "images.jsonl", Row,
                                noun="image", plural="images")
    reg.append(a_row("one"))
    with pytest.raises(snapshotting.SnapshotError,
                       match="image `one` already exists; images are immutable"):
        reg.refuse_duplicate("one")


def test_a_free_name_is_not_refused(tmp_path):
    reg = snapshotting.Registry(tmp_path / "snapshots.jsonl", Row)
    reg.append(a_row("one"))
    reg.refuse_duplicate("two")


def test_an_unknown_name_lists_what_is_registered(tmp_path):
    """A reader who mistyped a name needs to see the one they meant."""
    reg = snapshotting.Registry(tmp_path / "snapshots.jsonl", Row)
    reg.append(a_row("one"))
    with pytest.raises(snapshotting.SnapshotError, match="registered: one"):
        reg.find("won")


def test_an_unknown_name_against_an_empty_ledger_says_none(tmp_path):
    reg = snapshotting.Registry(tmp_path / "snapshots.jsonl", Row)
    with pytest.raises(snapshotting.SnapshotError, match="registered: none"):
        reg.find("one")


def test_two_kinds_keep_their_own_row_shapes_and_their_own_ledgers(tmp_path):
    """The reason this module holds no row type of its own: the fields worth
    recording differ per kind, and one table would make each carry the others'."""

    @dataclass(frozen=True)
    class ImageRow:
        name: str
        taken_at: str
        sha256: str
        byte_size: int

    pins = snapshotting.Registry(tmp_path / "snapshots.jsonl", Row)
    images = snapshotting.Registry(tmp_path / "images.jsonl", ImageRow, noun="image",
                              plural="images")
    pins.append(a_row("one"))
    images.append(ImageRow("one", snapshotting.now(), "c" * 64, 1150550016))

    assert pins.find("one").note == ""
    assert images.find("one").byte_size == 1150550016
    with pytest.raises(snapshotting.SnapshotError, match="unknown image"):
        images.find("two")


# --- context ----------------------------------------------------------------


def test_now_is_utc_and_sorts_as_text():
    stamp = snapshotting.now()
    assert stamp.endswith("+00:00")
    assert stamp[:4].isdigit()


def test_git_ref_of_this_checkout_is_a_short_sha(tmp_path):
    from pathlib import Path
    ref = snapshotting.git_ref(Path(__file__).resolve().parent)
    assert ref != "unknown" and len(ref) >= 7


def test_git_ref_outside_a_repository_is_unknown_not_a_crash(tmp_path):
    """Advisory context, never identity — its absence must not stop a pin."""
    assert snapshotting.git_ref(tmp_path) == "unknown"
