"""
Pinned-session launcher tests: the derived agent definition and scope validation.

Interfaces: thalamus.harness.pin
Infrastructure: tmp_path manifests only — no tmux, no claude, no graph
Scope: the pure half of the launcher. Actually launching a pinned process is
verified live (docs/07, lab/003) — a launcher can only be tested by the process
it launches, which is exactly the lab/001 boundary.
"""

import json
import subprocess
from pathlib import Path

import pytest

from thalamus.contract.manifest import available_scopes, load_manifest
from thalamus.harness import pin
from thalamus.harness.pin import (
    agent_name,
    render_agent,
    resolve,
    resolve_pin,
    spawn,
    write_agent,
    write_all_agents,
)

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config"


def _argv_only(monkeypatch):
    """Launch far enough to inspect the argv, and no further.

    A launch ends by holding the window it made to its harness's settle deadline,
    which drives tmux for real — a `subprocess.run` faked to return empty output
    cannot answer it, and these tests are not asking. The confirmation is exercised
    against a live tmux server in tests/test_spawn_settle.py.
    """
    monkeypatch.setattr("thalamus.harness.pin.confirm_started", lambda *a, **kw: None)


def test_agent_definition_is_derived_from_the_manifest():
    """
    Scenario: Render the pinned-agent definition for a live manifest

    Verifications:
    - frontmatter name/description and the body all come from manifest fields
    - the file declares itself GENERATED, pointing back at the manifest
    - the body states server-side enforcement and consultation routing

    Zero-glue: the manifest is the whole federation surface; the agent file is a
    derived artifact and must never carry hand-written persona to drift.
    """
    manifest = load_manifest("literature", REPO_CONFIG)

    rendered = render_agent(manifest)

    assert f"name: {agent_name('literature')}" in rendered
    assert "GENERATED from config/experts/literature.yaml" in rendered
    assert manifest.name in rendered
    assert "enforced server-side" in rendered
    assert "consult_request" in rendered


def test_write_agent_lands_in_the_projects_agents_dir(tmp_path):
    manifest = load_manifest("eval-methodology", REPO_CONFIG)

    path = write_agent(manifest, tmp_path)

    assert path == tmp_path / ".claude" / "agents" / "thalamus-eval-methodology.md"
    assert path.read_text() == render_agent(manifest)


def test_write_all_agents_writes_every_expert_into_the_dir(tmp_path):
    """
    Scenario: `spawn` regenerates all derived agents into ~/.claude/agents so a
    session opened in another project can --agent-pin AND spawn sibling consultation
    subagents — both are loaded per process from the agents dir, wherever cwd is.
    """
    write_all_agents(tmp_path, REPO_CONFIG)

    for scope in available_scopes(REPO_CONFIG):
        f = tmp_path / f"{agent_name(scope)}.md"
        assert f.exists()
        assert f"scope `{scope}`" in f.read_text()


def test_spawn_rejects_a_nonexistent_directory(tmp_path, monkeypatch):
    """spawn's cwd becomes the window's working dir — a bad path must fail loudly
    before any tmux window is created, not silently open somewhere wrong."""
    monkeypatch.setattr("thalamus.harness.pin.shutil.which", lambda _: "/usr/bin/tmux")

    with pytest.raises(ValueError, match="not a directory"):
        spawn("literature", tmp_path / "does-not-exist", base=REPO_CONFIG)


