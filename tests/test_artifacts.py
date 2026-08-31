"""Tests for the artifact-pinning vocabulary.

Interfaces: thalamus.artifacts.check_name, digest_and_size, check_digest, git_ref,
Registry.

The module owns no artifact kind, so every test here is about the vocabulary each
kind borrows: what a name may be, what a digest pairs with, what a duplicate costs,
and what a mismatch says.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from thalamus import artifacts


@dataclass(frozen=True)
class Row:
    name: str
    taken_at: str
    sha256: str
    note: str = ""


def a_row(name: str, sha: str = "a" * 64) -> Row:
    return Row(name=name, taken_at=artifacts.now(), sha256=sha)


# --- names ------------------------------------------------------------------


@pytest.mark.parametrize("name", ["exp008-wave1", "abc", "a" * 64, "a1-b2-c3"])
def test_accepts_a_citable_name(name):
    artifacts.check_name(name)


@pytest.mark.parametrize("name", ["", "ab", "a" * 65, "Exp008", "exp 008", "exp/008",
                                  "-leading", "exp_008", "exp.008"])
def test_refuses_a_name_that_would_be_quoted_wrong_somewhere(name):
    with pytest.raises(artifacts.ArtifactError, match="invalid pin name"):
        artifacts.check_name(name)


def test_the_message_names_the_kind_the_caller_asked_about():
    """A generic vocabulary that says 'pin name' to someone asking about a snapshot
    makes them translate."""
    with pytest.raises(artifacts.ArtifactError, match="invalid snapshot name"):
        artifacts.check_name("NOPE", noun="snapshot")


# --- digests ----------------------------------------------------------------


def test_check_digest_passes_when_the_bytes_are_unchanged():
    artifacts.check_digest("wave1", "a" * 64, "a" * 64)


def test_check_digest_reports_both_hashes_not_just_that_they_differ():
    with pytest.raises(artifacts.ArtifactError) as excinfo:
        artifacts.check_digest("wave1", "a" * 64, "b" * 64)
    message = str(excinfo.value)
    assert "aaaaaaaaaaaa" in message and "bbbbbbbbbbbb" in message


def test_check_digest_says_what_the_mismatch_means_for_this_operation():
    with pytest.raises(artifacts.ArtifactError, match="refusing to restore it"):
        artifacts.check_digest("wave1", "a" * 64, "b" * 64, noun="snapshot",
                             consequence="refusing to restore it")


# --- the registry -----------------------------------------------------------


def test_an_absent_ledger_reads_as_empty_not_as_an_error(tmp_path):
    reg = artifacts.Registry(tmp_path / "nothing-here.jsonl", Row)
    assert reg.rows() == [] and reg.names() == []


def test_append_then_read_round_trips(tmp_path):
    reg = artifacts.Registry(tmp_path / "pins.jsonl", Row)
    reg.append(a_row("one"))
    reg.append(a_row("two", sha="b" * 64))
    assert reg.names() == ["one", "two"]
    assert reg.find("two").sha256 == "b" * 64


def test_append_creates_the_parent_directory(tmp_path):
    reg = artifacts.Registry(tmp_path / "deep" / "down" / "pins.jsonl", Row)
    reg.append(a_row("one"))
    assert reg.path.is_file()


def test_the_ledger_is_one_json_object_per_line(tmp_path):
    """Append-only in the literal sense: a crashed write costs the last row, never
    the file."""
    reg = artifacts.Registry(tmp_path / "pins.jsonl", Row)
    reg.append(a_row("one"))
    reg.append(a_row("two"))
    lines = reg.path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["name"] == "one"


def test_blank_lines_in_the_ledger_are_skipped(tmp_path):
    path = tmp_path / "pins.jsonl"
    reg = artifacts.Registry(path, Row)
    reg.append(a_row("one"))
    path.write_text(path.read_text() + "\n\n")
    assert reg.names() == ["one"]


def test_a_duplicate_name_is_refused_before_the_artifact_is_made(tmp_path):
    reg = artifacts.Registry(tmp_path / "pins.jsonl", Row)
    reg.append(a_row("one"))
    with pytest.raises(artifacts.ArtifactError, match="already exists; pins are immutable"):
        reg.refuse_duplicate("one")


def test_the_duplicate_refusal_uses_the_kind_s_own_plural(tmp_path):
    reg = artifacts.Registry(tmp_path / "pins.jsonl", Row,
                           noun="snapshot", plural="snapshots")
    reg.append(a_row("one"))
    with pytest.raises(artifacts.ArtifactError, match="snapshot `one` already exists; "
                                               "snapshots are immutable"):
        reg.refuse_duplicate("one")


def test_a_free_name_is_not_refused(tmp_path):
    reg = artifacts.Registry(tmp_path / "pins.jsonl", Row)
    reg.append(a_row("one"))
    reg.refuse_duplicate("two")


def test_an_unknown_name_lists_what_is_registered(tmp_path):
    """A reader who mistyped a name needs to see the one they meant."""
    reg = artifacts.Registry(tmp_path / "pins.jsonl", Row)
    reg.append(a_row("one"))
    with pytest.raises(artifacts.ArtifactError, match="registered: one"):
        reg.find("won")


def test_an_unknown_name_against_an_empty_ledger_says_none(tmp_path):
    reg = artifacts.Registry(tmp_path / "pins.jsonl", Row)
    with pytest.raises(artifacts.ArtifactError, match="registered: none"):
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

    pins = artifacts.Registry(tmp_path / "pins.jsonl", Row)
    images = artifacts.Registry(tmp_path / "images.jsonl", ImageRow, noun="image",
                              plural="images")
    pins.append(a_row("one"))
    images.append(ImageRow("one", artifacts.now(), "c" * 64, 1150550016))

    assert pins.find("one").note == ""
    assert images.find("one").byte_size == 1150550016
    with pytest.raises(artifacts.ArtifactError, match="unknown image"):
        images.find("two")


# --- context ----------------------------------------------------------------


def test_now_is_utc_and_sorts_as_text():
    stamp = artifacts.now()
    assert stamp.endswith("+00:00")
    assert stamp[:4].isdigit()


def test_git_ref_of_this_checkout_is_a_short_sha(tmp_path):
    from pathlib import Path
    ref = artifacts.git_ref(Path(__file__).resolve().parent)
    assert ref != "unknown" and len(ref) >= 7


def test_git_ref_outside_a_repository_is_unknown_not_a_crash(tmp_path):
    """Advisory context, never identity — its absence must not stop a pin."""
    assert artifacts.git_ref(tmp_path) == "unknown"
