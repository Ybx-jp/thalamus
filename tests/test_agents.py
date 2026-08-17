"""The agent-CLI registry: what Thalamus may ask of each headless harness.

`harness/agents.py` is where "capability is declared, not assumed" is spelled out,
and until this file existed nothing tested it. That gap was not theoretical. Two
declarations in it were false against a live CLI for weeks and neither could fail:
the Composer identifier was carried as unverified prose, and one `arm_blockers`
row bundled a true claim (`--max-turns` is absent) with a false one (the permission
flags have no Cursor equivalent — `--force`, `--yolo`, `--sandbox` and
`--auto-review` all exist). A row asserting two things cannot be retired when only
one of them dies, so it never was.

So these tests check the *shape* that keeps declarations falsifiable, not the
prose. What a row says is a question for the live CLI; that each row says one
checkable thing is a question for here.
"""

from __future__ import annotations

import pytest

from thalamus.harness import agents


class TestRegistryShape:
    def test_every_harness_resolves(self):
        for harness in agents.HARNESSES:
            assert agents.cli_for(harness).harness == harness

    def test_unknown_harness_names_the_known_ones(self):
        # The error has to carry the alternatives: a machine that lacks a CLI
        # discovers it through a failure, and a bare "unknown harness" makes the
        # reader go find the registry to learn what to type instead.
        with pytest.raises(agents.UnknownHarness) as exc:
            agents.cli_for("emacs")
        for harness in agents.HARNESSES:
            assert harness in str(exc.value)

    def test_arm_blockers_are_distinct_and_substantive(self):
        """Each row is its own retirable claim.

        Atomicity itself is a review-time property, not a lexical one — "copies
        ~/.claude.json and ~/.claude/.credentials.json" is one claim carrying a
        list, and a test reading that `and` as two claims fires on correct prose.
        A guard with false positives gets routed around rather than obeyed,
        so this asserts only what a string can honestly answer: rows
        are distinct, and long enough to name a reason rather than a symptom.
        Whether a row states one thing stays with the reader who retires it.
        """
        for harness in agents.HARNESSES:
            blockers = agents.cli_for(harness).arm_blockers
            assert len(set(blockers)) == len(blockers), f"{harness} repeats a blocker"
            for blocker in blockers:
                assert len(blocker) > 20, (
                    f"{harness} blocker too terse to act on: {blocker!r}"
                )

    def test_runs_arms_agrees_with_the_blocker_list(self):
        # The property callers branch on, so it must not drift from the reasons.
        for harness in agents.HARNESSES:
            cli = agents.cli_for(harness)
            assert cli.runs_arms is (not cli.arm_blockers)


class TestHeadlessPreconditions:
    def test_argv_carries_them(self):
        for harness in agents.HARNESSES:
            cli = agents.cli_for(harness)
            argv = cli.argv("some-model")
            assert argv[:2] == [cli.binary, "-p"]
            assert "--output-format" in argv and "json" in argv
            for flag in cli.headless_preconditions:
                assert flag in argv

    def test_cursor_declares_workspace_trust(self):
        """Measured, not guessed: without it `agent -p` exits 1 in a fresh dir.

        The extraction sandbox is a new `mkdtemp` on every run, so it is never a
        trusted workspace and every Cursor distillation failed before doing any
        work. The failure is invisible in the ordinary way — extraction runs
        detached from SessionEnd — so nothing surfaced it until a live run.
        """
        assert "--trust" in agents.cli_for("cursor").headless_preconditions

    def test_claude_declares_none(self):
        # Not an oversight to be filled in later: Claude Code has no workspace
        # trust gate, and an empty tuple is the declaration that it needs nothing.
        assert agents.cli_for("claude").headless_preconditions == ()
