"""The console's read view: a roster window, resolved to the session transcript
running in it, projected into a feed of prose and collapsed tool calls.

Why this exists next to `capture()`. The pane mirror shows a *rendering* of a
session — a fixed-width repaint of whatever the TUI last drew, with colours
stripped by tmux and no structure left to act on. Claude Code writes the thing
that rendering came from to `~/.claude/projects/<slug>/<session_id>.jsonl`, one
JSON record per line, and reading that instead is what lets the phone show
flowing prose with an `Edit src/foo.py` chip where a forty-line diff used to be.

Two properties of that file make this practical, both measured on this box
(2026-08-09):

  * It is append-only. Prefix bytes never change and the inode is stable across
    a run; mutable state (`mode`, `relocated`, `worktree-state`) is re-appended
    rather than rewritten, so one transcript can hold hundreds of `mode` rows
    under last-wins semantics. A reader can therefore hold a byte offset and
    only ever read forward.
  * It is written at *turn* granularity, not token granularity — silent for the
    whole duration of an assistant block, then a jump. That is a feature here,
    not a lag to engineer around: text lands as finished blocks instead of
    reflowing under the reader mid-sentence, which is the specific thing that
    makes the pane mirror hard to read on a phone while a session streams.

What it deliberately cannot do — see `docs/console.md` — is replace the pane.
A pending permission prompt is never written to the transcript at all: nothing
is recorded while the dialog is on screen, and a rejection surfaces only
afterwards, as `tool_result` text. So a transcript reader sees a `tool_use` with
no result and cannot distinguish "still running" from "blocked, waiting on you",
which is the one state the roster console exists to surface. The read view is a
second view, and `capture()` stays the source of truth for acting.
"""

from __future__ import annotations

import calendar
import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from ..harness.extraction import _tool_use_line
from ..harness.transcripts import CLAUDE_PROJECTS, tool_result_text

PINS = Path.home() / ".thalamus" / "pins" / "pins.jsonl"

# How much of a feed we keep per session. The client merges by item id and only
# ever asks for what changed, so this bounds server memory, not what the reader
# can scroll back through in one sitting.
MAX_ITEMS = 400

# Tool results are shown collapsed; this is the size of what an expand reveals.
# Capped in both directions because one `Read` of a large file would otherwise
# outweigh the entire rest of the feed.
RESULT_CHAR_CAP = 2000
RESULT_LINE_CAP = 40

# The one-line trace of a result that rides along with the feed itself.
PREVIEW_CAP = 160

# `extraction._tool_use_line` clips commands at 300 chars, which is right for the
# extractor model reading a digest and far too wide for a phone: a heredoc commit
# renders as a paragraph where the reader wanted a chip. Clipped for display only,
# leaving the shared helper's own cap alone.
SUMMARY_CAP = 140

# Items delivered on a cold open. Everything older stays on the server.
COLD_OPEN_ITEMS = 60

# Ledger rows are matched to a legacy pane by process start time. The hook fires
# ~1s after exec (measured: +1s on all four live windows), so the row lands just
# after the process; the slack absorbs a loaded box without reaching the next
# spawn in a burst.
LEGACY_SKEW_SECONDS = 30.0


def project_slug(cwd: str) -> str:
    """The `~/.claude/projects` directory name for a working directory.

    Claude Code flattens the absolute path, rewriting `/`, `.` and `_` each to a
    single `-` and preserving case: `/home/ybx/.claude/plugins` becomes
    `-home-ybx--claude-plugins`. Verified against real directories on this box.
    """
    out = []
    for ch in cwd:
        out.append("-" if ch in "/._" else ch)
    return "".join(out)


