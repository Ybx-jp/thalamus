"""Consent is obtained for a named blast radius, and the radius must be the real one.

`thalamus init` writes into two editors' user-scope configuration — hook entries that
then run in every session on the box, in every directory — so `9bcd7c7` put a prompt in
front of it that names its write targets before asking. That prompt is the release's
consent mechanism, and consent is only as good as the description it was given for.

The property: **every path the installer creates under HOME is a path the prompt
named.** A target that appears in the code and not in the prompt is a write the operator
declined to be told about while being asked to approve the rest — and it is silent in
exactly the way that matters, because the prompt still looks complete.

Nothing else checks this. `_confirm()`'s list is hand-written prose enumerating five
targets; `install()` derives its targets from module constants; the two are joined only
by whoever edits both in the same change. `tests/test_install.py` asserts on the files it
patched, so a sixth target it did not think to patch is invisible to it by construction —
and would land in the operator's real `~/.claude` while its suite reported green.

The direction of the containment is deliberate and one-way. Naming a path the installer
does not currently write is not a failure: `_confirm()` names `~/.claude.json`, which
`claude mcp add` writes in a child process this probe stubs (see `_install_sandbox`), and
over-disclosure is not the harm. Under-disclosure is.

**Coverage is ancestry, not equality.** `.claude/skills/gremlin-python` is covered by a
prompt line naming `.claude/skills`, and the `.claude` directory itself is covered as an
*ancestor* of a named path — creating a parent on the way to a disclosed child discloses
nothing new. Uncovered means neither: a created path that is in no ancestor/descendant
relationship with anything the prompt named.

**The positive control runs.** A case asserting "no undisclosed path was found" and a case
whose predicate can no longer find one produce the same green, so the coverage predicate
is exercised against a synthetic undisclosed path on every run, and a predicate that calls
that one covered fails the case as MALFORMED-in-substance rather than passing.

**Shown capable of going red.** Mutate the *consent text* rather than `install()` — the
probe returns a plain dataclass, so `dataclasses.replace(probe, consent=...)` poisons it
with no edit to `src/`, and the mutant must be fed by rebinding this module's own
`observe` (it is bound at import; patching `_install_sandbox.observe` leaves the real
probe running and every mutant "passes"). Dropping the `symlinks the shipped skills` line
reports `doc-code-drift` naming eight undisclosed paths under `.claude/skills`; replacing
the whole text with `approve? [y/N]` reports the `collapsed-sentinel` control instead of a
false red, which is the distinction that matters.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._install_sandbox import observe

# Paths in the prompt's own text. `_confirm()` interpolates the constants, so the
# disclosed set is read out of what the operator is actually shown rather than out of the
# constants the check would then be comparing against themselves. `~` is a disclosure:
# the prompt writes `~/.claude.json` where it names a file the CLI owns, and a reader
# taking that as undisclosed would be reporting on the tilde.
_PATH = re.compile(r"~?/[^\s,]+")

# Written by the interpreter, uv, or the OS rather than by the installer. Present in the
# footprint because the child imports the package, and outside the subject: the claim is
# about what `install()` discloses, not about what running Python does to a home dir.
_NOT_OURS = (".cache/", ".local/share/uv/", ".venv/", ".config/uv/")


def _disclosed(consent: str, home: str) -> set[str]:
    return {p.rstrip(".").replace("~", home, 1) for p in _PATH.findall(consent)}


def _covered(created_abs: str, disclosed: set[str]) -> bool:
    """Is this created path named, inside something named, or on the way to one?"""
    created = PurePosixPath(created_abs)
    for name in disclosed:
        named = PurePosixPath(name)
        if created == named:
            return True
        if named in created.parents:      # created inside a disclosed directory
            return True
        if created in named.parents:      # a parent created on the way to a disclosed path
            return True
    return False


def run() -> Finding | None:
    probe = observe()
    if isinstance(probe, str):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the install probe did not run, so 'every write was disclosed' and "
                    "'no write was observed' are the same result",
            witness=probe,
            site="tests/qe/cases/_install_sandbox.py",
        )

    home = probe.home.rstrip("/")
    disclosed = _disclosed(probe.consent, home)

    # CONTROL: the prompt must have been shown at all. An empty or path-free consent text
    # would make every created path uncovered (a false red) or, if the footprint were also
    # empty, make the case vacuous. Either way it is not evidence about disclosure.
    if len(disclosed) < 2:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the consent prompt named fewer than two paths, so there is no "
                    "disclosed radius to compare the installer's writes against",
            witness=f"consent text ({len(probe.consent)} chars) yielded {sorted(disclosed)}",
            site="src/thalamus/harness/install.py:_confirm",
        )

    footprint = [rel for rel in probe.created
                 if not any(rel == p.rstrip("/") or rel.startswith(p) for p in _NOT_OURS)]

    # CONTROL: the installer must have written something. "Nothing undisclosed" is the
    # answer a no-op install gives too, and a no-op install is a plausible future — a
    # changed constant, a raised exception swallowed upstream, a harness flag default.
    if not footprint:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the installer created no paths under the redirected HOME, so this "
                    "case would report clean disclosure for an installer that does nothing",
            witness=f"install actions: {' | '.join(probe.install_actions)[:400]}",
            site="src/thalamus/harness/install.py:install",
        )

    # CONTROL, and it runs: the predicate must be able to say "uncovered" at all. A
    # coverage test that has drifted into always-true would clear every real target too.
    synthetic = f"{home}/.config/thalamus/undisclosed-state.json"
    if _covered(synthetic, disclosed):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the coverage predicate calls a path no prompt line names 'covered', "
                    "so it cannot detect an undisclosed write and its green means nothing",
            witness=f"synthetic={synthetic} was judged covered by {sorted(disclosed)}",
            site="tests/qe/cases/install_consent.py:_covered",
        )

    undisclosed = sorted(rel for rel in footprint
                         if not _covered(f"{home}/{rel}", disclosed))
    if not undisclosed:
        return None

    return Finding(
        failure_class=FailureClass.DOC_CODE_DRIFT,
        summary=(
            "`thalamus init` writes paths its consent prompt does not name: the operator "
            "approves a blast radius smaller than the one that lands, and the prompt reads "
            "complete either way"
        ),
        witness=(
            f"{len(undisclosed)} undisclosed of {len(footprint)} created: "
            + "; ".join(undisclosed[:8])
            + (f" (+{len(undisclosed) - 8} more)" if len(undisclosed) > 8 else "")
            + f" | disclosed: {', '.join(sorted(disclosed))}"
        ),
        site="src/thalamus/harness/install.py:_confirm vs install()",
    )


CASE = Case(
    name="consent-names-every-path-install-writes",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.DOC_CODE_DRIFT, FailureClass.COLLAPSED_SENTINEL),
    summary="every path `thalamus init` creates under HOME must be one its consent "
            "prompt named before asking",
    run=run,
)
