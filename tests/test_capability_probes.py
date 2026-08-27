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
        """The measured case that is the whole reason this module exists.

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

    def test_every_row_carries_a_reason(self):
        # A row without a stated reason is the unverified prose comment again, moved
        # into a tuple. The reason is what tells a later reader whether to retire it.
        for probe, _, reason in probes.CAPABILITY_ROWS:
            assert len(reason) > 20, f"{probe.binary} {probe.flag} has no reason"


class TestDerivedRows:
    """Claims the repo makes about itself, recomputed from the thing they describe.

    A CLI probe cannot reach these — the subject is the repo, not the harness — but
    the failure is identical: a declaration nothing re-asks, drifting while the data
    underneath it moves.
    """

    def test_the_declared_parity_matches_the_wirings(self):
        probe, _ = probes._declared_parity_row()
        assert probes.probe_derived(probe).outcome is Outcome.CONFIRMED

    def test_a_script_joining_one_wiring_is_drift(self, monkeypatch):
        """The measured event: three scripts joined HOOK_WIRING and the count did not.

        Nothing failed at the time, because the count lived in a comment. Here the
        declaration is fixed data and the derivation reads the tables, so the two
        diverge the moment one of them moves.
        """
        from thalamus.harness import install

        monkeypatch.setattr(
            install, "HOOK_WIRING",
            [*install.HOOK_WIRING, ("PostToolUse", "Bash", "newly-added.sh")],
        )
        probe, _ = probes._declared_parity_row()
        result = probes.probe_derived(probe)
        assert result.outcome is Outcome.DRIFT
        # The message must name the newcomer: "a count changed" sends the reader
        # back to diff two tables by hand, which is the work the checker exists to do.
        assert "newly-added.sh" in result.detail
        # Derived from the declaration rather than written as a literal: this asserts
        # that the count moved by exactly the one script the test added, which is the
        # property. A hardcoded pair asserts today's wiring instead, and goes red on
        # every legitimate hook — twice already.
        observed = probes.DERIVATIONS["hook_parity"]()
        declared = install.DECLARED_HOOK_PARITY.scripts["claude"]
        assert observed["scripts"]["claude"] == declared + 1
        # And the newcomer reads as missing from every *other* harness, which is the
        # half a bare count cannot say: a script wired on one harness alone is either
        # a deliberate asymmetry or a port nobody finished, and the record has to name
        # it either way.
        assert all("newly-added.sh" in names for names in observed["missing"].values())

    def test_only_declared_fields_are_compared(self):
        # A partial declaration is checked on what it names and stays silent on the
        # rest, rather than being forced to invent values it has no opinion about.
        from thalamus.harness import install

        shared = install.DECLARED_HOOK_PARITY.shared
        probe = probes.DerivedProbe(derivation="hook_parity", declared={"shared": shared})
        assert probes.probe_derived(probe).outcome is Outcome.CONFIRMED

    def test_an_unknown_derivation_is_malformed_not_skipped(self):
        # A row pointing at a derivation that no longer exists is itself the drift.
        probe = probes.DerivedProbe(derivation="gone", declared={"x": 1})
        result = probes.probe_derived(probe)
        assert result.outcome is Outcome.MALFORMED
        assert "gone" in result.detail

    def test_a_rename_is_not_counted_as_a_gap(self):
        """`mcp-tap.sh` is `post-tool-use.sh` under another filename.

        A name-set difference cannot tell the two apart, so reporting raw
        `claude_only` would say Cursor has no MCP tap when it has one — a capability
        the adapter *has*, reported as one it lacks.
        """
        from thalamus.harness.install import DECLARED_HOOK_PARITY

        assert "post-tool-use.sh" in DECLARED_HOOK_PARITY.missing["cursor"]
        assert ("post-tool-use.sh", "mcp-tap.sh") in DECLARED_HOOK_PARITY.renames["cursor"]
        # And it is not a gap on codex at all: codex's payload names MCP tools
        # `mcp__thalamus__<tool>` exactly as Claude Code does, so the real script is
        # wired there under its own name rather than renamed.
        assert "post-tool-use.sh" not in DECLARED_HOOK_PARITY.missing["codex"]

    def test_a_native_path_is_not_counted_as_a_gap_either(self):
        """`role-guard.sh` is unwired for Cursor and binds there anyway.

        Cursor translates `~/.claude/settings.json` into its own event names, so the
        guard runs there through the vendor's path with nothing under `.cursor/`.
        Wiring a Cursor adapter for it would run the same guard twice on one call —
        so its absence from `CURSOR_HOOK_WIRING` is the decision, not the gap, and
        this assertion is what stops a later reader from "fixing" it.
        """
        from thalamus.harness.install import DECLARED_HOOK_PARITY

        assert "role-guard.sh" in DECLARED_HOOK_PARITY.missing["cursor"]
        assert "role-guard.sh" in DECLARED_HOOK_PARITY.native["cursor"]

    def test_the_native_exemption_does_not_carry_to_a_harness_that_earned_none(self):
        """Codex has no `native` entry, and the record must not lend it Cursor's.

        The two look identical from a name-set difference — a script Claude Code wires
        and another harness does not — and they are opposite facts. Cursor reads
        `~/.claude/settings.json` and runs the guard through the vendor's own path;
        codex does not read that file at all (measured: three codex sessions with the
        Claude Code suite installed at user scope fired none of it), so anything
        absent from its table simply does not run. A `native` field keyed per harness
        is what keeps the two apart; a flat one would have exempted both.
        """
        from thalamus.harness.install import DECLARED_HOOK_PARITY

        assert "codex" not in DECLARED_HOOK_PARITY.native
        assert "codex" not in DECLARED_HOOK_PARITY.renames
        # `room-guard.sh` matches `SendMessage`, a tool codex has no analogue of, so
        # it stands as a declared gap rather than a quiet exemption.
        assert DECLARED_HOOK_PARITY.missing["codex"] == ("room-guard.sh",)


class TestRefutedParityClaims:
    """The two fields the wiring tables cannot re-derive, checked by refutation.

    `renames` and `native` were data in form and comment in effect: nothing compared
    them to anything, which is the exact state `HookParity`'s docstring says the record
    exists to end. The tables cannot produce their values — no table says one script
    plays another's role — so what is asked instead is whether anything the tables and
    the hook directories *do* know contradicts them.

    Every case here moves the world and expects the claim to break, because a
    refutation checker that cannot be made to fire is the green suite these fields
    already had.
    """

    def _declared(self, renames=None, native=None):
        from thalamus.harness.install import DECLARED_HOOK_PARITY, HookParity

        return HookParity(
            scripts=DECLARED_HOOK_PARITY.scripts,
            shared=DECLARED_HOOK_PARITY.shared,
            missing=DECLARED_HOOK_PARITY.missing,
            extra=DECLARED_HOOK_PARITY.extra,
            renames=DECLARED_HOOK_PARITY.renames if renames is None else renames,
            native=DECLARED_HOOK_PARITY.native if native is None else native,
        )

    def test_the_declared_claims_are_unrefuted_today(self):
        probe, _ = probes._parity_claims_row()
        result = probes.probe_derived(probe)
        assert result.outcome is Outcome.CONFIRMED, result.detail

    def test_wiring_the_renamed_script_under_its_own_name_refutes_the_rename(
        self, monkeypatch
    ):
        """The drift the issue names: a harness starts wiring `post-tool-use.sh`
        itself, and the record still calls it renamed to `mcp-tap.sh`."""
        from thalamus.harness import install

        monkeypatch.setattr(
            install, "CURSOR_HOOK_WIRING",
            [*install.CURSOR_HOOK_WIRING, ("afterShellCommand", "post-tool-use.sh")],
        )
        reasons = install.refute_parity_claims(self._declared())
        assert any("under its own name" in r for r in reasons), reasons
        assert any("post-tool-use.sh" in r and "cursor" in r for r in reasons)

    def test_a_rename_to_a_script_the_harness_does_not_wire_is_refuted(self):
        from thalamus.harness import install

        declared = self._declared(renames={"cursor": (("post-tool-use.sh", "gone.sh"),)})
        reasons = install.refute_parity_claims(declared)
        assert any("does not wire gone.sh" in r for r in reasons), reasons

    def test_a_rename_of_a_script_claude_code_does_not_wire_is_refuted(self):
        from thalamus.harness import install

        declared = self._declared(renames={"cursor": (("imaginary.sh", "mcp-tap.sh"),)})
        reasons = install.refute_parity_claims(declared)
        assert any("not wired on Claude Code" in r for r in reasons), reasons

    def test_wiring_a_native_script_locally_is_refuted_as_a_double_run(self, monkeypatch):
        """The hazard `native`'s own comment names: Cursor already runs the guard
        through the vendor's translation, so wiring it again runs it twice."""
        from thalamus.harness import install

        monkeypatch.setattr(
            install, "CURSOR_HOOK_WIRING",
            [*install.CURSOR_HOOK_WIRING, ("beforeShellCommand", "role-guard.sh")],
        )
        reasons = install.refute_parity_claims(self._declared())
        assert any("run twice on one call" in r for r in reasons), reasons

    def test_a_native_script_claude_code_does_not_wire_is_refuted(self):
        """There is nothing for the vendor to translate."""
        from thalamus.harness import install

        declared = self._declared(native={"cursor": ("imaginary.sh",)})
        reasons = install.refute_parity_claims(declared)
        assert any("nothing for the vendor to translate" in r for r in reasons), reasons

    def test_a_local_copy_of_a_native_script_is_refuted(self, tmp_path, monkeypatch):
        """A file under the harness's own hook directory is a local implementation.
        The claim is that the *vendor* runs it, and a local copy contradicts that."""
        from thalamus.harness import install

        cursor = tmp_path / "cursor"
        cursor.mkdir()
        # Everything the surviving claims need, so only the new file can refute.
        (cursor / "mcp-tap.sh").write_text("#!/bin/sh\n")
        (cursor / "role-guard.sh").write_text("#!/bin/sh\n")
        monkeypatch.setitem(install.HOOK_DIRS, "cursor", cursor)

        reasons = install.refute_parity_claims(self._declared())
        assert any("local implementation" in r for r in reasons), reasons
        assert not any("mcp-tap.sh" in r for r in reasons), "the rename must stay clean"

    def test_a_rename_naming_no_file_is_refuted(self, tmp_path, monkeypatch):
        """A rename that names nothing on disk renames nothing."""
        from thalamus.harness import install

        cursor = tmp_path / "cursor"
        cursor.mkdir()
        monkeypatch.setitem(install.HOOK_DIRS, "cursor", cursor)

        reasons = install.refute_parity_claims(self._declared())
        assert any("no mcp-tap.sh in cursor/" in r for r in reasons), reasons

    def test_a_harness_with_no_wiring_table_cannot_declare_either(self):
        from thalamus.harness import install

        assert install.refute_parity_claims(
            self._declared(renames={"zed": (("a.sh", "b.sh"),)})
        ) == ("zed declares renames and has no wiring table",)
        assert install.refute_parity_claims(
            self._declared(native={"zed": ("a.sh",)})
        ) == ("zed declares native scripts and has no wiring table",)

    def test_a_refutation_surfaces_as_drift_on_the_probe(self, monkeypatch):
        """The refutations have to reach `contract check --capabilities`, not just
        the function — a checker nothing runs is the state this replaced."""
        from thalamus.harness import install

        monkeypatch.setattr(
            install, "CURSOR_HOOK_WIRING",
            [*install.CURSOR_HOOK_WIRING, ("beforeShellCommand", "role-guard.sh")],
        )
        probe, _ = probes._parity_claims_row()
        result = probes.probe_derived(probe)
        assert result.outcome is Outcome.DRIFT
        assert "role-guard.sh" in result.detail

    def test_both_parity_rows_run_under_check_capabilities(self):
        """Two rows about one record, and neither may quietly stop being asked."""
        derivations = {
            r.probe.derivation for r in probes.check_capabilities()
            if isinstance(r.probe, probes.DerivedProbe)
        }
        assert derivations == {"hook_parity", "hook_parity_claims"}