def test_spawn_into_an_absent_session_leaves_no_shell_placeholder(tmp_path, monkeypatch):
    """
    Scenario: spawn is the first thing to touch tmux after a reboot, so it has to
    create the session itself. It must create it *with* the scope's window — a bare
    `new-session` leaves a shell at index 0, and the plane reads the lowest index as
    the anchor: un-closable, the reference cwd for roster sync, and a `restart` on it
    types `/exit` into a shell and hangs the recycle for its whole grace budget.
    """
    calls: list[list[str]] = []

    def fake_run(cmd, *a, **kw):
        calls.append(cmd)
        # has-session: report "no such session" so spawn takes the create path.
        rc = 1 if "has-session" in cmd else 0
        return subprocess.CompletedProcess(cmd, rc, stdout="", stderr="")

    monkeypatch.setattr("thalamus.harness.pin.shutil.which", lambda _: "/usr/bin/tmux")
    monkeypatch.setattr("thalamus.harness.pin.write_all_agents", lambda *a, **kw: None)
    monkeypatch.setattr("thalamus.harness.pin.subprocess.run", fake_run)
    _argv_only(monkeypatch)

    spawn("literature", tmp_path, base=REPO_CONFIG)

    created = [c for c in calls if "new-session" in c]
    assert len(created) == 1, "the session should be created exactly once"
    argv = created[0]
    assert argv[argv.index("-n") + 1] == "literature", "first window must be the scope's"
    assert "claude" in argv, "the first window must run claude, not a bare shell"
    assert "THALAMUS_SCOPE=literature" in argv, "the anchor must be armed for its scope"
    # A second window beside the placeholder is exactly the bug — the create path
    # already opened the window, so nothing should call new-window.
    assert not [c for c in calls if "new-window" in c]


def test_main_is_pinnable_without_a_manifest_and_unknown_scopes_are_not():
    """
    Scenario: Pin `main` (no manifest by design) and a scope nobody declared

    An unknown scope must fail with the available roster named — the same failure
    shape as every other manifest consumer.
    """
    assert resolve("main", REPO_CONFIG) is None

    with pytest.raises(FileNotFoundError, match="Available:.*literature"):
        resolve("nonexistent-expert", REPO_CONFIG)


def _tooled_config(tmp_path, url="http://127.0.0.1:8787/mcp"):
    """A config root where `designer` declares a server and `qe` declares none."""
    experts = tmp_path / "experts"
    experts.mkdir(exist_ok=True)
    for scope in ("designer", "qe"):
        (experts / f"{scope}.yaml").write_text(f"scope: {scope}\nname: {scope.title()}\n")
    mcp = tmp_path / "mcp"
    mcp.mkdir(exist_ok=True)
    (mcp / "designer.json").write_text(
        json.dumps({"mcpServers": {"penpot": {"type": "http", "url": url}}})
    )
    return tmp_path


def agent_frontmatter(text: str) -> dict:
    """Parse the generated agent file's frontmatter the way Claude Code will."""
    import yaml

    assert text.startswith("---\n")
    return yaml.safe_load(text.split("---\n", 2)[1])


def test_only_a_scope_with_its_own_mcp_file_pays_for_extra_tools(tmp_path):
    """
    Scenario: `designer` works through a 68-tool Penpot server; nobody else should

    A tool surface carried in `.mcp.json` arms in every session in the project, so
    one scope's tooling becomes the whole roster's context tax. The per-scope file
    keeps it where it is used, and the declaration is additive — the house
    `thalamus` server survives alongside it.
    """
    from thalamus.harness.pin import scope_mcp_config, scope_mcp_servers

    base = _tooled_config(tmp_path)

    assert scope_mcp_config("designer", base) == base / "mcp" / "designer.json"
    assert scope_mcp_config("qe", base) is None
    assert scope_mcp_config("main", base) is None

    assert set(scope_mcp_servers("designer", base)) == {"penpot"}
    assert scope_mcp_servers("qe", base) == {}
    assert scope_mcp_servers("main", base) == {}

    qe = render_agent(load_manifest("qe", base), scope_mcp_servers("qe", base))
    assert "mcpServers" not in qe, "a scope that declares nothing must arm nothing"


