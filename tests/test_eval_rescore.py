"""
Retroactive contamination stamping (src/thalamus/eval/rescore.py; lab/021-022).

Interfaces: rescore_records / apply_outcomes / write_records / render_rescore.
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

from thalamus.eval import rescore
from thalamus.eval.cost import project_slug

REPO = Path("/home/ybx/code/thalamus")


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
        assert rescore.apply_outcomes(records, outcomes) == 0
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
        assert rescore.apply_outcomes(records, outcomes) == 1
        assert records[0]["rescored_at"].endswith("Z")
        assert records[0]["contaminated"] is False


class TestIdempotence:
    def test_an_already_stamped_record_is_left_alone(self, tmp_path, battery):
        records = [record(tmp_path, contaminated=False, escapes=[])]
        outcomes = rescore.rescore_records(
            records, REPO, tasks_base=battery, projects_base=tmp_path / "projects"
        )
        assert outcomes[0].status == rescore.ALREADY
        assert rescore.apply_outcomes(records, outcomes) == 0

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


class TestWriteRecords:
    def test_write_keeps_the_previous_log(self, tmp_path):
        target = tmp_path / "runs.jsonl"
        target.write_text(json.dumps({"task": "t", "arm": "memory-on"}) + "\n")
        rescore.write_records([{"task": "t", "arm": "memory-on", "contaminated": False}], target)
        backup = target.with_suffix(target.suffix + ".pre-rescore")
        assert backup.is_file(), "the campaign evidence base keeps a pre-write copy"
        assert "contaminated" not in backup.read_text()
        assert "contaminated" in target.read_text()

    def test_round_trips_every_record(self, tmp_path):
        target = tmp_path / "runs.jsonl"
        records = [{"task": f"t{i}", "arm": "memory-on"} for i in range(5)]
        rescore.write_records(records, target)
        assert rescore.load_records(target) == records
