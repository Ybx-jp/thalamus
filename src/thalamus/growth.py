"""What this system accumulates, and what nothing is holding on to.

Two questions that look alike and are not. **Growth** is a rate: how fast the graph is
accumulating, which the vertices already answer because every one of them carries
`ingested_at` — a 57-day series nobody had to start recording. **Stock** is a quantity
that is simply there: 894 MB of eval worktrees git no longer tracks, sitting flat since
the day they were made.

The distinction is load-bearing, because the trend half cannot see the stock half. The
worktrees have been flat for two weeks, so every trend statistic scores them perfectly
healthy — Mann-Kendall Z of zero, slope of zero, time-to-exhaustion infinite. A growth
detector would have called the largest consumer on the box its best-behaved surface.
That is why the audit exists and why it comes first: what is *unreferenced* is a
different question from what is *increasing*, and only one of them found the 894 MB.

Rates use Sen's slope — the median of pairwise slopes (Garg, van Moorsel, Vaidyanathan &
Trivedi, ISSRE 1998, `scope:architect:source:444e1f573d725e353d656480f65a0c48954ef999bb429588966aeab5779898f5`).
The estimator is chosen for exactly the shape this data has: a mean over daily totals is
dragged by any single fat day, which is how a 6.9 MB/day archive was first reported as
40 MB/day. The median of slopes ignores that day.

Nothing here writes to the graph. A daily reading would mint a Source per day onto a
base of a few hundred, and the series it would record is already reconstructible from
the vertices themselves — so this reports, and the operator decides.
"""

from __future__ import annotations

import itertools
import statistics
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from thalamus.archive import archive_dir

# Where the eval harness leaves its per-arm checkouts. Named here rather than discovered,
# because the directory is the one place on this box that grew by a gigabyte unattended.
WORKTREE_ROOT = Path.home() / ".thalamus" / "counterfactuals" / "wt"

# Pairwise slopes are O(n^2). At one point per day this is trivial for years of data;
# the cap exists so a future per-hour series cannot quietly turn a report into a hang.
_MAX_POINTS = 2000


def sens_slope(points: list[tuple[float, float]]) -> float:
    """Median of pairwise slopes. 0.0 for fewer than two distinct x.

    Robust where a mean is not: one exceptional day moves the mean of daily totals by
    its whole excess and moves this estimator by nothing, because it changes the median
    of a large set of pairwise slopes only marginally.
    """
    if len(points) > _MAX_POINTS:
        step = len(points) // _MAX_POINTS + 1
        points = points[::step]
    slopes = [
        (y2 - y1) / (x2 - x1)
        for (x1, y1), (x2, y2) in itertools.combinations(points, 2)
        if x2 != x1
    ]
    return statistics.median(slopes) if slopes else 0.0


@dataclass
class Headline:
    """The two-line answer: how fast, and whether the rate itself is moving."""

    vertices: int
    days: int
    lifetime_per_day: float
    recent_per_day: float
    window: int = 30

    @property
    def accelerating(self) -> bool:
        """Is the recent rate materially above the lifetime rate?

        A ratio, not a significance test. Deciding whether a difference in rates is real
        is `eval-methodology`'s question, and this module deliberately does not answer
        it — it reports both numbers and lets the reader see the gap.
        """
        return self.lifetime_per_day > 0 and self.recent_per_day > self.lifetime_per_day * 1.25

    def lines(self) -> list[str]:
        trend = " (rate rising)" if self.accelerating else ""
        return [
            f"growth      {self.vertices} vertices over {self.days} days",
            f"            {self.lifetime_per_day:.0f}/day lifetime, "
            f"{self.recent_per_day:.0f}/day last {self.window}{trend}",
        ]


@dataclass
class Orphan:
    """Something large that nothing in the graph or in git refers to."""

    kind: str
    path: str
    bytes: int
    note: str = ""


@dataclass
class StockAudit:
    """What is sitting on disk unreferenced, largest first."""

    orphans: list[Orphan] = field(default_factory=list)
    scanned_bytes: int = 0

    @property
    def total_bytes(self) -> int:
        return sum(orphan.bytes for orphan in self.orphans)

    def ranked(self) -> list[Orphan]:
        return sorted(self.orphans, key=lambda orphan: -orphan.bytes)


def graph_series(g) -> list[tuple[int, int]]:
    """Cumulative vertex count by day, from the `ingested_at` every vertex carries.

    This is the series the growth question needed and that nobody had to start
    recording: the graph has been dating its own rows since the first write. Vertices
    missing the stamp are skipped rather than counted at day zero, which would invent a
    step at the series' start.
    """
    stamps = g.V().values("ingested_at").to_list()
    per_day: dict[str, int] = {}
    for stamp in stamps:
        day = str(stamp)[:10]
        if len(day) == 10:
            per_day[day] = per_day.get(day, 0) + 1

    days = sorted(per_day)
    if not days:
        return []
    base = datetime.fromisoformat(days[0]).toordinal()
    cumulative = 0
    series: list[tuple[int, int]] = []
    for day in days:
        cumulative += per_day[day]
        series.append((datetime.fromisoformat(day).toordinal() - base, cumulative))
    return series


