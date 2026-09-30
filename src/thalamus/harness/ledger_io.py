"""Append mechanics shared by the harness's JSONL ledgers.

A ledger row is one JSON object on one line, appended under an exclusive `flock` that the
caller holds across whatever it reads to decide the row. `write_row` is the write half of
that: it fences off a dangling partial line, writes, and makes the row durable before
the lock is released.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator


@contextmanager
def locked_ledger(path: Path) -> Iterator[IO[str]]:
    """Open `path` for append and hold an exclusive lock for the block's duration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield handle
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_row(handle: IO[str], row: dict) -> None:
    """Append `row` on a line of its own and fsync it, still under the caller's lock.

    A writer that died between its first and last byte leaves the file without a final
    newline; appending straight after it would merge the new row into that line and
    the reader's per-line JSON parse would drop both. The newline written here ends the
    partial line, which the reader skips as before, and the row lands on the next one.
    The flush precedes the caller's unlock: the handle is buffered, so unlocking first
    would let the next locker read a ledger missing this row.
    """
    fd = handle.fileno()
    size = os.fstat(fd).st_size
    if size:
        # The handle is append-only, so the last byte is read through a second one.
        with open(handle.name, "rb") as reader:
            reader.seek(size - 1)
            if reader.read(1) != b"\n":
                handle.write("\n")
    handle.write(json.dumps(row, sort_keys=True) + "\n")
    handle.flush()
    os.fsync(fd)
