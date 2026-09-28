#!/usr/bin/env python3
"""Stands in front of `codex` in a live-tier cell and records what each call used.

Distillation runs codex `--ephemeral`, so no rollout is written, and `thalamus extract`
prints no token counts for it — the only place a codex call's usage is visible is the
`turn.completed` event on its own `--json` stdout, which extract consumes. This passes
every byte of both streams through unchanged and appends each `turn.completed` usage it
sees to `$HOME/qe-live-evidence/codex-usage.jsonl` with the model the call asked for.

A call that exits non-zero also gets a row in `codex-failures.jsonl`: its flags (never
its prompt, which is the last argument), its exit code and the tails of both streams.
Extract keeps only a few hundred characters of a failure, and a codex error arrives on
either stream, so without this a failed distillation says only that it failed.

It decides nothing and changes nothing the product sees. The real binary sits beside
this file as `codex-real`.
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REAL = str(Path(__file__).resolve().parent / "codex-real")
TAIL = 4000


def _model(argv: list[str]) -> str:
    for flag in ("-m", "--model"):
        if flag in argv[:-1]:
            return argv[argv.index(flag) + 1]
    return ""


def _pump(src, dst, keep: list[bytes]) -> None:
    for raw in iter(src.readline, b""):
        dst.write(raw)
        dst.flush()
        keep.append(raw)
        if sum(len(k) for k in keep) > 4 * TAIL:
            del keep[0]


def main() -> int:
    argv = sys.argv[1:]
    if "--json" not in argv:
        os.execv(REAL, [REAL, *argv])
    evidence = Path(os.environ.get("HOME", "/tmp")) / "qe-live-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([REAL, *argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out: list[bytes] = []
    err: list[bytes] = []
    pumps = [threading.Thread(target=_pump, args=(proc.stdout, sys.stdout.buffer, out)),
             threading.Thread(target=_pump, args=(proc.stderr, sys.stderr.buffer, err))]
    for pump in pumps:
        pump.start()
    code = proc.wait()
    for pump in pumps:
        pump.join()
    for raw in out:
        if b"turn.completed" not in raw:
            continue
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        with (evidence / "codex-usage.jsonl").open("a") as fh:
            fh.write(json.dumps({"ts": time.time(), "model": _model(argv),
                                 "sandboxed": bool(os.environ.get("THALAMUS_SANDBOX")),
                                 "usage": event.get("usage")}) + "\n")
    if code:
        flags = [a for a in argv if a.startswith("-")]
        with (evidence / "codex-failures.jsonl").open("a") as fh:
            fh.write(json.dumps({
                "ts": time.time(), "exit": code, "flags": flags, "model": _model(argv),
                "stdout_tail": b"".join(out).decode(errors="replace")[-TAIL:],
                "stderr_tail": b"".join(err).decode(errors="replace")[-TAIL:]}) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