def test_the_arming_travels_with_the_agent_not_with_one_launchers_argv(tmp_path):
    """
    Scenario: `claude --agent thalamus-designer` typed by hand — no launcher, no flags

    THE defect this guards. A scope's MCP servers used to be a `--mcp-config` flag on
    `_session_argv`, which is one launch route out of several: the agent picker,
    FleetView, `thalamus spawn` and a bare shell all reach `--agent` without passing
    through it. Every one of those produced a session whose system prompt asserts it
    is a visual designer working in a design tool, in a process with no design tool
    and no way to notice.

    So the servers must be ON the agent definition, in the schema Claude Code reads:
    a `mcpServers` list whose entries are single-key maps of server name to the same
    config `.mcp.json` uses. Verified live against Claude Code 2.1.228 — `--agent
    thalamus-designer` alone reports `penpot` connected with 68 tools, and both `qe`
    and an unpinned session report zero.
    """
    from thalamus.harness.pin import _session_argv, scope_mcp_servers

    base = _tooled_config(tmp_path)

    front = agent_frontmatter(
        render_agent(load_manifest("designer", base), scope_mcp_servers("designer", base))
    )
    assert front["mcpServers"] == [
        {"penpot": {"type": "http", "url": "http://127.0.0.1:8787/mcp"}}
    ], "the documented schema is a LIST of single-key maps, not a mapping"

    # The flag is gone, and its absence is the point: nothing may depend on it.
    argv = _session_argv("designer", tmp_path / "proj", base=base)
    assert "--mcp-config" not in argv
    assert argv[:3] == ["claude", "--agent", "thalamus-designer"]

    # ...because the file the launcher just regenerated carries the servers instead.
    written = (tmp_path / "proj" / ".claude" / "agents" / "thalamus-designer.md").read_text()
    assert agent_frontmatter(written)["mcpServers"] == front["mcpServers"]


def test_spawn_arms_the_scopes_servers_too(tmp_path, monkeypatch):
    """
    Scenario: the console's spawn button — how room members are made from a phone

    `spawn` builds its own argv and never carried the MCP flag at all, so this route
    was mis-arming `designer` even when the roster was not. It writes agent files to
    the user agents dir; with the arming on the definition, writing them IS arming
    them, and the route cannot diverge from the roster's again.
    """
    from thalamus.harness.pin import write_all_agents

    base = _tooled_config(tmp_path)
    agents = tmp_path / "user-agents"

    write_all_agents(agents, base)

    designer = agent_frontmatter((agents / "thalamus-designer.md").read_text())
    assert designer["mcpServers"] == [
        {"penpot": {"type": "http", "url": "http://127.0.0.1:8787/mcp"}}
    ]
    assert "mcpServers" not in agent_frontmatter((agents / "thalamus-qe.md").read_text())


def test_a_tooled_agent_tells_its_session_what_to_do_when_the_tools_are_absent(tmp_path):
    """
    Scenario: the declaration is right, and the server behind it is down anyway

    Frontmatter closes the launch routes; it cannot close the server. A dead endpoint
    or a policy that skipped it lands in the same place — a prompt asserting a
    capability the process lacks — so the generated agent carries its own check,
    naming the tool prefix concretely and requiring stop-and-report rather than
    working around the gap.
    """
    from thalamus.harness.pin import scope_mcp_servers

    base = _tooled_config(tmp_path)
    body = render_agent(load_manifest("designer", base), scope_mcp_servers("designer", base))

    assert "mcp__penpot__*" in body, "a session cannot act on 'check your tools'"
    assert "mis-armed" in body
    assert "thalamus pin designer" in body, "the remedy must be in the same artifact"

    plain = render_agent(load_manifest("qe", base), scope_mcp_servers("qe", base))
    assert "mis-armed" not in plain, "a scope with no tooling gets no warning to ignore"


def test_an_unreadable_mcp_declaration_fails_the_launch_instead_of_arming_nothing(tmp_path):
    """
    Scenario: `config/mcp/<scope>.json` is malformed, or has the key spelled wrong

    Resolving that to "no extra tools" reproduces the whole defect quietly, at the one
    moment the operator is watching. It must raise.
    """
    from thalamus.harness.pin import scope_mcp_servers

    base = _tooled_config(tmp_path)
    mcp_file = base / "mcp" / "designer.json"

    mcp_file.write_text("{not json")
    with pytest.raises(ValueError, match="unreadable MCP config"):
        scope_mcp_servers("designer", base)

    mcp_file.write_text('{"mcp_servers": {"penpot": {}}}')  # snake_case typo
    with pytest.raises(ValueError, match="declares no `mcpServers`"):
        scope_mcp_servers("designer", base)


