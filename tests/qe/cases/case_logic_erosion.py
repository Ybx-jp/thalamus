"""Nothing watches a case's own logic, only its expectations. This does.

`expectation_additions.py` diffs `expectations.json` against a base revision.
`oracle_parses_whole.py` diffs the loader's own refusals. `suite_containment.py` watches
the collector. All three watch the file that names a defect as acceptable, or the
machinery that reads it. None of them opens a case module and asks whether its own
logic still does what it did. An agent — or a person — that quietly loosens an
assertion inside a case's `run()`, drops a witness check, or narrows the `FailureClass`
set a case may still emit, makes a real defect stop being detected while
`expectations.json` never changes at all. Every existing guard reports a clean repo in
that world, because none of them looks at the file this one looks at.

The sharper version of the same act: deleting a case module outright, or leaving the
file on disk but dropping its entry from `run.py`'s `CASE_MODULES` tuple. Either one
removes a detector from the suite with no expectation touched and no import error to
surface it — `run.py` only reports a module MALFORMED if something still names it and
the import then fails (`load_cases`, `run.py:94-107`); a name quietly removed from the
tuple imports nothing and fails nothing. This is the direct analogue of EvilGenie's
test-file-edit detector (`scope:qe:claim:836e6af8f6f87de8` — a model deleting test
files after correctly running them, categorized as *misaligned behavior* rather than
reward hacking precisely because it does not positively contribute to the score but
does remove the check), per this scope's round-2 design answer (consultation
`107f3a026be148ba`).

## What counts as weakening, and what does not

A judgment call, made explicit here rather than left for a reviewer to reconstruct from
a raw diff:

- **A case module tracked at the base revision is absent from disk, or absent from
  `CASE_MODULES`, at head.** The sharpest case: the detector is gone and nothing else
  in the suite notices.
- **The `classes=` tuple on a surviving case's `Case(...)` declaration lost a member.**
  `model.py` makes emitting a class outside that tuple MALFORMED, so shrinking the
  tuple is not cosmetic — the case is declaring, structurally, that it can no longer
  legitimately report a defect it used to be able to report.
- **The count of `Finding(...)` construction sites in a surviving case's module
  dropped.** Each one is a distinct place the case can hand back evidence of a defect;
  fewer of them is fewer ways the case can fail, counted structurally rather than by
  reading the diff for intent.

What does NOT count, on purpose: a shrinking line count, a renamed variable, a
docstring edit, tightening a witness string, or restructuring two conditions into one
`and`. None of those drops a class the case declares or a `Finding(` site it could
reach — ordinary editing, not erosion. The three signals above are structural rather
than semantic because "does this assert something weaker" is exactly the judgment call
an agent doing the loosening would also be making, and asking the same kind of question
to check it would buy nothing a reviewer's own read would not already have.

## The base-revision mechanism

Same mechanism as `expectation_additions.py`, duplicated in code rather than imported:
`GITHUB_EVENT_PATH` first, branching on the payload's own `pull_request` key rather
than trying a fixed field order regardless of shape — `pull_request.base.sha` when
that key is present (the merge target, on every action including `synchronize`), else
the top-level `before` (the pushed ref's own prior tip) — then `git merge-base` against
`origin/master`. See `_from_event_payload`'s docstring for why the two shapes are told
apart that way rather than by trying both candidates in order. Duplicated because every
case in this suite is resolved and run independently by name, which is `run.py`'s own
reason for resolving by name rather than holding a callable in data
(`run.py:36-39`); a cross-case import would make this case's behavior depend on
another case module's private internals staying byte-for-byte compatible, which is a
coupling nothing else in this tree accepts.

## The positive control

Two synthetic module-source pairs are fed to the extractors in-process: one plants a
dropped `classes=` member and a dropped `Finding(` site, and both must be caught. One
makes only a cosmetic edit — a renamed local, an added comment, one `if` folded into
another with no branch removed — and must NOT be caught; a detector that fires on every
edit is noise a reviewer will learn to route around, which is the failure mode this
whole suite exists to prevent. A third pair exercises the `CASE_MODULES` extractor the
same way: a planted removal must be caught, and an unchanged tuple must read as
unchanged.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_CASE_NAME = "case-erosion-is-never-silent"

_REPO = Path(__file__).resolve().parents[3]
_CASES_REL = "tests/qe/cases"
_RUNPY_REL = "tests/qe/run.py"
_ZERO = "0" * 40


class Undecidable(Exception):
    """The check could not be performed, so its silence would mean nothing.

    Raised rather than returned: `run.py` renders an exception as MALFORMED, and
    MALFORMED is the one verdict `reconcile()` refuses to let an expectation absorb.
    """


# --------------------------------------------------------------------------- base rev


def _git(*args: str) -> tuple[int, str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(_REPO), *args],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Undecidable(f"git is not usable here, so no base revision exists: {exc}")
    return out.returncode, out.stdout.strip()


def _is_commit(rev: str) -> bool:
    if not rev or set(rev) == {"0"} or rev == _ZERO:
        return False
    rc, _ = _git("cat-file", "-e", f"{rev}^{{commit}}")
    return rc == 0


def _from_event_payload() -> tuple[str, str] | None:
    """The base GitHub computed server-side, which is the part an agent cannot mint.

    Two event shapes, told apart by the payload's own `pull_request` key rather than by
    trying both candidates in a fixed order regardless of shape (#299, and the same bug
    in this function, #311):

    - A `pull_request` event (`opened`, `synchronize`, `reopened`, ...) carries
      `pull_request.base.sha` -- the merge target, requeried by GitHub at the time of
      that action. `synchronize` *also* adds a top-level `before`/`after` pair, but
      those name the PR branch's own previous and new head commit, not the base --
      reading them as "base" on this event was the #299/#311 bug. `base.sha` is a
      required string field of `pull_request.base` on every action, so checking for the
      `pull_request` key first, and reading only `base.sha` once it is present, never
      falls through to a top-level `before` that means something else on this shape.
    - Any other event (no `pull_request` key; this repo's workflow triggers only `push`
      and `pull_request`) carries top-level `before`: the pushed ref's own prior tip,
      immediately before this push landed it.

    Measured against octokit/webhooks' payload schemas and real runs 36122392392
    (`opened`) and 36122562958 (`synchronize`) -- `expectation_additions.py`'s own
    `_from_event_payload`, "Measured against a real run" in that module's docstring --
    rather than re-measured here: this function reads the same two payload shapes the
    same way, so the same evidence applies.
    """
    path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not path or not Path(path).is_file():
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    pull_request = payload.get("pull_request")
    if isinstance(pull_request, dict):
        base = pull_request.get("base")
        rev = base.get("sha") if isinstance(base, dict) else None
        how = "GITHUB_EVENT_PATH:pull_request.base.sha"
    else:
        rev = payload.get("before")
        how = "GITHUB_EVENT_PATH:before (prior tip of the pushed ref)"
    if isinstance(rev, str) and _is_commit(rev):
        return rev, how
    return None


def _base() -> tuple[str, str]:
    """(rev, how it was found). Raises rather than guessing."""
    found = _from_event_payload()
    if found:
        return found

    for ref in ("origin/master", "origin/HEAD"):
        rc, resolved = _git("rev-parse", "--verify", "--quiet", ref)
        if rc != 0 or not resolved:
            continue
        rc, merge_base = _git("merge-base", "HEAD", ref)
        if rc == 0 and _is_commit(merge_base):
            return merge_base, f"git merge-base HEAD {ref}"
        if _is_commit(resolved):
            return resolved, f"git rev-parse {ref}"

    raise Undecidable(
        "no base revision: the forge event payload names none and neither "
        "origin/master nor origin/HEAD resolves, so an erosion cannot be told from an "
        "ordinary edit. Fetch the default branch and rerun"
    )


def _content_at(rev: str, rel: str) -> str | None:
    rc, out = _git("show", f"{rev}:{rel}")
    if rc != 0:
        return None
    return out


def _case_files_at(rev: str) -> set[str]:
    rc, out = _git("ls-tree", "-r", "--name-only", rev, "--", _CASES_REL)
    if rc != 0:
        return set()
    return {ln for ln in out.splitlines() if ln.endswith(".py")}


# ------------------------------------------------------------------------- the ast


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return None


def declared_classes(source: str) -> tuple[str, ...] | None:
    """`FailureClass` member names in the `classes=` kwarg of `CASE = Case(...)`.

    None if the source does not parse, or declares no such call — both mean "cannot
    read", not "declares nothing", the same distinction `oracle_parses_whole.py` draws
    for `expectations.json`'s own declared-vs-loaded count.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if _call_name(node) != "Case":
            continue
        for kw in node.keywords:  # type: ignore[union-attr]
            if kw.arg == "classes" and isinstance(kw.value, (ast.Tuple, ast.List)):
                return tuple(
                    elt.attr for elt in kw.value.elts if isinstance(elt, ast.Attribute)
                )
    return None


def finding_call_count(source: str) -> int | None:
    """How many `Finding(...)` construction sites the module contains, anywhere."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    return sum(1 for node in ast.walk(tree) if _call_name(node) == "Finding")


def case_modules(source: str) -> set[str]:
    """String literals inside `run.py`'s `CASE_MODULES` tuple."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    for node in ast.walk(tree):
        is_target = isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "CASE_MODULES" for t in node.targets
        )
        if is_target and isinstance(node.value, (ast.Tuple, ast.List)):
            return {
                elt.value for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            }
    return set()


