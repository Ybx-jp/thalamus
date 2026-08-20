"""The launch surface: what pins a session, and what survives a window recycle.

`agents.py` is tested for headless invocation. This is the other surface, and the
reason it is its own module is the failure below: a pin that lives only in the
window's environment is undone by the console's restart button, silently, from a
phone — measured on a throwaway session in both arms.
"""

from __future__ import annotations

import pytest

from thalamus.harness.launcher import LAUNCH_SHAPES, PERMISSION_MODE, launch_argv


class TestLaunchArgv:
    def test_claude_still_selects_the_persona_and_the_mode(self):
        # Byte-identical to what shipped before the launcher existed: the Cursor work
        # must not have moved the harness that was already working.
        assert launch_argv("claude", "qe", persona="thalamus-qe") == [
            "claude", "--agent", "thalamus-qe", "--permission-mode", PERMISSION_MODE,
        ]

    def test_main_has_no_persona_on_either_harness(self):
        assert launch_argv("claude", "main") == ["claude", "--permission-mode", "auto"]
        assert launch_argv("cursor", "main")[-2:] == ["agent", "--trust"]

    def test_cursor_carries_the_scope_on_the_argv(self):
        """The recycle trap, as a permanent check.

        `tmux new-window -e` is not stored in the session environment, so
        `respawn-window` — the console's restart button — re-executes this argv with
        the window's `-e` variables gone. Claude Code survives because `--agent` rides
        the argv; Cursor has no such flag, so the `env` prefix IS the pin. Measured
        both ways: with the prefix a recycled window came back `qe`, without it `main`,
        and `role-guard.sh` short-circuits on `main` before it loads a manifest.
        """
        argv = launch_argv("cursor", "qe", persona="thalamus-qe")
        assert argv[0] == "env"
        assert "THALAMUS_SCOPE=qe" in argv
        assert argv.index("THALAMUS_SCOPE=qe") < argv.index("agent")

    def test_cursor_takes_no_persona_flag_even_when_one_is_offered(self):
        # The caller passes `persona` on every harness because the derived file is
        # still written (Cursor reads a workspace's .claude/agents as subagents).
        # Nothing may turn that into a flag Cursor does not have.
        assert "--agent" not in launch_argv("cursor", "qe", persona="thalamus-qe")

    def test_cursor_passes_no_permission_mode(self):
        """No mode is the decision, not an oversight.

        Cursor has none that keeps `auto`'s defining property of never stopping at a
        prompt: `--auto-review` prompts on whatever its classifier will not auto-run,
        and `--force`/`--yolo` is strictly more permissive than `auto` rather than
        equivalent. So the session obeys the operator's own config, and this test is
        what stops someone quietly promoting it to Run Everything.
        """
        argv = launch_argv("cursor", "qe")
        assert "--permission-mode" not in argv
        assert "--force" not in argv and "--yolo" not in argv
        assert "--auto-review" not in argv

    def test_an_unknown_harness_refuses_rather_than_guessing_a_binary(self):
        with pytest.raises(ValueError, match="no launch shape"):
            launch_argv("no-such-harness", "qe")

    def test_every_harness_in_the_registry_can_be_pinned(self):
        from thalamus.harness.agents import HARNESSES

        assert set(LAUNCH_SHAPES) == set(HARNESSES)


class TestPinRecord:
    def test_the_record_says_what_pinned_covers_per_harness(self):
        from thalamus.contract.boundaries import Provision
        from thalamus.contract.pinning import COMPONENTS, PIN_ROWS

        states = {(r.component, r.harness): r.state for r in PIN_ROWS}
        # The point of the record: `pinned` is not one property, and the two harnesses
        # do not carry the same subset.
        assert states[("pin.persona", "claude")] is Provision.PROVIDED
        assert states[("pin.persona", "cursor")] is Provision.ABSENT
        assert states[("pin.mcp_arming", "cursor")] is Provision.NATIVE
        assert {c for c, _ in states} == set(COMPONENTS)

    def test_no_row_is_left_without_evidence_or_a_re_ask_cost(self):
        from thalamus.contract.pinning import PIN_ROWS

        for row in PIN_ROWS:
            assert row.evidence.verified_against, row.label
            assert row.evidence.reask in ("free", "live-session"), row.label

    def test_the_persona_row_is_re_asked_from_the_parser_not_from_our_table(self):
        """If a Cursor release ever adds `--agent`, this row is what notices.

        A record that read `LAUNCH_SHAPES.persona_flag` back to itself would confirm
        forever — the same self-comparison that let the hook-parity record stay green
        while it was false.
        """
        import thalamus.contract.pinning as pinning

        rows = {row.label: (outcome, detail) for row, outcome, detail in pinning.check_pinning()}
        outcome, _ = rows["pin.persona on cursor"]
        # `unavailable` when the CLI is not installed — a checkout without Cursor must
        # not fail the suite, and must not silently read as confirmed either.
        assert outcome in ("confirmed", "unavailable")

    def test_recycle_survival_is_recomputed_from_the_argv(self, monkeypatch):
        from thalamus.contract import pinning
        from thalamus.harness import launcher

        broken = dict(launcher.LAUNCH_SHAPES)
        broken["cursor"] = launcher.LaunchShape(
            harness="cursor", binary="agent", persona_flag=None,
            persona_flag_carries_scope=False,
            always=("--trust",), capabilities=(), pin_carrier="env", settle_s=4.0,
        )
        monkeypatch.setattr(launcher, "LAUNCH_SHAPES", broken)
        monkeypatch.setattr(
            launcher, "launch_argv",
            lambda harness, scope, persona=None: ["agent", "--trust"],
        )
        verdicts = {row.label: outcome for row, outcome, _ in pinning.check_pinning()}
        assert verdicts["pin.recycle_survival on cursor"] == "drift"