def test_the_shipped_designer_scope_is_the_only_one_carrying_a_tool_surface():
    """The repo's own config, so a second scope acquiring 68 tools is a decision
    someone has to make deliberately rather than a file that quietly appeared."""
    from thalamus.contract.manifest import available_scopes
    from thalamus.harness.pin import scope_mcp_config

    carrying = [s for s in available_scopes(REPO_CONFIG) if scope_mcp_config(s, REPO_CONFIG)]
    assert carrying == ["designer"]


def test_resolve_pin_prefers_the_picked_agent_over_the_env_scope():
    """
    Scenario: The agent picker launched `claude --agent thalamus-literature` from a
    shell whose env still said THALAMUS_SCOPE=main (measured 2026-07-18: all
    three roster expert sessions were mis-armed exactly this way)

    The picked agent is operator intent and must win; the env is residue.
    """
    env = {"CLAUDE_CODE_AGENT": "thalamus-literature", "THALAMUS_SCOPE": "main"}

    assert resolve_pin(env, REPO_CONFIG) == "literature"


def test_resolve_pin_falls_back_to_env_then_main():
    """
    Scenario: No agent picked (roster main window / plain terminal), or the
    agent name doesn't map to a real manifest (never widen a pin on a typo)
    """
    assert resolve_pin({"THALAMUS_SCOPE": "literature"}, REPO_CONFIG) == "literature"
    assert resolve_pin({}, REPO_CONFIG) == "main"
    assert resolve_pin(
        {"CLAUDE_CODE_AGENT": "thalamus-nonexistent", "THALAMUS_SCOPE": "main"},
        REPO_CONFIG,
    ) == "main"
    # non-thalamus agents (e.g. Explore) never touch the pin
    assert resolve_pin(
        {"CLAUDE_CODE_AGENT": "Explore", "THALAMUS_SCOPE": "eval-methodology"},
        REPO_CONFIG,
    ) == "eval-methodology"


def test_a_room_rides_the_argv_so_it_survives_a_recycle(tmp_path, monkeypatch):
    """
    Scenario: a member window is opened while THALAMUS_ROOM is set

    Verifications:
    - the room reaches the process through BOTH channels: tmux `-e` and an `env`
      prefix on the window's own argv
    - CLAUDE_CONFIG_DIR points at the room's config dir, which IS the boundary
    - the member is named `<room>-<scope>`, the address the guard admits
    - outside a room the argv *unsets* both variables rather than staying silent

    The argv prefix is the load-bearing one. `-e` on `new-window` sets only the
    initial process environment — tmux does not store it in the session env — so
    `respawn-window`, which is what the console's recycle button runs,
    re-executes this argv with those variables gone (measured, tmux 3.4). The pin
    survives a recycle because `--agent thalamus-<scope>` rides the argv;
    `resolve_room` is env-only by design and would otherwise have no second
    channel, so a recycled member would drop back onto ~/.claude while still
    looking like a member.
    """
    calls: list[list[str]] = []

    def fake_run(cmd, *a, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1 if "has-session" in cmd else 0, stdout="", stderr="")

    monkeypatch.setattr("thalamus.harness.pin.shutil.which", lambda _: "/usr/bin/tmux")
    monkeypatch.setattr("thalamus.harness.pin.write_all_agents", lambda *a, **kw: None)
    monkeypatch.setattr("thalamus.harness.pin.subprocess.run", fake_run)
    monkeypatch.setattr("thalamus.harness.pin.ensure_room",
                        lambda room, host=None, harness="claude": None)
    _argv_only(monkeypatch)
    monkeypatch.setenv("THALAMUS_ROOM", "alpha")

    spawn("literature", tmp_path, base=REPO_CONFIG)

    created = [c for c in calls if "new-session" in c][0]
    room_dir = str(pin.room_config_dir("alpha"))

    # Verifies: the tmux env channel
    assert "THALAMUS_ROOM=alpha" in created
    assert f"CLAUDE_CONFIG_DIR={room_dir}" in created

    # Verifies: the durable argv channel, ahead of the command it wraps
    after = created[created.index("--") + 1:]
    assert after[0] == "env"
    assert f"CLAUDE_CONFIG_DIR={room_dir}" in after[: after.index("claude")]
    assert "THALAMUS_ROOM=alpha" in after[: after.index("claude")]

    # Verifies: the member carries the name the guard's roommate pattern admits
    assert after[after.index("--name") + 1] == "alpha-literature"

    # Verifies: outside a room the argv says so, rather than saying nothing.
    # `new-session -e` stores its variables in the tmux SESSION environment (unlike
    # `new-window -e`), so a session created for a room hands them to every later
    # window; silence would let a roomless spawn inherit the room's config dir and
    # join its roster invisibly. `-u`, not `CLAUDE_CONFIG_DIR=$HOME/.claude`:
    # naming the default is not a no-op, it moves `.claude.json` to an empty file.
    calls.clear()
    monkeypatch.delenv("THALAMUS_ROOM")
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    spawn("literature", tmp_path, base=REPO_CONFIG)
    plain = [c for c in calls if "new-session" in c][0]
    after = plain[plain.index("--") + 1:]
    assert after[: after.index("claude")] == ["env", "-u", "THALAMUS_ROOM",
                                              "-u", "CLAUDE_CONFIG_DIR"]
    assert "--name" not in after
    assert not [a for a in plain if a.startswith("CLAUDE_CONFIG_DIR=")]


