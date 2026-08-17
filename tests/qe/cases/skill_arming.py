"""A skill that ships and is armed for nobody is prose in a directory.

`src/thalamus/harness/skills/` is where the shipped skills live, and shipping one there
arms it for nothing on its own. Two links do that, and they are not the same link:

- `~/.claude/skills/<name>`, written by `thalamus init`, arms it for sessions opened
  anywhere on the box — and only after init has run.
- `.claude/skills/<name>`, **tracked in this repository**, arms it in a fresh clone
  before init has ever run. That is the one a first-time reader of a 0.1.0 tag gets.

Both have failed. `author-repo-diagram` shipped under the package and was symlinked
nowhere and armed for nobody, designer included — a session published a designed page
using the harness's ambient `artifact-design` while the skill the atlas room had just
built for exactly that sat unlinked in the tree (`24c6745`). `track-open-work` shipped the
same way and was linked in a separate later commit (`0086301`). Two instances, two
commits, one shape.

`tests/test_install.py::TestSkills::test_every_shipped_skill_lands_at_user_scope` and
`::test_links_to_the_package_so_one_edit_serves_every_scope` cover the **init-time**
user-scope link. Nothing covers the tracked project-scope set, which is the half a clone
depends on and the half both defects were in.

**`.claude/skills/` holds two kinds of entry, and the invariant is about one of them.**
Most names there are symlinks into the package. `track-open-work` and
`author-repo-diagram` are real directories — project-scope skills that do not ship in the
wheel, and whose content lives at that path and nowhere else. What must hold is the
shipped half: every skill under `src/thalamus/harness/skills/` is reachable through a
tracked entry of the same name that resolves into the package. A real directory holding a
name the package does not use is a skill this repository arms for its own sessions, and
nothing here has an opinion about it.

**Resolved through the links, not compared by name.** A `.claude/skills/x` that is a real
directory, or a symlink into some other checkout, has the right name and arms the wrong
content — and a name-only comparison calls that correct. One name holds one entry, so a
real directory taking a shipped skill's name is the same event as the link being absent:
the package's copy reaches nobody, and the session gets whatever the directory holds
instead, silently, because the name it looked for was there. The three shapes are reported
apart because the repair differs — an absent link is created, a foreign link is repointed,
and a shadowing directory is a decision about which copy is the real one.

**Two controls, both running.** Skills must have been found at all: an empty package
skills directory and a perfectly linked one produce the same empty difference, and "the
glob stopped matching" is a more likely future than "every skill was deleted". And the
classifier is exercised against a synthetic tree on every run — one good link, one
shadowing directory, one foreign link, one absent — because no entry of the last three
kinds exists in this repository to prove the classifier can still see them, and a
classifier that has drifted into calling everything armed reports a clean tree exactly the
way a clean tree does.

**Shown capable of going red.** That synthetic tree is the demonstration, and it runs: it
reports the withheld skill as absent, the real directory as shadowing, and the
outside-the-package symlink as foreign. It is built under `tempfile`, so nothing it does
touches this checkout.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import NamedTuple

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]
_PACKAGE_SKILLS = _REPO / "src" / "thalamus" / "harness" / "skills"
_PROJECT_LINKS = _REPO / ".claude" / "skills"


class Arming(NamedTuple):
    """How each shipped skill is reached from the tracked project-scope directory."""

    armed: dict[str, str]      # name -> resolved path inside the package
    absent: list[str]          # shipped, and no tracked entry carries the name
    shadowed: list[str]        # a real directory holds the name instead of a link
    foreign: list[str]         # a symlink holds the name and resolves outside the package
    dangling: list[str]        # a package symlink naming no shipped skill


def _shipped(package: Path) -> set[str]:
    # The directory is a parameter and never a default argument: a default binds the
    # constant at definition time, which is the capture `ranker-fingerprint-names-dials-in-force`
    # exists to report, and it would make the control below read the live tree.
    if not package.is_dir():
        return set()
    return {p.name for p in package.iterdir()
            if p.is_dir() and (p / "SKILL.md").is_file()}


def _classify(shipped: set[str], links: Path, package: Path) -> Arming:
    """Sort every tracked entry by what it actually arms. Pure over the two directories."""
    armed: dict[str, str] = {}
    shadowed: list[str] = []
    foreign: list[str] = []
    package_dir = package.resolve()

    for entry in sorted(links.iterdir()) if links.is_dir() else []:
        if not entry.is_symlink():
            # A real directory is a project-scope skill. It is this case's business only
            # when it takes a shipped skill's name, which is the one way it can arm
            # content the package thinks it is serving.
            if entry.name in shipped:
                shadowed.append(entry.name)
            continue
        target = entry.resolve()
        if target.parent == package_dir:
            armed[entry.name] = str(target)
        elif entry.name in shipped:
            foreign.append(f"{entry.name} -> {target}")

    named_elsewhere = set(shadowed) | {f.split(" -> ")[0] for f in foreign}
    return Arming(
        armed=armed,
        absent=sorted(shipped - set(armed) - named_elsewhere),
        shadowed=sorted(shadowed),
        foreign=sorted(foreign),
        # A tracked link resolving into the package but naming no shipped skill is the
        # other direction: a link left behind by a rename, arming a directory that no
        # longer exists.
        dangling=sorted(name for name, target in armed.items()
                        if name not in shipped or not Path(target).is_dir()),
    )


def _control() -> str:
    """Drive the classifier over a synthetic tree. Returns a complaint, or "" for sound."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "package"
        links = root / "links"
        outside = root / "other-checkout"
        for directory in (package, links, outside):
            directory.mkdir()
        for name in ("linked", "shadowed", "pointed-away", "unlinked"):
            (package / name).mkdir()
            (package / name / "SKILL.md").write_text("x", encoding="utf-8")
        (outside / "pointed-away").mkdir()

        (links / "linked").symlink_to(package / "linked")
        (links / "shadowed").mkdir()
        (links / "pointed-away").symlink_to(outside / "pointed-away")
        # "unlinked" is deliberately absent, and a project-only directory is present to
        # prove it is not swept up.
        (links / "project-only").mkdir()

        found = _classify(_shipped(package), links, package)

    problems = []
    if sorted(found.armed) != ["linked"]:
        problems.append(f"armed={sorted(found.armed)}, expected ['linked']")
    if found.absent != ["unlinked"]:
        problems.append(f"absent={found.absent}, expected ['unlinked']")
    if found.shadowed != ["shadowed"]:
        problems.append(f"shadowed={found.shadowed}, expected ['shadowed']")
    if len(found.foreign) != 1 or not found.foreign[0].startswith("pointed-away -> "):
        problems.append(f"foreign={found.foreign}, expected the pointed-away link")
    if found.dangling:
        problems.append(f"dangling={found.dangling}, expected none")
    return "; ".join(problems)


