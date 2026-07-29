"""
`thalamus rescope` — redirecting a session's distillation scope (docs/07).

Interfaces: harness/rescope.py, driven in-process against a pin ledger in
tmp_path. `distilled_scopes` is stubbed rather than hitting a live graph;
the one thing it must never do in a test is connect.
Scope: the refusal is the contract under test, not the append. Appending a row
is trivial; the value of the command is that it declines the corrections that
would silently fork a session's identity, because vertex IDs include scope
(contract.ontology.vid) and a post-distillation rescope mints a second Session
vertex rather than moving the first. The session that motivated this command was
itself already distilled — so the refusal path is the real one.
"""

import json

import pytest

from thalamus.harness import rescope as R

SID = "7f815861-b3eb-465a-b3cb-6aefcde575bf"


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "pins.jsonl"
    path.write_text(json.dumps(
        {"session_id": SID, "scope": "eval-methodology", "cwd": "/x", "ts": "2026-07-28T00:31:31Z"}
    ) + "\n")
    monkeypatch.setattr(R, "PINS_FILE", path)
    monkeypatch.setattr(R, "distilled_scopes", lambda sid, g=None: [])
    # Hermetic identity. Without this the real session's CLAUDE_CODE_SESSION_ID
    # leaks in and the foreign-session guard fires against the fixture's id —
    # tests would then pass or fail depending on who ran them and from where.
    monkeypatch.setenv(R.SESSION_ID_ENV, SID)
    return path


def rows_for(path, sid=SID):
    return [json.loads(x) for x in path.read_text().splitlines()
            if x.strip() and json.loads(x).get("session_id") == sid]


class TestRefusals:
    def test_refuses_when_the_session_already_distilled(self, ledger, monkeypatch):
        """The motivating case. A correction here forks rather than moves."""
        monkeypatch.setattr(R, "distilled_scopes", lambda sid, g=None: ["eval-methodology"])
        with pytest.raises(R.RescopeRefused, match="already distilled"):
            R.rescope(SID, "main")
        assert len(rows_for(ledger)) == 1, "a refused rescope must write nothing"

    def test_refuses_an_unknown_scope(self, ledger):
        with pytest.raises(R.RescopeRefused, match="unknown scope"):
            R.rescope(SID, "not-a-real-expert")

    def test_refuses_a_session_absent_from_the_ledger(self, ledger):
        with pytest.raises(R.RescopeRefused, match="not in the pin ledger"):
            R.rescope("deadbeef-0000-0000-0000-000000000000", "main")

    def test_refuses_a_no_op(self, ledger):
        with pytest.raises(R.RescopeRefused, match="already resolves"):
            R.rescope(SID, "eval-methodology")

    def test_allow_distilled_overrides_and_records_the_fork(self, ledger, monkeypatch):
        monkeypatch.setattr(R, "distilled_scopes", lambda sid, g=None: ["eval-methodology"])
        row = R.rescope(SID, "main", allow_distilled=True)
        assert row["forked_from"] == ["eval-methodology"], "a fork must be on the record"


class TestCorrection:
    def test_appends_rather_than_edits(self, ledger):
        """The original pin record has to survive: an audit log that can be
        rewritten cannot audit anything."""
        R.rescope(SID, "main", reason="operator meant main")
        rows = rows_for(ledger)
        assert len(rows) == 2
        assert rows[0]["scope"] == "eval-methodology", "original pin record retained"
        assert rows[1]["scope"] == "main" and rows[1]["event"] == "rescope"
        assert rows[1]["reason"] == "operator meant main"

    def test_last_row_wins_the_way_session_end_reads_it(self, ledger):
        """session-end.sh takes `select(.session_id==$sid) | .scope | tail -1`."""
        R.rescope(SID, "main")
        assert rows_for(ledger)[-1]["scope"] == "main"

    def test_dry_run_writes_nothing(self, ledger):
        R.rescope(SID, "main", dry_run=True)
        assert len(rows_for(ledger)) == 1

    def test_a_torn_line_does_not_hide_the_rest_of_the_ledger(self, ledger):
        with ledger.open("a") as fh:
            fh.write("{ truncated\n")
            fh.write(json.dumps({"session_id": SID, "scope": "eval-methodology"}) + "\n")
        assert len(R.read_rows(SID)) == 2


class TestSessionResolution:
    def test_accepts_a_prefix(self, ledger):
        assert R.resolve_session("7f815861") == SID

    def test_refuses_an_ambiguous_prefix(self, ledger):
        with ledger.open("a") as fh:
            fh.write(json.dumps({"session_id": "7f8ffffe-0000", "scope": "main"}) + "\n")
        with pytest.raises(R.RescopeRefused, match="ambiguous"):
            R.resolve_session("7f8")

    def test_refuses_an_unmatched_prefix(self, ledger):
        with pytest.raises(R.RescopeRefused, match="no session"):
            R.resolve_session("zzzz")


