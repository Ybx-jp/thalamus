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


class TestExitCode:
    def test_refusal_is_a_nonzero_exit(self, ledger, monkeypatch):
        monkeypatch.setattr(R, "distilled_scopes", lambda sid, g=None: ["eval-methodology"])
        assert R.run(SID, "main") == 1

    def test_success_is_zero(self, ledger):
        assert R.run(SID, "main") == 0