def test_a_deliberate_config_dir_override_survives_a_roomless_launch(tmp_path, monkeypatch):
    """
    Scenario: the operator runs with their own CLAUDE_CONFIG_DIR, and spawns outside a room

    Verifications:
    - the override is passed through, not unset

    Clearing the room must not clear an operator's own config tree. The variable is
    only stripped when it is unset or points into ROOMS_DIR — the leak this guards
    against is a room's dir arriving where no room was asked for, not a config dir
    the operator chose.
    """
    calls: list[list[str]] = []
    monkeypatch.setattr("thalamus.harness.pin.shutil.which", lambda _: "/usr/bin/tmux")
    monkeypatch.setattr("thalamus.harness.pin.write_all_agents", lambda *a, **kw: None)
    monkeypatch.setattr("thalamus.harness.pin.subprocess.run",
                        lambda cmd, *a, **kw: (calls.append(cmd), subprocess.CompletedProcess(
                            cmd, 1 if "has-session" in cmd else 0, stdout="", stderr=""))[1])
    _argv_only(monkeypatch)
    monkeypatch.delenv("THALAMUS_ROOM", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/home/someone/.config/claude")

    spawn("literature", tmp_path, base=REPO_CONFIG)

    after = [c for c in calls if "new-session" in c][0]
    after = after[after.index("--") + 1:]
    assert "CLAUDE_CONFIG_DIR=/home/someone/.config/claude" in after[: after.index("claude")]
    assert "-u" in after[: after.index("claude")]  # THALAMUS_ROOM still cleared


def _host(tmp_path: Path) -> Path:
    """A stand-in for the operator's own ~/.claude, with the entries a room borrows."""
    host = tmp_path / "host-claude"
    (host / "skills").mkdir(parents=True)
    (host / "agents").mkdir()
    (host / "plugins").mkdir()
    (host / ".credentials.json").write_text('{"token": "x"}')
    (host / "settings.json").write_text('{"hooks": {}}')
    (host / "settings.local.json").write_text('{"permissions": {}}')
    return host


def test_ensure_room_builds_the_measured_layout(tmp_path, monkeypatch):
    """
    Scenario: a room is entered for the first time

    Verifications:
    - the trees a room must own are real directories, not links
    - the trees it borrows are symlinks onto the operator's own
    - a host entry that does not exist produces no dangling link
    - `.claude.json` is a copy, and carries the operator's mcpServers
    - `settings.local.json` is the room's OWN file, seeded with the allowlist

    The own/borrow split is the whole design (lab/046): `projects/` shared is a
    transcript channel out of the room, while `settings.json` NOT shared is a
    member with zero Thalamus hooks — each side of the split fails a different way.

    `settings.local.json` sits on the owned side for a third reason (docs/12): a
    room's permission surface has to be declared for the room, not inherited from
    whatever the operator's own session accumulated — and borrowing it would let the
    room's policy move underneath it whenever the operator accepted a prompt
    somewhere else entirely.
    """
    monkeypatch.setattr(pin, "ROOMS_DIR", tmp_path / "rooms")
    host = _host(tmp_path)
    (host.parent / ".claude.json").write_text('{"mcpServers": {"thalamus": {"cmd": "x"}}}')
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: host.parent))

    config = pin.ensure_room("alpha", host=host)

    for owned in pin.ROOM_OWNED:
        assert (config / owned).is_dir() and not (config / owned).is_symlink(), owned
    for linked in ("skills", "agents", "plugins", "settings.json",
                   ".credentials.json"):
        assert (config / linked).is_symlink(), linked
        assert (config / linked).readlink() == host / linked
    assert not (config / "commands").exists()  # the host has none — no dead link

    policy = config / "settings.local.json"
    assert policy.is_file() and not policy.is_symlink()
    assert json.loads(policy.read_text())["permissions"]["allow"] == list(pin.ROOM_ALLOWLIST)

    copied = config / ".claude.json"
    assert copied.is_file() and not copied.is_symlink()
    assert json.loads(copied.read_text())["mcpServers"] == {"thalamus": {"cmd": "x"}}


