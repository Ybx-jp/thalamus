"""The evidence channel between a cell and the host: framing, commit, and outcome.

A cell commits its result to a file inside the one tree the host reads back off its
stopped disk. Nothing is mounted and nothing is running when that read happens:
`virt-copy-out` reads the filesystem out of the image directly, so it needs no root, no
guest network and no healthy guest, which is the one channel that still works on a cell
too broken to cooperate.

The frame is what makes the file a commit rather than a partial write, and it is worth
carrying for one reason the transport cannot supply: the host has to be able to tell a
guest that died mid-write from a guest that committed a failing result, and collapsing
those two is what makes a matrix unreadable three weeks later.

WHAT THIS CHANNEL DOES NOT SURVIVE, stated rather than assumed. A cell's overlay is
attached `cache=unsafe` — it is destroyed with the cell, so there is no durability to
lose and it removes the flush storm a `docker pull` and a `uv sync` would otherwise
cause. A cell the host has to destroy at its ceiling can therefore lose writes the guest
believed were flushed, including a verdict committed just before a hang. The console log
is written on the host side by qemu and survives that, which is why the PHASE markers
are a cell's diagnosis rather than a decoration, and why `classify()` consults them.

## Why the header is written last

The framing exists to answer two questions the host cannot otherwise answer: *how many
bytes are real*, and *is this complete*. A guest that dies mid-write must not leave
something that reads as a verdict.

So the guest writes the payload first, flushes, then writes the header, then flushes
again. The header's presence IS the commit. An absent header means the guest never
reached the commit point, which is a different outcome from a guest that committed a
failing result.

## Layout

| offset | size | field                                    |
|--------|------|------------------------------------------|
| 0      | 8    | magic `QECELLv1`                          |
| 8      | 16   | payload length, ASCII decimal, zero-padded|
| 24     | 64   | sha256 of the payload, lowercase hex      |
| 88     | 424  | NUL padding                               |
| 512    | LEN  | payload (JSON)                            |

The length and digest are ASCII rather than packed binary so that a torn header is
legible to a human reading `xxd` at 3am, and so the guest can write it with `printf`
and no tooling beyond coreutils.
"""

from __future__ import annotations

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

MAGIC = b"QECELLv1"
HEADER_SIZE = 512
LEN_OFFSET, LEN_SIZE = 8, 16
SHA_OFFSET, SHA_SIZE = 24, 64
PAYLOAD_OFFSET = HEADER_SIZE

# 32 MiB. Ample for a JSON verdict plus a gzipped tail of the guest's logs, and the
# ceiling a length field is checked against: a frame claiming more than this is a torn
# header rather than a very large verdict.
FRAME_LIMIT_BYTES = 32 * 1024 * 1024
MAX_PAYLOAD = FRAME_LIMIT_BYTES - HEADER_SIZE


class Frame(str, Enum):
    """What the committed bytes are, before asking what they say."""

    OK = "ok"
    NO_COMMIT = "no-commit"        # no magic: the guest never reached the commit point
    TORN_HEADER = "torn-header"    # magic present, header fields unreadable or absurd
    TORN_PAYLOAD = "torn-payload"  # header good, payload short or digest mismatched


class Outcome(str, Enum):
    """The five distinct ends a cell can come to.

    Kept distinct deliberately. Collapsing `STALLED` into a general error costs real
    diagnosis time — a stalled cell and a crashed cell need different next actions, and
    the harness knows which is which for free because the header is written last.

    `BOUNDARY_ABORT` is not a cell result at all: it records that a gate refused to let
    the cell run. It must never be counted as a pass or a fail of the software under
    test.
    """

    PASS = "pass"
    FAIL = "fail"
    CRASHED = "crashed"
    STALLED = "stalled"
    TORN = "torn"
    BOUNDARY_ABORT = "boundary-abort"


#: Outcomes whose root overlay is kept rather than deleted. A failed overlay is a
#: bootable copy of the exact broken machine, which is the cheapest possible repro.
KEEP_OVERLAY = frozenset({Outcome.FAIL, Outcome.CRASHED, Outcome.STALLED, Outcome.TORN})


