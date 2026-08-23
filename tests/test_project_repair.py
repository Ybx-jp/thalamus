"""
Project re-anchoring — the migration that repairs directory-named `project` values.

Interfaces: thalamus.substrate.project_repair.plan
Infrastructure: real `git init` checkouts under tmp_path, a synthetic pin ledger and
                archive; a fake traversal source, since the planner reads three shapes
                of row and none of them need a live graph
Scope: which values the plan is allowed to touch. Every test here is a case where an
       earlier version of the planner did the wrong thing against the live graph — the
       rules are asymmetric on purpose (too timid is a bug worth having, too eager is
       not) and that asymmetry is what these pin.
"""

import json
import subprocess

from thalamus.substrate import project_repair


def _checkout(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, capture_output=True)
    return str(path)


class _FakeTraversal:
    """Serves `plan`'s queries: rows per label, plus the flat distinct-values sweep."""

    def __init__(self, sessions, threads=(), artifacts=()):
        rows = {"Session": [], "Thread": list(threads), "Artifact": list(artifacts)}
        # `paths` is optional at the call site so the cases that say nothing about
        # touched files do not have to carry an empty list each.
        rows["Session"] = [{"paths": [], **row} for row in sessions]
        self._rows = rows
        self._label = None
        self._flat = False

    def V(self):
        self._label = None
        self._flat = False
        return self

    def has_label(self, label):
        self._label = label
        return self

    def has(self, *_args, **_kwargs):
        return self

    def project(self, *_keys):
        return self

    def by(self, *_args, **_kwargs):
        return self

    def values(self, _key):
        self._flat = True
        return self

    def dedup(self):
        return self

    def to_list(self):
        if self._flat:
            every = [r for rows in self._rows.values() for r in rows]
            return sorted({str(r.get("project", "")) for r in every})
        return self._rows[self._label]


def _ledger(tmp_path, rows):
    path = tmp_path / "pins.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def test_a_directory_name_is_disproved_and_a_repo_name_is_not(tmp_path):
    """
    Scenario: one session ran from a real checkout named `myrepo`; another ran from
    `$HOME`, which exists and is not a checkout

    The whole migration turns on telling those apart, and neither is distinguishable
    from the value alone — `op` and `resumes` are equally directory-shaped, and only
    the recovered working directory says one belongs to a repo and the other does not.
    """
    repo = _checkout(tmp_path / "myrepo")
    loose = tmp_path / "home"
    loose.mkdir()
    ledger = _ledger(tmp_path, [
        {"session_id": "s-good", "cwd": repo},
        {"session_id": "s-junk", "cwd": str(loose)},
    ])
    g = _FakeTraversal([
        {"vid": "v-good", "project": "myrepo", "sid": "s-good", "hashes": []},
        {"vid": "v-junk", "project": "home", "sid": "s-junk", "hashes": []},
    ])

    repair = project_repair.plan(g, ledger=ledger, archive=tmp_path / "archive")

    assert [(c.vid, c.after) for c in repair.changes] == [("v-junk", "")]


def test_a_repo_that_moved_keeps_its_name(tmp_path):
    """
    Scenario: every session carrying `plane` ran in a directory that no longer exists,
    because the checkout was moved rather than deleted

    `git rev-parse` on a vanished path answers "no repo", which is the same answer it
    gives for a path that never had one — and the two demand opposite actions. Absence
    is not evidence. On the live graph this case is `thalamus-plane`, moved into
    `code/graveyard/`, and an earlier planner blanked 53 correctly-labelled vertices.
    """
    ledger = _ledger(tmp_path, [{"session_id": "s-1", "cwd": str(tmp_path / "gone")}])
    g = _FakeTraversal([{"vid": "v-1", "project": "plane", "sid": "s-1", "hashes": []}])

    repair = project_repair.plan(g, ledger=ledger, archive=tmp_path / "archive")

    assert repair.changes == []
    assert [(v, label, value) for v, label, value in repair.left_alone] == [
        ("v-1", "Session", "plane")
    ]


