"""
`thalamus init` — user-scope harness installation.

Interfaces: harness/install.py, driven in-process with every filesystem target
monkeypatched into tmp_path. Nothing here may touch the operator's real
~/.claude — a test that corrupts user settings breaks every session on the box.
Infrastructure: no live graph, no MCP server, no subprocess installs.
Scope: the *config the installer writes* is the contract under test. The faults
it guards are latent configuration errors in the sense of Xu et al. (OSDI 2016):
set at startup, exercised much later, and therefore silent until the damage is
done. So the assertions are about what the written config would do at that later
moment — absolute paths that survive a foreign cwd, one definition rather than
two, and foreign hooks left intact — not about the installer's return value.
"""

import json
import re
from pathlib import Path

import pytest

from thalamus.harness import install
from thalamus.contract.paths import PROJECT_ROOT


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirect every write target into tmp_path."""
    user_settings = tmp_path / "user" / "settings.json"
    project_settings = tmp_path / "project" / "settings.json"
    project_mcp = tmp_path / "project" / ".mcp.json"
    agents = tmp_path / "agents"
    skills = tmp_path / "skills"
    cursor_user_hooks = tmp_path / "user" / "cursor-hooks.json"
    cursor_user_mcp = tmp_path / "user" / "cursor-mcp.json"
    cursor_project_hooks = tmp_path / "project" / "cursor-hooks.json"
    cursor_project_mcp = tmp_path / "project" / "cursor-mcp.json"
    codex_hooks = tmp_path / "user" / "codex-hooks.json"
    codex_config = tmp_path / "user" / "codex-config.toml"
    codex_home = tmp_path / "codex-home"
    monkeypatch.setattr(install, "USER_SETTINGS", user_settings)
    monkeypatch.setattr(install, "PROJECT_SETTINGS", project_settings)
    monkeypatch.setattr(install, "PROJECT_MCP", project_mcp)
    monkeypatch.setattr(install, "USER_AGENTS_DIR", agents)
    monkeypatch.setattr(install, "USER_SKILLS_DIR", skills)
    # The Cursor leg runs by default (harness="both"), so these must be
    # redirected too: an unpatched run rewrites the operator's real
    # ~/.cursor/hooks.json and strips the checkout's committed .cursor files.
    monkeypatch.setattr(install, "USER_CURSOR_HOOKS", cursor_user_hooks)
    monkeypatch.setattr(install, "USER_CURSOR_MCP", cursor_user_mcp)
    monkeypatch.setattr(install, "PROJECT_CURSOR_HOOKS", cursor_project_hooks)
    monkeypatch.setattr(install, "PROJECT_CURSOR_MCP", cursor_project_mcp)
    # The codex leg runs by default too, and its two paths are resolved from
    # `CODEX_HOME` at *import* — so an unpatched run writes the operator's real
    # ~/.codex/hooks.json and reads their real config.toml for the trust check.
    monkeypatch.setattr(install, "USER_CODEX_HOOKS", codex_hooks)
    monkeypatch.setattr(install, "USER_CODEX_MCP", codex_config)
    # The directory itself, not only the two paths derived from it. `CODEX_HOME` is
    # resolved at import (install.py:98), and redirecting `USER_CODEX_HOOKS` and
    # `USER_CODEX_MCP` leaves everything that globs the *directory* pointed at the
    # operator's real ~/.codex: `install()` wrote derived profiles into it and
    # `uninstall()` deleted them, so the suite rewrote his roster as it ran (#71).
    # Both resolutions, because there are two and they disagree about *when*.
    # `install.CODEX_HOME` is computed at import, so it needs the attribute; the
    # profile writer goes through `codex_transcripts.codex_home()`, which reads the
    # env var per call, so it needs the variable. Closing one and not the other left
    # `uninstall()` deleting inside the sandbox while `install()` wrote outside it.
    monkeypatch.setattr(install, "CODEX_HOME", codex_home)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    # And never the real `codex mcp add|remove`: it writes `$CODEX_HOME/config.toml`,
    # which HOME does not move — the same containment failure that made the Claude
    # Code registration a stubbed seam.
    codex_calls: list = []
    monkeypatch.setattr(install, "register_codex_mcp",
                        lambda dry_run=False: codex_calls.append(dry_run) or "codex mcp: stubbed")
    monkeypatch.setattr(install, "deregister_codex_mcp",
                        lambda dry_run=False: "codex mcp: deregistration stubbed")
    # Stubbed as *registered against this checkout*, matching the stubbed `add` above:
    # a fixture whose reader always answers "absent" would make a successful install
    # read as a fresh box forever. The absent branch is exercised where it belongs, by
    # the tests that are about it.
    monkeypatch.setattr(
        install, "codex_mcp_registration",
        lambda: f"  args: run --project {PROJECT_ROOT} thalamus-mcp\n")
    # The Claude Code read, stubbed for the same reason: it shells out to the
    # operator's `claude`, so an unstubbed test reports on his registration rather
    # than on the code, and comes back blocked on a runner that has no `claude`.
    monkeypatch.setattr(
        install, "claude_mcp_registration",
        lambda: f"  Args: run --project {PROJECT_ROOT} thalamus-mcp\n")
    # The twin of the seam above, and the one that was never wired into it:
    # `registered_mcp_env` shells out to the same `claude mcp get thalamus`, so an
    # unstubbed test reads the operator's real registration and pays a real CLI boot
    # for it. Measured 2026-08-26: 47 spawns, 137s of a 343s suite.
    monkeypatch.setattr(install, "registered_mcp_env", dict)
    # And the graph probe. Unstubbed it opens a real socket to the operator's live
    # graph and spawns an interpreter to run a real traversal against it — so a
    # sandboxed test's verdict depends on whether his container happens to be up.
    # The tests that are *about* the advisory monkeypatch this themselves, which
    # still wins: this clears the floor, it does not hold it down.
    monkeypatch.setattr(install, "_probe_graph", lambda url: (True, "stubbed", False))
    # And the entry-point spawn, the third of the same family. `verify()` runs on
    # every `install()`, so unstubbed this is a full `uv` resolution and CLI boot
    # per installing test. Measured 2026-08-26: 72 spawns, 42.9s.
    #
    # The real one is handed back under `probe_entry_point` because the stub is a
    # module attribute: the one test that must pay the real spawn cannot reach it
    # by calling `install.probe_entry_point()`, which is the stub by then.
    real_probe_entry_point = install.probe_entry_point
    monkeypatch.setattr(install, "probe_entry_point",
                        lambda: (True, "stubbed: `thalamus` resolves from a foreign cwd"))
    monkeypatch.setattr(install, "write_all_agents", lambda d: d.mkdir(parents=True, exist_ok=True))
    # Never invoke the real `claude mcp add` from a test — it writes the
    # operator's shared ~/.claude.json.
    calls: list = []
    monkeypatch.setattr(install, "register_mcp",
                        lambda dry_run=False: calls.append(dry_run) or "mcp: stubbed")
    # And never the real `claude mcp remove`, for a sharper version of the same
    # reason: overriding HOME for the child does not reliably contain it, so an
    # unstubbed uninstall test deregisters the server of whoever ran the suite.
    monkeypatch.setattr(install, "deregister_mcp",
                        lambda dry_run=False: "mcp: deregistration stubbed")
    return {"user": user_settings, "project": project_settings,
            "project_mcp": project_mcp, "mcp_calls": calls, "skills": skills,
            "cursor_user": cursor_user_hooks, "cursor_user_mcp": cursor_user_mcp,
            "cursor_project": cursor_project_hooks,
            "cursor_project_mcp": cursor_project_mcp,
            "codex_hooks": codex_hooks, "codex_config": codex_config,
            "codex_home": codex_home, "codex_mcp_calls": codex_calls,
            "probe_entry_point": real_probe_entry_point}


class TestCursorWiring:
    """Cursor parity. The contract that matters is that the
    written config still works when the session's workspace root is some other
    repo — the whole reason a work machine needs an installer at all."""

    def test_every_command_is_absolute(self):
        """User-scope Cursor hooks run from ~/.cursor/, project hooks from the
        project root. A relative command is therefore broken in one of the two
        scopes, whichever way it is written."""
        for entries in install.build_cursor_hook_block().values():
            for entry in entries:
                assert entry["command"].startswith("/")
                assert "$" not in entry["command"]

    def test_scripts_named_in_the_wiring_actually_exist(self):
        missing = [s for _, s in install.CURSOR_HOOK_WIRING
                   if not (install.CURSOR_HOOK_DIR / s).is_file()]
        assert not missing

    def test_prompt_tiers_reach_cursor_through_the_spool(self):
        """timestamp and conditioning had no Cursor carrier before: they ride
        beforeSubmitPrompt to compute and postToolUse to deliver."""
        block = install.build_cursor_hook_block()
        prompt_side = {e["command"].rsplit("/", 1)[1] for e in block["beforeSubmitPrompt"]}
        assert {"timestamp.sh", "conditioning.sh"} <= prompt_side
        assert [e["command"].rsplit("/", 1)[1] for e in block["postToolUse"]] == ["inject.sh"]

    def test_taps_stay_on_the_specialized_events(self):
        """Cursor's generic postToolUse also fires for MCP and shell calls. Until
        a live Cursor settles whether both fire, only the specialized events may
        tap — two writers would double-count every retrieval in `eval sync`.

        The subject is which events carry a *tap*, not how many hooks an event holds:
        `readiness-ready.sh` shares both after-events and writes no trace, so a check
        that counted entries would refuse it for a reason that does not apply to it.
        """
        block = install.build_cursor_hook_block()
        taps_on = {
            event: {e["command"].rsplit("/", 1)[1] for e in entries
                    if "tap" in e["command"]}
            for event, entries in block.items()
        }
        assert taps_on["afterMCPExecution"] == {"mcp-tap.sh"}
        assert taps_on["afterShellExecution"] == {"gremlin-tap.sh"}
        assert "tap" not in str(block["postToolUse"])

    def test_guard_declares_its_fail_open_posture(self):
        guard = [e for e in install.build_cursor_hook_block()["beforeShellExecution"]
                 if e["command"].endswith("gremlin-guard.sh")][0]
        assert guard["failClosed"] is False


class TestCursorInstall:
    def test_writes_hooks_and_mcp_at_user_scope(self, sandbox):
        install.install()
        hooks = json.loads(sandbox["cursor_user"].read_text())
        assert hooks["version"] == 1
        assert set(hooks["hooks"]) == {e for e, _ in install.CURSOR_HOOK_WIRING}
        served = json.loads(sandbox["cursor_user_mcp"].read_text())["mcpServers"]["thalamus"]
        assert str(PROJECT_ROOT) in served["args"]

    def test_strips_the_project_scope_duplicate(self, sandbox):
        """Cursor documents Project > User precedence, so a surviving project
        block silently outranks the user-scope one just written."""
        sandbox["cursor_project"].parent.mkdir(parents=True, exist_ok=True)
        sandbox["cursor_project"].write_text(json.dumps({"version": 1, "hooks": {
            "sessionStart": [{"command": "./src/thalamus/harness/hooks/cursor/session-start.sh"}]}}))
        install.install()
        assert json.loads(sandbox["cursor_project"].read_text())["hooks"] == {}

    def test_preserves_cursor_hooks_the_operator_added(self, sandbox):
        sandbox["cursor_user"].parent.mkdir(parents=True, exist_ok=True)
        sandbox["cursor_user"].write_text(json.dumps({"version": 1, "hooks": {
            "afterFileEdit": [{"command": "/opt/mine/format.sh"}]}}))
        install.install()
        hooks = json.loads(sandbox["cursor_user"].read_text())["hooks"]
        assert hooks["afterFileEdit"] == [{"command": "/opt/mine/format.sh"}]

    def test_keeps_other_cursor_mcp_servers(self, sandbox):
        sandbox["cursor_user_mcp"].parent.mkdir(parents=True, exist_ok=True)
        sandbox["cursor_user_mcp"].write_text(
            json.dumps({"mcpServers": {"other": {"command": "x"}}}))
        install.install()
        servers = json.loads(sandbox["cursor_user_mcp"].read_text())["mcpServers"]
        assert set(servers) == {"other", "thalamus"}

    def test_reinstall_does_not_accumulate_duplicates(self, sandbox):
        install.install()
        install.install()
        entries = json.loads(sandbox["cursor_user"].read_text())["hooks"]["beforeSubmitPrompt"]
        commands = [e["command"] for e in entries]
        assert len(commands) == len(set(commands)) == 3

    def test_dry_run_writes_nothing(self, sandbox):
        install.install(dry_run=True)
        assert not sandbox["cursor_user"].exists()
        assert not sandbox["cursor_user_mcp"].exists()

    def test_claude_only_install_leaves_cursor_untouched(self, sandbox):
        install.install(harnesses=("claude",))
        assert not sandbox["cursor_user"].exists()

    def test_cursor_only_install_leaves_claude_untouched(self, sandbox):
        install.install(harnesses=("cursor",))
        assert sandbox["cursor_user"].exists()
        assert not sandbox["user"].exists()
        assert sandbox["mcp_calls"] == [], "cursor-only must not register the Claude MCP server"

    def test_cursor_only_still_links_skills(self, sandbox):
        """A Cursor session gets the hooks and the server; without the skills it
        queries the graph with no recall-strategy and grounds nothing."""
        install.install(harnesses=("cursor",))
        assert list(sandbox["skills"].iterdir())


class TestCodexWiring:
    """Codex's table, whose subject is what its payloads actually name.

    The wiring is Claude Code's schema — codex reads matcher groups from
    `$CODEX_HOME/hooks.json` and its matchers are regexes (measured 2026-08-17) — so
    what these assert is not the shape but the *vocabulary*: a matcher naming a tool
    codex does not have is a boundary that reads as enforced and fires for nothing,
    which is `room-guard.sh`'s history on this repo.
    """

    def test_every_command_is_absolute(self):
        """`$CODEX_HOME` expands inside a command and nothing else does, so a
        relative path resolves against the session's own cwd — a different repo
        entirely whenever a session is opened outside the checkout."""
        for groups in install.build_codex_hook_block().values():
            for group in groups:
                for hook in group["hooks"]:
                    assert hook["command"].startswith("/")
                    assert "$" not in hook["command"]

    def test_scripts_named_in_the_wiring_actually_exist(self):
        missing = [s for _, _, s in install.CODEX_HOOK_WIRING
                   if not (install.CODEX_HOOK_DIR / s).is_file()]
        assert not missing

    def test_the_shell_matcher_is_the_name_codex_actually_sends(self):
        """Codex's shell tool is `Bash`, with `tool_input.command` — measured against
        a live `codex exec`, and not what the rollout says (there every call is a
        `custom_tool_call` named `exec` carrying a JavaScript program). The hook layer
        is the surface a matcher is matched against, so it is the one that decides."""
        block = install.build_codex_hook_block()
        bash_pre = {h["command"].rsplit("/", 1)[1]
                    for g in block["PreToolUse"] if g.get("matcher") == "Bash"
                    for h in g["hooks"]}
        assert {"gremlin-guard.sh", "write-guard.sh", "room-command-guard.sh"} == bash_pre

    def test_the_editing_matcher_is_apply_patch_and_nothing_unmeasured(self):
        """`apply_patch` is codex's editing tool, and `Skill`/`Artifact` are not in
        the matcher because codex's skill and artifact surfaces have not been
        measured. A matcher naming an unobserved tool reads as enforcement and is
        not — the failure `contract/boundaries.py` exists to keep separate."""
        matchers = [g.get("matcher") for g in install.build_codex_hook_block()["PreToolUse"]
                    for h in g["hooks"] if h["command"].endswith("role-guard.sh")]
        assert matchers == ["apply_patch|mcp__penpot__.*"]
        assert "Skill" not in str(matchers) and "Artifact" not in str(matchers)

    def test_the_room_tool_guard_has_no_codex_wiring(self):
        """`room-guard.sh` matches `SendMessage` and codex has no such tool, so peer
        traffic there is a shell command or it is nothing — the same call Cursor
        made. Declared as a gap in the parity record rather than silently absent."""
        assert "room-guard.sh" not in {s for _, _, s in install.CODEX_HOOK_WIRING}
        assert "room-guard.sh" in install.DECLARED_HOOK_PARITY.missing["codex"]

    def test_taps_are_wired_on_the_names_codex_reports(self):
        block = install.build_codex_hook_block()
        post = {g.get("matcher"): {h["command"].rsplit("/", 1)[1] for h in g["hooks"]}
                for g in block["PostToolUse"]}
        assert post["mcp__thalamus__.*"] == {"post-tool-use.sh"}
        assert post["Bash"] == {"gremlin-tap.sh", "recipe-stage.sh"}
        # TaskCreate has no codex carrier — it is Claude Code task-list UI — so the
        # milestone conditioning class must not be wired against a tool that never
        # fires. The two lexical classes ride UserPromptSubmit and both cross.
        assert "TaskCreate" not in post
        prompt = {h["command"].rsplit("/", 1)[1]
                  for g in block["UserPromptSubmit"] for h in g["hooks"]}
        assert prompt == {"timestamp.sh", "conditioning.sh", "pin-engaged.sh"}


class TestCodexInstall:
    def test_writes_hooks_and_registers_mcp_at_the_codex_config_root(self, sandbox):
        install.install()
        hooks = json.loads(sandbox["codex_hooks"].read_text())["hooks"]
        assert set(hooks) == {e for e, _, _ in install.CODEX_HOOK_WIRING}
        assert sandbox["codex_mcp_calls"] == [False], "codex MCP goes through `codex mcp add`"

    def test_there_is_no_project_scope_to_strip(self, sandbox):
        """Measured: `$CODEX_HOME/hooks.json` is the only file codex loads hooks from
        — a project-level `./.codex/hooks.json` is not discovered and hooks in
        `config.toml` do not fire. So the mutual-exclusion problem the other two legs
        solve by removing a second definition cannot arise, and the installer must not
        invent a second place to look."""
        assert not any(name.startswith("PROJECT_CODEX") for name in dir(install))

    def test_config_toml_is_never_written_by_us(self, sandbox):
        """`codex mcp add` owns that file: it also holds the per-project trust levels
        and the `[hooks.state]` trust hashes codex writes for itself, so a
        read-modify-write would drop whatever the CLI put there."""
        install.install()
        assert not sandbox["codex_config"].exists()

    def test_preserves_codex_hooks_the_operator_added(self, sandbox):
        sandbox["codex_hooks"].parent.mkdir(parents=True, exist_ok=True)
        sandbox["codex_hooks"].write_text(json.dumps({"hooks": {
            "PreCompact": [{"hooks": [{"type": "command", "command": "/opt/mine/note.sh"}]}]}}))
        install.install()
        hooks = json.loads(sandbox["codex_hooks"].read_text())["hooks"]
        assert hooks["PreCompact"] == [
            {"hooks": [{"type": "command", "command": "/opt/mine/note.sh"}]}]

    def test_reinstall_does_not_accumulate_duplicates(self, sandbox):
        """A duplicate costs more here than elsewhere: codex's trust records are keyed
        by (event, group index, hook index), so a table that grows on every install
        renumbers the coordinates and quietly untrusts the hooks that moved."""
        install.install()
        install.install()
        settings = json.loads(sandbox["codex_hooks"].read_text())
        wired = [(g.get("matcher"), h["command"])
                 for g in settings["hooks"]["PostToolUse"] for h in g["hooks"]]
        assert len(wired) == len(set(wired))

    def test_dry_run_writes_nothing(self, sandbox):
        install.install(dry_run=True)
        assert not sandbox["codex_hooks"].exists()
        assert sandbox["codex_mcp_calls"] == [True], "dry run must not register"

    def test_codex_only_install_leaves_the_others_untouched(self, sandbox):
        install.install(harnesses=("codex",))
        assert sandbox["codex_hooks"].exists()
        assert not sandbox["user"].exists()
        assert not sandbox["cursor_user"].exists()
        assert sandbox["mcp_calls"] == [], "codex-only must not register the Claude MCP server"

    def test_claude_only_install_leaves_codex_untouched(self, sandbox):
        install.install(harnesses=("claude",))
        assert not sandbox["codex_hooks"].exists()

    def test_uninstall_removes_the_codex_hooks_and_leaves_the_operators(self, sandbox):
        install.install()
        hooks = json.loads(sandbox["codex_hooks"].read_text())
        hooks["hooks"].setdefault("PreCompact", []).append(
            {"hooks": [{"type": "command", "command": "/opt/mine/note.sh"}]})
        sandbox["codex_hooks"].write_text(json.dumps(hooks))

        install.uninstall()

        left = json.loads(sandbox["codex_hooks"].read_text())["hooks"]
        assert left == {"PreCompact": [
            {"hooks": [{"type": "command", "command": "/opt/mine/note.sh"}]}]}


class TestCodexTrust:
    """The gate that makes a correct install do nothing.

    Measured 2026-08-17: with a `hooks.json` present and untrusted, a headless
    `codex exec` ran to completion, exited 0, printed nothing about hooks, and fired
    none of them. That is the latent configuration error this module is written
    against — the wiring is right and the memory simply stops accumulating — so the
    trust state is a finding of its own rather than an assumption inside the wiring
    check.
    """

    def _trust(self, sandbox, *, all_of_them: bool) -> None:
        keys = sorted(
            f"{install.USER_CODEX_HOOKS}:{install._codex_event_key(event)}:{gi}:{hi}"
            for event, groups in install.build_codex_hook_block().items()
            for gi, group in enumerate(groups)
            for hi, _ in enumerate(group["hooks"])
        )
        if not all_of_them:
            keys = keys[:1]
        sandbox["codex_config"].parent.mkdir(parents=True, exist_ok=True)
        sandbox["codex_config"].write_text("".join(
            f'[hooks.state."{key}"]\ntrusted_hash = "sha256:deadbeef"\n\n' for key in keys))

    def test_an_untrusted_install_is_advisory_and_names_the_consequence(self, sandbox):
        """Advisory, not pending: the install is wired correctly and something outside
        it has to become true — the same shape as an unreachable graph. `pending`
        would print "Run `thalamus init` to install it", and no run of that command
        can grant a trust the operator has to give in a TUI."""
        install.install()
        check = {c.name: c for c in install.verify_codex()}["codex hooks trusted"]
        assert check.advisory and not check.ok and not check.pending
        assert "trust" in check.detail
        # Verifies: the consequence is stated, not just the remedy. An operator who
        # reads "not trusted yet" and shrugs has been told nothing about the silence.
        assert "distilled nothing" in check.detail

    def test_a_box_with_no_hooks_written_is_pending_on_thalamus_init(self, sandbox):
        """Before the file exists there is no trust question, and the command that
        moves the box forward is the installer's — so this one *is* the pending
        state, and naming `thalamus init` in it is correct."""
        check = {c.name: c for c in install.verify_codex()}["codex hooks trusted"]
        assert check.pending and "thalamus init" in check.detail

    def test_a_fully_trusted_install_passes(self, sandbox):
        install.install()
        self._trust(sandbox, all_of_them=True)
        assert {c.name: c for c in install.verify_codex()}["codex hooks trusted"].ok

    def test_a_partly_trusted_install_is_a_failure_not_a_pending_item(self, sandbox):
        """Some entries trusted and some not is drift — the file was written, codex
        was asked, and the answer covered only part of it. The untrusted ones do not
        fire, so this must stay loud rather than reading as an uninstalled box."""
        install.install()
        self._trust(sandbox, all_of_them=False)
        check = {c.name: c for c in install.verify_codex()}["codex hooks trusted"]
        assert not check.ok and not check.pending

    def test_the_trust_key_is_the_coordinate_codex_writes(self, sandbox):
        """`<hooks.json path>:<event_snake>:<group index>:<hook index>` — measured
        from a real `[hooks.state]` table after pressing trust in the codex TUI."""
        assert install._codex_event_key("PreToolUse") == "pre_tool_use"
        assert install._codex_event_key("UserPromptSubmit") == "user_prompt_submit"
        assert install._codex_event_key("SessionEnd") == "session_end"

    def test_trust_records_survive_a_reinstall_of_an_unchanged_wiring(self, sandbox):
        """The install rewrites `hooks.json`, and the trust records live in a file it
        never touches — so an idempotent re-run must not cost the operator the gate
        they already cleared. It holds because the generated block is deterministic:
        the same events, groups and indices every time."""
        install.install()
        self._trust(sandbox, all_of_them=True)
        install.install()
        assert {c.name: c for c in install.verify_codex()}["codex hooks trusted"].ok


class TestHookBlock:
    def test_every_wired_script_is_reachable_by_absolute_path(self):
        """The whole point: no $CLAUDE_PROJECT_DIR, which names the wrong repo."""
        block = install.build_hook_block()
        commands = [h["command"] for groups in block.values()
                    for g in groups for h in g["hooks"]]
        assert len(commands) == len(install.HOOK_WIRING)
        for cmd in commands:
            assert "$CLAUDE_PROJECT_DIR" not in cmd
            assert cmd.startswith("/")

    def test_matchers_are_preserved_per_event(self):
        block = install.build_hook_block()
        post = {g.get("matcher") for g in block["PostToolUse"]}
        assert post == {
            "mcp__thalamus__.*",
            "Bash",
            "TaskCreate",
            "Agent",
            "mcp__thalamus__memory_query",
        }
        assert all("matcher" not in g for g in block["SessionEnd"])

        # One script legitimately serves three matchers: conditioning.sh carries the
        # milestone class (TaskCreate), the selfticket class (Agent) and the falsify
        # class (memory_query). Grouping is per matcher, so they must land in
        # different groups — the same script in one group twice would fire it twice
        # for one tool call.
        conditioning = [
            g.get("matcher")
            for g in block["PostToolUse"]
            for h in g["hooks"]
            if h["command"].endswith("conditioning.sh")
        ]
        assert sorted(conditioning) == [
            "Agent",
            "TaskCreate",
            "mcp__thalamus__memory_query",
        ]

        # recipe-stage.sh covers both graph surfaces, for the same reason the tap
        # does: memory_query and inline gremlin Bash query the same graph, and a
        # store fed by only one of them would miss whichever the session preferred.
        staging = sorted(
            g.get("matcher")
            for g in block["PostToolUse"]
            for h in g["hooks"]
            if h["command"].endswith("recipe-stage.sh")
        )
        assert staging == ["Bash", "mcp__thalamus__memory_query"]

    def test_scripts_named_in_the_wiring_actually_exist(self):
        """A wiring entry naming a script that isn't there is a latent error."""
        for _, _, script in install.HOOK_WIRING:
            assert (install.HOOK_DIR / script).is_file(), script