def run() -> Finding | None:
    # CONTROL: the classifier must still be able to tell the three broken shapes from an
    # armed one. Nothing in this tree is broken, so without a synthetic tree a classifier
    # that had drifted into calling everything armed would report exactly what a healthy
    # checkout reports.
    complaint = _control()
    if complaint:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the classifier misreads a synthetic tree whose faults are known, so "
                    "its clean reading of this one is not evidence",
            witness=complaint,
            site="tests/qe/cases/skill_arming.py:_classify",
        )

    shipped = _shipped(_PACKAGE_SKILLS)

    # CONTROL: the scan must have found skills. An empty package directory and a fully
    # linked one both yield an empty difference, and the first is the likelier accident —
    # a moved directory, a renamed package path, a glob that stopped matching.
    if not shipped:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no shipped skill was found, so 'every skill is armed' and 'no skill "
                    "was looked for' are the same result",
            witness=f"{_PACKAGE_SKILLS} yielded no directory containing a SKILL.md",
            site="tests/qe/cases/skill_arming.py:_shipped",
        )

    found = _classify(shipped, _PROJECT_LINKS, _PACKAGE_SKILLS)
    if not (found.absent or found.shadowed or found.foreign or found.dangling):
        return None

    parts = []
    if found.absent:
        parts.append("shipped and no tracked entry names it, so it is armed for nobody in "
                     f"a fresh clone: {', '.join(found.absent)}")
    if found.shadowed:
        parts.append("a real directory holds the name, arming its own content instead of "
                     f"the package's: {', '.join(found.shadowed)}")
    if found.foreign:
        parts.append(f"a tracked link arms content outside the package: "
                     f"{', '.join(found.foreign)}")
    if found.dangling:
        parts.append(f"tracked link naming no shipped skill: {', '.join(found.dangling)}")

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "a skill ships in the package and the tracked project-scope entry of its name "
            "does not arm it, so a fresh clone of this release gets the file and not the "
            "skill — the session reaches for an ambient default, or for whatever else "
            "holds the name, and nothing reports it"
        ),
        witness=f"{len(shipped)} shipped, {len(found.armed)} armed through the package; "
                + "; ".join(parts),
        site=".claude/skills vs src/thalamus/harness/skills",
    )


CASE = Case(
    name="every-shipped-skill-is-armed-in-a-fresh-clone",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="every skill in the package must be reachable through a tracked "
            "project-scope entry that resolves into the package",
    run=run,
)
