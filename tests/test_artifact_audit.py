"""
Artifact identity fragmentation audit.

Interfaces: thalamus.substrate.artifact_audit.audit_artifact_identity
Infrastructure: none — the graph read is stubbed, the arithmetic is the subject
Scope: whether the audit finds duplicate spellings of one file without trusting
       `project`, and separates the pairs the `(repo, path)` projection has since
       joined from the residue it cannot reach
"""

from thalamus.substrate import artifact_audit
from thalamus.substrate.artifact_audit import audit_artifact_identity


def _rows(monkeypatch, rows):
    monkeypatch.setattr(artifact_audit, "_artifact_rows", lambda _g: rows)


def test_an_absolute_path_duplicating_a_relative_one_is_counted_with_its_touches(monkeypatch):
    """
    Scenario: One file has been written twice — once as a repo-relative path and once
    as an absolute path — and both vertices carry touch edges

    Verifications:
    - The absolute spelling is reported as a duplicate of the relative one
    - The touches stranded on the duplicate are counted

    This is the whole point of the audit. `Artifact` is global so that two experts
    touching one file share a vertex; a second spelling silently breaks that join, and
    the touches on the losing vertex are invisible to anything that queries the winner.
    """
    _rows(monkeypatch, [
        {"identifier": "src/thalamus/cli.py", "project": "thalamus", "touches": 62},
        {"identifier": "/home/u/code/thalamus/src/thalamus/cli.py",
         "project": "thalamus", "touches": 50},
    ])

    audit = audit_artifact_identity(object())

    # Verifies: the duplicate is found, and resolved onto the path it duplicates
    assert len(audit.split_pairs) == 1
    assert audit.split_pairs[0].relative == "src/thalamus/cli.py"

    # Verifies: only the stranded side is counted, not the surviving side
    assert audit.split_pairs[0].touches == 50
    assert audit.stranded_touches == 50


def test_the_audit_does_not_depend_on_project_being_a_real_repo_name(monkeypatch):
    """
    Scenario: The duplicate belongs to a session whose `project` is junk — the live
    graph carries values like a home-directory name, `tmp`, `code` and an episode title

    Verifications:
    - The duplicate is still detected

    Suffix matching is chosen precisely so this holds. Every anchor-based rule — cut
    the absolute path at the project name — inverts on these rows and produces two
    identities for one file, so an audit built on `project` would under-report exactly
    the sessions whose data is worst.
    """
    _rows(monkeypatch, [
        {"identifier": "docs/index.md", "project": "thalamus", "touches": 49},
        {"identifier": "/home/u/code/thalamus/docs/index.md", "project": "u", "touches": 49},
    ])

    audit = audit_artifact_identity(object())

    # Verifies: junk in `project` costs the audit nothing
    assert [pair.relative for pair in audit.split_pairs] == ["docs/index.md"]


def test_a_suffix_that_is_not_a_path_boundary_is_not_a_match(monkeypatch):
    """
    Scenario: One artifact's identifier happens to be a trailing substring of another's
    without being a path component of it

    Verifications:
    - No duplicate is reported

    `.../src/cli.py` ends with the characters of `i.py`, and a naive `endswith` would
    fuse two unrelated files. Fusing is worse than missing here: a missed duplicate
    leaves the graph as it already is, while a wrong merge invents a file that never
    existed and moves touches onto it.
    """
    _rows(monkeypatch, [
        {"identifier": "i.py", "project": "thalamus", "touches": 1},
        {"identifier": "/home/u/code/thalamus/src/cli.py", "project": "thalamus", "touches": 3},
    ])

    audit = audit_artifact_identity(object())

    # Verifies: matching respects path boundaries
    assert audit.split_pairs == []


def test_one_relative_path_owned_by_several_projects_is_reported(monkeypatch):
    """
    Scenario: Two repositories each contain a README.md, one naming it relatively and
    the other absolutely

    Verifications:
    - The path is reported as claimed by both projects

    Repo furniture (README.md, CLAUDE.md, .gitignore, pyproject.toml) is why a bare
    relative path cannot be identity on its own. Resolving the absolute spelling first
    is what makes the second owner visible — counted on raw identifiers, the two never
    meet and the path looks uncontested.
    """
    _rows(monkeypatch, [
        {"identifier": "README.md", "project": "thalamus", "touches": 4},
        {"identifier": "/home/u/code/stepmania/README.md",
         "project": "stepmania-chart-generator", "touches": 2},
    ])

    audit = audit_artifact_identity(object())

    # Verifies: both owners are attributed to the one path
    assert audit.collisions == {
        "README.md": {"thalamus", "stepmania-chart-generator"}
    }


def test_a_split_pair_the_projection_reaches_is_separated_from_the_residue(monkeypatch):
    """
    Scenario: Two split pairs — one whose spellings both anchor onto the same
    `(repo, path)`, and one whose absolute spelling sits in no proven checkout

    Verifications:
    - the anchored pair is reported as joined, with its touches counted as rejoined
    - the unanchored pair is the residue, and the historical totals are unchanged

    Both vertices still exist in both cases; nothing is re-keyed. What separates them is
    whether a reader can reach them together, which is the number the projection was
    built to move. Quoting the whole historical count after the projection landed would
    report work already done as work outstanding.
    """
    _rows(monkeypatch, [
        {"identifier": "src/a.py", "project": "thalamus",
         "repo": "thalamus", "path": "src/a.py", "touches": 9},
        {"identifier": "/home/u/code/thalamus/src/a.py", "project": "thalamus",
         "repo": "thalamus", "path": "src/a.py", "touches": 40},
        {"identifier": "docs/b.md", "project": "thalamus",
         "repo": "", "path": "", "touches": 3},
        {"identifier": "/somewhere/unproven/docs/b.md", "project": "thalamus",
         "repo": "", "path": "", "touches": 7},
    ])

    audit = audit_artifact_identity(object())

    # Verifies: the historical measure is untouched — it is still the honest total
    assert len(audit.split_pairs) == 2
    assert audit.stranded_touches == 47

    # Verifies: only the anchored pair counts as reached
    assert [pair.relative for pair in audit.joined_pairs] == ["src/a.py"]
    assert audit.rejoined_touches == 40

    # Verifies: an unanchored pair shares `("", "")`, which is two unknowns not one file
    assert [pair.relative for pair in audit.residue] == ["docs/b.md"]