def test_a_tuned_room_allowlist_survives_the_next_launch(tmp_path, monkeypatch):
    """
    Scenario: an operator widens a room's allowlist, and the room is launched again.

    Verification: the edit survives. `ensure_room` runs on every launch and
    idempotently repairs everything else, because drift there is corruption — but
    this is the one file an operator is *expected* to edit, since widening the
    allowlist is how a room gets work done. Rewriting it on the next launch would
    silently revert that, and the revert would show up as a member stopping at a
    prompt, which reads as a dispatch that never arrived.
    """
    monkeypatch.setattr(pin, "ROOMS_DIR", tmp_path / "rooms")
    host = _host(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: host.parent))

    config = pin.ensure_room("alpha", host=host)
    policy = config / "settings.local.json"
    policy.write_text(json.dumps({"permissions": {"allow": ["Bash(make:*)"]}}))

    pin.ensure_room("alpha", host=host)

    assert json.loads(policy.read_text())["permissions"]["allow"] == ["Bash(make:*)"]


def test_every_pinned_session_launches_in_auto_and_only_a_room_gets_a_name(tmp_path,
                                                                          monkeypatch):
    """
    Scenario: the same scope launched into a room, and outside one.

    Verifications:
    - both carry `--permission-mode auto` — the operator drives every session in that
      mode by hand, so a launcher starting them stricter made them behave unlike the
      sessions they were modelled on
    - only the room member carries `--name`, which is the address SendMessage routes
      on and the prefix room-guard.sh matches; a solo session has nothing to answer to
    - the mode is not `bypassPermissions`

    That last one is the substantive half. `auto` still resolves allow/deny rules and
    PreToolUse hooks before anything else, which is what keeps the room guard and the
    role guard standing; bypass is the mode that removes the control FIDES measured as
    the one that stops prompt injection outright.
    """
    monkeypatch.setattr(pin, "ROOMS_DIR", tmp_path / "rooms")

    from thalamus.harness.launcher import PERMISSION_MODE, launch_argv

    assert launch_argv("claude", "qe", persona="thalamus-qe") == [
        "claude", "--agent", "thalamus-qe", "--permission-mode", "auto",
    ]
    assert pin.launch_flags("", "qe") == []
    assert pin.launch_flags("alpha", "qe") == ["--name", "alpha-qe"]
    assert PERMISSION_MODE != "bypassPermissions"


