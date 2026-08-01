"""
Retroactive contamination stamping (src/thalamus/eval/rescore.py; lab/021-022).

Interfaces: rescore_records / apply_outcomes / append_revisions / render_rescore.
Infrastructure: a hermetic task battery in tmp_path (an `authored` task has no
`fix_ref`, so nothing here touches git) and synthetic transcripts placed where
`transcript_text` looks; no live graph, no campaign.
Scope: the discipline around the stamps rather than the detectors themselves,
which tests/test_eval_arms.py already covers. Re-scoring is the operation where
a silent default is invisible — there is no live run to contradict it — so the
central obligation is that incomplete evidence refuses a stamp instead of
producing a clean one.
"""

import json
from pathlib import Path

import pytest
import yaml

from thalamus.eval import corpora, rescore
from thalamus.eval.cost import project_slug

# Synthetic. Rescoring reads the transcript's recorded paths, never the disk.
REPO = Path("/repo/thalamus")


@pytest.fixture
def battery(tmp_path):
    """An authored task: no fix_ref, so no ref check and no git call."""
    tasks = tmp_path / "config" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "sample-task.yaml").write_text(yaml.safe_dump({
        "task": "v0",
        "id": "sample-task",
        "title": "A sample task",
        "overlap": "none",
        "source": {"kind": "authored", "ref": "abc1234"},
        "prompt": "do the thing",
    }))
    return tmp_path / "config"


def transcript_for(projects_base, worktree, session_id, *tool_calls):
    slug_dir = projects_base / project_slug(worktree)
    slug_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": name, "input": tool_input},
            ]},
        })
        for name, tool_input in tool_calls
    ]
    (slug_dir / f"{session_id}.jsonl").write_text("\n".join(lines) or "{}")


def record(tmp_path, session_id="sess-1", task="sample-task", arm="memory-on", **over):
    base = {
        "task": task,
        "arm": arm,
        "ts": "2026-07-20T05:45:07Z",
        "worktree": str(tmp_path / "wt" / f"{task}--{arm}--x"),
        "agent": {"session_id": session_id},
    }
    base.update(over)
    return base


class TestIncompleteEvidenceRefusesAStamp:
    """The failure that re-scoring makes invisible: a default that returns a
    plausible value. An arm whose transcript is gone must never be filed as one
    that stayed inside its experiment."""

    def test_missing_transcript_is_refused_not_clean(self, tmp_path, battery):
        records = [record(tmp_path)]
        outcomes = rescore.rescore_records(
            records, REPO, tasks_base=battery, projects_base=tmp_path / "projects"
        )
        assert outcomes[0].status == rescore.NO_TRANSCRIPT
        assert outcomes[0].contaminated is None, "absence of evidence is not clean"
        assert not outcomes[0].stamped

    def test_a_refused_record_is_left_unstamped(self, tmp_path, battery):
        records = [record(tmp_path)]
        outcomes = rescore.rescore_records(
            records, REPO, tasks_base=battery, projects_base=tmp_path / "projects"
        )
        assert rescore.apply_outcomes(records, outcomes) == []
        assert "contaminated" not in records[0]
        assert "rescored_at" not in records[0]

    def test_missing_session_id_is_refused(self, tmp_path, battery):
        records = [record(tmp_path, agent={})]
        outcomes = rescore.rescore_records(
            records, REPO, tasks_base=battery, projects_base=tmp_path / "projects"
        )
        assert outcomes[0].status == rescore.NO_SESSION
        assert outcomes[0].contaminated is None

    def test_unknown_task_is_refused(self, tmp_path, battery):
        records = [record(tmp_path, task="no-such-task")]
        outcomes = rescore.rescore_records(
            records, REPO, tasks_base=battery, projects_base=tmp_path / "projects"
        )
        assert outcomes[0].status == rescore.UNKNOWN_TASK
        assert outcomes[0].contaminated is None


class TestStamping:
    def test_reading_the_battery_stamps_contaminated(self, tmp_path, battery):
        projects = tmp_path / "projects"
        records = [record(tmp_path)]
        transcript_for(
            projects, Path(records[0]["worktree"]), "sess-1",
            ("Read", {"file_path": str(REPO / "config" / "tasks" / "sample-task.yaml")}),
        )
        outcomes = rescore.rescore_records(
            records, REPO, tasks_base=battery, projects_base=projects
        )
        assert outcomes[0].stamped
        assert outcomes[0].contaminated is True
        assert any(e["kind"] == "answer_key" for e in outcomes[0].escapes)

    def test_a_clean_transcript_stamps_false_not_none(self, tmp_path, battery):
        projects = tmp_path / "projects"
        records = [record(tmp_path)]
        transcript_for(
            projects, Path(records[0]["worktree"]), "sess-1",
            ("Read", {"file_path": "src/thalamus/eval/arms.py"}),
        )
        outcomes = rescore.rescore_records(
            records, REPO, tasks_base=battery, projects_base=projects
        )
        assert outcomes[0].stamped
        assert outcomes[0].contaminated is False, "evidence present and negative"

    def test_apply_marks_the_stamp_as_retroactive(self, tmp_path, battery):
        projects = tmp_path / "projects"
        records = [record(tmp_path)]
        transcript_for(projects, Path(records[0]["worktree"]), "sess-1")
        outcomes = rescore.rescore_records(
            records, REPO, tasks_base=battery, projects_base=projects
        )
        revisions = rescore.apply_outcomes(records, outcomes)
        assert len(revisions) == 1
        assert revisions[0]["rescored_at"].endswith("Z")
        assert revisions[0]["contaminated"] is False
        # The verdict is a new revision; the record it was derived from is untouched.
        assert "rescored_at" not in records[0]
        assert revisions[0]["supersedes"] == corpora.body_digest(records[0])