class TestMcpEntry:
    def test_anchored_on_the_checkout_not_the_session_cwd(self):
        entry = install.build_mcp_entry()
        assert entry["args"] == ["run", "--project", str(PROJECT_ROOT), "thalamus-mcp"]

    def test_no_scope_is_baked_in(self):
        """A static user-scope config cannot know the pin; baking one would pin
        every session on the box to one expert (harness/pin.resolve_pin)."""
        assert "THALAMUS_SCOPE" not in install.build_mcp_entry()["env"]


class TestInstall:
    def test_writes_hooks_and_registers_mcp_at_user_scope(self, sandbox):
        install.install()
        settings = json.loads(sandbox["user"].read_text())
        assert set(settings["hooks"]) == {
            "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse"}
        assert sandbox["mcp_calls"] == [False], "MCP goes through `claude mcp add`"

    def test_removes_the_project_scope_mcp_server(self, sandbox):
        sandbox["project_mcp"].parent.mkdir(parents=True, exist_ok=True)
        sandbox["project_mcp"].write_text(json.dumps(
            {"mcpServers": {"thalamus": {"command": "uv", "args": ["run", "thalamus-mcp"]}}}))
        install.install()
        assert not sandbox["project_mcp"].exists(), "file held nothing else; remove it"

    def test_keeps_other_project_mcp_servers(self, sandbox):
        sandbox["project_mcp"].parent.mkdir(parents=True, exist_ok=True)
        sandbox["project_mcp"].write_text(json.dumps({"mcpServers": {
            "thalamus": {"command": "uv"}, "other": {"command": "npx"}}}))
        install.install()
        servers = json.loads(sandbox["project_mcp"].read_text())["mcpServers"]
        assert set(servers) == {"other"}

    def test_is_idempotent(self, sandbox):
        install.install()
        first = sandbox["user"].read_text()
        actions, _ = install.install()
        assert sandbox["user"].read_text() == first
        assert any("already current" in a for a in actions)

    def test_preserves_hooks_the_operator_added(self, sandbox):
        """Stripping ours must not evict someone else's tooling."""
        sandbox["user"].parent.mkdir(parents=True, exist_ok=True)
        sandbox["user"].write_text(json.dumps({
            "model": "opus",
            "hooks": {"SessionStart": [{"hooks": [
                {"type": "command", "command": "/usr/local/bin/my-own-hook.sh"}]}]},
        }))
        install.install()
        settings = json.loads(sandbox["user"].read_text())
        commands = [h["command"] for g in settings["hooks"]["SessionStart"] for h in g["hooks"]]
        assert "/usr/local/bin/my-own-hook.sh" in commands
        assert settings["model"] == "opus", "unrelated settings must survive"

    def test_reinstall_does_not_accumulate_duplicates(self, sandbox):
        """Without stripping ours first, each run would append another copy.

        Keyed on (matcher, command), not command alone: one script may serve
        several matchers on purpose (conditioning.sh carries both the milestone
        and falsify classes), and the duplicate that actually costs anything is
        the same script firing twice for the same tool.
        """
        install.install()
        install.install()
        install.install()
        settings = json.loads(sandbox["user"].read_text())
        wired = [
            (g.get("matcher"), h["command"])
            for g in settings["hooks"]["PostToolUse"]
            for h in g["hooks"]
        ]
        assert len(wired) == len(set(wired))

    def test_strips_the_project_scope_duplicate(self, sandbox):
        """Option 3: one definition, so the undocumented merge behaviour of
        Claude Code's settings scopes is never load-bearing."""
        sandbox["project"].parent.mkdir(parents=True, exist_ok=True)
        sandbox["project"].write_text(json.dumps({"hooks": {"SessionEnd": [{"hooks": [
            {"type": "command",
             "command": "$CLAUDE_PROJECT_DIR/src/thalamus/harness/hooks/claude-code/session-end.sh"}
        ]}]}}))
        install.install()
        assert "hooks" not in json.loads(sandbox["project"].read_text())

    def test_dry_run_writes_nothing(self, sandbox):
        actions, _ = install.install(dry_run=True)
        assert actions and not sandbox["user"].exists()
        assert sandbox["mcp_calls"] == [True], "dry run must not register"

    def test_refuses_to_overwrite_unparseable_settings(self, sandbox):
        """Clobbering a malformed ~/.claude/settings.json would destroy config
        the operator has to hand-restore; fail loudly instead."""
        sandbox["user"].parent.mkdir(parents=True, exist_ok=True)
        sandbox["user"].write_text("{ this is not json")
        with pytest.raises(RuntimeError, match="not valid JSON"):
            install.install()


