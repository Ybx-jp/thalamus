"""Ceremony occasions, priced — a room's token burn attributed to the occasion it ran in.

Reads the ceremony ledger (`console/ceremonies.py`) for each occasion's window, the pin
ledger for which sessions were in which room, and each member's transcripts for usage,
weighted by `eval/cost.py`'s proxy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from thalamus.eval.cost import PROJECTS_DIR, BucketCost, load_rooms, weighted_tokens
from thalamus.harness.pin import room_config_dir

def _parse_ts(value: str) -> datetime | None:
    """Both timestamp dialects in play, as datetimes rather than as strings.

    The ledger writes `...:00Z` and the harness transcripts write `...:00.000Z`, and
    those two sort against each other wrongly under a string compare — `.` precedes
    `Z`, so a call made exactly at an occasion's start reads as preceding it.
    """
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class OccasionBurn:
    """What one ceremony occasion cost, and what its room spent outside every occasion."""

    windows: dict[str, BucketCost] = field(default_factory=dict)
    unattributed: dict[str, BucketCost] = field(default_factory=dict)

    def render(self) -> str:
        if not self.windows and not self.unattributed:
            return (
                "No ceremony occasion overlaps a room member's transcript in range — "
                "either no room has run since, or its members carry no room in the "
                "pin ledger, which makes them invisible here and to `eval rooms` alike."
            )
        lines = ["Burn by ceremony occasion (weighted-token proxy):"]
        for occasion in sorted(self.windows, key=lambda o: -self.windows[o].weighted):
            bucket = self.windows[occasion]
            lines.append(
                f"  {occasion:32} {bucket.weighted:>14,} weighted "
                f"({len(bucket.sessions)} session(s), {bucket.calls} calls)"
            )
        for room in sorted(self.unattributed, key=lambda r: -self.unattributed[r].weighted):
            bucket = self.unattributed[room]
            lines.append(
                f"  {'`' + room + '` outside occasions':32} {bucket.weighted:>14,} weighted "
                f"({len(bucket.sessions)} session(s), {bucket.calls} calls)"
            )
        lines.append(
            "  A room's burn outside every occasion is not overhead to be minimised — "
            "it is the work the ceremony structure does not describe, and reading it "
            "as waste would reward rooms that hold ceremonies over rooms that do work."
        )
        return "\n".join(lines)


def occasion_windows(ledger_path: Path | None = None) -> list[tuple[str, str, datetime, datetime | None]]:
    """(occasion_id, room, start, end) per occasion, end `None` while it is still open.

    Read from the ceremony ledger rather than from a field on the session, because a
    room member is one session that sits in many occasions — attributing its whole
    burn to a single id would answer the question item 8 asks with a number that
    cannot be right for more than one ceremony.
    """
    from thalamus.console import ceremonies

    rows = ceremonies.read_rows(ledger_path)
    ends: dict[str, datetime] = {}
    for row in rows:
        if row.get("event") == ceremonies.EVENT_END:
            parsed = _parse_ts(str(row.get("ts_end") or row.get("ts") or ""))
            if parsed:
                ends[str(row.get("occasion_id"))] = parsed

    windows = []
    for row in rows:
        if row.get("event") != ceremonies.EVENT_START:
            continue
        started = _parse_ts(str(row.get("ts_start") or row.get("ts") or ""))
        if not started:
            continue
        key = str(row.get("occasion_id"))
        windows.append((key, str(row.get("room")), started, ends.get(key)))
    return windows


def occasion_burn(
    since: date,
    *,
    projects_base: Path | None = None,
    rooms_base: Path | None = None,
    pins_path: Path | None = None,
    ledger_path: Path | None = None,
) -> OccasionBurn:
    """Attribute room members' token burn to the ceremony occasion it happened inside.

    A call is attributed to the *most recently started* occasion of its room whose
    window contains it. Occasions nest — a review runs while the room is open — and
    counting a call once per containing window would inflate the total by the depth
    of the nesting rather than by anything about the work.
    """
    windows = occasion_windows(ledger_path)
    rooms = load_rooms(pins_path)
    report = OccasionBurn()
    if not windows or not rooms:
        return report

    by_room: dict[str, list[tuple[str, datetime, datetime | None]]] = {}
    for occasion, room, start, end in windows:
        by_room.setdefault(room, []).append((occasion, start, end))

    # Both roots, because a room member's transcript is written under the room's own
    # `CLAUDE_CONFIG_DIR/projects/` and never appears in the operator's. Walking only
    # the latter is why a room's burn has read as zero: the boundary that partitions
    # discovery partitions the transcripts the cost report is computed from.
    bases = [projects_base or PROJECTS_DIR]
    if projects_base is None:
        bases.extend(
            room_config_dir(room) / "projects"
            for room in sorted(by_room)
        )
    elif rooms_base is not None:
        bases.extend(rooms_base / room / "projects" for room in sorted(by_room))

    for base in bases:
        if not base.is_dir():
            continue
        for pdir in base.iterdir():
            if not pdir.is_dir():
                continue
            for transcript in pdir.glob("*.jsonl"):
                room = rooms.get(transcript.stem)
                if not room or room not in by_room:
                    continue
                _tally_occasions(report, transcript, room, by_room[room], since)
    return report


def _tally_occasions(
    report: OccasionBurn,
    transcript: Path,
    room: str,
    windows: list[tuple[str, datetime, datetime | None]],
    since: date,
) -> None:
    session_id = transcript.stem
    with transcript.open(errors="ignore") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            message = record.get("message")
            usage = message.get("usage") if isinstance(message, dict) else None
            if not isinstance(usage, dict):
                continue
            raw = str(record.get("timestamp") or "")
            if len(raw) < 10 or raw[:10] < since.isoformat():
                continue
            stamp = _parse_ts(raw)
            if not stamp:
                continue
            containing = [
                (start, occasion)
                for occasion, start, end in windows
                if start <= stamp and (end is None or stamp <= end)
            ]
            weight = weighted_tokens(usage)
            if containing:
                _, occasion = max(containing)
                bucket = report.windows.setdefault(occasion, BucketCost())
            else:
                bucket = report.unattributed.setdefault(room, BucketCost())
            bucket.weighted += weight
            bucket.calls += 1
            bucket.sessions.add(session_id)