class TestIdempotence:
    def test_an_already_stamped_record_is_left_alone(self, tmp_path, battery):
        records = [record(tmp_path, contaminated=False, escapes=[])]
        outcomes = rescore.rescore_records(
            records, REPO, tasks_base=battery, projects_base=tmp_path / "projects"
        )
        assert outcomes[0].status == rescore.ALREADY
        assert rescore.apply_outcomes(records, outcomes) == []

    def test_force_re_derives(self, tmp_path, battery):
        projects = tmp_path / "projects"
        records = [record(tmp_path, contaminated=False, escapes=[])]
        transcript_for(
            projects, Path(records[0]["worktree"]), "sess-1",
            ("Read", {"file_path": str(REPO / "config" / "tasks" / "sample-task.yaml")}),
        )
        outcomes = rescore.rescore_records(
            records, REPO, tasks_base=battery, projects_base=projects, force=True
        )
        assert outcomes[0].stamped and outcomes[0].contaminated is True


class TestUnitsAndGrouping:
    """lab/022 reported "9 of 88" — 9 git-reach events against an 88-arm
    denominator, spanning six campaigns. Both halves are fixed here."""

    def test_a_campaign_is_one_tasks_arms_not_one_days(self):
        same_day = [
            rescore.Outcome(0, "task-a", "memory-on", "2026-07-26", rescore.STAMPED),
            rescore.Outcome(1, "task-b", "memory-on", "2026-07-26", rescore.STAMPED),
        ]
        assert len({o.campaign for o in same_day}) == 2

    def test_history_hits_include_fix_naming_reaches(self):
        """`detect_history_reach` files a reach naming the fix as `answer_key`,
        so counting only `history_reach` undercounts the git channel."""
        outcome = rescore.Outcome(
            0, "t", "memory-on", "2026-07-27", rescore.STAMPED,
            escapes=[
                {"tool": "Bash", "path": "git show", "kind": "answer_key",
                 "command": "git show deadbee"},
                {"tool": "Read", "path": "src/x.py", "kind": "operator_repo"},
            ],
        )
        assert len(outcome.history_hits) == 1

    def test_render_states_arms_and_events_separately(self):
        outcome = rescore.Outcome(
            0, "t", "memory-on", "2026-07-27", rescore.STAMPED,
            contaminated=False,
            escapes=[
                {"tool": "Bash", "path": "git log", "kind": "history_reach",
                 "command": "git log --all"},
                {"tool": "Bash", "path": "git show", "kind": "history_reach",
                 "command": "git show cafe123"},
            ],
        )
        out = rescore.render_rescore([outcome], wrote=False)
        assert "1/1 arms" in out and "2 event(s)" in out
        assert "LOWER BOUND" in out
        assert "DRY RUN" in out


class TestAppendRevisions:
    """The write-side half of the corpus pin: re-scoring appends, never overwrites.

    The corpus lost 88 pre-rescore judgements to in-place rewrites and kept nothing
    but a `restamped_by` marker on 23 more (lab/038). These pin the property that
    would have prevented it.
    """

    def test_the_superseded_body_stays_on_disk(self, tmp_path):
        target = tmp_path / "runs.jsonl"
        prior = {"ts": "2026-07-01T00:00:00Z", "task": "t", "arm": "memory-on",
                 "contaminated": False}
        target.write_text(json.dumps(prior) + "\n")

        revised = corpora.supersede(
            {**prior, "contaminated": True}, prior, scorer_config="d1:test"
        )
        rescore.append_revisions([revised], target)

        lines = [json.loads(line) for line in target.read_text().splitlines()]
        assert len(lines) == 2, "the revision is appended, not written over the original"
        assert lines[0] == prior, "nothing already written moved"
        assert lines[1]["supersedes"] == corpora.body_digest(prior)
        assert lines[1]["revision"] == 1

    def test_load_records_returns_the_head_revision(self, tmp_path):
        target = tmp_path / "runs.jsonl"
        prior = {"ts": "2026-07-01T00:00:00Z", "task": "t", "arm": "memory-on",
                 "contaminated": False}
        revised = corpora.supersede(
            {**prior, "contaminated": True}, prior, scorer_config="d1:test"
        )
        target.write_text(
            json.dumps(prior) + "\n" + json.dumps(revised) + "\n"
        )
        current = rescore.load_records(target)
        assert len(current) == 1, "two revisions of one run are one run"
        assert current[0]["contaminated"] is True

    def test_records_written_before_revisions_existed_still_load(self, tmp_path):
        target = tmp_path / "runs.jsonl"
        records = [
            {"ts": f"2026-07-0{i}T00:00:00Z", "task": f"t{i}", "arm": "memory-on"}
            for i in range(1, 6)
        ]
        target.write_text("".join(json.dumps(r) + "\n" for r in records))
        assert rescore.load_records(target) == records