class TestSkills:
    """The skills have to arm outside the checkout for the same reason the hooks do.

    A session opened elsewhere gets hooks, MCP and agents; without this it gets no
    `recall-strategy`, `ground-in-literature` or `gremlin-python`, and that absence
    never announces itself — it shows up as an uncited design or a lazy traversal.
    """

    def test_every_shipped_skill_lands_at_user_scope(self, sandbox):
        install.install()
        names = {p.name for p in sandbox["skills"].iterdir()}
        assert names == {p.name for p in install.shipped_skills()}
        assert {"recall-strategy", "ground-in-literature", "gremlin-python"} <= names

    def test_a_skill_md_without_frontmatter_is_not_installed(self, sandbox, tmp_path,
                                                             monkeypatch):
        """Frontmatter is what makes a directory invocable; prose in a SKILL.md
        is a note or a prompt template, and installing it would advertise
        something no session can call."""
        shipped = tmp_path / "shipped"
        (shipped / "real").mkdir(parents=True)
        (shipped / "real" / "SKILL.md").write_text("---\nname: real\n---\nbody\n")
        (shipped / "prose").mkdir()
        (shipped / "prose" / "SKILL.md").write_text("# Just a prompt\n\nno frontmatter\n")
        monkeypatch.setattr(install, "SKILL_DIR", shipped)
        assert [p.name for p in install.shipped_skills()] == ["real"]
        install.link_skills()
        assert [p.name for p in sandbox["skills"].iterdir()] == ["real"]

    def test_links_to_the_package_so_one_edit_serves_every_scope(self, sandbox):
        install.install()
        for src in install.shipped_skills():
            dest = sandbox["skills"] / src.name
            assert dest.is_symlink(), f"{src.name} must be a link, not a copy"
            assert dest.resolve() == src.resolve()

    def test_a_hand_written_skill_of_the_same_name_is_never_clobbered(self, sandbox):
        """User scope holds skills we did not write. Destroying one to install
        ours would be a worse failure than the one being fixed."""
        victim = sandbox["skills"] / install.shipped_skills()[0].name
        victim.mkdir(parents=True)
        (victim / "SKILL.md").write_text("---\nname: mine\n---\nhand written\n")
        actions, _ = install.install()
        assert (victim / "SKILL.md").read_text().endswith("hand written\n")
        assert any("left alone" in a for a in actions), "and it must say so"

    def test_is_idempotent(self, sandbox):
        install.install()
        actions, _ = install.install()
        assert any("already linked" in a for a in actions)

    def test_dry_run_links_nothing(self, sandbox):
        actions, _ = install.install(dry_run=True)
        assert any("would link" in a for a in actions)
        assert not sandbox["skills"].exists()


