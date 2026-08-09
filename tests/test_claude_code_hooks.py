"""
Claude Code session-start hook tests (docs/07 harness integration; lab/012-013).

Interfaces: src/thalamus/harness/hooks/claude-code/session-start.sh, driven
live (bash) with synthetic stdin payloads shaped per Claude Code's hook
contract.
Infrastructure: tmp_path as $HOME so the pin ledger is sandboxed; no live
graph, no MCP server.
Scope: the *injected instruction* is the contract under test here — it is the
only channel by which a session learns the memory surface exists, and two
counterfactual campaigns were voided by it being wrong (lab/012: the project it
names; lab/013: the calling convention it omitted). Pin-ledger writes are
covered because session-end and eval both read them. The Cursor variant's
mirror of these checks lives in test_cursor_hooks.py.
"""

import json
import subprocess
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks" / "claude-code"


def run_hook(payload, home, env=None):
    full_env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(HOOKS / "session-start.sh")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
        timeout=30,
    )


def context_of(result):
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def session_start_payload(**overrides):
    payload = {
        "session_id": "cc-sess-1",
        "cwd": "/home/user/code/myproject",
        "hook_event_name": "SessionStart",
        "source": "startup",
    }
    payload.update(overrides)
    return payload


class TestInjectedInstruction:
    def test_names_the_deferred_tool_step_before_the_tools(self, tmp_path):
        """
        Scenario: a normal session starts.

        Verification: the injected text tells the agent how to *reach* the
        tools, not just to call them. lab/013 measured both memory-on arms of
        a campaign making zero thalamus calls with the server reachable and
        all tools registered — the instruction named tools whose schemas were
        deferred, so it could not be followed as written. The ToolSearch step
        must appear, must name both tools the instruction goes on to use, and
        must come before the first call instruction.
        """
        ctx = context_of(run_hook(session_start_payload(), tmp_path))
        assert "ToolSearch" in ctx
        assert (
            "select:mcp__thalamus__memory_open_threads,"
            "mcp__thalamus__memory_recall_by_project" in ctx
        )
        assert ctx.index("ToolSearch") < ctx.index("At the start of this session")

    def test_project_comes_from_cwd_by_default(self, tmp_path):
        ctx = context_of(run_hook(session_start_payload(), tmp_path))
        assert 'project="myproject"' in ctx

    def test_thalamus_project_overrides_the_cwd_guess(self, tmp_path):
        """
        Scenario: an eval arm's headless session, whose cwd is a disposable
        worktree named <task-id>--<arm>--<timestamp>.

        Verification: the injected project is the repo's real name, not the
        worktree's. basename(cwd) here is a string no session has ever
        distilled under, so recall scoped to it silently returns nothing —
        the bug that made two campaigns' memory-on arms inert (lab/012).
        """
        result = run_hook(
            session_start_payload(cwd="/tmp/wt/reader-recall--memory-on--20260726T000000Z"),
            tmp_path,
            env={"THALAMUS_PROJECT": "thalamus"},
        )
        ctx = context_of(result)
        assert 'project="thalamus"' in ctx
        assert "memory-on--" not in ctx

    def test_pinned_scope_leads_the_context_and_lands_in_the_ledger(self, tmp_path):
        result = run_hook(
            session_start_payload(),
            tmp_path,
            env={"THALAMUS_SCOPE": "literature"},
        )
        assert context_of(result).startswith("This session is pinned to expert scope `literature`")
        pins = [
            json.loads(line)
            for line in (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert pins[0]["scope"] == "literature"
        assert pins[0]["session_id"] == "cc-sess-1"

    def test_resume_is_not_primed_but_is_still_recorded(self, tmp_path):
        """
        Scenario: a resumed or forked session starts

        Verifications:
        - it is not primed — resume/compact already carry their context
        - its pin row IS written, with room and fork parent

        These are two concerns, and one early return used to serve both. A fork
        (`--resume <id> --fork-session`) arrives as `source=resume`, so gating the
        ledger on `startup` meant the launcher's `room` and `forked_from` were
        dropped for exactly the sessions those fields exist to describe — a fork's
        agreement with its parent is inheritance, not corroboration (lab/043).
        session-end.sh resolves ledger-first precisely so a later re-extraction
        from a plain shell lands the same way, so an env var that happens to
        survive to session end does not make the row optional.
        """
        result = run_hook(
            session_start_payload(source="resume"),
            tmp_path,
            env={"THALAMUS_ROOM": "alpha", "THALAMUS_FORKED_FROM": "parent-sess-9"},
        )

        # Verifies: still not primed
        assert json.loads(result.stdout) == {}

        # Verifies: recorded anyway, with the launch facts nothing else can recover
        pins = [
            json.loads(line)
            for line in (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert len(pins) == 1
        assert pins[0]["session_id"] == "cc-sess-1"
        assert pins[0]["room"] == "alpha"
        assert pins[0]["forked_from"] == "parent-sess-9"


class TestSessionIdentityInjection:
    """A session must be told which session it is.

    lab/026: nothing put the id in the model's context, so self-referential
    reasoning guessed its own subject and got a real, adjacent, same-scope
    session. The harness knew the answer the whole time.
    """

    def test_the_session_is_told_its_own_id(self, tmp_path):
        ctx = context_of(run_hook(session_start_payload(session_id="abc-123"), tmp_path))
        assert "abc-123" in ctx

    def test_the_id_is_marked_authoritative_over_inferred_ones(self, tmp_path):
        """The failure mode is a *plausible* competing UUID, so stating the id is
        not enough — it has to outrank what the session infers elsewhere."""
        ctx = context_of(run_hook(session_start_payload(session_id="abc-123"), tmp_path))
        assert "authoritative" in ctx.lower()
        assert "prefer it over any session id you infer" in ctx

    def test_no_id_means_no_claim_about_identity(self, tmp_path):
        result = run_hook(session_start_payload(session_id=""), tmp_path)
        assert "session_id is" not in context_of(result)


class TestForeignCwdPinResolution:
    """A pinned session opened outside the checkout (`thalamus spawn --dir`).

    CLAUDE_PROJECT_DIR then names the *working* repo, not the Thalamus checkout.
    Anchoring manifest lookup on it made the hooks resolve `main` while the MCP
    server — which anchors on contract/manifest._DEFAULT_CONFIG and never reads
    CLAUDE_PROJECT_DIR — enforced the real scope. Because session-end is
    ledger-first, that mismatch distilled the whole session into the wrong
    scope: the 2026-07-18 mis-scoping leak arriving through the ledger instead
    of the env. The bash mirror must stay anchored the way the Python is.
    """

    def resolve(self, tmp_path, env):
        full_env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        full_env.update(env)
        return subprocess.run(
            ["bash", "-c", f'. "{HOOKS}/resolve-scope.sh"; thalamus_resolve_scope'],
            capture_output=True, text=True, env=full_env, cwd=str(tmp_path), timeout=30,
        ).stdout.strip()

    def test_picked_agent_wins_when_project_dir_is_a_foreign_repo(self, tmp_path):
        assert self.resolve(tmp_path, {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "CLAUDE_CODE_AGENT": "thalamus-literature",
        }) == "literature"

    def test_ledger_records_the_launch_channel_beside_the_resolved_scope(self, tmp_path):
        """Scope alone cannot audit its own resolution.

        When agent and env disagreed before ed18887, the ledger kept only the
        resolved scope — the value that was wrong — so the mis-scoped-writes
        audit could not separate a mis-scoped expert session from a main session
        that consulted an expert. Recording the channel makes divergence visible.
        """
        run_hook(
            session_start_payload(cwd=str(tmp_path)),
            tmp_path,
            env={"CLAUDE_CODE_AGENT": "thalamus-literature", "THALAMUS_SCOPE": "main"},
        )
        row = json.loads(
            (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()[0])
        assert row["agent"] == "thalamus-literature"
        assert row["scope"] == "literature"

    def test_ledger_agent_is_empty_for_an_unpinned_session(self, tmp_path):
        run_hook(session_start_payload(cwd=str(tmp_path)), tmp_path)
        row = json.loads(
            (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()[0])
        assert row["agent"] == "" and row["scope"] == "main"

    def test_ledger_records_the_pin_from_a_foreign_cwd(self, tmp_path):
        """End-to-end: the ledger session-end reads must carry the real pin."""
        run_hook(
            session_start_payload(cwd=str(tmp_path)),
            tmp_path,
            env={"CLAUDE_PROJECT_DIR": str(tmp_path),
                 "CLAUDE_CODE_AGENT": "thalamus-literature"},
        )
        pins = [
            json.loads(line)
            for line in (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert pins[0]["scope"] == "literature"

    def test_unknown_agent_still_falls_through_to_env(self, tmp_path):
        """The manifest check is what makes agent-first safe; keep it load-bearing."""
        assert self.resolve(tmp_path, {
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "CLAUDE_CODE_AGENT": "thalamus-nosuchexpert",
            "THALAMUS_SCOPE": "main",
        }) == "main"

    def test_config_dir_override_still_takes_precedence(self, tmp_path):
        """THALAMUS_CONFIG_DIR overrides the anchor, mirroring manifest.experts_dir."""
        assert self.resolve(tmp_path, {
            "THALAMUS_CONFIG_DIR": str(tmp_path / "nonexistent"),
            "CLAUDE_CODE_AGENT": "thalamus-literature",
        }) == "main"

    def test_repo_root_is_the_checkout_not_the_working_project(self, tmp_path):
        root = subprocess.run(
            ["bash", "-c", f'. "{HOOKS}/resolve-scope.sh"; thalamus_repo_root'],
            capture_output=True, text=True, timeout=30, cwd=str(tmp_path),
            env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin",
                 "CLAUDE_PROJECT_DIR": str(tmp_path)},
        ).stdout.strip()
        assert Path(root) == HOOKS.parents[4]
        assert (Path(root) / "pyproject.toml").is_file()


class TestDistillationAnchor:
    """session-end must run `thalamus` from the checkout, not the session's cwd.

    A foreign cwd is not a uv project with thalamus in it, so a cwd-anchored
    invocation resolves no `thalamus` command and the session silently never
    distills — the failure is invisible because extraction is detached.
    """

    def test_uv_is_pointed_at_the_checkout_from_a_foreign_cwd(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        argv_log = tmp_path / "uv-argv.txt"
        stub = bin_dir / "uv"
        stub.write_text(f'#!/bin/bash\nprintf "%s\\n" "$*" >> "{argv_log}"\n')
        stub.chmod(0o755)
        _transcript(tmp_path, tmp_path, "cc-sess-9")

        _session_end(tmp_path, tmp_path, "cc-sess-9", bin_dir)

        deadline = time.time() + 20
        while time.time() < deadline and not argv_log.exists():
            time.sleep(0.2)
        assert argv_log.exists(), "session-end never invoked uv"
        calls = argv_log.read_text()

        checkout = str(HOOKS.parents[4])
        assert f"--project {checkout}" in calls
        assert f"--directory {tmp_path}" not in calls
        assert "thalamus extract" in calls

    def test_project_dir_comes_from_the_transcript_not_the_exit_cwd(self, tmp_path):
        """A session that cd'd away must still distill from its own project dir.

        Claude Code files a transcript under the dir named for the *startup* cwd;
        the SessionEnd payload carries the cwd at exit. Deriving the project dir
        from the latter points extract at the wrong dir, which selects zero
        sessions — silently, when the drifted-to dir happens to exist.
        """
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        argv_log = tmp_path / "uv-argv.txt"
        stub = bin_dir / "uv"
        stub.write_text(f'#!/bin/bash\nprintf "%s\\n" "$*" >> "{argv_log}"\n')
        stub.chmod(0o755)

        started_in = "-home-someone"
        transcript = tmp_path / ".claude" / "projects" / started_in / "cc-sess-10.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text("{}\n")
        drifted_to = tmp_path / "code" / "elsewhere"
        drifted_to.mkdir(parents=True)

        subprocess.run(
            [str(HOOKS / "session-end.sh")],
            input=json.dumps({"session_id": "cc-sess-10", "cwd": str(drifted_to),
                              "transcript_path": str(transcript),
                              "hook_event_name": "SessionEnd", "reason": "exit"}),
            capture_output=True, text=True, timeout=30,
            env={"HOME": str(tmp_path),
                 "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin",
                 "CLAUDE_PROJECT_DIR": str(tmp_path),
                 "THALAMUS_SCOPE": "main"},
        )

        deadline = time.time() + 20
        while time.time() < deadline and not argv_log.exists():
            time.sleep(0.2)
        assert argv_log.exists(), "session-end never invoked uv"
        calls = argv_log.read_text()

        assert f"-- {started_in}" in calls
        assert str(drifted_to).replace("/", "-") not in calls


def _transcript(home, cwd, session_id, body="{}\n"):
    """The transcript Claude Code writes for a real session, where the hook looks."""
    path = (Path(home) / ".claude" / "projects"
            / str(cwd).replace("/", "-") / f"{session_id}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _session_end(home, cwd, session_id, bin_dir, scope="literature", transcript_path=""):
    payload = {"session_id": session_id, "cwd": str(cwd),
               "hook_event_name": "SessionEnd", "reason": "exit"}
    if transcript_path:
        payload["transcript_path"] = str(transcript_path)
    return subprocess.run(
        [str(HOOKS / "session-end.sh")],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=30,
        env={"HOME": str(home),
             "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin",
             "CLAUDE_PROJECT_DIR": str(cwd),
             "THALAMUS_SCOPE": scope},
    )


class TestTranscriptlessSessionsAreNotDistilled:
    """A subagent is a session to the harness: it fires SessionEnd like any other,
    but has no transcript of its own, so extracting it can only ever fail. Spawning
    `uv run … claude -p` to find that out cost a measured 1234 of 1826 session-end
    logs on a working box, and a burst of them starved a real distillation to death.
    """

    def _stub_uv(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        argv_log = tmp_path / "uv-argv.txt"
        stub = bin_dir / "uv"
        stub.write_text(f'#!/bin/bash\nprintf "%s\\n" "$*" >> "{argv_log}"\n')
        stub.chmod(0o755)
        return bin_dir, argv_log

    def test_a_session_with_no_transcript_never_spawns_an_extract(self, tmp_path):
        bin_dir, argv_log = self._stub_uv(tmp_path)

        _session_end(tmp_path, tmp_path, "sub-agent-1", bin_dir)

        time.sleep(1.5)          # a detached extract would have landed by now
        assert not argv_log.exists(), "a transcriptless session still ran extract"

    def test_it_leaves_no_log_behind_either(self, tmp_path):
        """Otherwise the logs directory fills with files for sessions that were
        never distillable, which is what the console's widget has to filter."""
        bin_dir, _ = self._stub_uv(tmp_path)

        _session_end(tmp_path, tmp_path, "sub-agent-2", bin_dir)

        assert not (tmp_path / ".thalamus" / "logs").exists()

    def test_a_real_session_missing_its_transcript_is_logged_as_an_anomaly(self, tmp_path):
        """A pin-ledger row means this was a real session, so the missing file is a
        fault worth surfacing rather than routine subagent noise."""
        bin_dir, argv_log = self._stub_uv(tmp_path)
        pins = tmp_path / ".thalamus" / "pins"
        pins.mkdir(parents=True)
        (pins / "pins.jsonl").write_text(
            json.dumps({"session_id": "real-sess-1", "scope": "homelab",
                        "cwd": str(tmp_path), "ts": "now"}) + "\n")

        _session_end(tmp_path, tmp_path, "real-sess-1", bin_dir)

        log = tmp_path / ".thalamus" / "logs" / "session-end-real-ses.log"
        assert log.exists(), "a real session's missing transcript went unrecorded"
        assert "nothing to distill" in log.read_text()
        time.sleep(1.5)
        assert not argv_log.exists()

    def test_a_session_with_a_transcript_still_distills(self, tmp_path):
        bin_dir, argv_log = self._stub_uv(tmp_path)
        _transcript(tmp_path, tmp_path, "real-sess-2")

        _session_end(tmp_path, tmp_path, "real-sess-2", bin_dir)

        deadline = time.time() + 20
        while time.time() < deadline and not argv_log.exists():
            time.sleep(0.2)
        assert argv_log.exists()
        assert "thalamus extract" in argv_log.read_text()

    def test_the_guard_looks_where_the_transcript_actually_landed(self, tmp_path):
        """A room runs under its own CLAUDE_CONFIG_DIR and files its transcript in
        that dir's `projects/`, which ~/.claude/projects never sees (lab/046). The
        guard has to resolve against the root the transcript came from; anchored to
        the default root instead, every room session reads as transcriptless and is
        skipped — the guard would silently become the memory loss it prevents.
        """
        bin_dir, argv_log = self._stub_uv(tmp_path)
        room_projects = tmp_path / "room-config" / "projects" / "-some-project"
        room_projects.mkdir(parents=True)
        transcript = room_projects / "room-sess-1.jsonl"
        transcript.write_text("{}\n")
        assert not (tmp_path / ".claude" / "projects").exists()   # not the default root

        _session_end(tmp_path, tmp_path, "room-sess-1", bin_dir,
                     transcript_path=transcript)

        deadline = time.time() + 20
        while time.time() < deadline and not argv_log.exists():
            time.sleep(0.2)
        assert argv_log.exists(), "a room session was skipped as transcriptless"
        assert "thalamus extract" in argv_log.read_text()


def _run_conditioning(payload, home):
    return subprocess.run(
        [str(HOOKS / "conditioning.sh")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        timeout=30,
    )


def _firings(home, cls):
    logs = list((home / ".thalamus" / "conditioning").glob("*.jsonl"))
    records = []
    for log in logs:
        for line in log.read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))
    return [r for r in records if r.get("class") == cls]


def _query_call(session_id, agent_id=""):
    return {
        "hook_event_name": "PostToolUse",
        "session_id": session_id,
        "agent_id": agent_id,
        "tool_name": "mcp__thalamus__memory_query",
        "tool_input": {"query": "g.V().count()"},
    }


def test_falsify_fires_on_an_ad_hoc_traversal_and_throttles_per_agent(tmp_path):
    """
    Scenario: A main session runs two memory_query calls, then two of its
    subagents each run one.

    Verifications:
    - the class fires on memory_query and names the check-it-first instruction
    - the main session is reminded once, not twice
    - each subagent is reminded once: they share the parent's session_id, so a
      session-only throttle would exempt every one of them — and the subagent is
      where lab/029's two correctly-cited, wrong-mechanism answers were written
    """
    first = _run_conditioning(_query_call("s-falsify"), tmp_path)
    context = json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "what would make the conclusion WRONG" in context
    assert "recall-strategy" in context

    assert _run_conditioning(_query_call("s-falsify"), tmp_path).stdout.strip() == ""

    for agent in ("agent-a", "agent-b"):
        out = _run_conditioning(_query_call("s-falsify", agent), tmp_path).stdout
        assert "what would make the conclusion WRONG" in out

    fired = _firings(tmp_path, "falsify")
    assert [r["agent"] for r in fired] == ["", "agent-a", "agent-b"]


def test_falsify_ignores_tools_that_are_not_the_ad_hoc_surface(tmp_path):
    """The recall tools render prose already labelled as data; memory_query
    returns raw aggregates that get turned into claims. Only the latter fires."""
    for tool in ("mcp__thalamus__memory_recall", "Read", "mcp__thalamus__memorize"):
        payload = _query_call("s-quiet")
        payload["tool_name"] = tool
        assert _run_conditioning(payload, tmp_path).stdout.strip() == ""
    assert _firings(tmp_path, "falsify") == []


def test_milestone_class_survives_the_new_branch(tmp_path):
    """TaskCreate still reaches the milestone class after memory_query joined
    the same PostToolUse branch."""
    payload = _query_call("s-milestone")
    payload["tool_name"] = "TaskCreate"
    out = _run_conditioning(payload, tmp_path).stdout
    assert "multi-step work is starting" in out
    assert len(_firings(tmp_path, "milestone")) == 1


# --------------------------------------------------------------------------------------
# recipe-stage.sh — RECIPES.md capture as a hook, not a habit.
# --------------------------------------------------------------------------------------


def _run_stage(payload, home):
    return subprocess.run(
        [str(HOOKS / "recipe-stage.sh")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        timeout=30,
    )


def _staged(home):
    path = Path(home) / ".thalamus" / "recipes" / "staged.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _query_payload(query, response):
    return {
        "session_id": "s1",
        "tool_name": "mcp__thalamus__memory_query",
        "tool_input": {"query": query},
        "tool_response": response,
    }


def _bash_payload(command, stdout):
    return {
        "session_id": "s1",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"stdout": stdout},
    }


def test_a_query_that_ran_and_answered_is_staged(tmp_path):
    """
    Scenario: A session runs a memory_query that comes back with data

    Rule 5 of the gremlin-python skill is "check RECIPES.md before writing, add to it
    after validating". The guard enforces step one; step two was left to an agent
    remembering a second obligation mid-task, measured at 0-for-3 in one session.
    """
    _run_stage(_query_payload("g.V().hasLabel('Exchange').count()", "[42]"), tmp_path)

    staged = _staged(tmp_path)
    assert len(staged) == 1
    assert staged[0]["surface"] == "memory_query"
    assert staged[0]["query"] == "g.V().hasLabel('Exchange').count()"


def test_a_query_that_failed_is_not_a_validated_recipe(tmp_path):
    """
    Scenario: Traversals that errored, were refused, or returned nothing

    Verifications:
    - none of them stage

    The admission threshold the hook *can* check is that the query ran and answered.
    Staging failures would fill the queue with the thing the skill exists to warn
    about, and a store of broken queries is worse than no store.
    """
    for response in (
        "Traceback (most recent call last): GremlinServerError",
        "memory_query is a master-plane instrument and this session is pinned to `x`",
        "No results",
        "",
        "   ",
    ):
        _run_stage(_query_payload("g.V().bogus()", response), tmp_path)

    assert _staged(tmp_path) == []


def test_a_lazy_traversal_is_refused_rather_than_stored_as_a_recipe(tmp_path):
    """
    Scenario: A Bash gremlin call prints a GraphTraversal repr

    A repr means the traversal was never iterated — the single most common Gremlin
    mistake in this project, and the precise opposite of a proven recipe. Storing it
    would teach the next session the error.
    """
    _run_stage(
        _bash_payload(
            "python -c 'from gremlin_python import x; print(g.V())'",
            "<gremlin_python.process.graph_traversal.GraphTraversal object at 0x7f>",
        ),
        tmp_path,
    )

    assert _staged(tmp_path) == []


def test_only_bash_that_actually_inlines_gremlin_is_a_graph_query(tmp_path):
    """
    Scenario: Ordinary Bash runs alongside inline gremlin

    Verifications:
    - `ls` does not stage
    - a command importing the substrate does

    Same marker heuristic as gremlin-guard.sh and gremlin-tap.sh, deliberately: three
    surfaces disagreeing about what counts as a graph query would be three different
    answers to one question.
    """
    _run_stage(_bash_payload("ls -la", "a.py b.py"), tmp_path)
    assert _staged(tmp_path) == []

    _run_stage(
        _bash_payload(
            "python -c 'from thalamus.substrate.writer import connect'", "3 rows"
        ),
        tmp_path,
    )
    staged = _staged(tmp_path)
    assert len(staged) == 1 and staged[0]["surface"] == "gremlin-python"


def test_staging_never_blocks_and_never_speaks(tmp_path):
    """
    Scenario: Every payload shape reaches the hook

    A PostToolUse hook that exits non-zero or writes to stdout would inject itself
    into the session. This one records and says nothing — promotion is a human
    judgement made later, out of band.
    """
    for payload in (
        _query_payload("g.V().count()", "[5]"),
        _bash_payload("ls", "x"),
        {"session_id": "s", "tool_name": "Read", "tool_input": {}, "tool_response": "x"},
    ):
        result = _run_stage(payload, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestRoomLedger:
    """The room is the third axis: project = which repo, scope = which expert,
    room = which event. It rides the ledger because by SessionEnd the spawner's
    environment is gone, and a finished graph cannot tell three sessions that
    independently agreed from three that were in the room together.
    """

    def test_room_lands_in_the_ledger(self, tmp_path):
        run_hook(
            session_start_payload(cwd=str(tmp_path)),
            tmp_path,
            env={"THALAMUS_ROOM": "room-7"},
        )
        row = json.loads(
            (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()[0])
        assert row["room"] == "room-7"

    def test_a_session_that_worked_alone_records_an_empty_room(self, tmp_path):
        """Empty is the honest default. Inferring a room from co-timing would
        manufacture exactly the correlation the field exists to make detectable."""
        run_hook(session_start_payload(cwd=str(tmp_path)), tmp_path)
        row = json.loads(
            (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()[0])
        assert row["room"] == ""

    def test_room_is_orthogonal_to_scope_and_project(self, tmp_path):
        run_hook(
            session_start_payload(cwd=str(tmp_path)),
            tmp_path,
            env={
                "THALAMUS_ROOM": "room-7",
                "CLAUDE_CODE_AGENT": "thalamus-literature",
                "THALAMUS_PROJECT": "thalamus",
            },
        )
        row = json.loads(
            (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()[0])
        assert row["room"] == "room-7"
        assert row["scope"] == "literature"


class TestForkedFromLedger:
    """`room` says these sessions saw one event; `forked_from` says this session
    derives from that one. A fork inherited its parent's context, so its agreement
    with the parent is not corroboration — and unlike room membership, that
    dependence is exact rather than circumstantial.
    """

    def test_fork_parent_lands_in_the_ledger(self, tmp_path):
        run_hook(
            session_start_payload(cwd=str(tmp_path)),
            tmp_path,
            env={"THALAMUS_FORKED_FROM": "parent-sess-9"},
        )
        row = json.loads(
            (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()[0])
        assert row["forked_from"] == "parent-sess-9"

    def test_a_cold_session_records_no_parent(self, tmp_path):
        run_hook(session_start_payload(cwd=str(tmp_path)), tmp_path)
        row = json.loads(
            (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()[0])
        assert row["forked_from"] == ""

    def test_room_and_fork_parent_are_independent(self, tmp_path):
        """A fork may be in a room, in no room, or a room member may be unforked.
        Neither field implies the other."""
        run_hook(
            session_start_payload(cwd=str(tmp_path)),
            tmp_path,
            env={"THALAMUS_FORKED_FROM": "parent-sess-9"},
        )
        row = json.loads(
            (tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text().splitlines()[0])
        assert row["forked_from"] == "parent-sess-9" and row["room"] == ""
