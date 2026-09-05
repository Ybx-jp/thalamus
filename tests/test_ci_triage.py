"""
CI triage loop tests (harness/ci_triage.py) — the guards that keep it from feeding itself.

Interfaces: thalamus.harness.ci_triage (RedRun, red_master_runs, TriageState,
witness_key, refusal_for, verify_report, actionable_cases, read_ledger, run_once)
Infrastructure: a tmp_path state file and ledger; `gh` is stubbed, never called
Scope: every test here is anchored on a way the loop could run away from its operator —
firing on its own output, dispatching twice for one failure, retrying forever, or acting
on a report the ledger does not support. The happy path is one test; the rest are the
ways it stops.
"""

import json

import pytest

from thalamus.harness import ci_triage


def _run(event="push", branch="master", run_id="1", conclusion="failure"):
    return {
        "databaseId": run_id,
        "workflowName": "qe-fast",
        "headBranch": branch,
        "event": event,
        "conclusion": conclusion,
        "headSha": "c092bf23400f3394",
        "url": f"https://example.invalid/{run_id}",
    }


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "state.json"


# --- 1. The self-trigger guard -------------------------------------------------------


def test_a_pull_request_run_is_never_dispatchable():
    """
    Scenario: the loop's own remediation PR is open, and its CI is red.

    Verification: a run on master under the `pull_request` event is not dispatchable.
    Every gating workflow triggers on both `push` and `pull_request`, so the loop's own
    PR produces red runs on the loop's own branch. If this predicate admitted them, the
    watcher would dispatch against its own exhaust before a human had read any of it.
    """
    pr_run = ci_triage.RedRun(
        run_id="1", workflow="qe-fast", branch="master",
        event="pull_request", head_sha="abc", url="",
    )
    assert not pr_run.dispatchable


def test_a_red_on_another_branch_is_never_dispatchable():
    """
    Scenario: a worktree branch is red mid-development.

    Verification: not dispatchable. Only master's own history is the loop's business;
    a branch red is the author's problem while they are still iterating.
    """
    branch_run = ci_triage.RedRun(
        run_id="1", workflow="qe-fast", branch="worktree-something",
        event="push", head_sha="abc", url="",
    )
    assert not branch_run.dispatchable


def test_red_master_runs_keeps_only_pushes_to_master(monkeypatch):
    """
    Scenario: `gh run list` returns the real mix — PR runs, branch runs, a green master
    run, and one genuine red push to master.

    Verification: exactly the last one survives. The filter lives inside
    `red_master_runs` rather than in its callers precisely so no caller can widen it by
    forgetting a clause.
    """
    rows = [
        _run(event="pull_request", run_id="10"),
        _run(branch="worktree-x", run_id="11"),
        _run(run_id="12", conclusion="success"),
        _run(run_id="13"),
    ]
    monkeypatch.setattr(ci_triage, "_gh", lambda *a, **k: (0, json.dumps(rows)))

    found = ci_triage.red_master_runs()

    assert [run.run_id for run in found] == ["13"]


def test_a_watcher_that_cannot_see_ci_refuses_rather_than_reporting_green(monkeypatch):
    """
    Scenario: `gh` is missing, unauthenticated, or the network is down.

    Verification: raises rather than returning []. An empty list is indistinguishable
    from "master is green", and a watcher that reports green when it cannot look is
    worse than one that reports broken.
    """
    monkeypatch.setattr(ci_triage, "_gh", lambda *a, **k: (1, ""))

    with pytest.raises(ci_triage.TriageRefused):
        ci_triage.red_master_runs()


# --- 2. Not dispatching twice for one failure ---------------------------------------


def test_a_case_with_an_open_pr_is_refused(state_file):
    """
    Scenario: a fix for this case is already in flight, and master is still red because
    that fix has not merged yet — which is the normal state, not an edge case.

    Verification: refused, naming the PR. Without this the loop spawns a second session
    against a case someone is already working, on every poll, for as long as review takes.
    """
    state = ci_triage.TriageState()
    state.record_pr("a-stalled-teardown", 181)

    refusal = ci_triage.refusal_for("a-stalled-teardown", "witness text", state)

    assert "#181" in refusal