class TestVerify:
    def test_exercises_the_entry_point_rather_than_asserting_it(self, sandbox):
        """PCheck's early-detection idea: run the late usage now. The check must
        be a real spawn, so a broken uv project fails here and not at SessionEnd.

        Takes the real seam from the sandbox, which stubs the module attribute
        for every other test. This is the one place in the suite that pays the
        real spawn, and one is what the check is worth: the other 71 asserted
        nothing about it.
        """
        ok, detail = sandbox["probe_entry_point"]()
        assert ok, detail
        assert "foreign cwd" in detail

        # And `verify()` still reports it, so the seam cannot go orphaned.
        checks = {c.name: c for c in install.verify()}
        assert "distillation entry point" in checks
        assert checks["jq on PATH"].ok

    def test_reports_missing_agents_rather_than_silently_passing(self, sandbox):
        checks = {c.name: c for c in install.verify()}
        assert not checks["derived agents installed"].ok

    def test_reads_skills_through_the_link_instead_of_trusting_it(self, sandbox):
        """A dangling symlink passes `.exists()` on the name and fails on the
        read — which is the moment a real session would have needed it."""
        install.install()
        name = install.shipped_skills()[0].name
        link = sandbox["skills"] / name
        link.unlink()
        link.symlink_to(sandbox["skills"] / "gone")
        check = {c.name: c for c in install.verify()}["skills load at user scope"]
        assert not check.ok and name in check.detail
        # A link that exists and cannot be read is breakage, not an absent install.
        assert not check.pending

    def test_passes_once_the_skills_are_installed(self, sandbox):
        install.install()
        assert {c.name: c for c in install.verify()}["skills load at user scope"].ok

    def test_a_link_to_a_skill_that_no_longer_ships_is_reported(self, sandbox):
        """The dangling case the shipped-set walk cannot reach.

        `verify` reads each skill through its user-scope path, which finds every
        broken link whose *name* is still in `shipped_skills()`. Rename a skill or
        drop one and the link its install left behind has a name in no shipped set:
        the walk never visits it, and it sits in the user's skills directory
        dangling and unreported until something silently fails to arm.
        """
        install.install()
        stale = sandbox["skills"] / "skill-that-was-renamed"
        stale.symlink_to(install.SKILL_DIR / "skill-that-was-renamed")

        check = {c.name: c for c in install.verify()}["skills load at user scope"]

        assert not check.ok and "skill-that-was-renamed" in check.detail
        # Present and wrong, and `thalamus init` clears it — so a hard failure,
        # not the pending shape an uninstalled box gets.
        assert not check.pending
        assert "thalamus init" in check.detail

    def test_a_foreign_link_of_the_same_shape_is_not_claimed(self, sandbox):
        """The other half of the identity test: it is scoped to *our* skill dir."""
        install.install()
        theirs = sandbox["skills"] / "someone-elses"
        theirs.symlink_to(sandbox["skills"].parent / "elsewhere" / "someone-elses")

        check = {c.name: c for c in install.verify()}["skills load at user scope"]

        assert check.ok, check.detail

    def test_run_exits_nonzero_when_a_check_fails(self, sandbox, monkeypatch):
        monkeypatch.setattr(install, "verify",
                            lambda *a, **k: [install.Check("fake", False, "boom")])
        assert install.run(check_only=True) == 1


