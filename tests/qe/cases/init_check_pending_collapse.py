"""A blinded install and a never-installed one must not read the same.

Issue #125. `verify_armed()` (`src/thalamus/harness/install.py:1862`) returns three
states over the 17 declared hook wirings: all present (ok), some missing (fatal), or
*all* missing (`pending=True`, `install.py:1899`-1905). `pending` is excluded from
`failed` (`install.py:2294`-2295), so a HOME where every wiring is missing exits 0 —
deliberately, because that is what a machine that has never run `thalamus init` looks
like, and listing all 17 wirings at someone who has not installed yet would be a wall of
text about a machine that is fine.

The defect is that the same branch also fires for a HOME whose `.claude/settings.json`
*exists*, carries a foreign hook, and has none of our 17 wirings — the shape produced by
hand-editing the file, or by another tool replacing it. `armed_hooks()` only ever asks
"is our wiring present"; it has no way to notice that the file it read was not empty.
Both HOMEs report `pending`, both print the identical sentence, both exit 0. A user whose
settings file was silently replaced gets a passing `--check` on a box where distillation,
the guards and the eval taps are all inert — the exact incident `verify_armed` was
written to catch (`room-guard.sh` declared and unarmed, every real room reading as
solo sessions wearing a room label), reopened one level up.

This case does not prescribe the fix — issue #125's own "Open decision" leaves that to
the implementer (the cheap discriminator is whether `~/.claude/settings.json` exists at
all, but whether that suffices or the install needs its own marker is unsettled). It
asserts only that the two states must become DISTINGUISHABLE: different output, a
different exit code, or both.

Three synthetic HOMEs, none of them ever `~`:

- blinded: `.claude/settings.json` present, one foreign `PreToolUse` hook, none of our
  17 wirings.
- never-installed: nothing in HOME at all.
- partial (the discrimination control): 16 of the 17 wirings present, one dropped. This
  is the case issue #125 says is already correct — fatal, not pending — and it is run
  here alongside the other two so that a fix which broke enforcement generally, rather
  than fixing the blinded/never split, could not pass this case by accident: if partial
  ever stopped being fatal, "blinded == never-installed" would just be the shape "the
  whole check does nothing" and this case would be answering the wrong question.

All three go through the actual CLI (`thalamus init --check --harness claude --json`,
via `python -m thalamus.cli` on this interpreter) in a subprocess with `HOME` redirected
to a temp dir — the real command a user runs, not a reimplementation of what it does.
`--json` is `check_report()`'s documented shape for a caller that has to decide something
from a check rather than pattern-match prose, so reading it here is the same contract
`thalamus-eval`'s confinement cell reads.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "tests/qe/cases/init_check_pending_collapse.py"


def _write_settings(home: Path, hooks: dict) -> None:
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "settings.json").write_text(json.dumps({"hooks": hooks}), encoding="utf-8")


def _blinded_settings() -> dict:
    """A settings file that exists, carries a hook, and is none of ours."""
    return {
        "PreToolUse": [{
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "/opt/foreign-tool/audit-shim.sh"}],
        }],
    }


def _partial_settings(wiring: tuple[tuple[str, str | None, str], ...]) -> tuple[dict, tuple]:
    """All declared wirings but one — the shape `hook_arming.py` also builds.

    Not reused from that module directly: this case's control is a subprocess-level
    assertion (the CLI's exit code and JSON row), not `verify_armed()` called in-process,
    so it needs its own settings blob rather than that case's in-process helper.
    """
    dropped = wiring[0]
    hooks: dict[str, list] = {}
    for event, matcher, script in wiring:
        if (event, matcher, script) == dropped:
            continue
        group = {"matcher": matcher} if matcher else {}
        group["hooks"] = [{"type": "command", "command": f"/somewhere/{script}"}]
        hooks.setdefault(event, []).append(group)
    return hooks, dropped


def _run_check(home: Path) -> tuple[int, dict | None, str]:
    """The actual documented surface: `thalamus init --check --harness claude --json`.

    HOME is redirected for this subprocess only — the parent process's real HOME is
    never touched, and nothing here runs `thalamus init` without `--check`.
    """
    env = dict(os.environ)
    env["HOME"] = str(home)
    proc = subprocess.run(
        [sys.executable, "-m", "thalamus.cli", "init", "--check", "--harness", "claude", "--json"],
        capture_output=True, text=True, env=env, timeout=180, check=False,
    )
    try:
        report = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        report = None
    return proc.returncode, report, proc.stdout


def _row(report: dict, key: str) -> dict | None:
    return next((c for c in report["checks"] if c["key"] == key), None)


def run() -> Finding | None:
    from thalamus.harness.install import HOOK_WIRING  # noqa: PLC0415

    wiring = tuple(HOOK_WIRING)
    if not wiring:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="HOOK_WIRING is empty, so 'all missing' and 'nothing declared' are "
                    "indistinguishable and this case proves nothing",
            witness="len(HOOK_WIRING) == 0",
            site="src/thalamus/harness/install.py",
        )

    partial_hooks, dropped = _partial_settings(wiring)

    with tempfile.TemporaryDirectory() as base:
        home_blinded = Path(base) / "blinded"
        home_never = Path(base) / "never-installed"
        home_partial = Path(base) / "partial"
        for home in (home_blinded, home_never, home_partial):
            home.mkdir()
        _write_settings(home_blinded, _blinded_settings())
        # home_never gets no .claude directory at all.
        _write_settings(home_partial, partial_hooks)

        rc_blinded, rep_blinded, raw_blinded = _run_check(home_blinded)
        rc_never, rep_never, raw_never = _run_check(home_never)
        rc_partial, rep_partial, raw_partial = _run_check(home_partial)

    if rep_blinded is None or rep_never is None or rep_partial is None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the sandboxed `thalamus init --check --json` subprocess did not "
                    "produce parseable JSON for at least one HOME, so no comparison "
                    "is possible",
            witness=(f"rc blinded={rc_blinded} raw={raw_blinded[:200]!r}; "
                     f"rc never={rc_never} raw={raw_never[:200]!r}; "
                     f"rc partial={rc_partial} raw={raw_partial[:200]!r}"),
            site=_SITE,
        )

    row_blinded = _row(rep_blinded, "declared_hooks_armed")
    row_never = _row(rep_never, "declared_hooks_armed")
    row_partial = _row(rep_partial, "declared_hooks_armed")
    if row_blinded is None or row_never is None or row_partial is None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the --json report has no 'declared_hooks_armed' row, so this case "
                    "cannot ask its question",
            witness=f"blinded keys={[c['key'] for c in rep_blinded['checks']]}",
            site="src/thalamus/harness/install.py::check_report",
        )

    # CONTROL 1 — discrimination: the partial HOME (16 of 17 armed) must still be
    # FATAL. Issue #125 says this half already works; if it stopped, "blinded reads
    # the same as never-installed" would mean nothing, because nothing would be
    # gating at all.
    if row_partial["state"] != "failed" or rc_partial == 0:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "control failed: a HOME missing 1 of 17 declared wirings did not fail "
                "the run, so this case cannot tell 'the all-missing branch is too "
                "permissive' from 'the whole check does nothing'"
            ),
            witness=(f"partial HOME (dropped {dropped}): state={row_partial['state']} "
                     f"ok={row_partial['ok']} exit={rc_partial} "
                     f"detail={row_partial['detail']!r}"),
            site="src/thalamus/harness/install.py:verify_armed (partial branch)",
        )

    def normalize(detail: str, home: Path) -> str:
        return detail.replace(str(home), "<HOME>")

    detail_blinded = normalize(row_blinded["detail"], home_blinded)
    detail_never = normalize(row_never["detail"], home_never)

    # CONTROL 2 — the comparator can see a difference. Run it against a deliberately
    # mutated copy of one row before trusting a "no difference" verdict below.
    mutated_state, mutated_ok = "failed", False
    comparator_is_alive = (mutated_state, mutated_ok) != (row_never["state"], row_never["ok"])
    if not comparator_is_alive:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "comparator self-check failed: a deliberately mutated (state='failed', "
                "ok=False) row still compared equal to the never-installed row, so this "
                "comparator cannot detect any difference and a green verdict would "
                "prove nothing"
            ),
            witness=f"mutated=('failed', False) never=({row_never['state']!r}, {row_never['ok']!r})",
            site=_SITE,
        )

    same_state = (row_blinded["state"], row_blinded["ok"]) == (row_never["state"], row_never["ok"])
    same_detail = detail_blinded == detail_never
    same_exit = rc_blinded == rc_never

    if same_state and same_detail and same_exit:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "a HOME with .claude/settings.json present, carrying a foreign hook and "
                "none of our 17 declared wirings, reports IDENTICALLY to a HOME with "
                "nothing installed at all — same state, same detail (modulo the HOME "
                "path), same exit code. verify_armed()'s all-missing branch cannot "
                "tell 'never touched' from 'installed then blinded'"
            ),
            witness=(
                f"blinded:  state={row_blinded['state']} ok={row_blinded['ok']} "
                f"exit={rc_blinded} detail={detail_blinded!r}\n"
                f"never:    state={row_never['state']} ok={row_never['ok']} "
                f"exit={rc_never} detail={detail_never!r}\n"
                f"partial (control, dropped {dropped}): state={row_partial['state']} "
                f"exit={rc_partial} detail={row_partial['detail']!r}"
            ),
            site="src/thalamus/harness/install.py:1899 (verify_armed, all-missing branch)",
        )

    return None


CASE = Case(
    name="blinded-install-reads-as-never-installed",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.COLLAPSED_SENTINEL,),
    summary="a HOME with all 17 wirings missing must be distinguishable from one whose "
            "settings file was replaced out from under it",
    run=run,
    issue=125,
    fixed=False,
)
