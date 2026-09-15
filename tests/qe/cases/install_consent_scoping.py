"""The consent radius for a narrowed `--harness` run must not name another harness's
write targets.

A different property from `install_consent`'s. That case checks one-way containment —
every path `install()` creates is one the prompt named — and its docstring rules
over-disclosure out of scope on purpose: `_confirm()` naming `~/.claude.json`, which a
stubbed child process writes, is a disclosure the operator can act on, not a defect.
That reasoning holds for the ALL_HARNESSES run it probes, where the full nine-line
radius is the truthful description of what the run will touch.

It stops holding once a selection narrows the run. `_confirm()` used to print an
unconditional blast-radius list regardless of `--harness`, so `--harness claude`
showed the operator `~/.cursor/hooks.json`, `~/.cursor/mcp.json`,
`~/.codex/hooks.json`, `~/.codex/config.toml` and "one derived codex profile per
expert" under `~/.codex` — five lines naming writes that specific run could not
reach, because `install()` gates the cursor and codex legs on membership in the
selection (`install.py:1986-1989`) (#220). An operator approving that prompt consents
to a radius wider than the one that lands, and the prompt still reads complete. This
is not the inverse of `install_consent`'s containment — it is a second, independent
property: **the radius named for selection X contains no target exclusive to a
harness outside X.**

**No sandbox, no redirected HOME.** `_confirm()` only prints and then declines on a
non-tty stdin — it is a pure function of `harnesses` given non-interactive input, and
the property under test is entirely in what it prints. `install_consent` needs
`_install_sandbox`'s subprocess because it also asserts about what `install()`
*writes*; this case asserts nothing about writes and calling `_confirm()` in-process
is safe by the same reasoning that probe's own docstring gives for why `_confirm` is
called with a declining stdin there too.

**The positive control runs.** `_targets()` names the write targets that belong to
exactly one harness, read off the same `install.py` path constants
`install_cursor`/`install_codex`/the claude branch write through — independent of
`_confirm`, the function actually under suspicion, so a break that moved both in the
same wrong direction would still be caught. Before trusting a clean run, this case
feeds the leak predicate a *synthetic* disclosure, `_confirm_text(install.HARNESSES)`
read for a `claude`-only frame, and requires it to find the cursor and codex targets
leaking in. That frame is not invented for the control: it is the union-of-everything
radius, which is exactly what `--harness claude` printed before #220's fix, because
pre-fix `_confirm()` had no selection to condition on at all. A predicate that cannot
see this control leak could not see the real one either, and this exists as a runtime
control rather than a one-off scratch check specifically so a *future* edit to
`_targets` or `_covers` that quietly stops matching anything is caught here rather
than by a clean suite going on to say nothing was found.

**Shown capable of going red against the shipped defect, not just a stand-in for it.**
`_confirm_text` catches the `TypeError` a pre-#220 `_confirm()` raises when called
with a `harnesses` argument it does not accept, and retries the bare call — so this
same case, unmodified, runs against `git show <pre-fix rev>:src/thalamus/harness/
install.py` too, and reports `BOUNDARY_LEAK` naming cursor's and codex's targets
leaking into every non-matching selection. Verified by hand against that revision
(2026-09-14): the leak set it reports for `--harness claude` there is the same one
`#220` measured on a real box — four paths plus the codex profile directory.
"""

from __future__ import annotations

import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path, PurePosixPath

from thalamus.harness import install

from ..model import Case, FailureClass, Finding, Substrate, Tier

# Same shape as `install_consent._PATH`: a path token in the prompt's own rendered
# text, tilde included because `_consent_lines` writes `~/.claude.json` and
# `~/.thalamus/profiles/` as literals rather than resolving them.
_PATH = re.compile(r"~?/[^\s,]+")


class _NotATty(io.StringIO):
    def isatty(self) -> bool:
        return False


def _confirm_text(harnesses: tuple[str, ...]) -> str:
    """What `_confirm()` prints for this selection. Writes nothing: non-tty stdin makes
    it decline before `input()`, which is the same guarantee `_install_sandbox`'s
    docstring gives for calling it the same way.

    Tolerant of the pre-#220 signature on purpose. `_confirm()` used to take no
    argument at all and print the union of every harness unconditionally; calling it
    with `harnesses` against that shape raises `TypeError` at the call site before the
    function body runs, so the fallback re-issues the bare call inside the same
    `redirect_stdout` block. That is what lets this case run — and go red — against
    the defect as it actually shipped, not only against a synthetic stand-in for it.
    """
    buf = io.StringIO()
    old_stdin = sys.stdin
    sys.stdin = _NotATty()
    try:
        with redirect_stdout(buf):
            try:
                install._confirm(harnesses)
            except TypeError:
                install._confirm()  # ty: ignore[missing-argument]
    finally:
        sys.stdin = old_stdin
    return buf.getvalue()


