"""Interfaces: thalamus.arch.growth
Infrastructure: none — directories are built in tmp_path; the graph is a stub
Scope: the robust rate estimator, the series reconstructed from `ingested_at`, and the
       stock audit's accounting (hardlinks, blocks, unreferenced blobs).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from thalamus.arch import growth


class _Values:
    def __init__(self, values):
        self._values = values

    def to_list(self):
        return list(self._values)


class _Vertices:
    """Enough of a traversal to answer the two reads this module makes."""

    def __init__(self, stamps=(), hashes=()):
        self._stamps = stamps
        self._hashes = hashes
        self._label = None

    def has_label(self, label):
        self._label = label
        return self

    def values(self, name):
        if name == "ingested_at":
            return _Values(self._stamps)
        if name == "content_hash":
            return _Values(self._hashes)
        raise AssertionError(f"unexpected property read: {name}")


class _Graph:
    def __init__(self, stamps=(), hashes=()):
        self._stamps = stamps
        self._hashes = hashes

    def V(self):
        return _Vertices(self._stamps, self._hashes)


def test_sens_slope_is_the_median_of_pairwise_slopes():
    points = [(0.0, 0.0), (1.0, 2.0), (2.0, 4.0), (3.0, 6.0)]
    assert growth.sens_slope(points) == 2.0


def test_sens_slope_survives_one_bad_reading_where_least_squares_does_not():
    """Robust to a mismeasured point — which is the guarantee, and the limit of it.

    A single wrong reading moves only the pairs that involve it, so the median of
    pairwise slopes is untouched while least squares is dragged. What this does NOT
    promise is immunity to a genuine step: if the series really does jump and stay
    jumped, the trend really has risen and the estimator says so. That distinction is
    why the archive's 6.9 MB/day lifetime rate and its 25.9 MB/day recent burst are
    both true and are reported separately rather than averaged.
    """
    steady = [(float(day), float(day * 10)) for day in range(10)]
    misread = [*steady[:5], (5.0, 5000.0), *steady[6:]]

    assert growth.sens_slope(steady) == 10.0
    assert growth.sens_slope(misread) == 10.0

    def least_squares(points):
        n = len(points)
        mean_x = sum(x for x, _ in points) / n
        mean_y = sum(y for _, y in points) / n
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in points)
        return numerator / sum((x - mean_x) ** 2 for x, _ in points)

    assert least_squares(steady) == pytest.approx(10.0)
    # Four times the true rate, from one bad point sitting at the series' midpoint
    # where its leverage is lowest. Nearer either end it distorts further.
    assert least_squares(misread) > 3 * least_squares(steady)


def test_sens_slope_reports_a_real_step_as_a_real_rise():
    """A burst that persists is not an outlier, and must not be smoothed away."""
    flat = [(float(day), float(day * 10)) for day in range(6)]
    stepped = flat + [(float(day), float(50 + (day - 5) * 200)) for day in range(6, 12)]
    assert growth.sens_slope(stepped) > growth.sens_slope(flat)


def test_sens_slope_is_zero_without_two_distinct_points():
    assert growth.sens_slope([]) == 0.0
    assert growth.sens_slope([(1.0, 5.0)]) == 0.0
    assert growth.sens_slope([(1.0, 5.0), (1.0, 9.0)]) == 0.0


def test_graph_series_reconstructs_a_cumulative_series_from_stamps():
    """No new recording: every vertex already dates itself."""
    stamps = (
        ["2026-06-01T10:00:00+00:00"] * 3
        + ["2026-06-02T10:00:00+00:00"] * 2
        + ["2026-06-04T10:00:00+00:00"] * 5
    )
    series = growth.graph_series(_Graph(stamps=stamps))
    assert series == [(0, 3), (1, 5), (3, 10)]


def test_graph_series_skips_unstamped_vertices_rather_than_dating_them_zero():
    series = growth.graph_series(_Graph(stamps=["2026-06-01T00:00:00", "", None]))
    assert series == [(0, 1)]


def test_headline_reports_lifetime_and_recent_rates():
    stamps = []
    for day in range(1, 41):
        # 1/day for the first 20 days, 5/day after — a rate that rises.
        count = 1 if day <= 20 else 5
        stamps += [f"2026-06-{day:02d}T00:00:00"] * count if day <= 30 else []
    for day in range(1, 11):
        stamps += [f"2026-07-{day:02d}T00:00:00"] * 5

    found = growth.headline(_Graph(stamps=stamps))

    assert found is not None
    assert found.recent_per_day > found.lifetime_per_day
    assert found.accelerating
    assert "rate rising" in " ".join(found.lines())


def test_headline_is_none_without_a_series():
    assert growth.headline(_Graph(stamps=[])) is None
    assert growth.headline(_Graph(stamps=["2026-06-01T00:00:00"])) is None


def test_headline_does_not_claim_acceleration_on_a_steady_rate():
    stamps = [f"2026-06-{day:02d}T00:00:00" for day in range(1, 29) for _ in range(3)]
    found = growth.headline(_Graph(stamps=stamps))
    assert found is not None
    assert not found.accelerating
    assert "rate rising" not in " ".join(found.lines())


def test_directory_bytes_charges_a_hardlinked_file_once(tmp_path):
    """1.2 GB against a true 894 MB was this bug; the fixture is the same shape."""
    root = tmp_path / "tree"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    payload = b"x" * 8192
    original = root / "a" / "blob"
    original.write_bytes(payload)
    os.link(original, root / "b" / "blob")

    doubled = sum(item.stat().st_size for item in root.rglob("*") if item.is_file())
    assert doubled == 2 * len(payload)

    counted = growth._directory_bytes(root)
    assert counted < doubled
    assert counted >= len(payload)


def test_directory_bytes_shares_its_seen_set_across_directories(tmp_path):
    """A blob hardlinked into two orphans is recovered once, so it is charged once."""
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    original = first / "blob"
    original.write_bytes(b"y" * 4096)
    os.link(original, second / "blob")

    seen: set[tuple[int, int]] = set()
    charged_first = growth._directory_bytes(first, seen)
    charged_second = growth._directory_bytes(second, seen)

    assert charged_first > 0
    assert charged_second == 0


def test_orphan_worktrees_skips_the_ones_git_still_tracks(tmp_path, monkeypatch):
    root = tmp_path / "wt"
    tracked = root / "kept"
    stray = root / "left-behind"
    for path in (tracked, stray):
        path.mkdir(parents=True)
        (path / "file").write_bytes(b"z" * 2048)

    monkeypatch.setattr(growth, "registered_worktrees", lambda repo: {str(tracked)})

    found = growth.orphan_worktrees(tmp_path, root=root)

    assert [orphan.path for orphan in found] == [str(stray)]
    assert found[0].kind == "worktree"
    assert "does not track" in found[0].note


def test_orphan_worktrees_is_empty_when_the_root_does_not_exist(tmp_path):
    assert growth.orphan_worktrees(tmp_path, root=tmp_path / "nope") == []


def test_orphan_blobs_reports_only_what_no_source_cites(tmp_path):
    archive = tmp_path / "archive"
    (archive / "ab").mkdir(parents=True)
    (archive / "ab" / "abcdef.yaml").write_bytes(b"cited" * 100)
    (archive / "ab" / "abbbbb.yaml").write_bytes(b"stray" * 100)

    found = growth.orphan_blobs(_Graph(hashes=["abcdef"]), base=archive)

    assert len(found) == 1
    assert found[0].kind == "archive"
    assert "1 retained blob(s)" in found[0].note


def test_orphan_blobs_is_silent_when_everything_is_cited(tmp_path):
    archive = tmp_path / "archive"
    (archive / "cd").mkdir(parents=True)
    (archive / "cd" / "cdef01.yaml").write_bytes(b"cited")

    assert growth.orphan_blobs(_Graph(hashes=["cdef01"]), base=archive) == []


def test_stock_audit_ranks_by_size_and_totals_what_it_found(tmp_path, monkeypatch):
    root = tmp_path / "wt"
    small, large = root / "small", root / "large"
    for path, size in ((small, 2048), (large, 40960)):
        path.mkdir(parents=True)
        (path / "file").write_bytes(b"q" * size)
    monkeypatch.setattr(growth, "registered_worktrees", lambda repo: set())
    monkeypatch.setattr(growth, "WORKTREE_ROOT", root)

    audit = growth.stock_audit(_Graph(hashes=[]), tmp_path, archive_base=tmp_path / "missing")

    assert [Path(orphan.path).name for orphan in audit.ranked()] == ["large", "small"]
    assert audit.total_bytes == sum(orphan.bytes for orphan in audit.orphans)


def test_human_bytes_reads_as_sizes_not_digits():
    assert growth.human_bytes(512) == "512B"
    assert growth.human_bytes(2048).endswith("KB")
    assert growth.human_bytes(5 * 1024 * 1024).endswith("MB")
    assert growth.human_bytes(3 * 1024**3).endswith("GB")