@dataclass(frozen=True)
class Verdict:
    """What the host concluded, and the evidence it concluded it from.

    `tiebreaker` records WHICH signal resolved an ambiguous case, because a verdict
    whose provenance cannot be reconstructed later is the failure mode this whole
    channel is designed against.
    """

    outcome: Outcome
    frame: Frame
    payload: dict | None
    detail: str
    tiebreaker: str = ""

    @property
    def keep_overlay(self) -> bool:
        return self.outcome in KEEP_OVERLAY


def read_frame(path: str | Path) -> tuple[bytes | None, Frame]:
    """Read the committed file and say whether it carries a complete payload.

    Trusts the guest for nothing: not that it wrote the length it meant to, not that the
    payload it hashed is the payload it wrote. A file that was never written at all —
    or is not there — reads as `NO_COMMIT` rather than as an error, because that is the
    ordinary state of a cell that crashed early.
    """
    try:
        with open(path, "rb") as fh:
            header = fh.read(HEADER_SIZE)
            if len(header) < HEADER_SIZE or header[:len(MAGIC)] != MAGIC:
                return None, Frame.NO_COMMIT
            try:
                length = int(header[LEN_OFFSET:LEN_OFFSET + LEN_SIZE])
                digest = header[SHA_OFFSET:SHA_OFFSET + SHA_SIZE].decode("ascii")
            except (ValueError, UnicodeDecodeError):
                return None, Frame.TORN_HEADER
            if not 0 < length <= MAX_PAYLOAD:
                return None, Frame.TORN_HEADER
            if not (len(digest) == SHA_SIZE and all(c in "0123456789abcdef" for c in digest)):
                return None, Frame.TORN_HEADER
            fh.seek(PAYLOAD_OFFSET)
            payload = fh.read(length)
    except OSError:
        return None, Frame.NO_COMMIT

    if len(payload) != length:
        return None, Frame.TORN_PAYLOAD
    if hashlib.sha256(payload).hexdigest() != digest:
        return None, Frame.TORN_PAYLOAD
    return payload, Frame.OK


def classify(path: str | Path, domstate: str, deadline_expired: bool,
             last_phase: str = "", post_mortem_found: bool = False) -> Verdict:
    """Turn the committed file, the domain state and the deadline into one of five
    outcomes.

    The decision table:

    | header                        | domain at deadline        | outcome   |
    |-------------------------------|---------------------------|-----------|
    | valid, result in {pass, fail} | shut off                  | that      |
    | absent                        | shut off before deadline  | crashed   |
    | absent                        | still running at deadline | stalled   |
    | torn                          | either                    | torn      |

    The genuinely ambiguous case is "no header, shut off": the guest may have crashed,
    or it may never have got far enough to have anything to say. Two independent
    tie-breakers settle it and BOTH are consulted before anything is recorded — the
    console stream's last PHASE marker, and whether a post-mortem copy-out found any
    guest log at all. If neither fired, the cell did not boot, and that indicts the
    image or the seed rather than the software under test.
    """
    payload_bytes, frame = read_frame(path)

    if frame in (Frame.TORN_HEADER, Frame.TORN_PAYLOAD):
        return Verdict(Outcome.TORN, frame, None,
                       f"the committed file carries a {frame.value}; the guest died "
                       "mid-commit")

    if frame is Frame.NO_COMMIT:
        if deadline_expired and domstate != "shut off":
            return Verdict(Outcome.STALLED, frame, None,
                           f"no verdict committed and the domain was still {domstate!r} "
                           "at the deadline",
                           tiebreaker=f"last phase marker: {last_phase or 'none'}")
        if last_phase:
            return Verdict(Outcome.CRASHED, frame, None,
                           "the guest powered off without committing a verdict",
                           tiebreaker=f"console last reached {last_phase!r}")
        if post_mortem_found:
            return Verdict(Outcome.CRASHED, frame, None,
                           "the guest powered off without committing a verdict",
                           tiebreaker="no console markers; guest logs recovered post-mortem")
        return Verdict(Outcome.CRASHED, frame, None,
                       "no verdict, no console marker and no recoverable guest log: the "
                       "cell did not boot, which indicts the image or the seed rather "
                       "than the install under test",
                       tiebreaker="neither tie-breaker fired")

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        return Verdict(Outcome.TORN, Frame.TORN_PAYLOAD, None,
                       f"payload passed its digest but is not JSON: {exc}")
    if not isinstance(payload, dict):
        return Verdict(Outcome.TORN, Frame.TORN_PAYLOAD, None,
                       "payload passed its digest but is not a JSON object")

    result = payload.get("result")
    if result == "pass":
        return Verdict(Outcome.PASS, frame, payload, "the cell committed a passing verdict")
    if result == "fail":
        failed = payload.get("failed") or []
        return Verdict(Outcome.FAIL, frame, payload,
                       f"the cell committed a failing verdict: {len(failed)} check(s) failed")
    return Verdict(Outcome.TORN, frame, payload,
                   f"committed payload carries no usable result field: {result!r}")