class TestBoundaryRows:
    """The record whose subject is the obligation rather than the wiring table.

    The wiring-parity record was clean and green while `role-guard.sh` was listed as
    a Cursor gap and was in fact binding there, because a derivation over our own
    tables never asks a harness anything. These rows are what carries the
    answer instead, so what must stay true of them is that they cannot quietly become
    a boolean again.
    """

    def test_every_row_names_what_it_was_verified_against(self):
        from thalamus.contract.boundaries import BOUNDARY_ROWS

        for row in BOUNDARY_ROWS:
            assert row.evidence.verified_against, row.label
            assert row.evidence.reask in ("free", "live-session"), row.label

    def test_the_cursor_rows_report_unprobeable_rather_than_confirmed(self):
        """A vendor's undocumented compat path has no free re-ask, and says so.

        This is the row that would be most comfortable as a green tick and must not
        be: nothing in this repo can re-ask it without a live session, so it belongs
        in the unchecked count on every run.
        """
        from thalamus.contract.boundaries import check_boundaries

        cursor = [(row, outcome) for row, outcome, _ in check_boundaries()
                  if row.harness == "cursor"]
        assert cursor
        assert all(outcome == "unprobeable" for _, outcome in cursor)

    def test_the_claude_rows_are_recomputed_against_the_wiring(self):
        from thalamus.contract.boundaries import check_boundaries

        from thalamus.contract.boundaries import BOUNDARY_ROWS

        claude = [(row, outcome) for row, outcome, _ in check_boundaries()
                  if row.harness == "claude"]
        # Derived rather than stated. The risk this guards is `check_boundaries()`
        # silently dropping a row it cannot recompute, which a literal count would
        # also catch — and then go on catching every time a boundary is legitimately
        # added, which is how a literal becomes something people edit without reading.
        assert len(claude) == sum(1 for row in BOUNDARY_ROWS if row.harness == "claude")
        assert all(outcome == "confirmed" for _, outcome in claude)

    def test_a_boundary_declared_but_never_armed_is_drift(self, monkeypatch):
        """Measured: room-guard.sh was declared here and never wired, and every room
        reported a treatment that had not occurred. A record that cannot catch that
        is decoration."""
        from thalamus.contract import boundaries
        from thalamus.harness import install

        monkeypatch.setattr(install, "HOOK_WIRING", [
            (event, matcher, script) for event, matcher, script in install.HOOK_WIRING
            if script != "room-guard.sh"
        ])
        verdicts = {row.label: outcome for row, outcome, _ in boundaries.check_boundaries()}
        assert verdicts["room_boundary.message on claude"] == "drift"
        assert verdicts["write_boundary.path on claude"] == "confirmed"

    def test_absent_and_unknown_are_not_merged(self):
        """`Artifact` has no referent on Cursor; skills have one with no interception
        point. Collapsing those into "unenforced" is how an unmeasured thing acquires
        a measured-sounding state."""
        from thalamus.contract.boundaries import BOUNDARY_ROWS, Provision

        states = {(r.boundary, r.harness): r.state for r in BOUNDARY_ROWS}
        assert states[("capability_boundary.tool", "cursor")] is Provision.ABSENT
        assert states[("capability_boundary.skill", "cursor")] is Provision.UNKNOWN
        assert states[("write_boundary.path", "cursor")] is Provision.NATIVE