def test_one_session_in_the_wrong_place_cannot_condemn_a_confirmed_repo_name(tmp_path):
    """
    Scenario: many sessions confirm `myrepo` is a checkout; one session labelled
    `myrepo` ran from a loose directory instead

    A verdict is reached about the *value*, not the vertex. The pin ledger records no
    project, so a label `basename(cwd)` could not have produced is indistinguishable
    from a deliberate THALAMUS_PROJECT override — and a name a hundred other sessions
    confirm is not this migration's business. Four such sessions on the live graph
    would otherwise blank `thalamus` and `stepmania-chart-generator`.
    """
    repo = _checkout(tmp_path / "myrepo")
    loose = tmp_path / "elsewhere"
    loose.mkdir()
    ledger = _ledger(tmp_path, [
        {"session_id": "s-1", "cwd": repo},
        {"session_id": "s-2", "cwd": str(loose)},
    ])
    g = _FakeTraversal([
        {"vid": "v-1", "project": "myrepo", "sid": "s-1", "hashes": []},
        {"vid": "v-2", "project": "myrepo", "sid": "s-2", "hashes": []},
    ])

    repair = project_repair.plan(g, ledger=ledger, archive=tmp_path / "archive")

    assert repair.changes == []
    assert ("v-2", "Session", "myrepo") in repair.left_alone


def test_a_subdirectory_of_a_checkout_re_anchors_to_the_checkout(tmp_path):
    """
    Scenario: a session ran from a subdirectory of a repo, so `project` took the
    subdirectory's name

    The other direction of the same defect, and the reason blanking is not the only
    outcome: a value naming a subdirectory of a checkout should re-anchor to the
    checkout's name, not to empty. Threads follow the session they belong to.
    """
    _checkout(tmp_path / "workbench")
    inner = tmp_path / "workbench" / "sub"
    inner.mkdir()
    ledger = _ledger(tmp_path, [{"session_id": "s-1", "cwd": str(inner)}])
    g = _FakeTraversal(
        [{"vid": "v-s", "project": "sub", "sid": "s-1", "hashes": []}],
        threads=[{"vid": "v-t", "project": "sub", "sessions": ["v-s"]}],
    )

    repair = project_repair.plan(g, ledger=ledger, archive=tmp_path / "archive")

    assert {(c.vid, c.after) for c in repair.changes} == {
        ("v-s", "workbench"), ("v-t", "workbench")
    }


def test_the_cwd_is_recovered_from_the_archive_when_the_ledger_has_none(tmp_path):
    """
    Scenario: a session predates the pin ledger, but its transcript was archived

    The first `cwd` in the transcript, not the last — a session that stepped into a
    worktree and exited there must not be re-anchored to where it stopped. Nine of the
    seventeen junk-valued sessions on the live graph are only recoverable this way.
    """
    loose = tmp_path / "home"
    loose.mkdir()
    archive = tmp_path / "archive"
    (archive / "ab").mkdir(parents=True)
    (archive / "ab" / "abcdef.jsonl").write_text(
        json.dumps({"type": "user", "cwd": str(loose)}) + "\n"
        + json.dumps({"type": "assistant", "cwd": "/somewhere/else"}) + "\n"
    )
    g = _FakeTraversal([
        {"vid": "v-1", "project": "home", "sid": "s-1", "hashes": ["abcdef"]},
    ])

    repair = project_repair.plan(g, ledger=tmp_path / "absent.jsonl", archive=archive)

    assert [(c.vid, c.after) for c in repair.changes] == [("v-1", "")]
    assert "archived transcript" in repair.changes[0].evidence


def test_an_artifact_keeps_a_value_that_was_never_disproved(tmp_path):
    """
    Scenario: artifacts carrying a confirmed repo name, next to artifacts carrying a
    disproved one

    Artifacts are global and the session that touched one first does not own its
    identity, so re-anchoring them to the repo their path is really in is the separate
    question of Artifact identity — which is answered with derived properties rather
    than by overwriting what is there. This migration only corrects values that are
    not repo names at all.
    """
    repo = _checkout(tmp_path / "myrepo")
    loose = tmp_path / "home"
    loose.mkdir()
    ledger = _ledger(tmp_path, [
        {"session_id": "s-1", "cwd": repo},
        {"session_id": "s-2", "cwd": str(loose)},
    ])
    g = _FakeTraversal(
        [
            {"vid": "v-1", "project": "myrepo", "sid": "s-1", "hashes": []},
            {"vid": "v-2", "project": "home", "sid": "s-2", "hashes": []},
        ],
        artifacts=[
            {"vid": "a-keep", "project": "myrepo", "identifier": "/gone/file.py"},
            {"vid": "a-fix", "project": "home", "identifier": "/gone/other.py"},
            {"vid": "a-name", "project": "home", "identifier": "some service"},
        ],
    )

    repair = project_repair.plan(g, ledger=ledger, archive=tmp_path / "archive")

    moved = {c.vid for c in repair.changes}
    assert "a-keep" not in moved
    assert {"a-fix", "a-name"} <= moved


