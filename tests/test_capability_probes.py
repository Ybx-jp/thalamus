"""The capability checker: does re-asking the CLI actually catch drift?

These run without either CLI installed — the probe *runner* is faked, because what
needs testing here is the discrimination logic, not commander.js. The live end is
exercised by `thalamus contract check --capabilities` on a box that has the binaries,
and by the row table itself, which is the part that must stay honest.
"""

from __future__ import annotations

import pytest

from thalamus.contract import probes
from thalamus.contract.probes import FlagProbe, Outcome, probe_flag


def _fake_cli(*, unknown: str | None):
    """A CLI that names `unknown` as an unrecognised option, or nothing at all.

    The control call — the bare sentinel, with no flag under test — is answered
    honestly, because a fake that failed the control would send every probe down the
    MALFORMED path and the discrimination logic would never be reached.
    """
    def run(argv):
        # `[binary, SENTINEL, "-p", "x"]` is `sentinel_is_rejected`'s own call.
        if argv[1] == probes.SENTINEL:
            return f"error: unknown option '{probes.SENTINEL}'\n"
        return f"error: unknown option '{unknown}'\n" if unknown else "some other output\n"
    return run


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(probes.shutil, "which", lambda b: f"/usr/bin/{b}")
    return monkeypatch


class TestDiscrimination:
    def test_naming_the_sentinel_means_the_flag_parsed(self, live):
        # Everything before the sentinel parsed, so the flag under test exists.
        live.setattr(probes, "_run", _fake_cli(unknown=probes.SENTINEL))
        result = probe_flag(FlagProbe("agent", "--trust"), declared=True)
        assert result.observed is True
        assert result.outcome is Outcome.CONFIRMED

    def test_naming_the_flag_means_it_is_absent(self, live):
        live.setattr(probes, "_run", _fake_cli(unknown="--max-turns"))
        result = probe_flag(FlagProbe("agent", "--max-turns", ("5",)), declared=False)
        assert result.observed is False
        assert result.outcome is Outcome.CONFIRMED

    def test_a_flag_declared_absent_but_present_is_drift(self, live):
        """The lab/054 case, which is the whole reason this module exists.

        `arm_blockers` declared the permission flags absent from Cursor. `--force`,
        `--yolo`, `--sandbox` and `--auto-review` were all there, and the row survived
        because it also carried a true claim about `--max-turns`.
        """
        live.setattr(probes, "_run", _fake_cli(unknown=probes.SENTINEL))
        result = probe_flag(FlagProbe("agent", "--force"), declared=False)
        assert result.outcome is Outcome.DRIFT
        assert "declared absent" in result.detail

    def test_a_flag_declared_present_but_absent_is_drift(self, live):
        # The other direction: a vendor removing a flag we depend on. `--trust` is
        # load-bearing for every Cursor extraction, so its disappearance must be loud.
        live.setattr(probes, "_run", _fake_cli(unknown="--trust"))
        result = probe_flag(FlagProbe("agent", "--trust"), declared=True)
        assert result.outcome is Outcome.DRIFT


class TestRefusals:
    def test_an_answer_that_is_neither_is_not_rounded_into_one(self, live):
        """`agent --max-turns 5 --version` exits 0 and prints the version.

        Action options short-circuit option validation, so a probe that reached one
        would report every absent flag as present. When neither name appears, the CLI
        did something other than reject an unknown option, and that is not an answer.
        """
        live.setattr(probes, "_run", _fake_cli(unknown=None))
        result = probe_flag(FlagProbe("agent", "--max-turns", ("5",)), declared=False)
        assert result.outcome is Outcome.UNPROBEABLE
        assert result.observed is None

    def test_a_failed_control_refuses_rather_than_reports(self, live):
        """If the sentinel is ever accepted, every flag reads as present.

        That failure is silent and unanimous — a clean sweep of confirmations — which
        is worse than no answer, so the control is checked before the measurement.
        Here the CLI accepts the sentinel, which is the failure being simulated.
        """
        live.setattr(probes, "_run", lambda argv: "no complaint at all\n")
        result = probe_flag(FlagProbe("agent", "--trust"), declared=True)
        assert result.outcome is Outcome.MALFORMED
        assert result.observed is None

    def test_a_missing_binary_is_not_a_missing_flag(self, monkeypatch):
        # A Cursor-only box has no `claude`, and "not installed" must never be
        # recorded as "the flag went away".
        monkeypatch.setattr(probes.shutil, "which", lambda b: None)
        result = probe_flag(FlagProbe("claude", "--max-turns", ("5",)), declared=True)
        assert result.outcome is Outcome.UNAVAILABLE
        assert result.observed is None


class TestProbeShape:
    def test_the_sentinel_comes_after_the_flag(self):
        # Order is the mechanism: the sentinel must be the only thing that can fail.
        argv = FlagProbe("agent", "--model", ("composer-2.5",)).argv()
        assert argv[:4] == ["agent", "--model", "composer-2.5", probes.SENTINEL]

    def test_a_flag_probe_claims_only_parse_scope(self):
        """Sound as a falsifier, unsound as a generalizer.

        That a flag parses says nothing about what it does, and nothing about a mode
        the probe never entered — the error this session nearly shipped by inferring
        interactive behaviour from one print-mode observation.
        """
        assert FlagProbe("agent", "--trust").condition is probes.Condition.PARSE

    def test_every_row_carries_a_reason(self):
        # A row without a stated reason is the unverified prose comment again, moved
        # into a tuple. The reason is what tells a later reader whether to retire it.
        for probe, _, reason in probes.CAPABILITY_ROWS:
            assert len(reason) > 20, f"{probe.binary} {probe.flag} has no reason"