def transcript_path(session_id: str, cwd: str) -> Path | None:
    """Locate a session's transcript file.

    The slug is a fast path, not the contract. A session that enters a worktree
    mid-run appends a `relocated` record but keeps writing to the directory
    derived from its *starting* cwd, and the ledger stores that starting cwd — so
    the slug is normally right. The glob is the fallback that keeps this working
    if the flattening rule ever changes or the recorded cwd disagrees, since the
    filename is the session id and that is unambiguous on its own.
    """
    if not session_id:
        return None
    if cwd:
        direct = CLAUDE_PROJECTS / project_slug(cwd) / f"{session_id}.jsonl"
        if direct.is_file():
            return direct
    if not CLAUDE_PROJECTS.is_dir():
        return None
    for found in CLAUDE_PROJECTS.glob(f"*/{session_id}.jsonl"):
        return found
    return None


class LedgerIndex:
    """`pins.jsonl`, tailed, indexed by the pane each session was launched into.

    The ledger is append-only and already ~170KB, so it is read forward from a
    saved offset rather than re-parsed on every poll. Last row wins per pane:
    when a console recycle respawns a window the pane id is preserved, so the
    replacement session simply appends a fresher row under the same key.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or PINS
        self._offset = 0
        self._buffer = ""
        self._by_pane: dict[str, dict] = {}
        self._rows: list[dict] = []

    def refresh(self) -> None:
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size < self._offset:  # truncated or replaced; start over
            self._offset, self._buffer, self._by_pane, self._rows = 0, "", {}, []
        if size == self._offset:
            return
        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(self._offset)
                chunk = fh.read()
                self._offset = fh.tell()
        except OSError:
            return
        lines = (self._buffer + chunk).split("\n")
        self._buffer = lines.pop()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or not row.get("session_id"):
                continue
            # `event` rows (engaged/…) carry no launch facts and must not
            # overwrite the row that does.
            if row.get("event"):
                continue
            pane = row.get("tmux_pane") or ""
            if pane:
                self._by_pane[pane] = row
            self._rows.append(row)

    def by_pane(self, pane_id: str) -> dict | None:
        return self._by_pane.get(pane_id) if pane_id else None

    def legacy_match(self, scope: str, cwd: str, started_at: float) -> dict | None:
        """Resolve a session started before the hook recorded pane ids.

        Deliberately narrow: the row must sit within a launch-sized window of the
        process start, and it must be the only one that does. An unbounded
        "newest row at or after start" would be wrong in the common case rather
        than the rare one — every *later* session sharing this scope and cwd also
        satisfies it, so a window would drift onto its successor's transcript the
        moment a second one launched.

        The cost of the narrow rule is that a legacy session which has since run
        `/clear` (a new session id, a new file, minted mid-process) resolves to
        nothing. That is the right trade: this path only serves windows that
        predate the pane id in the ledger, it stops serving them the moment they
        are recycled, and showing the wrong session's transcript is worse than
        showing none.
        """
        if not started_at:
            return None
        hits = [
            row for row in self._rows
            if row.get("scope") == scope
            and row.get("cwd") == cwd
            and abs(_row_epoch(row) - started_at) <= LEGACY_SKEW_SECONDS
        ]
        return hits[0] if len(hits) == 1 else None


def _row_epoch(row: dict) -> float:
    """Ledger timestamps are UTC. `timegm`, not `mktime` — the latter reads the
    struct as local time and would skew every comparison by the box's offset,
    silently and by a different amount either side of a DST boundary."""
    ts = row.get("ts") or ""
    try:
        return calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return 0.0


def pane_started_at(pane_pid: int) -> float:
    """Process start, as epoch seconds. The `/proc/<pid>` directory is created
    with the process, so its mtime is the start time to within a second — enough
    for a join with a ±30s window, and it needs no boot-time arithmetic."""
    try:
        return os.stat(f"/proc/{pane_pid}").st_mtime
    except OSError:
        return 0.0


def resolve(pane_id: str, scope: str, cwd: str, pane_pid: int,
            ledger: LedgerIndex) -> tuple[str, Path, str] | None:
    """(session_id, transcript path, launch cwd) for the session in a window.

    The cwd returned is the ledger's — where the session *started*, which is both
    what names its transcript directory and what its tool paths are relative to.
    The pane's current directory can differ (a worktree entered mid-run) and is
    only ever an input to the fallback match.
    """
    ledger.refresh()
    row = ledger.by_pane(pane_id)
    if row is None and pane_pid:
        row = ledger.legacy_match(scope, cwd, pane_started_at(pane_pid))
    if row is None:
        return None
    session_id = row.get("session_id") or ""
    launch_cwd = row.get("cwd") or ""
    path = transcript_path(session_id, launch_cwd)
    if path is None:
        return None
    return session_id, path, launch_cwd


def shorten(summary: str, cwd: str) -> str:
    """Drop the working directory from a tool summary.

    Every path in a session rooted at one repo starts with the same 25 characters,
    and the Bash tool prefixes commands with a `cd` to that same directory. On a
    phone that prefix is most of the visible width of the line while carrying none
    of the information — the whole point of the chip is which file, which command.
    """
    if not cwd:
        return summary
    return summary.replace(f"cd {cwd}; ", "").replace(f"{cwd}/", "")


def _cap_result(text: str) -> tuple[str, bool]:
    """Trim a tool result for display, preserving line structure.

    Deliberately not `extraction._clip`, which collapses all whitespace to single
    spaces — correct for a one-line summary, destructive for the diffs, file
    contents and command output this is showing.
    """
    truncated = False
    lines = text.split("\n")
    if len(lines) > RESULT_LINE_CAP:
        lines = lines[:RESULT_LINE_CAP]
        truncated = True
    out = "\n".join(lines)
    if len(out) > RESULT_CHAR_CAP:
        out = out[:RESULT_CHAR_CAP]
        truncated = True
    return out, truncated


@dataclass
class Feed:
    """One session's transcript, tailed and projected into display items.

    Items are assigned a stable `id` and a `seq` that bumps whenever the item
    changes, so the client can ask for everything after the last `seq` it saw and
    still receive a *late* update to an old item — which is the normal case here,
    since a tool call is emitted pending and only resolves when its result lands
    in a later record.
    """

    session_id: str
    path: Path
    cwd: str = ""
    offset: int = 0
    buffer: str = ""
    seq: int = 0
    next_id: int = 1
    mode: str = ""
    permission_mode: str = ""
    agent: str = ""
    items: deque = field(default_factory=lambda: deque(maxlen=MAX_ITEMS))
    _by_tool_id: dict = field(default_factory=dict)

    def _emit(self, item: dict) -> dict:
        self.seq += 1
        item["id"] = self.next_id
        item["seq"] = self.seq
        self.next_id += 1
        self.items.append(item)
        return item

    def _touch(self, item: dict) -> None:
        self.seq += 1
        item["seq"] = self.seq

    def refresh(self) -> None:
        """Read every complete record appended since the last call."""
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size < self.offset:
            self.offset, self.buffer = 0, ""
            self.items.clear()
            self._by_tool_id.clear()
        if size == self.offset:
            return
        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(self.offset)
                chunk = fh.read()
                self.offset = fh.tell()
        except OSError:
            return
        lines = (self.buffer + chunk).split("\n")
        # A record can in principle be observed mid-write; the trailing fragment
        # is carried rather than parsed.
        self.buffer = lines.pop()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                self._ingest(json.loads(line))
            except json.JSONDecodeError:
                continue

    def _ingest(self, record: dict) -> None:
        if not isinstance(record, dict):
            return
        kind = record.get("type")

        # State records. Unlike the pane mirror, the transcript actually carries
        # the permission mode, so the read view can show it instead of leaving
        # the operator to read it off a footer that may have scrolled.
        if kind == "mode":
            self.mode = record.get("mode") or self.mode
            return
        if kind == "permission-mode":
            self.permission_mode = record.get("permissionMode") or self.permission_mode
            return
        if kind == "agent-setting":
            self.agent = record.get("agentSetting") or self.agent
            return
        if kind not in ("user", "assistant"):
            return

        sidechain = bool(record.get("isSidechain"))
        message = record.get("message") or {}
        content = message.get("content")

        if kind == "user":
            # A bare string is the operator typing; a list is tool results coming
            # back. Meta records are the harness talking to itself.
            if isinstance(content, str):
                text = content.strip()
                if text and not record.get("isMeta"):
                    self._emit({"kind": "user", "text": text, "sidechain": sidechain})
                return
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        self._resolve_tool(block)
            return

        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text = (block.get("text") or "").strip()
                if text:
                    self._emit({"kind": "prose", "text": text, "sidechain": sidechain})
            elif btype == "thinking":
                text = (block.get("thinking") or "").strip()
                if text:
                    self._emit({"kind": "thinking", "text": text, "sidechain": sidechain})
            elif btype == "tool_use":
                item = self._emit({
                    "kind": "tool",
                    "name": block.get("name") or "?",
                    "summary": shorten(_tool_use_line(block), self.cwd),
                    "status": "pending",
                    "result": "",
                    "truncated": False,
                    "sidechain": sidechain,
                })
                tool_id = block.get("id")
                if tool_id:
                    self._by_tool_id[tool_id] = item

    def _resolve_tool(self, block: dict) -> None:
        item = self._by_tool_id.get(block.get("tool_use_id"))
        if item is None:
            return
        text, truncated = _cap_result(tool_result_text(block))
        item["result"] = text
        item["truncated"] = truncated
        item["status"] = "error" if block.get("is_error") else "done"
        self._touch(item)

    def since(self, seq: int, limit: int = 0) -> list[dict]:
        """Items changed since `seq`, newest-biased.

        `limit` bounds a *cold* open, where `seq` is 0 and every item qualifies.
        Measured on a real session: 276 items serialise to 278KB, nearly all of
        it tool-result bodies that the reader has not asked to see — an
        unreasonable payload for a phone on a tailnet. Taking the tail rather
        than the head is what makes truncation safe: the newest items are always
        delivered, so the client never stalls behind a backlog it will not be
        shown.
        """
        out = [item for item in self.items if item["seq"] > seq]
        if limit and len(out) > limit:
            out = out[-limit:]
        return out

    def body(self, item_id: int) -> str | None:
        """The retained result text for one tool item, fetched on expand."""
        for item in self.items:
            if item["id"] == item_id:
                return item.get("result") or ""
        return None


def wire(items: list[dict]) -> list[dict]:
    """The over-the-wire shape: result bodies replaced by a one-line preview.

    The body stays on the server and is fetched only when the reader expands a
    call, which is what keeps a feed of mostly-collapsed tool calls cheap.
    Collapsing whitespace is correct *here* — a preview is a single line by
    construction — and wrong for the body, which is why they are separate.
    """
    out = []
    for item in items:
        if item["kind"] != "tool":
            out.append(item)
            continue
        result = item.get("result") or ""
        shown = dict(item)
        shown.pop("result", None)
        summary = shown.get("summary") or ""
        if len(summary) > SUMMARY_CAP:
            shown["summary"] = summary[:SUMMARY_CAP] + " …"
        shown["preview"] = " ".join(result.split())[:PREVIEW_CAP]
        shown["has_body"] = bool(result)
        out.append(shown)
    return out


class FeedStore:
    """Live feeds, one per session id, kept across polls so each poll reads only
    the bytes appended since the last one.

    Bounded and least-recently-used: a long-lived console would otherwise
    accumulate a parsed feed for every session ever viewed, and the roster is only
    ever a handful of windows wide. Evicting costs a re-read of that session's
    transcript on next view, which is the cheap direction to be wrong in.
    """

    def __init__(self, cap: int = 8) -> None:
        self._feeds: dict[str, Feed] = {}
        self._cap = cap

    def get(self, session_id: str, path: Path, cwd: str = "") -> Feed:
        feed = self._feeds.pop(session_id, None)
        if feed is None or feed.path != path:
            feed = Feed(session_id=session_id, path=path, cwd=cwd)
        self._feeds[session_id] = feed  # reinserted → most recently used last
        while len(self._feeds) > self._cap:
            self._feeds.pop(next(iter(self._feeds)))
        feed.refresh()
        return feed
