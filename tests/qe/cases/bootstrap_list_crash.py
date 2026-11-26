"""`thalamus bootstrap` with no project dir lists what is available, then exits clean.

docs/cli.md documents `thalamus bootstrap` as "list session transcripts available to
ingest", and the `projects` help says "Omit to list what is available".
`_claude_bootstrap_groups` returns None after printing that listing, and
`_cmd_bootstrap` only checks for None on the cursor/codex branch — 7c685da swapped the
branches and left both checks under `else:` — so the claude listing falls through into
`for label, results in groups` and dies on `TypeError`.

**Control.** The same subprocess, given a project dir that does not exist, must exit 1
with the "Unknown project dir(s)" sentence: the probe can tell a clean refusal from a
traceback.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "src/thalamus/cli.py::_cmd_bootstrap"


def _bootstrap(home: Path, *extra: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("THALAMUS_")}
    env["HOME"] = str(home)
    env["THALAMUS_ARCHIVE_DIR"] = str(home / "archive")
    return subprocess.run(
        [sys.executable, "-m", "thalamus", "bootstrap",
         "--projects-dir", str(home / "projects"), *extra],
        capture_output=True, text=True, env=env, timeout=60, check=False,
    )


def run() -> Finding | None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        proj = home / "projects" / "-home-you-code-x"
        proj.mkdir(parents=True)
        (proj / "abcd1234.jsonl").write_text(json.dumps(
            {"type": "user", "sessionId": "abcd1234",
             "message": {"role": "user", "content": "hi"}}) + "\n")

        control = _bootstrap(home, "--", "-no-such-dir")
        if control.returncode != 1 or "Unknown project dir(s)" not in control.stderr:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="control: an unknown project dir was not refused cleanly",
                witness=f"control exit={control.returncode} {control.stderr[-200:]!r}",
                site=_SITE,
            )

        proc = _bootstrap(home)
    if "-home-you-code-x" not in proc.stdout:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the listing did not name the seeded project dir",
            witness=f"stdout={proc.stdout[-200:]!r}",
            site=_SITE,
        )
    if proc.returncode == 0 and "Traceback" not in proc.stderr:
        return None
    last = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else ""
    return Finding(
        failure_class=FailureClass.DOC_CODE_DRIFT,
        summary="`thalamus bootstrap` prints the listing docs/cli.md promises, then "
                "crashes iterating the None that means 'only listed'",
        witness=f"listing exit={proc.returncode} {last}",
        site=_SITE,
    )


CASE = Case(
    name="bootstrap-listing-crashes-on-none",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.DOC_CODE_DRIFT, FailureClass.COLLAPSED_SENTINEL),
    summary="`thalamus bootstrap` with no project dir lists transcripts and exits 0",
    run=run,
    issue=439,
)