def _disclosed(text: str, home: str) -> set[str]:
    return {p.rstrip(".").replace("~", home, 1) for p in _PATH.findall(text)}


def _covers(disclosed: set[str], target: str) -> bool:
    """Is `target` named, or inside something named, by the disclosed set? Ancestor
    coverage is deliberately included, the same as `install_consent._covered` — a
    line naming `~/.codex` covers `~/.codex/hooks.json` even though it never spells
    the child out."""
    target_p = PurePosixPath(target)
    for name in disclosed:
        named = PurePosixPath(name)
        if target_p == named or named in target_p.parents:
            return True
    return False


def _targets(home: str) -> dict[str, tuple[str, ...]]:
    """Write targets exclusive to one harness, resolved against this box's home so a
    run under a redirected HOME (there is none here, but a future caller might) is not
    compared against the operator's own paths."""
    return {
        "claude": (str(install.USER_SETTINGS), f"{home}/.claude.json"),
        "cursor": (str(install.USER_CURSOR_HOOKS), str(install.USER_CURSOR_MCP)),
        "codex": (str(install.USER_CODEX_HOOKS), str(install.USER_CODEX_MCP),
                  str(install.CODEX_HOME)),
    }


def _leaks(text: str, home: str, selected: str) -> list[str]:
    disclosed = _disclosed(text, home)
    found = []
    for other, targets in _targets(home).items():
        if other == selected:
            continue
        for t in targets:
            if _covers(disclosed, t):
                found.append(f"--harness {selected} discloses {other}'s {t}")
    return found


def run() -> Finding | None:
    home = str(Path.home())

    # CONTROL: `_confirm_text(install.HARNESSES)` is the union-of-everything radius —
    # on the fixed code it is what a run selecting every harness prints; on the
    # pre-#220 shape it is the ONLY thing `_confirm()` ever printed, unconditionally.
    # Read for a claude-only frame, it is exactly what #220 measured for
    # `--harness claude`. If the leak predicate cannot see cursor's and codex's
    # targets in this frame, a clean result below means nothing.
    unconditioned = _confirm_text(install.HARNESSES)
    control_leaks = _leaks(unconditioned, home, selected="claude")
    if len(control_leaks) < 3:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the leak predicate found fewer than 3 leaks in a synthetic "
                    "disclosure naming every harness's targets read for a claude-only "
                    "selection — the exact shape #220 measured — so a clean run over "
                    "the real `_confirm()` output would mean nothing",
            witness=f"control found {len(control_leaks)}: {control_leaks}",
            site="tests/qe/cases/install_consent_scoping.py:_leaks",
        )

    findings: list[str] = []
    for selected in install.HARNESSES:
        findings.extend(_leaks(_confirm_text((selected,)), home, selected))

    if not findings:
        return None

    return Finding(
        failure_class=FailureClass.BOUNDARY_LEAK,
        summary=(
            "`_confirm()`'s consent text for a narrowed `--harness` selection names "
            "write target(s) exclusive to a harness that was not selected — the "
            "operator approves a wider radius than the run will touch, and the "
            "prompt reads complete either way (#220)"
        ),
        witness="; ".join(findings[:8])
        + (f" (+{len(findings) - 8} more)" if len(findings) > 8 else ""),
        site="src/thalamus/harness/install.py:_confirm",
    )


CASE = Case(
    name="consent-radius-does-not-leak-across-harness-selection",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="the consent prompt for `--harness X` must name no write target exclusive "
            "to a harness other than X",
    run=run,
    issue=220,
    #: The `src/` repair (`_confirm(harnesses)` / `_consent_lines()`) ships in the same
    #: change that lands this case, so this case's first appearance is already the
    #: regression guard for #220, not a red awaiting one. No `expectations.json` entry
    #: exists to delete — there was never a window where this case was red and
    #: unacknowledged in a committed tree.
    fixed=True,
)