class TestTheClaudeCodeMcpRegistration:
    """The registration every Claude Code user depends on, and the one nobody checked.

    Cursor's was verified and codex's was; this one was not. `register_mcp` returns
    `SKIPPED MCP registration: 'claude' not on PATH` into the *actions* list, so an
    install run before the CLI existed printed `Installed for Claude Code…`, exited 0,
    registered nothing, and `--check` reported no failure — no `mcp__thalamus__*` tool
    in any session, and no surface saying why.

    Asserted on `verify()`'s output rather than on the registration call: `claude mcp
    add|remove` writes the operator's real `~/.claude.json` even under a redirected
    HOME, which is why the write is a stubbed seam and the read now is too.
    """

    def _absent(self, monkeypatch, *names):
        real = install.shutil.which
        monkeypatch.setattr(install.shutil, "which",
                            lambda b: None if b in names else real(b))

    def test_a_registration_against_this_checkout_passes(self, sandbox):
        check = install.verify_claude_mcp()

        assert check.ok and str(PROJECT_ROOT) in check.detail

    def _present(self, monkeypatch, *names):
        """Pin the CLI as present: pending is the state of a box that can act on it,
        and a runner with no `claude` would otherwise read this as blocked."""
        real = install.shutil.which
        monkeypatch.setattr(install.shutil, "which",
                            lambda b: f"/usr/bin/{b}" if b in names else real(b))

    def test_an_absent_registration_is_pending_on_thalamus_init(self, sandbox, monkeypatch):
        self._present(monkeypatch, "claude")
        monkeypatch.setattr(install, "claude_mcp_registration", lambda: "")

        check = install.verify_claude_mcp()

        assert check.pending and not check.ok and not check.blocked
        assert "thalamus init" in check.detail
        # The consequence, not just the remedy — this is the failure that says nothing.
        assert "mcp__thalamus__" in check.detail

    def test_a_registration_against_another_checkout_is_a_hard_failure(self, sandbox,
                                                                       monkeypatch):
        """Reached by moving or renaming the checkout after `thalamus init` — the same
        drift the Cursor leg reports, on the leg that had no report at all.

        Asserted with `claude` *absent*, which is the case that gets this wrong: the
        registration was read and names another checkout, so the answer is known and
        the finding is real. Blocking it on the missing binary would hide a live
        defect behind "could not run".
        """
        self._absent(monkeypatch, "claude")
        monkeypatch.setattr(install, "claude_mcp_registration",
                            lambda: "  Args: run --project /somewhere/else thalamus-mcp\n")

        check = install.verify_claude_mcp()

        assert not check.ok and not check.pending and not check.blocked
        assert "not against this checkout" in check.detail
        assert check.render().startswith("  ✗")

    def test_a_box_without_the_claude_cli_could_not_run_it(self, sandbox, monkeypatch):
        """`thalamus init` registers through `claude mcp add`, so without the binary
        the command a pending item would name cannot clear it."""
        self._absent(monkeypatch, "claude")
        monkeypatch.setattr(install, "claude_mcp_registration", lambda: "")

        check = install.verify_claude_mcp()

        assert check.blocked and not check.pending and not check.ok
        assert "claude" in check.detail and "could not run" in check.detail
        assert check.render().startswith("  ?")

    def test_it_is_in_the_claude_leg_and_not_the_others(self, sandbox):
        assert "claude MCP server registered" in {c.name for c in install.verify(("claude",))}
        assert "claude MCP server registered" not in {c.name for c in install.verify(("cursor",))}


class TestAnUninstalledMachineIsNotABrokenOne:
    """`--check` and `--dry-run` are what a cautious operator runs *before*
    installing, and everything they find absent is the expected shape of a machine
    that has not installed yet. Reporting those as `✗` and exiting 1 tells someone
    whose box is fine that it is broken, and makes looking before you leap the
    option that reports failure.

    The line held here is the other half: anything present and *wrong* — a dangling
    skill link, a partially wired hooks file, an MCP entry that no longer matches
    this checkout — stays a hard failure, because that is what the check is for.
    """

    NOT_INSTALLED = ("derived agents installed", "skills load at user scope",
                     "declared hooks armed", "cursor hooks wired at user scope",
                     "cursor MCP server registered", "codex hooks wired at user scope",
                     "codex hooks trusted")

    def test_a_fresh_box_reports_pending_and_names_the_fix(self, sandbox):
        checks = {c.name: c for c in install.verify()}
        for name in self.NOT_INSTALLED:
            check = checks[name]
            assert check.pending, f"{name} reads as broken on an uninstalled box"
            assert "thalamus init" in check.detail, name
            assert check.render().startswith("  ○"), name

    def test_a_fresh_box_does_not_exit_nonzero(self, sandbox):
        assert install.run(check_only=True) == 0

    def test_nothing_is_pending_once_it_is_installed(self, sandbox):
        install.install()
        # The fixture stubs agent generation out, so stand one in: the subject here
        # is that a fully installed box has nothing left in the pending state.
        (install.USER_AGENTS_DIR / "thalamus-main.md").write_text("---\nname: x\n---\n")
        assert not [c.name for c in install.verify() if c.pending]

    def test_a_partly_wired_cursor_is_a_failure_not_a_pending_item(self, sandbox):
        """Some of our scripts present and some absent is drift — the file was
        written and has since moved — and drift must stay loud."""
        install.install()
        wiring = json.loads(sandbox["cursor_user"].read_text())
        first = next(iter(wiring["hooks"]))
        wiring["hooks"][first] = []
        sandbox["cursor_user"].write_text(json.dumps(wiring))

        check = {c.name: c for c in install.verify()}["cursor hooks wired at user scope"]
        assert not check.ok and not check.pending
        assert install.run(check_only=True) == 1

    def test_a_stale_cursor_mcp_entry_is_a_failure_not_a_pending_item(self, sandbox):
        install.install()
        registered = json.loads(sandbox["cursor_user_mcp"].read_text())
        registered["mcpServers"]["thalamus"]["args"] = ["--from", "somewhere-else"]
        sandbox["cursor_user_mcp"].write_text(json.dumps(registered))

        check = {c.name: c for c in install.verify()}["cursor MCP server registered"]
        assert not check.ok and not check.pending

    def test_a_stale_cursor_mcp_entry_says_so_and_names_the_field(self, sandbox):
        """The mark and the words have to agree.

        A stale entry is a non-empty dict, so ordering the detail's branches by
        truthiness put the healthy-install sentence beside the `✗` — the run said
        "`thalamus` in ~/.cursor/mcp.json" and exited 1. Reached by moving or
        renaming a checkout after `thalamus init`, where the differing field is a
        path inside `args` and the user has no other pointer to it.
        """
        install.install()
        registered = json.loads(sandbox["cursor_user_mcp"].read_text())
        registered["mcpServers"]["thalamus"]["args"] = ["--from", "somewhere-else"]
        sandbox["cursor_user_mcp"].write_text(json.dumps(registered))

        check = {c.name: c for c in install.verify()}["cursor MCP server registered"]

        assert "does not match" in check.detail
        assert "differing: args" in check.detail
        assert "thalamus init" in check.detail

    def test_one_missing_wiring_is_still_named_and_loud(self, sandbox):
        """Pending is *none* of them armed. One missing is `room-guard.sh` all over
        again — a declared hook that fires for nothing — and it must still say which.
        """
        install.install()
        settings = json.loads(sandbox["user"].read_text())
        settings["hooks"].pop("SessionEnd")
        sandbox["user"].write_text(json.dumps(settings))

        check = install.verify_armed()
        assert not check.ok and not check.pending
        assert "session-end.sh" in check.detail