def test_an_extraction_sandbox_is_disproved_without_any_filesystem_evidence(tmp_path):
    """
    Scenario: artifacts touched inside an extraction sandbox, whose throwaway cwd was
    deleted with the subprocess and which no Session carries at all

    The evidence path cannot reach these — the sandbox's own run is never distilled, so
    no session carries the value and no directory survives to resolve. `is_sandbox_project`
    is the same test the transcript reader uses to refuse these sessions, so treating it
    as a definitional disproof adds no new judgement about what a sandbox is.
    """
    g = _FakeTraversal(
        [],
        artifacts=[
            {"vid": "a-1", "project": "thalamus-extract-lpe3snna", "identifier": "/gone/x.py"},
            {"vid": "a-2", "project": "notasandbox", "identifier": "/gone/y.py"},
        ],
    )

    repair = project_repair.plan(g, ledger=tmp_path / "none.jsonl", archive=tmp_path / "none")

    assert [(c.vid, c.after) for c in repair.changes] == [("a-1", "")]


def test_touched_files_attribute_a_session_its_cwd_cannot_and_only_when_unanimous(tmp_path):
    """
    Scenario: two sessions run from a directory that is no repo — one touched files in a
    single checkout, the other touched files in two

    Touched paths are recorded tool-call inputs, so this is evidence of the same kind as
    cwd rather than inference about it, and filling an empty value needs no disproof:
    there is nothing there to be wrong about. Unanimity is what keeps it from being a
    guess — one live session names 25 paths across three repos, and a plurality rule
    would hand it to one of them on a 4-1-1 split.
    """
    one = _checkout(tmp_path / "solo")
    other = _checkout(tmp_path / "second")
    (tmp_path / "solo" / "a.py").write_text("")
    (tmp_path / "second" / "b.py").write_text("")
    loose = tmp_path / "home"
    loose.mkdir()
    ledger = _ledger(tmp_path, [
        {"session_id": "s-1", "cwd": str(loose)},
        {"session_id": "s-2", "cwd": str(loose)},
    ])
    g = _FakeTraversal([
        {"vid": "v-1", "project": "", "sid": "s-1", "hashes": [],
         "paths": [f"{one}/a.py"]},
        {"vid": "v-2", "project": "", "sid": "s-2", "hashes": [],
         "paths": [f"{one}/a.py", f"{other}/b.py"]},
    ])

    repair = project_repair.plan(g, ledger=ledger, archive=tmp_path / "archive")

    assert [(c.vid, c.after) for c in repair.changes] == [("v-1", "solo")]


def test_a_correct_value_is_stamped_with_its_evidence_without_moving(tmp_path):
    """
    Scenario: a session whose project already matches the checkout it ran in

    Nothing to re-anchor, but the reason it is trusted was never written down. Without
    this the field arrives blank on every session distilled before it existed — and a
    provenance field that is empty across the whole corpus reads as "unknown", which is
    the state it was added to replace. 219 sessions on the live graph are in this case.
    """
    repo = _checkout(tmp_path / "myrepo")
    ledger = _ledger(tmp_path, [{"session_id": "s-1", "cwd": repo}])
    g = _FakeTraversal([{"vid": "v-1", "project": "myrepo", "sid": "s-1", "hashes": []}])

    repair = project_repair.plan(g, ledger=ledger, archive=tmp_path / "archive")

    assert repair.changes == []
    assert repair.stamps == [("v-1", project_repair.ProjectEvidence.CWD)]


def test_a_cleared_value_carries_no_evidence(tmp_path):
    """
    Scenario: a session run outside any checkout, whose directory name was its project

    There is no project left to justify, so the evidence is absent rather than some
    token meaning "proved to have none". The vocabulary holds only kinds something
    writes; a member for absence would be a state no consumer could act on.
    """
    loose = tmp_path / "home"
    loose.mkdir()
    ledger = _ledger(tmp_path, [{"session_id": "s-1", "cwd": str(loose)}])
    g = _FakeTraversal([{"vid": "v-1", "project": "home", "sid": "s-1", "hashes": []}])

    repair = project_repair.plan(g, ledger=ledger, archive=tmp_path / "archive")

    assert [(c.after, c.kind) for c in repair.changes] == [("", None)]