def test_the_attempt_budget_stops_the_loop(state_file):
    """
    Scenario: two unattended sessions have already tried this exact case+witness and it
    is still red.

    Verification: refused. The bound is inferred rather than measured (no attempt-to-
    success curve exists for this loop), so the test pins the behaviour, not the number.
    """
    state = ci_triage.TriageState()
    for _ in range(ci_triage.ESCALATE_AFTER):
        state.record_dispatch("mcp-tool-argument-sweep", "same witness")

    refusal = ci_triage.refusal_for("mcp-tool-argument-sweep", "same witness", state)

    assert "escalating" in refusal


def test_a_new_witness_at_the_same_site_gets_a_fresh_budget():
    """
    Scenario: a case that already spent its budget starts failing with a *different*
    witness.

    Verification: not refused. A different witness at the same site is a different
    defect, and charging it the previous defect's attempts would retire it before it had
    been tried even once.
    """
    state = ci_triage.TriageState()
    for _ in range(ci_triage.ESCALATE_AFTER):
        state.record_dispatch("query-guard-evasion-corpus", "the old witness")

    assert ci_triage.refusal_for("query-guard-evasion-corpus", "a new witness", state) == ""


def test_a_dry_run_does_not_consume_the_dedup(monkeypatch, tmp_path, state_file):
    """
    Scenario: the operator previews what the watcher would do against a live red master.

    Verification: nothing is spawned AND `seen_runs` is untouched, so the next real poll
    still acts on that failure. A rehearsal that marked the run seen would suppress the
    performance.
    """
    monkeypatch.setattr(ci_triage, "_gh", lambda *a, **k: (0, json.dumps([_run(run_id="99")])))
    monkeypatch.setattr(
        ci_triage, "dispatch",
        lambda *a, **k: pytest.fail("dry run must not spawn a session"),
    )

    first = ci_triage.run_once(tmp_path, state_path=state_file, spawn=False)
    second = ci_triage.run_once(tmp_path, state_path=state_file, spawn=False)

    assert first is not None and second is not None
    assert first.run_id == second.run_id == "99"
    assert not state_file.exists()


def test_one_red_run_is_dispatched_for_exactly_once(monkeypatch, tmp_path, state_file):
    """
    Scenario: the watcher polls on an interval while master stays red — the same run
    comes back on every poll until something merges.

    Verification: one dispatch, then None. At a five-minute interval, a watcher without
    this would open twelve sessions an hour against one failure.
    """
    monkeypatch.setattr(ci_triage, "_gh", lambda *a, **k: (0, json.dumps([_run(run_id="42")])))
    spawned = []
    monkeypatch.setattr(ci_triage, "dispatch", lambda root, **k: spawned.append(root))

    first = ci_triage.run_once(tmp_path, state_path=state_file)
    second = ci_triage.run_once(tmp_path, state_path=state_file)

    assert first is not None and first.run_id == "42"
    assert second is None
    assert len(spawned) == 1


# --- 3. State survives the process ---------------------------------------------------


def test_state_round_trips_through_disk(state_file):
    """
    Scenario: the watcher restarts between polls.

    Verification: open PRs and attempt budgets come back. The file is rewritten whole
    and renamed into place rather than appended to, so it cannot enter the partial-write
    class the append-log ledgers in this repo carry.
    """
    state = ci_triage.TriageState()
    state.record_pr("case-a", 7)
    state.record_dispatch("case-b", "w", run_id="5")
    state.save(state_file)

    back = ci_triage.TriageState.load(state_file)

    assert back.open_prs == {"case-a": 7}
    assert back.attempts_for("case-b", "w") == 1
    assert back.seen_runs == ["5"]


def test_unreadable_state_degrades_to_empty_rather_than_stopping(state_file):
    """
    Scenario: the state file is truncated or hand-edited into invalid JSON.

    Verification: loads as empty instead of raising. The cost of guessing wrong here is
    one duplicate dispatch, which the open-PR check catches; the cost of refusing to run
    is a red master nobody looks at, which is the failure this whole loop exists to end.
    """
    state_file.write_text("{not json", encoding="utf-8")

    assert ci_triage.TriageState.load(state_file).open_prs == {}