class TestDryRunSaysItWroteNothing:
    """The one thing `--dry-run` promises. It used to return on the failure branch
    before reaching the line that says it, so the run that most needed the
    reassurance — the one that found faults — was the one that withheld it."""

    def test_it_prints_its_closing_line(self, sandbox, capsys):
        install.run(dry_run=True)
        assert "DRY RUN — nothing written" in capsys.readouterr().out

    def test_it_prints_it_even_when_a_check_failed(self, sandbox, capsys, monkeypatch):
        monkeypatch.setattr(install, "verify",
                            lambda *a, **k: [install.Check("hooks present", False, "gone")])
        code = install.run(dry_run=True)
        out = capsys.readouterr().out
        assert "FAILED" in out
        assert "DRY RUN — nothing written" in out
        assert code == 1, "a failing check must still exit 1 under --dry-run"

    def test_it_does_not_claim_to_have_installed_anything(self, sandbox, capsys):
        install.run(dry_run=True)
        assert "Installed for" not in capsys.readouterr().out


class TestADistillationLoopThatStalled:
    """`jq on PATH` answers about this machine *now*. If jq went missing over a
    weekend and is back by Monday it passes, and the sessions lost in between are
    invisible — distillation runs detached, so nothing announced them. The hooks
    write the loss down (`thalamus_require_binaries`); this reads it back on the
    surface an operator already runs when memory looks stale.
    """

    def _record(self, tmp_path, monkeypatch, *lines):
        log = tmp_path / "hook-failures.log"
        if lines:
            log.write_text("".join(f"{ln}\n" for ln in lines))
        monkeypatch.setattr(install, "HOOK_FAILURE_LOG", log)
        return log

    def test_an_absent_record_is_a_pass(self, tmp_path, monkeypatch):
        self._record(tmp_path, monkeypatch)
        check = install.recorded_hook_failures()
        assert check.ok and check.advisory

    def test_it_counts_the_lost_sessions_and_quotes_the_last(self, tmp_path, monkeypatch):
        self._record(tmp_path, monkeypatch,
                     "2026-08-14T09:00:00Z session-end.sh: not on PATH: jq — old",
                     "2026-08-15T09:00:00Z session-end.sh: not on PATH: jq — newest")
        check = install.recorded_hook_failures()
        assert not check.ok
        assert "2 ended undistilled" in check.detail
        assert "newest" in check.detail

    def test_it_is_advisory_and_does_not_fail_the_run(self, tmp_path, monkeypatch, sandbox):
        """A record of what the environment did is not the wiring being wrong, and
        `--check` refusing over it would make the history impossible to look at."""
        self._record(tmp_path, monkeypatch,
                     "2026-08-15T09:00:00Z session-end.sh: not on PATH: uv")
        monkeypatch.setattr(install, "verify", lambda *a, **k: [
            install.Check("hook scripts present", True, "all found"),
            install.recorded_hook_failures(),
        ])
        assert install.run(check_only=True) == 0

    def test_the_runtime_block_carries_it(self, tmp_path, monkeypatch):
        self._record(tmp_path, monkeypatch,
                     "2026-08-15T09:00:00Z session-end.sh: not on PATH: uv")
        monkeypatch.setattr(install, "_probe_graph", lambda url: (True, "ok", False))
        names = [c.name for c in install.verify_runtime(("claude",))]
        assert "sessions lost to a missing binary" in names


class TestACheckThatCouldNotRunIsNotACheckThatFailed:
    """The fourth state, and the one the other three could not say.

    `--check`'s legend defines `✗` as something the install needs being present and
    wrong, and `○` as something not written yet whose fix is `thalamus init`. A check
    whose prerequisite is missing is neither: the question was never asked. Both
    shapes were live. Without `jq`, two round trips printed `✗` beside the word
    "skipped". And on the ordinary machine that has Claude Code and not codex, the
    codex MCP item reported `○` forever under a closing line telling the operator to
    run a command that skips the registration and leaves the item exactly as it was.
    """

    def _absent(self, monkeypatch, *names):
        real = install.shutil.which
        monkeypatch.setattr(install.shutil, "which",
                            lambda b: None if b in names else real(b))

    def test_a_round_trip_without_jq_could_not_run_rather_than_failed(
            self, sandbox, monkeypatch):
        self._absent(monkeypatch, "jq")

        checks = {c.name: c for c in install.verify_cursor()}
        check = checks["cursor deferred injection round trip"]

        assert check.blocked and not check.ok
        assert "jq" in check.detail and "could not run" in check.detail
        # `?` and not `!`: an advisory is a finding that is true, and this is the
        # absence of one. A reader scanning marks should not need the closing
        # summary to tell "the graph is down" from "nobody looked".
        assert check.render().startswith("  ?")

    def test_a_blocked_check_does_not_fail_the_run(self, sandbox, monkeypatch):
        monkeypatch.setattr(install, "verify", lambda *a, **k: [
            install.Check("hook scripts present", True, "all found"),
            install.Check("codex delegation round trip", False,
                          "could not run: jq missing on this machine", blocked=True),
        ])

        assert install.run(check_only=True) == 0

    def test_the_codex_mcp_item_is_not_pending_on_a_box_without_codex(
            self, sandbox, monkeypatch):
        """`thalamus init` registers this through `codex mcp add`, so without the
        binary the command the pending text names cannot clear the item."""
        self._absent(monkeypatch, "codex")
        monkeypatch.setattr(install, "codex_mcp_registration", lambda: "")

        check = {c.name: c for c in install.verify_codex()}["codex MCP server registered"]

        assert check.blocked and not check.pending and not check.ok
        assert "codex" in check.detail and "could not run" in check.detail
        assert "thalamus init" not in check.detail
        assert check.render().startswith("  ?")

    def test_a_check_that_reads_a_file_is_not_blocked_by_a_missing_remedy(
            self, sandbox, monkeypatch):
        """`blocked` is for a check nobody could look at, not for one whose fix needs
        a missing program.

        `codex hooks trusted` reads the trust record out of `$CODEX_HOME/config.toml`
        whether or not the binary exists, so it has a real answer and the answer is a
        real finding. Granting it `blocked` because the remedy — a codex TUI prompt —
        is unreachable would make the word mean "inconvenient to fix", and there is
        then nothing left that means "unknown".
        """
        self._absent(monkeypatch, "codex")
        install.install()

        check = {c.name: c for c in install.verify_codex()}["codex hooks trusted"]

        assert not check.blocked
        assert check.advisory and not check.ok

    def test_a_missing_prerequisite_is_an_advisory_and_exits_zero(
            self, sandbox, monkeypatch):
        """`jq` and `uv` are other vendors' binaries, so a box without them is an
        environment finding and not a broken install.

        `--check` is what the getting-started page teaches as the step you run
        *before* installing. Exiting 1 on a box that is simply missing a prerequisite
        tells a reader following that sequence their install is broken, when what
        they have is a machine they have not finished setting up — the same reason a
        graph that is not up is `!` rather than `✗`.
        """
        self._absent(monkeypatch, "jq")

        checks = {c.name: c for c in install.verify()}
        check = checks["jq on PATH"]

        assert check.advisory and not check.ok
        assert check.render().startswith("  !"), check.render()
        # The severity moved; the finding did not. Without jq the hook layer dies on
        # the first event, and an advisory that did not say so would be a demotion of
        # the fact rather than of the exit code.
        assert "every hook will fail" in check.detail
        assert "install jq" in check.detail.lower(), "no command that fixes it"
        assert install.run(check_only=True) == 0

    def test_a_missing_prerequisite_is_a_finding_rather_than_unknown(
            self, sandbox, monkeypatch):
        """`!` and not `?`. The check ran `shutil.which` and got a real answer, so it
        has a finding; `blocked` is "nobody could look", never "the fix needs a
        program you do not have" — the line already drawn on `codex hooks trusted`
        and on the MCP registration items.
        """
        self._absent(monkeypatch, "jq", "uv")

        checks = {c.name: c for c in install.verify()}

        for name in ("jq on PATH", "uv on PATH"):
            assert not checks[name].blocked, f"{name} claims nobody looked"
            assert checks[name].advisory, name

    def test_the_entry_point_probe_is_blocked_rather_than_absent_without_uv(
            self, sandbox, monkeypatch):
        """It is the one check here that genuinely could not run, and it used to
        vanish instead of saying so.

        `probe_entry_point` spawns `uv run`, so without `uv` there is nothing to ask.
        Dropping the item left a shorter list in which every remaining line had
        passed, which reads as a cleaner box rather than a less-examined one.
        """
        self._absent(monkeypatch, "uv")

        checks = {c.name: c for c in install.verify()}

        assert "distillation entry point" in checks, "the check vanished with uv"
        check = checks["distillation entry point"]
        assert check.blocked and not check.ok
        assert check.render().startswith("  ?"), check.render()
        assert install.run(check_only=True) == 0

    def test_the_codex_mcp_item_is_still_pending_when_codex_is_installed(
            self, sandbox, monkeypatch):
        """The pending shape is right for the box that can actually clear it."""
        monkeypatch.setattr(install, "codex_mcp_registration", lambda: "")
        real = install.shutil.which
        monkeypatch.setattr(install.shutil, "which",
                            lambda b: "/usr/bin/codex" if b == "codex" else real(b))

        check = {c.name: c for c in install.verify_codex()}["codex MCP server registered"]

        assert check.pending and not check.blocked
        assert "thalamus init" in check.detail


