"""
`thalamus init` — user-scope harness installation (docs/07).

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

import pytest

from thalamus.harness import install
from thalamus.harness.pin import PROJECT_ROOT


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
    monkeypatch.setattr(install, "write_all_agents", lambda d: d.mkdir(parents=True, exist_ok=True))
    # Never invoke the real `claude mcp add` from a test — it writes the
    # operator's shared ~/.claude.json.
    calls: list = []
    monkeypatch.setattr(install, "register_mcp",
                        lambda dry_run=False: calls.append(dry_run) or "mcp: stubbed")
    return {"user": user_settings, "project": project_settings,
            "project_mcp": project_mcp, "mcp_calls": calls, "skills": skills,
            "cursor_user": cursor_user_hooks, "cursor_user_mcp": cursor_user_mcp,
            "cursor_project": cursor_project_hooks,
            "cursor_project_mcp": cursor_project_mcp}


class TestCursorWiring:
    """Cursor parity (docs/07, lab/027). The contract that matters is that the
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
        tap — two writers would double-count every retrieval in `eval sync`."""
        block = install.build_cursor_hook_block()
        assert [e["command"].rsplit("/", 1)[1] for e in block["afterMCPExecution"]] == ["mcp-tap.sh"]
        assert [e["command"].rsplit("/", 1)[1]
                for e in block["afterShellExecution"]] == ["gremlin-tap.sh"]
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
        assert post == {"mcp__thalamus__.*", "Bash", "TaskCreate"}
        assert all("matcher" not in g for g in block["SessionEnd"])

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
        """Without stripping ours first, each run would append another copy."""
        install.install()
        install.install()
        install.install()
        settings = json.loads(sandbox["user"].read_text())
        commands = [h["command"] for g in settings["hooks"]["PostToolUse"] for h in g["hooks"]]
        assert len(commands) == len(set(commands))

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
        be a real spawn, so a broken uv project fails here and not at SessionEnd."""
        checks = {c.name: c for c in install.verify()}
        assert checks["distillation entry point"].ok
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

    def test_passes_once_the_skills_are_installed(self, sandbox):
        install.install()
        assert {c.name: c for c in install.verify()}["skills load at user scope"].ok

    def test_run_exits_nonzero_when_a_check_fails(self, sandbox, monkeypatch):
        monkeypatch.setattr(install, "verify",
                            lambda *a, **k: [install.Check("fake", False, "boom")])
        assert install.run(check_only=True) == 1