def test_marking_a_case_done_clears_both_its_pr_and_its_budget(state_file):
    """
    Scenario: the defect is actually fixed and its expectation deleted.

    Verification: the case is dispatchable again from scratch. A budget that outlived
    its defect would leave a permanently-retired site — the next real regression there
    would be refused rather than triaged.
    """
    state = ci_triage.TriageState()
    state.record_pr("case-c", 9)
    for _ in range(ci_triage.ESCALATE_AFTER):
        state.record_dispatch("case-c", "w")

    state.forget("case-c", "w")

    assert ci_triage.refusal_for("case-c", "w", state) == ""


# --- 4. Independent verification -----------------------------------------------------


def test_a_report_claiming_a_new_failure_is_triaged_is_refused():
    """
    Scenario: a triage report says a case is `known-red` and safe to leave, while the
    ledger for that same run records `new-failure` against it.

    Verification: refused, naming both sides. This is the step that makes `main` a second
    reader rather than a rubber stamp — it re-derives the verdict from the ledger instead
    of accepting the classifying agent's word for it.
    """
    ledger = [{"case": "policy-load-collapses-hash-collision", "verdict": "new-failure"}]

    found = ci_triage.verify_report({"policy-load-collapses-hash-collision": "known-red"}, ledger)

    assert len(found) == 1
    assert "new-failure" in str(found[0]) and "known-red" in str(found[0])


def test_a_report_about_a_case_the_ledger_never_ran_is_refused():
    """
    Scenario: a report names a case that does not appear in the run it claims to
    describe — a stale case name, or one invented wholesale.

    Verification: refused as `<absent>`. Silence in the ledger is not agreement; a case
    that did not run is not a case that passed.
    """
    found = ci_triage.verify_report({"a-case-that-did-not-run": "ok"}, [{"case": "other",
                                                                        "verdict": "ok"}])

    assert len(found) == 1 and found[0].ledger == "<absent>"


def test_an_honest_report_verifies_clean():
    """
    Scenario: the report says exactly what the ledger says.

    Verification: no disagreements. The refusal path above is worth nothing without this
    — a verifier that rejected everything would be equally "safe" and entirely useless.
    """
    ledger = [{"case": "one", "verdict": "known-red"}, {"case": "two", "verdict": "ok"}]

    assert ci_triage.verify_report({"one": "known-red", "two": "ok"}, ledger) == []


# --- 5. Reading the ledger -----------------------------------------------------------


def test_only_the_newest_runs_rows_are_read(tmp_path):
    """
    Scenario: the ledger has accumulated several runs, and an older one was red.

    Verification: only the newest run's rows come back. A verdict from three runs ago is
    not evidence about the tree as it stands, and mixing runs would let a stale red
    dispatch a session against a defect already fixed.
    """
    ledger = tmp_path / "runs.jsonl"
    ledger.write_text(
        json.dumps({"run_id": "old", "case": "a", "verdict": "new-failure", "witness": "w"})
        + "\n"
        + json.dumps({"run_id": "new", "case": "a", "verdict": "known-red", "witness": "w"})
        + "\n",
        encoding="utf-8",
    )

    rows = ci_triage.read_ledger(ledger)

    assert [row["verdict"] for row in rows] == ["known-red"]


def test_actionable_cases_ignores_the_settled_verdicts(tmp_path):
    """
    Scenario: a run with one of everything.

    Verification: `ok`, `known-red` and `skipped` are not work. Only the four verdicts
    that demand somebody do something come back — a loop that woke for `known-red` would
    wake on every single run forever.
    """
    rows = [
        {"case": "settled", "verdict": "known-red", "witness": ""},
        {"case": "green", "verdict": "ok", "witness": ""},
        {"case": "absent-substrate", "verdict": "skipped", "witness": ""},
        {"case": "real", "verdict": "new-failure", "witness": "w"},
        {"case": "changed", "verdict": "drifted", "witness": "w2"},
    ]

    assert ci_triage.actionable_cases(rows) == [("real", "w"), ("changed", "w2")]