class TestRuntimeAdvisories:
    """Install wires configuration; it does not own services or other vendors'
    binaries. Both gaps here are silent in the Xu et al. sense — an unreachable
    graph reads as "no memory yet", and a missing CLI surfaces as memory that
    quietly stopped accumulating, because distillation runs detached — so they
    are reported with the command that fixes them and never fail the install."""

    def test_an_unreachable_graph_is_advisory_and_says_how_to_start_it(self, monkeypatch):
        monkeypatch.setenv("THALAMUS_GRAPH_URL", "ws://localhost:9/gremlin")
        graph = [c for c in install.verify_runtime(("claude",)) if c.name == "graph reachable"][0]
        assert not graph.ok and graph.advisory
        assert "docker compose up -d" in graph.detail

    def test_a_graph_that_is_up_but_not_yet_serving_is_not_told_to_start(self, monkeypatch):
        """The third state the two-stage probe did not distinguish.

        Docker publishes 127.0.0.1:8182 the moment the container starts, and the JVM
        then takes 3.5-4s to reach `Channel started at port 8182` — plus the image
        pull on a genuinely first run. A user who runs step 4 promptly after step 2
        landed in that window and was told to start a container he could see running.
        """
        monkeypatch.setattr(
            install, "_probe_graph",
            lambda url: (False, "localhost:8182 accepted a connection but did not "
                                "answer (timed out)", False))

        graph = [c for c in install.verify_runtime(("claude",))
                 if c.name == "graph reachable"][0]

        assert not graph.ok and graph.advisory
        assert "docker compose up -d" not in graph.detail
        assert "docker compose ps" in graph.detail
        assert "a few seconds" in graph.detail

    def test_an_empty_graph_is_not_a_fault(self, monkeypatch):
        """Every install is fresh — the graph is one operator's private history and
        is never shipped, so zero vertices is the normal starting state."""
        monkeypatch.setattr(install, "_probe_graph",
                            lambda url: (True, "0 vertices at " + url + " (fresh)", False))
        graph = [c for c in install.verify_runtime(("claude",)) if c.name == "graph reachable"][0]
        assert graph.ok

    def test_a_missing_agent_cli_is_advisory_per_harness(self, monkeypatch):
        monkeypatch.setattr(install.shutil, "which", lambda b: None)
        monkeypatch.setattr(install, "_probe_graph", lambda url: (True, "ok", False))
        clis = [c for c in install.verify_runtime(("claude", "cursor"))
                if c.name.endswith("distillation CLI")]
        assert len(clis) == 2
        assert all(c.advisory and not c.ok for c in clis)
        assert any("`agent` not on PATH" in c.detail for c in clis)

    def test_advisories_do_not_fail_the_install(self, sandbox, monkeypatch):
        """A machine whose containers are not up yet is still a machine worth
        wiring; refusing would be the wrong end of the trade."""
        monkeypatch.setattr(install, "verify", lambda *a, **k: [
            install.Check("hook scripts present", True, "all found"),
            install.Check("graph reachable", False, "down", advisory=True),
        ])
        assert install.run(check_only=True) == 0

    def test_a_real_check_failure_still_fails(self, sandbox, monkeypatch):
        monkeypatch.setattr(install, "verify",
                            lambda *a, **k: [install.Check("hook scripts present", False, "gone")])
        assert install.run(check_only=True) == 1

    def test_the_graph_advisory_is_the_same_text_a_live_caller_gets(self):
        """One diagnosis for a down container, whether it is found by a deliberate
        probe here or by a recall that wanted to read (substrate/writer.connect)."""
        from thalamus.substrate.writer import graph_down_detail

        monkey_url = "ws://localhost:9/gremlin"
        _, probed, _ = install._probe_graph(monkey_url)
        assert graph_down_detail(probed).endswith("re-run `thalamus init --check`")
        assert "nothing listening on localhost:9" in graph_down_detail(probed)


# --------------------------------------------------------------------------------------
# The MCP env is per-process, and a changed env leaves live sessions stale.
# --------------------------------------------------------------------------------------


def _mcp_get_output(env_lines: str) -> str:
    return (
        "thalamus:\n"
        "  Scope: User config (available in all your projects)\n"
        "  Status: ✔ Connected\n"
        "  Type: stdio\n"
        "  Command: uv\n"
        "  Args: run --project /home/x/code/thalamus thalamus-mcp\n"
        "  Environment:\n"
        f"{env_lines}"
        "\nTo remove this server, run: claude mcp remove thalamus -s user\n"
    )


def test_the_registered_mcp_env_is_read_back_from_the_cli(monkeypatch):
    """
    Scenario: Read what env the *currently registered* server would launch with

    Verifications:
    - the Environment block is parsed into name/value pairs
    - the trailing prose after the block is not swallowed as an env var

    Read through `claude mcp get` rather than `~/.claude.json` for the same reason
    registration goes through `claude mcp add`: the CLI owns that file, and parsing
    a private schema we are told not to write is a dependency worth not taking.
    """
    import subprocess

    monkeypatch.setattr(install.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(
        install.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a[0], 0,
            stdout=_mcp_get_output(
                "    THALAMUS_GRAPH_URL=ws://localhost:8182/gremlin\n"
                "    THALAMUS_WITHHOLD=0.25\n"),
            stderr="",
        ),
    )

    assert install.registered_mcp_env() == {
        "THALAMUS_GRAPH_URL": "ws://localhost:8182/gremlin",
        "THALAMUS_WITHHOLD": "0.25",
    }


def test_an_unregistered_server_reports_no_env_rather_than_failing(monkeypatch):
    """
    Scenario: `thalamus init` runs on a box where the server was never registered,
    or where the `claude` CLI is not installed

    Both mean "nothing is running the old config", which is the same as no drift —
    so this must not be an error, and must not manufacture a relaunch warning on a
    first install.
    """
    monkeypatch.setattr(install.shutil, "which", lambda _: None)
    assert install.registered_mcp_env() == {}
    assert install.relaunch_checks(install.mcp_env_drift({}, {"A": "1"})) != []


def test_a_changed_withholding_rate_raises_a_relaunch_advisory():
    """
    Scenario: The MCP server is re-registered with a different THALAMUS_WITHHOLD

    Verifications:
    - the specific variable and both values are named, not just "something changed"
    - the finding is advisory: the install is correct, what is untrue is that
      anything is running it
    - the text says outright that open sessions keep the OLD config

    This is the failure that costs data rather than time. A withholding rate that
    moves while sessions are open produces records at two rates with the operator
    believing the campaign ran at one — and the pre-registered study needs the rate to
    be a property of the machine for the campaign's whole duration. Nothing about those
    sessions looks wrong from the inside, so the install is the only place it can
    be caught.
    """
    drift = install.mcp_env_drift(
        {"THALAMUS_GRAPH_URL": "ws://localhost:8182/gremlin", "THALAMUS_WITHHOLD": "0.25"},
        {"THALAMUS_GRAPH_URL": "ws://localhost:8182/gremlin", "THALAMUS_WITHHOLD": "0.5"},
    )
    assert drift == ["THALAMUS_WITHHOLD `0.25` -> `0.5`"]

    checks = install.relaunch_checks(drift)
    assert len(checks) == 1
    assert checks[0].advisory and not checks[0].ok
    assert "0.25" in checks[0].detail and "0.5" in checks[0].detail
    # Verifies: the operator is told the old config is still live, not just that
    # a relaunch is a good idea
    assert "OLD config" in checks[0].detail
    assert "`/clear` is not enough" in checks[0].detail


def test_an_unchanged_env_raises_nothing():
    """
    Scenario: A re-run of `thalamus init` with no env change

    The standing "arms per process" line already prints on every install. Repeating
    it as a finding when nothing moved is what made it stop being read in the first
    place, so an idempotent re-run must stay silent here.
    """
    env = {"THALAMUS_GRAPH_URL": "ws://localhost:8182/gremlin"}
    assert install.mcp_env_drift(env, dict(env)) == []
    assert install.relaunch_checks([]) == []


def test_dropping_a_variable_is_drift_too():
    """
    Scenario: The rate was set when the server was registered and is not exported
    in the shell running this install

    An unset is the easiest change to make by accident — a new terminal is enough —
    and it silently returns a withholding campaign to full recall.
    """
    drift = install.mcp_env_drift({"THALAMUS_WITHHOLD": "0.25"}, {})
    assert drift == ["THALAMUS_WITHHOLD unset (was `0.25`)"]


