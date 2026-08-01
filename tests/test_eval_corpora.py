"""Named corpus pins over the trajectory run log (src/thalamus/eval/corpora.py; lab/038).

Interfaces: run_id / body_digest / head_revisions / manifest / supersede / seal /
            verify / diff / derivation_fingerprint.
Infrastructure: the registry, manifest directory and pinned directory are all
            redirected into tmp_path. No live graph, no campaign, no git.
Scope: the promises a published study rests on — that a corpus name means one state
       forever, that the manifest can tell a legitimate append from an in-place
       rewrite, and that a re-derived verdict never destroys the one it replaces.
       The detectors themselves are tests/test_eval_arms.py's.
"""

import json

import pytest

from thalamus.eval import corpora


@pytest.fixture
def pinned(tmp_path, monkeypatch):
    """Registry, manifests and sealed copies, all inside tmp_path."""
    monkeypatch.setattr(corpora, "REGISTRY", tmp_path / "corpora.jsonl")
    monkeypatch.setattr(corpora, "MANIFEST_DIR", tmp_path / "manifests")
    monkeypatch.setattr(corpora, "PINNED_DIR", tmp_path / "pinned")
    monkeypatch.setattr(corpora, "_git_ref", lambda: "deadbee")
    return tmp_path


def arm(ts="2026-07-30T10:00:00Z", task="t", armname="memory-on", **over):
    base = {
        "ts": ts,
        "task": task,
        "arm": armname,
        "scope": "main",
        "ref": "abc1234",
        "model": "sonnet",
        "worktree": f"/wt/{task}--{armname}--{ts}",
        "order_index": 0,
        "contaminated": False,
    }
    base.update(over)
    return base


