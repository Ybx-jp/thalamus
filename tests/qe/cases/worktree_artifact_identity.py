"""`artifact_paths.relativize` keys an Artifact's `repo` identity to the bare checkout
directory name, so two worktree checkouts of one repository mint two identities for
the same file instead of one.

Issue #157 measured this against the live graph: 125 Artifact vertices for one file
present under three `thalamus-notes` worktrees, split across `-r1`/`-r2`/`-r3`
directory-name spellings, with 23 TOUCHES edges fragmented across them. The module's
own docstring names worktree fragmentation as in scope
(`src/thalamus/substrate/artifact_paths.py`, "Raw tool-call strings do not deliver
that ... via a worktree from a third"), so this is a defect against the module's
stated contract.

The fixture is a throwaway git repository, built fresh under a tmpdir on every run, with
a second worktree checked out beside it — never the operator's real checkouts. HOME and
git's system/global config are redirected for the same reason `home_isolation.py`
redirects them: nothing here may read or write the operator's real `~/.gitconfig`.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_RELATIVE_FILE = "notes/plan.md"


def _git(args: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), env=env,
        capture_output=True, text=True, timeout=30, check=True,
    )
    return proc.stdout.strip()


def _isolated_env(fake_home: Path) -> dict[str, str]:
    """No inherited identity, no inherited signing key, no system config.

    A global `commit.gpgsign` or missing `user.email` on the real box must not change
    whether this fixture builds — the git repos it creates are throwaway and the
    identity that commits them is fixed here, not read from the operator's config.
    """
    return {
        "HOME": str(fake_home),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "qe", "GIT_AUTHOR_EMAIL": "qe@example.invalid",
        "GIT_COMMITTER_NAME": "qe", "GIT_COMMITTER_EMAIL": "qe@example.invalid",
    }


def _make_repo(root: Path, env: dict[str, str]) -> Path:
    """A one-commit repo with `_RELATIVE_FILE` committed, resolved absolute path."""
    root.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], cwd=root, env=env)
    _git(["config", "commit.gpgsign", "false"], cwd=root, env=env)
    (root / "notes").mkdir()
    (root / _RELATIVE_FILE).write_text("shared content\n")
    _git(["add", "-A"], cwd=root, env=env)
    _git(["commit", "-q", "-m", "init"], cwd=root, env=env)
    return root.resolve()


def _add_worktree(main_root: Path, target: Path, env: dict[str, str]) -> Path:
    _git(["worktree", "add", str(target)], cwd=main_root, env=env)
    return target.resolve()


def _common_dir(root: Path, env: dict[str, str]) -> str:
    return _git(
        ["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root, env=env,
    )


def run() -> Finding | None:
    from thalamus.substrate.artifact_paths import relativize  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        fake_home = tmp_root / "home"
        fake_home.mkdir()
        env = _isolated_env(fake_home)

        # --- The worktree fixture: one repo, two checkouts. ---
        main_root = _make_repo(tmp_root / "repo-main", env)
        secondary_root = _add_worktree(
            main_root, tmp_root / "repo-secondary", env,
        )

        main_common = _common_dir(main_root, env)
        secondary_common = _common_dir(secondary_root, env)

        # CONTROL (fixture sanity): both checkouts must actually be one repository, or
        # a repo-identity mismatch below would be correct behaviour and not a defect.
        if main_common != secondary_common:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the worktree fixture did not produce a shared git-common-dir, "
                        "so a repo-identity mismatch below would prove nothing",
                witness=f"git-common-dir main={main_common!r} secondary={secondary_common!r}",
                site="tests/qe/cases/worktree_artifact_identity.py",
            )

        registry = [str(main_root), str(secondary_root)]
        identifier_main = str(main_root / _RELATIVE_FILE)
        identifier_secondary = str(secondary_root / _RELATIVE_FILE)
        repo_main, path_main = relativize(identifier_main, registry)
        repo_secondary, path_secondary = relativize(identifier_secondary, registry)

        if not repo_main or not repo_secondary:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="relativize resolved neither or only one checkout root, so this "
                        "case is exercising a registry miss rather than the identity "
                        "the two worktrees actually mint",
                witness=f"repo_main={repo_main!r} repo_secondary={repo_secondary!r} "
                        f"registry={[Path(r).name for r in registry]}",
                site="tests/qe/cases/worktree_artifact_identity.py",
            )
        if path_main != path_secondary:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the two worktrees resolved to different relative paths for the "
                        "one file committed to both, so a repo-identity mismatch below "
                        "would not be isolating the worktree defect",
                witness=f"path_main={path_main!r} path_secondary={path_secondary!r}",
                site="tests/qe/cases/worktree_artifact_identity.py",
            )

        # --- CONTROL: two roots of genuinely DIFFERENT repositories must legitimately
        # mint two identities, or "two identities" proves nothing about this defect. ---
        repo_x_root = _make_repo(tmp_root / "repo-x", env)
        repo_y_root = _make_repo(tmp_root / "repo-y", env)
        registry_c = [str(repo_x_root), str(repo_y_root)]
        repo_x, _ = relativize(str(repo_x_root / _RELATIVE_FILE), registry_c)
        repo_y, _ = relativize(str(repo_y_root / _RELATIVE_FILE), registry_c)
        common_x = _common_dir(repo_x_root, env)
        common_y = _common_dir(repo_y_root, env)
        if repo_x == repo_y or common_x == common_y:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="two independently-initialised repositories did not mint two "
                        "distinct identities (or shared a git-common-dir), so this case's "
                        "positive control is broken and the worktree comparison below "
                        "cannot be trusted",
                witness=f"repo_x={repo_x!r} repo_y={repo_y!r} "
                        f"common_x={common_x!r} common_y={common_y!r}",
                site="tests/qe/cases/worktree_artifact_identity.py",
            )

        # --- GREEN direction: a comparator keyed on git-common-dir instead of bare
        # directory name DOES fold the two worktree roots to one identity (checked
        # above: main_common == secondary_common), so the mismatch below is the
        # derivation defect and not a broken assertion. ---
        if repo_main == repo_secondary:
            return None  # already folds to one identity

        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "artifact_paths.relativize derives an Artifact's repo identity from the "
                "bare checkout directory name, so two worktree checkouts of one "
                "repository mint two identities for the same file; a comparator keyed "
                "on git-common-dir instead folds them to one"
            ),
            witness=(
                f"one repo, two worktrees ({main_root.name!r}, {secondary_root.name!r}), "
                f"shared git-common-dir; relativize gave repo_main={repo_main!r} "
                f"repo_secondary={repo_secondary!r} for the same relative path "
                f"{path_main!r} — two Artifact identities for one file. Control: two "
                f"independent repos correctly mint repo_x={repo_x!r} != repo_y={repo_y!r} "
                f"with distinct git-common-dirs. A comparator keyed on git-common-dir "
                f"instead of bare directory name folds main and secondary to one identity"
            ),
            site="src/thalamus/substrate/artifact_paths.py::relativize",
        )


CASE = Case(
    name="artifact-repo-identity-splits-across-worktrees",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="two worktree checkouts of one repository must resolve one file to one "
            "Artifact repo identity, not one identity per checkout directory name",
    run=run,
    issue=157,
    fixed=False,
)