def weakenings(rel: str, base_src: str, head_src: str) -> list[str]:
    """Every structural erosion signal between one case module's two revisions."""
    problems: list[str] = []

    base_classes, head_classes = declared_classes(base_src), declared_classes(head_src)
    if base_classes is not None and head_classes is not None:
        dropped = sorted(set(base_classes) - set(head_classes))
        if dropped:
            problems.append(
                f"{rel}: classes= dropped {dropped} — this case can no longer "
                f"legitimately report a Finding of that class (model.py makes an "
                f"emitted class outside the declared set MALFORMED)"
            )

    base_n, head_n = finding_call_count(base_src), finding_call_count(head_src)
    if base_n is not None and head_n is not None and head_n < base_n:
        problems.append(
            f"{rel}: Finding(...) construction sites dropped from {base_n} to "
            f"{head_n} — a way this case could report a defect was removed"
        )

    return problems


# ---------------------------------------------------------------------- the control

_CONTROL_BASE = '''
from ..model import Case, FailureClass, Finding, Substrate, Tier


def run():
    if _bad_a():
        return Finding(failure_class=FailureClass.BOUNDARY_LEAK, summary="a", witness="a")
    if _bad_b():
        return Finding(failure_class=FailureClass.INVARIANT_FALSIFIED, summary="b", witness="b")
    return None


CASE = Case(
    name="planted",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.INVARIANT_FALSIFIED),
    summary="s",
    run=run,
)
'''