def test_a_declared_hook_missing_from_settings_is_a_finding():
    """
    Scenario: `room-guard.sh` is declared in HOOK_WIRING and absent from the
    settings file — the real state of this machine until 2026-08-11

    This is the defect that corrupted a measurement rather than an install.
    `eval/rooms.py` builds a room's realized edges exclusively from the rows
    `room-guard.sh` writes, so an unarmed guard made every real room report
    "TREATMENT DID NOT OCCUR" — the manipulation check answering a question about
    the hook's installation while appearing to answer one about the room.

    The existing checks could not catch it: the script was present and executable,
    which is what they ask. Present-and-runnable and actually-wired are different
    questions, and only the first was being asked.
    """
    hooks: dict[str, list] = {}
    for event, matcher, script in install.HOOK_WIRING:
        if script == "room-guard.sh":
            continue
        hooks.setdefault(event, []).append(
            {"matcher": matcher, "hooks": [{"command": f"/x/hooks/{script}"}]})
    settings = {"hooks": hooks}
    armed = install.armed_hooks(settings)
    declared = {(e, m, s) for e, m, s in install.HOOK_WIRING}

    assert ("PreToolUse", "SendMessage", "room-guard.sh") in declared - armed
    # Verifies: nothing else is reported missing, so the finding names the real
    # gap rather than drowning it in false positives from the matcher shapes
    assert declared - armed == {("PreToolUse", "SendMessage", "room-guard.sh")}


def test_armed_hooks_reads_the_script_out_of_a_full_command_line():
    """
    Scenario: settings.json holds the absolute path install actually writes

    The comparison is against `HOOK_WIRING`'s bare script names, so a wiring that
    is present would read as missing if the path were compared whole — which would
    make the check fire on every correctly-installed machine and get ignored.
    """
    settings = {"hooks": {"SessionEnd": [
        {"matcher": None, "hooks": [{"command": "/home/u/repo/hooks/session-end.sh"}]}
    ]}}
    assert install.armed_hooks(settings) == {("SessionEnd", None, "session-end.sh")}


class TestTheSuiteWritesOnlyInsideItsSandbox:
    """A test that reaches the operator's real config is a test that damages his box.

    Found the slow way: `CODEX_HOME` is resolved at import, and the fixture redirected
    the two paths *derived* from it while leaving the directory itself pointed at the
    real `~/.codex`. `install()` wrote derived codex profiles into it and `uninstall()`
    deleted them, so a suite run rewrote the operator's roster — 9 profiles from his
    private manifests replaced by the 5 tracked here — and nothing said so. It
    surfaced as a `thalamus init --check` line that disagreed with a directory listing
    a minute later.

    This asserts the containment directly, so the next constant that escapes the
    fixture fails here instead.
    """

    def test_install_and_uninstall_touch_nothing_under_the_real_home(self, sandbox,
                                                                     tmp_path):
        real = Path.home()
        redirected = [install.USER_SETTINGS, install.USER_AGENTS_DIR,
                      install.USER_SKILLS_DIR, install.USER_CURSOR_HOOKS,
                      install.USER_CURSOR_MCP, install.USER_CODEX_HOOKS,
                      install.USER_CODEX_MCP, install.CODEX_HOME]

        escaped = [str(p) for p in redirected
                   if p == real or real in Path(p).parents and tmp_path not in Path(p).parents]

        assert not escaped, (
            f"these write targets still resolve under the real home: {escaped}. "
            "A test that installs or uninstalls will edit the operator's own config.")

    def test_a_full_install_writes_the_codex_profiles_into_the_sandbox(self, sandbox):
        """The specific path that leaked: profiles are globbed off the directory."""
        install.install()

        written = sorted(sandbox["codex_home"].glob("thalamus-*.config.toml"))

        assert written, "no profiles written — the test would pass vacuously"
        assert all(str(sandbox["codex_home"]) in str(p) for p in written)

    def test_uninstall_removes_only_the_sandbox_profiles(self, sandbox):
        install.install()
        assert sorted(sandbox["codex_home"].glob("thalamus-*.config.toml"))

        install.uninstall()

        assert not sorted(sandbox["codex_home"].glob("thalamus-*.config.toml"))


class TestUninstall:
    """Taking it back out.

    An installer that writes into two editors' user-scope config, symlinks into
    a skills directory and registers an MCP server needs a way back out, or the
    only honest thing to tell someone trying it is "don't". The removal has the
    harder half of the problem though: it runs against a machine it did not
    install, so every step has to prove a thing is ours before deleting it.
    """

    def test_it_removes_the_hooks_it_wrote_and_leaves_the_operators_alone(
            self, sandbox, monkeypatch):
        mine = install.build_hook_block()
        theirs = {"matcher": None,
                  "hooks": [{"type": "command", "command": "/home/u/bin/my-own-hook.sh"}]}
        merged = {"hooks": {k: list(v) for k, v in mine.items()}}
        merged["hooks"].setdefault("SessionEnd", []).append(theirs)
        install._write_json(sandbox["user"], merged)

        install.uninstall()

        left = install._load_json(sandbox["user"])
        assert theirs in left["hooks"]["SessionEnd"]
        # `armed_hooks` reports every hook present, so the operator's own is
        # expected in the result — what must be empty is the intersection with
        # our own declared wiring.
        declared = {(e, m, s) for e, m, s in install.HOOK_WIRING}
        assert install.armed_hooks(left) & declared == set(), "a Thalamus hook survived"
        assert install.armed_hooks(left) == {("SessionEnd", None, "my-own-hook.sh")}

    def test_a_skill_link_is_removed_only_when_it_is_ours(self, sandbox):
        skills = sandbox["skills"]
        skills.mkdir(parents=True)
        shipped = install.shipped_skills()
        assert shipped, "fixture needs at least one shipped skill"
        (skills / shipped[0].name).symlink_to(shipped[0])
        handwritten = skills / "my-own-skill"
        handwritten.mkdir()
        (handwritten / "SKILL.md").write_text("---\nname: mine\n---\n")
        impostor = skills / "elsewhere"
        impostor.symlink_to(sandbox["user"].parent)

        install.uninstall()

        assert not (skills / shipped[0].name).exists()
        assert handwritten.is_dir(), "a hand-written skill was deleted"
        assert impostor.is_symlink(), "a symlink pointing outside the package was deleted"

    def test_a_link_whose_skill_no_longer_ships_is_still_ours(self, sandbox):
        """`README` promises uninstall removes only what it can prove it installed.

        The gap ran the other way: a link this installer wrote, whose skill was
        later renamed or dropped, resolved to a path in no shipped set — so it was
        neither removed by `--uninstall` nor seen by `--check`, and stayed in the
        user's skills directory for good. Identity is where the link points.
        """
        skills = sandbox["skills"]
        skills.mkdir(parents=True)
        stale = skills / "skill-that-was-renamed"
        stale.symlink_to(install.SKILL_DIR / "skill-that-was-renamed")

        actions = install.uninstall()

        assert not stale.is_symlink()
        assert any("skill-that-was-renamed" in a for a in actions)

    def test_install_prunes_a_link_whose_skill_no_longer_ships(self, sandbox):
        """And `thalamus init` is the command that clears it, so `--check` can
        report it as a hard failure rather than an advisory nothing acts on."""
        install.install()
        stale = sandbox["skills"] / "skill-that-was-renamed"
        stale.symlink_to(install.SKILL_DIR / "skill-that-was-renamed")

        actions = install.link_skills()

        assert not stale.is_symlink()
        assert any("no longer ships" in a for a in actions)
        assert {c.name: c for c in install.verify()}["skills load at user scope"].ok

    def test_a_dry_run_removes_nothing(self, sandbox):
        install._write_json(sandbox["user"], {"hooks": install.build_hook_block()})
        before = sandbox["user"].read_text()

        actions = install.uninstall(dry_run=True)

        assert sandbox["user"].read_text() == before
        assert any("would remove" in a for a in actions)

    def test_uninstalling_a_machine_that_never_installed_is_not_an_error(self, sandbox):
        actions = install.uninstall()
        assert actions and not any("FAILED" in a for a in actions)


class TestTheInstallMatrixCountsTheSameWiring:
    """`tests/qe/install/checks.py` hardcodes how many hook entries a healthy box
    carries, deliberately: it is an oracle run *against an installed machine* and
    must not import the package it is judging. The cost of that independence is a
    number that rots — adding a HOOK_WIRING entry reddens every cell of the install
    matrix with `N of our hook entries are wired, but HOOK_WIRING declares M`, a
    45-second-per-cell CI job reporting a stale constant as an install defect.

    Read out of the source text rather than imported, so this stays a consistency
    guard and does not make the oracle depend on the package by a back route.
    """

    def test_expected_hook_entries_matches_hook_wiring(self):
        source = (PROJECT_ROOT / "tests" / "qe" / "install" / "checks.py").read_text()
        match = re.search(r"^EXPECTED_HOOK_ENTRIES = (\d+)$", source, re.M)
        assert match, "checks.py no longer declares EXPECTED_HOOK_ENTRIES"

        assert int(match.group(1)) == len(install.HOOK_WIRING), (
            "tests/qe/install/checks.py:EXPECTED_HOOK_ENTRIES is stale — the install "
            "matrix will fail every cell until it is bumped to "
            f"{len(install.HOOK_WIRING)}"
        )
