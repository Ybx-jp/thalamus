"""A skill that ships and is armed for nobody is prose in a directory.

`src/thalamus/harness/skills/` is where skills live, and shipping one there arms it for
nothing on its own. Two links do that, and they are not the same link:

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

**Resolved through the links, not compared by name.** A `.claude/skills/x` that is a real
directory, or a symlink pointing at some other checkout, has the right name and arms the
wrong content — and a name-only comparison calls that correct. Each tracked entry must be
a symlink resolving to the package's own skill directory of the same name.

**The control is that skills were found at all.** An empty package skills directory and a
perfectly linked one produce the same empty difference, and "the glob stopped matching"
is a more likely future than "every skill was deleted".

**Shown capable of going red.** Compare the two sets with one package skill withheld: the
case reports `invariant-falsified` naming it as shipped-but-unlinked. Point one tracked
link at a directory outside the package and it is named as arming foreign content. Both
mutations act on copies of the sets, so neither touches the tree.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]
_PACKAGE_SKILLS = _REPO / "src" / "thalamus" / "harness" / "skills"
_PROJECT_LINKS = _REPO / ".claude" / "skills"


def _shipped() -> set[str]:
    if not _PACKAGE_SKILLS.is_dir():
        return set()
    return {p.name for p in _PACKAGE_SKILLS.iterdir()
            if p.is_dir() and (p / "SKILL.md").is_file()}


def _armed() -> dict[str, str]:
    """Tracked project-scope links that resolve into the package. name -> resolved path."""
    out: dict[str, str] = {}
    if not _PROJECT_LINKS.is_dir():
        return out
    for entry in _PROJECT_LINKS.iterdir():
        if not entry.is_symlink():
            continue
        target = entry.resolve()
        if target.parent == _PACKAGE_SKILLS.resolve():
            out[entry.name] = str(target)
    return out


def run() -> Finding | None:
    shipped = _shipped()

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

    armed = _armed()
    unlinked = sorted(shipped - set(armed))
    # A tracked link resolving into the package but naming no shipped skill is the other
    # direction: a link left behind by a rename, arming a directory that no longer exists.
    dangling = sorted(name for name, target in armed.items()
                      if name not in shipped or not Path(target).is_dir())

    if not unlinked and not dangling:
        return None

    parts = []
    if unlinked:
        parts.append(f"shipped but armed for nobody in a fresh clone: {', '.join(unlinked)}")
    if dangling:
        parts.append(f"tracked link naming no shipped skill: {', '.join(dangling)}")

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "a skill ships in the package and is not armed by the tracked project-scope "
            "link, so a fresh clone of this release gets the file and not the skill — "
            "the session reaches for an ambient default instead and nothing reports it"
        ),
        witness=f"{len(shipped)} shipped, {len(armed)} armed; " + "; ".join(parts),
        site=".claude/skills vs src/thalamus/harness/skills",
    )


CASE = Case(
    name="every-shipped-skill-is-armed-in-a-fresh-clone",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="every skill in the package must be reachable through a tracked "
            "project-scope symlink resolving into the package",
    run=run,
)