# --------------------------------------------------------------------------------------
# memo-echo re-scoring: a superseded judge's verdicts, re-derived under the current one.
# --------------------------------------------------------------------------------------


def test_a_record_with_no_memo_is_not_rescored(tmp_path):
    """
    Scenario: memory-on and memory-off arms reach the memo-echo re-scorer

    They were never handed a memo, so there is no verdict to re-derive. Refusing by
    reason keeps them distinguishable from an injected arm whose evidence is gone.
    """
    from thalamus.eval.rescore import NOT_INJECTED, memo_echo_outcomes

    outcomes = memo_echo_outcomes([
        {"task": "t", "arm": "memory-on", "ts": "2026-07-30T10:00:00"},
        {"task": "t", "arm": "memory-off", "ts": "2026-07-30T10:00:00"},
    ])

    assert [o.status for o in outcomes] == [NOT_INJECTED, NOT_INJECTED]
    assert all(o.memo_echoed is None for o in outcomes)


def test_an_injected_arm_with_no_transcript_is_refused_not_stamped(tmp_path):
    """
    Scenario: A ceiling arm whose transcript is gone — the confined arm wrote it into
    the container HOME beside the worktree, and both were deleted

    Verifications:
    - the outcome is a refusal carrying the session id
    - nothing is stamped

    This is the failure lab/022 caught in `transcript_text`: a default that returns a
    plausible value instead of failing files a verdict nobody can check. Re-scoring is
    exactly where that would be invisible, since there is no live run to contradict it.
    """
    from thalamus.eval.rescore import NO_TRANSCRIPT, memo_echo_outcomes

    outcomes = memo_echo_outcomes([{
        "task": "arm-runner-session-death-classification",
        "arm": "ceiling",
        "ts": "2026-07-30T10:30:24",
        "worktree": str(tmp_path / "gone"),
        "agent": {"session_id": "abc-123"},
        "memo_echoed": {"used": True, "ratio": 0.486, "evidence": "cited by vertex ID"},
    }])

    assert outcomes[0].status == NO_TRANSCRIPT
    assert "abc-123" in outcomes[0].detail
    assert outcomes[0].memo_echoed is None


def test_applying_a_memo_rescore_keeps_the_prior_verdict_beside_the_fresh_one():
    """
    Scenario: A stale verdict is re-derived and written back

    Verifications:
    - the fresh verdict replaces the stored one
    - the prior value survives under `memo_echoed_prior`
    - the record is marked as retroactively re-scored

    The old value is the only evidence of which judge the corpus used to carry.
    Discarding it while fixing a provenance gap would be the same mistake pointing the
    other way — so the fix keeps both and says which is which.
    """
    from thalamus.eval.rescore import Outcome, STAMPED, apply_outcomes

    records = [{
        "task": "t", "arm": "ceiling", "ts": "2026-07-30T11:46:34",
        "memo_echoed": {"used": True, "ratio": 0.784, "evidence": "cited by vertex ID"},
    }]
    outcome = Outcome(index=0, task="t", arm="ceiling", date="2026-07-30", status=STAMPED)
    outcome.memo_echoed = {
        "used": True, "ratio": 0.784, "evidence": "matched 29/37 terms: arm, arms",
        "judge_config": "j1:shipped-t2-r0.3",
    }

    revisions = apply_outcomes(records, [outcome])
    assert len(revisions) == 1
    revised = revisions[0]

    assert revised["memo_echoed"]["evidence"].startswith("matched 29/37")
    assert revised["memo_echoed"]["judge_config"] == "j1:shipped-t2-r0.3"
    # Verifies: the superseded judge's output is preserved, not overwritten
    assert revised["memo_echoed_prior"]["evidence"] == "cited by vertex ID"
    assert revised["memo_echo_rescored_at"]
    # Verifies: a memo re-score does not masquerade as a contamination stamp
    assert "contaminated" not in revised
    assert "rescored_at" not in revised
    # Verifies: the record it was derived from is left exactly as it was, and the
    # revision names the body it replaces rather than only the fact of replacement.
    assert records[0]["memo_echoed"]["evidence"] == "cited by vertex ID"
    assert revised["supersedes"] == corpora.body_digest(records[0])
    assert revised["scorer_config"] == "j1:shipped-t2-r0.3"