def write_log(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


class TestIdentity:
    """The corpus carries no id field. It has to be derived, and derived stably —
    every guarantee below is downstream of `run_id` meaning one arm run forever."""

    def test_run_id_is_stable_across_verdict_changes(self):
        born = arm()
        rescored = {**born, "contaminated": True, "rescored_at": "2026-07-31T00:00:00Z"}
        assert corpora.run_id(born) == corpora.run_id(rescored), (
            "a re-scored arm is the same run — identity is birth, not verdict"
        )

    def test_different_arms_of_one_campaign_are_different_runs(self):
        assert corpora.run_id(arm(armname="memory-on")) != corpora.run_id(
            arm(armname="memory-off")
        )

    def test_run_id_ignores_key_order(self):
        forward = arm()
        reversed_keys = dict(reversed(list(forward.items())))
        assert corpora.run_id(forward) == corpora.run_id(reversed_keys)

    def test_body_digest_excludes_revision_bookkeeping(self):
        """Stamping a revision must not change the digest of the body being stamped,
        or `supersedes` would never match what it points at."""
        body = arm()
        stamped = {**body, "run_id": "x" * 16, "revision": 3, "supersedes": "y" * 64}
        assert corpora.body_digest(body) == corpora.body_digest(stamped)

    def test_body_digest_tracks_a_verdict_change(self):
        assert corpora.body_digest(arm()) != corpora.body_digest(arm(contaminated=True))


class TestSupersession:
    def test_the_revision_names_the_body_it_replaces(self):
        prior = arm()
        revised = corpora.supersede(
            {**prior, "contaminated": True}, prior, scorer_config="d1:test"
        )
        assert revised["supersedes"] == corpora.body_digest(prior)
        assert revised["revision"] == 1
        assert revised["run_id"] == corpora.run_id(prior)
        assert revised["scorer_config"] == "d1:test"

    def test_supersession_does_not_mutate_the_prior_record(self):
        prior = arm()
        before = json.dumps(prior, sort_keys=True)
        corpora.supersede({**prior, "contaminated": True}, prior, scorer_config="d1:test")
        assert json.dumps(prior, sort_keys=True) == before

    def test_revisions_stack(self):
        prior = arm()
        first = corpora.supersede({**prior, "contaminated": True}, prior, scorer_config="a")
        second = corpora.supersede({**first, "contaminated": False}, first, scorer_config="b")
        assert second["revision"] == 2
        assert second["supersedes"] == corpora.body_digest(first)

    def test_head_revisions_takes_the_latest(self):
        prior = arm()
        revised = corpora.supersede(
            {**prior, "contaminated": True}, prior, scorer_config="d1:test"
        )
        heads = corpora.head_revisions([prior, revised])
        assert len(heads) == 1 and heads[0]["contaminated"] is True

    def test_head_revisions_is_identity_on_a_pre_revision_log(self):
        """Every record written before this discipline existed must read back
        unchanged, or the change would silently rewrite published numbers."""
        records = [arm(ts=f"2026-07-30T1{i}:00:00Z", order_index=i) for i in range(5)]
        assert corpora.head_revisions(records) == records

    def test_head_revisions_preserves_first_appearance_order(self):
        a, b = arm(armname="memory-on"), arm(armname="memory-off", order_index=1)
        revised_a = corpora.supersede({**a, "contaminated": True}, a, scorer_config="x")
        heads = corpora.head_revisions([a, b, revised_a])
        assert [h["arm"] for h in heads] == ["memory-on", "memory-off"]


class TestSeal:
    def test_seal_records_what_was_pinned(self, pinned):
        log = write_log(pinned / "runs.jsonl", [arm(), arm(armname="memory-off", order_index=1)])
        row = corpora.seal("campaign-one", note="two arms", runs_path=log)
        assert row.records == 2
        assert row.git_ref == "deadbee"
        assert row.note == "two arms"
        assert corpora.verify("campaign-one") == (True, True)

    def test_the_sealed_copy_is_read_only(self, pinned):
        log = write_log(pinned / "runs.jsonl", [arm()])
        row = corpora.seal("campaign-one", runs_path=log)
        assert row.pinned_path.is_file()
        assert not (row.pinned_path.stat().st_mode & 0o222), "a pin that can be written is not a pin"

    def test_a_name_cannot_be_reused(self, pinned):
        log = write_log(pinned / "runs.jsonl", [arm()])
        corpora.seal("campaign-one", runs_path=log)
        write_log(log, [arm(), arm(armname="memory-off", order_index=1)])
        with pytest.raises(corpora.CorpusError, match="immutable"):
            corpora.seal("campaign-one", runs_path=log)

    def test_an_invalid_name_is_refused(self, pinned):
        log = write_log(pinned / "runs.jsonl", [arm()])
        with pytest.raises(corpora.CorpusError, match="invalid corpus name"):
            corpora.seal("Campaign One", runs_path=log)

    def test_an_empty_log_is_refused(self, pinned):
        log = write_log(pinned / "runs.jsonl", [])
        with pytest.raises(corpora.CorpusError, match="no records"):
            corpora.seal("campaign-one", runs_path=log)

    def test_verify_separates_a_moved_corpus_from_a_moved_manifest(self, pinned):
        """Two answers, never pooled — the worse failure must not hide behind the
        better one."""
        log = write_log(pinned / "runs.jsonl", [arm()])
        row = corpora.seal("campaign-one", runs_path=log)
        row.manifest_path.write_text("tampered\n")
        assert corpora.verify("campaign-one") == (True, False)


class TestDiff:
    """The distinction the module exists to draw: appends are legitimate, in-place
    rewrites are not, and a whole-file digest reports both as one bit."""

    def test_appends_are_clean(self, pinned):
        first = arm()
        log = write_log(pinned / "runs.jsonl", [first])
        corpora.seal("campaign-one", runs_path=log)

        later = arm(armname="memory-off", order_index=1)
        delta = corpora.diff("campaign-one", [first, later])
        assert delta.added == [corpora.run_id(later)]
        assert delta.rewritten == []
        assert delta.unchanged == 1
        assert delta.clean

    def test_an_in_place_rewrite_is_caught(self, pinned):
        first = arm()
        log = write_log(pinned / "runs.jsonl", [first])
        corpora.seal("campaign-one", runs_path=log)

        # The exact shape of the 23 records the void fix moved: same identity, same
        # revision, different body, and a marker saying only *that* it changed.
        rewritten = {**first, "void": True, "restamped_by": "voidfix"}
        delta = corpora.diff("campaign-one", [rewritten])
        assert delta.rewritten == [corpora.run_id(first)]
        assert not delta.clean

    def test_a_supersession_is_not_a_rewrite(self, pinned):
        first = arm()
        log = write_log(pinned / "runs.jsonl", [first])
        corpora.seal("campaign-one", runs_path=log)

        revised = corpora.supersede(
            {**first, "contaminated": True}, first, scorer_config="d1:test"
        )
        delta = corpora.diff("campaign-one", [first, revised])
        assert delta.superseded == [corpora.run_id(first)]
        assert delta.rewritten == []
        assert delta.clean, "the write-side discipline working is not a violation"

    def test_a_removed_record_is_caught(self, pinned):
        first = arm()
        second = arm(armname="memory-off", order_index=1)
        log = write_log(pinned / "runs.jsonl", [first, second])
        corpora.seal("campaign-one", runs_path=log)

        delta = corpora.diff("campaign-one", [first])
        assert delta.removed == [corpora.run_id(second)]
        assert not delta.clean

    def test_diff_against_an_unknown_pin_refuses(self, pinned):
        with pytest.raises(corpora.CorpusError, match="no pinned corpus"):
            corpora.diff("never-sealed", [arm()])


class TestDerivationFingerprint:
    """lab/037 finding #5: a campaign record stored `ref` and nothing else about its
    own oracle, so a later task-YAML edit re-scoped verdicts already recorded."""

    def test_the_fingerprint_carries_what_the_verdict_was_computed_against(self, tmp_path):
        from thalamus.eval.tasks import Task

        task = Task(
            task="v0", id="sample-task", title="A sample task", overlap="none",
            source={"kind": "authored", "ref": "abc1234"}, prompt="do the thing",
        )
        fingerprint = corpora.derivation_fingerprint(
            task, tmp_path, fix_paths=frozenset({"src/a.py", "tests/b.py"}),
            tasks_base=tmp_path / "config",
        )
        assert fingerprint["fix_paths"] == ["src/a.py", "tests/b.py"]
        assert fingerprint["detector_config"] == corpora.DETECTOR_CONFIG
        assert fingerprint["task_digest"]

    def test_a_task_yaml_edit_moves_the_digest(self, tmp_path):
        """The highest-value field in the fingerprint, because it is the one that
        re-scopes verdicts already recorded."""
        import yaml

        from thalamus.eval.tasks import Task

        tasks = tmp_path / "config" / "tasks"
        tasks.mkdir(parents=True)
        definition = {
            "task": "v0", "id": "sample-task", "title": "A sample task",
            "overlap": "none", "source": {"kind": "authored", "ref": "abc1234"},
            "prompt": "do the thing",
        }
        path = tasks / "sample-task.yaml"
        path.write_text(yaml.safe_dump(definition))
        task = Task(**definition)
        before = corpora.task_digest(task, tmp_path / "config")

        path.write_text(yaml.safe_dump(definition) + "\n# a comment edit\n")
        assert corpora.task_digest(task, tmp_path / "config") != before, (
            "digested over the YAML bytes — the 2026-07-29 ref remapping lives in "
            "a comment block, and a parsed-model digest would call that no change"
        )