def test_the_room_allowlist_reaches_neither_the_network_nor_history(tmp_path):
    """
    Verification: the seed allows no network fetch and no history rewrite.

    Not a style preference. Transcript-mediated laundering is closed for
    WebFetch/WebSearch while Bash curl remains a residual channel, so a room — which
    exists to let several differently-pinned experts write into one memory — is the
    last place to widen it. `git commit`/`push` are out for a separate reason: a room
    member's commit is a decision the operator should see happen.
    """
    seed = " ".join(pin.ROOM_ALLOWLIST)
    for forbidden in ("curl", "wget", "nc ", "ssh", "git commit", "git push", "rm "):
        assert forbidden not in seed, forbidden
    # And it is a real allowlist rather than a wildcard wearing one's clothes.
    assert "Bash(:*)" not in seed and "Bash(*)" not in seed


def test_ensure_room_replaces_a_symlinked_projects_dir(tmp_path, monkeypatch):
    """
    Scenario: a room dir built under the withdrawn lab/045 shape, where `projects/`
              was symlinked back to the real config dir

    Verifications:
    - the link is replaced by a directory the room owns
    - the operator's own transcripts are untouched

    This is the repair that closes the third channel. `claude --resume` consults
    neither the discovery roster nor the send path — it reads transcripts off disk,
    so while that link stands, any non-member can fork a member's session and read
    its context verbatim (measured in both directions, lab/046).
    """
    monkeypatch.setattr(pin, "ROOMS_DIR", tmp_path / "rooms")
    host = _host(tmp_path)
    real_projects = host / "projects"
    real_projects.mkdir()
    (real_projects / "keep.jsonl").write_text("the operator's own transcript")

    config = pin.room_config_dir("alpha")
    config.mkdir(parents=True)
    (config / "projects").symlink_to(real_projects)

    pin.ensure_room("alpha", host=host)

    assert (config / "projects").is_dir() and not (config / "projects").is_symlink()
    assert not any((config / "projects").iterdir())
    assert (real_projects / "keep.jsonl").exists()  # unlinking a link is not a delete


def test_ensure_room_refreshes_mcp_servers_without_resetting_the_member(tmp_path, monkeypatch):
    """
    Scenario: the operator adds an MCP server after a room already exists

    Verifications:
    - the new server reaches the room's copied .claude.json
    - the member's own state in that file survives

    A copy taken once goes stale silently: the member keeps starting fine and
    simply has no memory tools. Only mcpServers is carried over, because the rest
    of the file is the member's state and overwriting it resets the room.
    """
    monkeypatch.setattr(pin, "ROOMS_DIR", tmp_path / "rooms")
    host = _host(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: host.parent))
    source = host.parent / ".claude.json"
    source.write_text('{"mcpServers": {"thalamus": {"cmd": "x"}}}')
    pin.ensure_room("alpha", host=host)

    copied = pin.room_config_dir("alpha") / ".claude.json"
    copied.write_text(json.dumps({"mcpServers": {}, "hasTrustDialogAccepted": True,
                                  "projects": {"/room/work": {}}}))
    source.write_text('{"mcpServers": {"thalamus": {"cmd": "x"}, "other": {"cmd": "y"}}}')

    pin.ensure_room("alpha", host=host)

    after = json.loads(copied.read_text())
    assert set(after["mcpServers"]) == {"thalamus", "other"}
    assert after["hasTrustDialogAccepted"] is True
    assert after["projects"] == {"/room/work": {}}