_CONTROL_HEAD_WEAKENED = '''
from ..model import Case, FailureClass, Finding, Substrate, Tier


def run():
    if _bad_a():
        return Finding(failure_class=FailureClass.BOUNDARY_LEAK, summary="a", witness="a")
    return None


CASE = Case(
    name="planted",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK,),
    summary="s",
    run=run,
)
'''

_CONTROL_HEAD_HONEST = '''
from ..model import Case, FailureClass, Finding, Substrate, Tier


def run():
    # renamed, commented, folded — no branch or class removed
    first_bad = _bad_a()  # was inlined before
    if first_bad:
        return Finding(failure_class=FailureClass.BOUNDARY_LEAK, summary="a", witness="a")
    if _bad_b():
        return Finding(failure_class=FailureClass.INVARIANT_FALSIFIED, summary="b", witness="b")
    return None


CASE = Case(
    name="planted",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.INVARIANT_FALSIFIED),
    summary="s",
    run=run,
)
'''

_RUNPY_BASE = '''
CASE_MODULES = (
    "qe.cases.alpha",
    "qe.cases.beta",
)
'''

_RUNPY_HEAD_DEREGISTERED = '''
CASE_MODULES = (
    "qe.cases.alpha",
)
'''


def _control() -> None:
    weakened = weakenings("planted.py", _CONTROL_BASE, _CONTROL_HEAD_WEAKENED)
    if len(weakened) != 2:
        raise Undecidable(
            f"the differ did not catch both planted signals (a dropped classes= "
            f"member and a dropped Finding( site): got {weakened!r}"
        )

    honest = weakenings("planted.py", _CONTROL_BASE, _CONTROL_HEAD_HONEST)
    if honest:
        raise Undecidable(
            f"the differ flagged a purely cosmetic edit (renamed local, added "
            f"comment, no class or Finding site dropped) as erosion: {honest!r}. A "
            f"detector that fires on every edit is noise a reviewer will learn to "
            f"ignore, which is the failure mode this whole suite exists to prevent"
        )

    dereg = case_modules(_RUNPY_BASE) - case_modules(_RUNPY_HEAD_DEREGISTERED)
    if dereg != {"qe.cases.beta"}:
        raise Undecidable(
            f"the CASE_MODULES extractor did not isolate the planted removal: "
            f"expected {{'qe.cases.beta'}}, got {dereg!r}"
        )
    unchanged = case_modules(_RUNPY_BASE) - case_modules(_RUNPY_BASE)
    if unchanged:
        raise Undecidable(
            f"an unchanged CASE_MODULES tuple read as having lost entries: "
            f"{unchanged!r}"
        )


