"""Read-modify-write mechanics shared by the harness's small JSON stores.

A store here is one JSON document that a writer reads, edits and writes back whole, from
a threaded server and from the CLI at once. `locked` serialises those writers across
threads and processes, on a sidecar lock file rather than the store itself, because the
store is replaced rather than rewritten in place and a lock on a replaced inode guards
nothing. `replace_json` is the write half: a temp file with a name no other writer
shares, then `os.replace`, so a reader sees the old document or the new one and never
part of either.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold an exclusive lock on `path`'s sidecar `.lock` for the block's duration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + ".lock").open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def replace_json(path: Path, document: object) -> None:
    """Write `document` to `path` whole, through a temp file only this call names."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