@pytest.mark.parametrize("name", ["../escape", "a/b", "Alpha.", "", "-lead", "a b", "x|y"])
def test_ensure_room_refuses_a_name_that_is_not_a_room(name, tmp_path, monkeypatch):
    """
    Scenario: a room name carrying a path or regex metacharacter

    Verifications:
    - it is refused before any directory is made

    The name is three things at once: a path segment under ROOMS_DIR, a session-name
    prefix, and an interpolation into room-guard.sh's roommate pattern. A name with
    a metacharacter would rewrite the boundary it is meant to be checked against.
    """
    monkeypatch.setattr(pin, "ROOMS_DIR", tmp_path / "rooms")
    with pytest.raises(ValueError):
        pin.ensure_room(name, host=_host(tmp_path))


def test_ensure_room_refuses_without_credentials(tmp_path, monkeypatch):
    """
    Scenario: a room is entered on a box that has never run `claude /login`

    Verifications:
    - the launcher refuses, naming the missing file

    A member gets its own config dir, so it cannot reach a login that is not there:
    without the token it starts, reports "Not logged in" and exits in well under a
    second — which, watched from a phone, reads as nothing happening at all.
    """
    monkeypatch.setattr(pin, "ROOMS_DIR", tmp_path / "rooms")
    host = _host(tmp_path)
    (host / ".credentials.json").unlink()
    with pytest.raises(RuntimeError, match="credentials"):
        pin.ensure_room("alpha", host=host)


def test_rooms_lists_what_is_on_disk(tmp_path, monkeypatch):
    """
    Scenario: two rooms exist, plus a stray file and an invalid directory name

    Verifications:
    - both rooms are listed, and nothing else is

    Read off the filesystem rather than a registry, for the same reason the pin is
    read off the process: a room exists exactly when its config dir does, and a
    separate list could disagree with that.
    """
    rooms = tmp_path / "rooms"
    monkeypatch.setattr(pin, "ROOMS_DIR", rooms)
    assert pin.rooms() == []
    for name in ("alpha", "beta", "Not A Room"):
        (rooms / name).mkdir(parents=True)
    (rooms / "loose.txt").write_text("x")
    assert sorted(pin.rooms()) == ["alpha", "beta"]


def test_the_ledger_answers_what_room_a_session_was_launched_into(tmp_path):
    """
    Scenario: A session is re-extracted later, from a shell that was never in its room

    Verifications:
    - the room is recovered from the launch row, not from the current environment
    - lifecycle rows are skipped rather than read as "no room"
    - the newest launch row wins, so a recycled window's later row is the answer
    - a session with no row at all returns nothing, rather than borrowing another's

    `resolve_room` is env-only and correct inside the session; afterwards the variable
    is gone. Reading the environment then stamps `room=""` on a member, and
    `witnesses.py` counts that room's correlated writes as independent corroboration —
    the failure that invents evidence rather than losing it.
    """
    ledger = tmp_path / "pins.jsonl"
    ledger.write_text("\n".join([
        json.dumps({"session_id": "s1", "scope": "main", "room": "alpha", "ts": "1"}),
        # pin-engaged.sh appends this shape: no room, no fork parent.
        json.dumps({"session_id": "s1", "scope": "main", "event": "engaged", "ts": "2"}),
        json.dumps({"session_id": "s2", "scope": "qe", "room": "", "ts": "3"}),
        json.dumps({"session_id": "s3", "scope": "main", "forked_from": "s1", "ts": "4"}),
        "not json at all",
    ]) + "\n")

    assert pin.ledger_facts("s1", ledger)["room"] == "alpha"
    assert pin.ledger_facts("s2", ledger) == {}
    assert pin.ledger_facts("s3", ledger)["forked_from"] == "s1"
    assert pin.ledger_facts("never-launched", ledger) == {}

    # Verifies: a later launch row for the same session supersedes the earlier one
    with ledger.open("a") as handle:
        handle.write(json.dumps({"session_id": "s1", "room": "beta", "ts": "5"}) + "\n")
    assert pin.ledger_facts("s1", ledger)["room"] == "beta"


def test_a_missing_ledger_is_not_an_error(tmp_path):
    """A box that never launched a pinned session has no ledger, and re-extraction
    there is ordinary rather than broken."""
    assert pin.ledger_facts("s1", tmp_path / "absent.jsonl") == {}