def headline(g, window: int = 30) -> Headline | None:
    """Lifetime and recent growth rate. None when there is not yet a series."""
    series = graph_series(g)
    if len(series) < 2:
        return None
    recent = [point for point in series if point[0] >= series[-1][0] - window]
    return Headline(
        vertices=series[-1][1],
        days=series[-1][0],
        lifetime_per_day=sens_slope([(float(x), float(y)) for x, y in series]),
        recent_per_day=sens_slope([(float(x), float(y)) for x, y in recent]),
        window=window,
    )


def _directory_bytes(path: Path, seen: set[tuple[int, int]] | None = None) -> int:
    """Disk actually occupied, counting each inode once.

    Two corrections over a naive sum of `st_size`, both measured on this box's own eval
    worktrees, where the naive answer was 1.2 GB and the true one is 894 MB:

    **Hardlinks.** 3,860 of 31,674 files there have a link count above one, so summing
    every path charges the same blocks several times. A number that says a gigabyte is
    recoverable when 894 MB is recoverable is the kind of error this whole half exists
    to avoid, and `du` has always counted inodes once for exactly this reason.

    **Blocks, not bytes.** Thousands of small files occupy more disk than they contain.
    `st_blocks` is what the filesystem gave them, which is what deleting them returns.

    `seen` is threaded across directories by the caller so a file hardlinked into two
    orphaned worktrees is charged to the first and not to both.
    """
    seen = seen if seen is not None else set()
    total = 0
    for item in path.rglob("*"):
        try:
            info = item.stat()
        except OSError:
            continue  # a file that vanished mid-walk is not a measurement error
        if not item.is_file():
            continue
        key = (info.st_dev, info.st_ino)
        if key in seen:
            continue
        seen.add(key)
        total += info.st_blocks * 512
    return total


def registered_worktrees(repo: Path) -> set[str]:
    """Paths git currently knows as worktrees of this repo."""
    result = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return set()
    return {
        line.split(" ", 1)[1].strip()
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    }


def orphan_worktrees(repo: Path, root: Path | None = None) -> list[Orphan]:
    """Checkout directories under the eval worktree root that git no longer tracks.

    The failure this catches is not deletion going wrong — it is a harness that made
    real checkouts, finished with them, and left them registered nowhere. Nothing
    references them, nothing is growing, and nothing would ever mention them again.
    """
    root = root or WORKTREE_ROOT
    if not root.is_dir():
        return []
    registered = registered_worktrees(repo)
    found: list[Orphan] = []
    # Shared across siblings: these checkouts hardlink into each other, so a blob under
    # two orphaned directories is recovered once, not twice. Largest first, so the
    # shared blocks are charged to the biggest holder rather than to whichever sorted
    # first alphabetically.
    seen: set[tuple[int, int]] = set()
    entries = sorted(
        (entry for entry in root.iterdir() if entry.is_dir() and str(entry) not in registered),
        key=lambda entry: -sum(1 for _ in entry.rglob("*")),
    )
    for entry in entries:
        stamp = datetime.fromtimestamp(entry.stat().st_mtime).date().isoformat()
        found.append(
            Orphan(
                kind="worktree",
                path=str(entry),
                bytes=_directory_bytes(entry, seen),
                note=f"git does not track this worktree; last touched {stamp}",
            )
        )
    return found


def orphan_blobs(g, base: Path | None = None) -> list[Orphan]:
    """Archived blobs no Source in the graph points at.

    The archive is the evidence floor, so a blob nothing cites is not automatically
    garbage — it may be evidence for a write that failed, which is worth knowing about
    for the opposite reason. Reported as one aggregate rather than a file list: the
    count and the bytes are the finding, and 600 paths are not.
    """
    root = base or archive_dir()
    if not root.is_dir():
        return []
    referenced = {
        str(value) for value in g.V().has_label("Source").values("content_hash").to_list()
    }
    stray_bytes = 0
    stray_count = 0
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        content_hash = item.name.split(".")[0]
        if content_hash not in referenced:
            stray_count += 1
            stray_bytes += item.stat().st_blocks * 512
    if not stray_count:
        return []
    return [
        Orphan(
            kind="archive",
            path=str(root),
            bytes=stray_bytes,
            note=f"{stray_count} retained blob(s) no Source cites",
        )
    ]


def stock_audit(g, repo: Path, *, archive_base: Path | None = None) -> StockAudit:
    """Everything large that nothing refers to. Reads only.

    Ordered by what the evidence says actually happens: worktrees first, because that is
    the surface that produced a gigabyte, and the archive second, because a stray blob
    there is usually a failed write rather than waste.
    """
    audit = StockAudit()
    audit.orphans.extend(orphan_worktrees(repo))
    audit.orphans.extend(orphan_blobs(g, archive_base))
    audit.scanned_bytes = sum(orphan.bytes for orphan in audit.orphans)
    return audit


def human_bytes(count: int) -> str:
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"
