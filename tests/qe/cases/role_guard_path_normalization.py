"""A path boundary must bind the file a write reaches, not the string that names it.

`role-guard.sh` decides both path rules on the string in the payload's `file_path`:
`contract/ownership.denies` (which binds `main` too) and `WriteBoundary.denies` both
normalise with `PurePosixPath(...).as_posix()`, which folds `//` and `.` and nothing
else, then `fnmatch` the result. Two spellings of one file therefore get two verdicts:

- **`..` through a sibling directory.** `<repo>/tests/<sibling>/../qe/cases/f.py` is the
  file `<repo>/tests/qe/cases/f.py` once the kernel resolves it, and the string carries
  no `/tests/qe/` for the ownership row `*/tests/qe/*` to match. Scope `main` writes
  the oracle.
- **A symlink.** `.claude/skills/<name>` is a symlink into
  `src/thalamus/harness/skills/<name>` for every skill the package ships, and CLAUDE.md
  states that editing through it works. The string carries no `/src/`, so qe's
  `*/src/*` deny does not match: scope `qe` writes `src/`.

Both are reachable with the editing tools alone, which is what separates them from the
Bash route the guard's header already names. The property: a write the guard blocks
under its canonical path is blocked under every spelling that reaches the same file.

**Controls.** Each boundary blocks its canonical path (`main` → `tests/qe/cases/…`,
`qe` → `src/thalamus/…`) and permits a path it does not own (`main` → `tests/…`,
`qe` → `docs/…`), in the same temporary HOME with the repository's own config root, so
a block or a pass means the rule and not the box. The `..` row's sibling and the
symlink row's link are found on disk, not named, and the case asserts the spelling
resolves to the file the control blocked before it counts a pass as a leak.

**Shown capable of going red.** It is red today, on the two rows above. Resolving the
target (`os.path.realpath`) before matching, in both `denies` functions, turns it
green; matching the realpath only, and not also the string as given, is what a fix has
to avoid, since a deny glob written against the link path would then stop matching.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]
_GUARD = _REPO / "src/thalamus/harness/hooks/claude-code/role-guard.sh"
_CONFIG_ROOT = _REPO / "config"
_SITE = "src/thalamus/contract/ownership.py::_normalise, src/thalamus/contract/manifest.py::WriteBoundary.denies"


def _guard(scope: str, tool: str, tool_input: dict) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory(prefix="qe-roleguard-") as home:
        env = dict(os.environ, HOME=home, THALAMUS_SCOPE=scope, THALAMUS_CONFIG_DIR=str(_CONFIG_ROOT))
        for var in ("CLAUDE_CODE_AGENT", "THALAMUS_ROOM", "THALAMUS_SANDBOX"):
            env.pop(var, None)
        payload = {"tool_name": tool, "session_id": "qe-probe", "cwd": str(_REPO), "tool_input": tool_input}
        return subprocess.run(["bash", str(_GUARD)], input=json.dumps(payload), capture_output=True,
                              text=True, env=env, timeout=60, check=False)


def _write(scope: str, path: str) -> int:
    return _guard(scope, "Write", {"file_path": path, "content": "qe probe"}).returncode


def _edit(scope: str, path: str) -> int:
    return _guard(scope, "Edit", {"file_path": path, "old_string": "a", "new_string": "b"}).returncode


def _rel(path: str) -> str:
    return path.replace(str(_REPO), "<repo>")


def run() -> Finding | None:
    oracle = str(_REPO / "tests/qe/cases/qe-probe.py")
    source = str(_REPO / "src/thalamus/qe-probe.py")
    controls = [("main", oracle, 2), ("main", str(_REPO / "tests/qe-probe.py"), 0),
                ("qe", source, 2), ("qe", str(_REPO / "docs/qe-probe.md"), 0)]
    for scope, path, want in controls:
        got = _write(scope, path)
        if got != want:
            return Finding(FailureClass.FAILED_OPEN if want == 2 else FailureClass.INVARIANT_FALSIFIED,
                           f"control: scope {scope} writing its canonical path gave exit {got}, not {want}",
                           witness=f"{scope} Write {_rel(path)} -> exit {got}", site=_SITE)

    spellings: list[tuple[str, str, str, int]] = []   # (row, scope, spelling, exit)
    siblings = sorted(p for p in (_REPO / "tests").iterdir() if p.is_dir() and p.name != "qe" and p.name[0] not in "._")
    if siblings:
        dotdot = f"{siblings[0]}/../qe/cases/qe-probe.py"
        assert os.path.normpath(dotdot) == oracle
        spellings.append(("ownership */tests/qe/* via ..", "main", dotdot, _write("main", dotdot)))
    links = sorted(p for p in (_REPO / ".claude/skills").iterdir()
                   if p.is_symlink() and (p / "SKILL.md").resolve().is_relative_to(_REPO / "src"))
    if links:
        linked = str(links[0] / "SKILL.md")
        spellings.append(("qe write_boundary */src/* via symlink", "qe", linked, _edit("qe", linked)))
    if not spellings:
        return Finding(FailureClass.COLLAPSED_SENTINEL,
                       "no sibling of tests/qe and no .claude/skills symlink into src/: nothing was probed",
                       site=_SITE)

    leaks = [f"{row}: {scope} {_rel(path)} -> exit {code}" for row, scope, path, code in spellings if code != 2]
    if leaks:
        return Finding(FailureClass.BOUNDARY_LEAK,
                       "role-guard permits a write its own rule blocks, when the path names the same file "
                       "another way",
                       witness="; ".join(leaks), site=_SITE)
    return None


CASE = Case(
    name="role-guard-binds-the-file-not-the-spelling",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.FAILED_OPEN, FailureClass.INVARIANT_FALSIFIED,
             FailureClass.COLLAPSED_SENTINEL),
    summary="a path boundary blocks every spelling of a file it blocks: `..` and symlinks included",
    run=run,
    issue=424,
)