def boundary_abort(reason: str) -> Verdict:
    """A gate refused the run. Never a statement about the software under test."""
    return Verdict(Outcome.BOUNDARY_ABORT, Frame.NO_COMMIT, None, reason)


def commit_script() -> str:
    """The guest-side committer, generated from the constants above.

    Generated rather than kept as a sibling file so the format has exactly one
    definition. A host reader and a guest writer that drift apart produce `torn-payload`
    on every cell, which reads as a guest fault and is not one.
    """
    return f"""#!/bin/bash
# Commits a verdict payload. Written by verdict.commit_script(); do not edit in the
# guest.
#
# Order is the commit protocol: payload, flush, header, flush. The header is written
# last because its presence is what tells the host the payload is complete.
#
# The destination is named by the caller and has no default. A default would be a
# second place the channel is defined, and a cell that committed to the wrong one
# would look to the host exactly like a cell that committed nothing.
set -euo pipefail
P="$1"
DEST="${{2:?the destination the host reads back must be named}}"
LEN=$(stat -c %s "$P")
SHA=$(sha256sum "$P" | cut -d' ' -f1)

if [ "$LEN" -le 0 ] || [ "$LEN" -gt {MAX_PAYLOAD} ]; then
    echo "verdict payload is $LEN bytes, outside 1..{MAX_PAYLOAD}" >&2
    exit 1
fi

dd if="$P" of="$DEST" bs={HEADER_SIZE} seek=1 conv=notrunc,fsync status=none
sync

printf '{MAGIC.decode()}%0{LEN_SIZE}d%s' "$LEN" "$SHA" > /tmp/qe-hdr
truncate -s {HEADER_SIZE} /tmp/qe-hdr
dd if=/tmp/qe-hdr of="$DEST" bs={HEADER_SIZE} count=1 conv=notrunc,fsync status=none
sync

echo "PHASE verdict-committed $(date +%s) len=$LEN" > /dev/ttyS0 || true
"""


def write_frame(path: str | Path, payload: bytes) -> None:
    """Write a complete frame from the host. Used to build fixtures; the real path is
    the guest committer above."""
    if not 0 < len(payload) <= MAX_PAYLOAD:
        raise ValueError(f"payload of {len(payload)} bytes is outside 1..{MAX_PAYLOAD}")
    header = bytearray(b"\0" * HEADER_SIZE)
    header[0:len(MAGIC)] = MAGIC
    header[LEN_OFFSET:LEN_OFFSET + LEN_SIZE] = f"{len(payload):0{LEN_SIZE}d}".encode()
    header[SHA_OFFSET:SHA_OFFSET + SHA_SIZE] = hashlib.sha256(payload).hexdigest().encode()
    with open(path, "r+b" if Path(path).exists() else "w+b") as fh:
        fh.write(bytes(header))
        fh.seek(PAYLOAD_OFFSET)
        fh.write(payload)
        fh.flush()