# ---------------------------------------------------------------------------- case


def run() -> Finding | None:
    _control()

    rev, how = _base()

    base_runpy = _content_at(rev, _RUNPY_REL)
    base_modules = case_modules(base_runpy) if base_runpy is not None else set()
    head_runpy = (_REPO / _RUNPY_REL).read_text(encoding="utf-8")
    head_modules = case_modules(head_runpy)
    deregistered = sorted(base_modules - head_modules)

    base_files = _case_files_at(rev)
    head_files = {f"{_CASES_REL}/{p.name}" for p in (_REPO / _CASES_REL).glob("*.py")}
    deleted = sorted(base_files - head_files)

    problems: list[str] = []
    if deregistered:
        problems.append(
            f"removed from run.py's CASE_MODULES since {rev[:12]}: {deregistered} — "
            f"the module may still exist on disk but nothing imports it, so it "
            f"raises no import error and produces no case result at all"
        )
    if deleted:
        problems.append(
            f"case file(s) present at {rev[:12]} and absent from disk now: {deleted}"
        )

    for rel in sorted(base_files & head_files):
        base_src = _content_at(rev, rel)
        if base_src is None:
            continue
        try:
            head_src = (_REPO / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        if head_src == base_src:
            continue
        problems.extend(weakenings(rel, base_src, head_src))

    if not problems:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "a case module's own logic eroded since the base revision with no change "
            "to expectations.json — none of the three existing guards "
            "(expectation-additions-are-never-silent, oracle-refuses-a-collapse-it-"
            "cannot-report, in-loop-suite-collects-nothing-from-this-tree) watch "
            "this, because all three watch the expectations file or the collector, "
            "never a case's own run(). A quietly loosened assertion, a dropped "
            "witness check, or a deregistered case makes a real defect stop being "
            "detected while every other check in the suite stays green"
        ),
        witness=f"base={rev[:12]} via {how} | " + " || ".join(problems),
        site=_CASES_REL,
    )


CASE = Case(
    name=_CASE_NAME,
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED,),
    summary="a case module's declared FailureClass set, its Finding(...) sites, and "
            "its own registration in CASE_MODULES may shrink only where a reviewer "
            "can see it happen",
    run=run,
)
