"""An unarmed declared hook must be able to fail a run.

The detector already exists and is correct. `verify_armed()`
(`src/thalamus/harness/install.py:843`) was written for a real incident its own
docstring records: `room-guard.sh` was declared in `HOOK_WIRING` and absent from
`settings.json`, so it never ran — and because `eval/rooms.py` builds a room's realized
edges only from rows that guard writes, every real room read as *"TREATMENT DID NOT
OCCUR — a set of solo sessions wearing a room label."*

This case does not re-assert that detector. It asserts the thing one level up, which
nothing checks: that the detector can gate. `install.py:877` sets `advisory=True`, and
`install.py:1023` computes `failed = [c for c in checks if not c.ok and not c.advisory]`
— so `thalamus init --check` exits 0 with hooks unarmed. A correct signal is wired to
nothing that enforces it, which is the same shape as the bug it was written to catch.

That advisory choice is DEFENSIBLE for `thalamus init`: the docstring argues a stale
settings file should not refuse to verify everything else, and that reasoning holds for
an install command a human is watching. It does not hold for CI, which has no human to
read a `!`. So this case is not a claim that `install.py` is wrong — it is the claim
that a CI suite must consume the signal, and today there is no non-advisory path that
does.

Hermetic: builds a settings dict in a temp file and never touches `~/.claude`.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier


def _settings_missing_one_wiring(wiring) -> tuple[dict, tuple[str, str | None, str]]:
    """Build a settings blob armed with everything EXCEPT one declared wiring.

    Dropped rather than emptied: an absent event key and an event key whose hook list
    omits one script are different failure modes, and the one that actually bit was the
    second — `room-guard.sh` missing from a `PreToolUse` block that existed and looked
    populated.
    """
    dropped = wiring[0]
    hooks: dict[str, list] = {}
    for event, matcher, script in wiring:
        if (event, matcher, script) == dropped:
            continue
        group = {"matcher": matcher} if matcher else {}
        group["hooks"] = [{"type": "command", "command": f"/somewhere/{script}"}]
        hooks.setdefault(event, []).append(group)
    return {"hooks": hooks}, dropped


def run() -> Finding | None:
    from thalamus.harness import install  # noqa: PLC0415

    wiring = tuple(install.HOOK_WIRING)
    if not wiring:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="HOOK_WIRING is empty, so 'nothing missing' and 'nothing declared' "
                    "are indistinguishable and this case proves nothing",
            witness="len(HOOK_WIRING) == 0",
            site="src/thalamus/harness/install.py",
        )

    settings, dropped = _settings_missing_one_wiring(wiring)

    # First: the detector itself must still detect. Without this control, a green below
    # could mean the enforcement gap closed OR that armed_hooks stopped parsing.
    armed = install.armed_hooks(settings=settings)
    if dropped in armed:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="control failed: armed_hooks() reported a wiring that was removed "
                    "from the settings blob, so absence is not detectable here",
            witness=f"dropped={dropped} still present in armed_hooks()",
            site="src/thalamus/harness/install.py:823",
        )

    # Now the actual question: with a wiring provably unarmed, is there a check that
    # would FAIL a run? `verify_armed()` reads USER_SETTINGS from disk, so point it at
    # the temp file rather than monkeypatching the function.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        path.write_text(json.dumps(settings), encoding="utf-8")
        original = install.USER_SETTINGS
        try:
            install.USER_SETTINGS = path
            check = install.verify_armed()
        finally:
            install.USER_SETTINGS = original

    if check.ok:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="control failed: verify_armed() reported OK against settings that "
                    "provably omit a declared wiring",
            witness=f"dropped={dropped}, check.ok=True, detail={check.detail!r}",
            site="src/thalamus/harness/install.py:843",
        )

    if getattr(check, "advisory", False):
        return Finding(
            failure_class=FailureClass.UNENFORCED_SIGNAL,
            summary=(
                "verify_armed() correctly detects an unarmed declared hook but returns "
                "advisory=True, and install.py:1023 excludes advisory checks from the "
                "failure set — so no run can be gated on it and a hook wired to nothing "
                "passes CI"
            ),
            witness=f"dropped={dropped}, check.ok=False, check.advisory=True",
            site="src/thalamus/harness/install.py:877 (flag) / :1023 (exclusion)",
        )

    return None


CASE = Case(
    name="unarmed-hook-must-gate",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.UNENFORCED_SIGNAL, FailureClass.COLLAPSED_SENTINEL),
    summary="a declared-but-unarmed hook must be able to fail a run, not only advise",
    run=run,
)