class TestCurrentSession:
    """Which session am I — the question lab/026 answered wrongly.

    The harness exports the id; the fix is to read it, and to refuse rather than
    infer when it is absent.
    """

    def test_reads_the_harness_exported_id(self):
        assert R.current_session_id({R.SESSION_ID_ENV: SID}) == SID

    def test_absent_env_is_none_not_a_guess(self):
        assert R.current_session_id({}) is None

    def test_empty_env_value_is_none(self):
        assert R.current_session_id({R.SESSION_ID_ENV: ""}) is None

    def test_defaults_to_the_current_session(self, ledger, monkeypatch):
        monkeypatch.setenv(R.SESSION_ID_ENV, SID)
        assert R.run(None, "main") == 0
        assert rows_for(ledger)[-1]["scope"] == "main"

    def test_refuses_rather_than_guessing_when_the_env_is_absent(self, ledger, monkeypatch):
        """No ledger heuristic: concurrent sessions share a cwd, so 'most recent
        entry here' would reintroduce the wrong-subject bug it papers over."""
        monkeypatch.delenv(R.SESSION_ID_ENV, raising=False)
        assert R.run(None, "main") == 1
        assert len(rows_for(ledger)) == 1, "a refusal must not write"

    def test_an_explicit_session_wins_only_when_acknowledged(self, ledger, monkeypatch):
        """An explicit id no longer silently overrides the live one — that was
        the hole. It wins, but only once the caller says it means to."""
        monkeypatch.setenv(R.SESSION_ID_ENV, "ffffffff-0000-0000-0000-000000000000")
        assert R.run(SID, "main") == 1, "unacknowledged override must refuse"
        assert R.run(SID, "main", other_session=True) == 0
        assert rows_for(ledger)[-1]["scope"] == "main"


class TestForeignSessionGuard:
    """Passing an id that is not this session's.

    This is the lab/026 shape exactly: a plausible UUID from a path, a
    transcript, or a recall, passed with confidence. The guard is mechanical —
    the live id comes from the harness, so an agent wrong about its own identity
    cannot assert its way past it.
    """

    LIVE = "e05114ff-ee60-4a76-ae3f-1bbb7562eb97"

    def test_refuses_a_foreign_session_without_the_flag(self, ledger, monkeypatch):
        monkeypatch.setenv(R.SESSION_ID_ENV, self.LIVE)
        assert R.run(SID, "main") == 1
        assert len(rows_for(ledger)) == 1, "a refusal must not write"

    def test_the_refusal_names_both_sessions(self, ledger, monkeypatch, capsys):
        monkeypatch.setenv(R.SESSION_ID_ENV, self.LIVE)
        R.run(SID, "main")
        out = capsys.readouterr().out
        assert SID[:8] in out and self.LIVE[:8] in out
        assert "lab/026" in out, "the guard should say what inferring an id cost"

    def test_the_flag_permits_it_and_the_row_records_the_crossing(self, ledger, monkeypatch):
        monkeypatch.setenv(R.SESSION_ID_ENV, self.LIVE)
        assert R.run(SID, "main", other_session=True) == 0
        row = rows_for(ledger)[-1]
        assert row["cross_session"] is True
        assert row["by_session"] == self.LIVE, "the ledger must record who edited whom"

    def test_the_flag_is_unnecessary_for_your_own_session(self, ledger, monkeypatch):
        monkeypatch.setenv(R.SESSION_ID_ENV, SID)
        assert R.run(SID, "main") == 0
        assert "cross_session" not in rows_for(ledger)[-1]

    def test_own_session_row_still_records_authorship(self, ledger, monkeypatch):
        monkeypatch.setenv(R.SESSION_ID_ENV, SID)
        R.run(None, "main")
        assert rows_for(ledger)[-1]["by_session"] == SID

    def test_no_live_id_means_the_guard_cannot_run_and_does_not_pretend_to(
            self, ledger, monkeypatch):
        """Outside a session there is nothing to compare against; an explicit id
        is then the only input, and blocking it would be theatre."""
        monkeypatch.delenv(R.SESSION_ID_ENV, raising=False)
        assert R.run(SID, "main") == 0


class TestExitCode:
    def test_refusal_is_a_nonzero_exit(self, ledger, monkeypatch):
        monkeypatch.setattr(R, "distilled_scopes", lambda sid, g=None: ["eval-methodology"])
        assert R.run(SID, "main") == 1

    def test_success_is_zero(self, ledger):
        assert R.run(SID, "main") == 0
