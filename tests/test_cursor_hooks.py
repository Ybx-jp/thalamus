"""
Cursor hook-suite tests (harness integration).

Interfaces: src/thalamus/harness/hooks/cursor/*.sh, driven live (bash) with
synthetic stdin payloads shaped per Cursor's documented hook contract
(verified against docs.cursor.com 2026-07-19).
Infrastructure: tmp_path as $HOME so ledger/trace/guard writes are sandboxed;
no live graph, no Cursor.
Scope: the adapter boundary — each Cursor hook must reshape its payload into
the Claude Code shape, produce Cursor-valid output, and leave the same
on-disk records the Claude Code suite leaves, so eval reads stay
harness-agnostic. This is contract conformance, not an end-to-end Cursor
test: only a live Cursor run can validate the payloads Cursor actually sends.
"""

import json
import subprocess
from pathlib import Path


HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks" / "cursor"

DOOMED_GREMLIN = (
    "python -c \"from gremlin_python.driver.driver_remote_connection import"
    " DriverRemoteConnection; g.V().has_label('Session')\""
)


def run_hook(script, payload, home, env=None):
    full_env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
        timeout=30,
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def session_start_payload(**overrides):
    payload = {
        "session_id": "cur-sess-1",
        "conversation_id": "cur-conv-1",
        "workspace_roots": ["/home/user/code/myproject"],
        "is_background_agent": False,
        "hook_event_name": "sessionStart",
    }
    payload.update(overrides)
    return payload


class TestSessionStart:
    def test_primes_context_and_records_pin(self, tmp_path):
        """
        Scenario: a foreground Cursor session starts in a workspace.

        Verifications:
        - stdout is Cursor-shaped: bare `additional_context`, no
          hookSpecificOutput wrapper
        - the context names the project and the bare (unprefixed) tool names
        - it does *not* carry the Claude Code variant's deferred-tool
          (ToolSearch) step — that mechanism is Claude Code's, and naming a
          tool Cursor has no notion of would be an instruction the agent
          cannot follow, the same class of defect found in the other
          direction
        - the pin ledger gets one line in the same record shape the Claude
          Code hook writes (session-end + eval read both harnesses' lines)
        """
        # A real checkout: `project` is the repo's name resolved through git, the same
        # derivation the write path uses, so a synthetic path would resolve to nothing.
        checkout = tmp_path / "myproject"
        checkout.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=checkout, check=True, capture_output=True)

        result = run_hook(
            "session-start.sh",
            session_start_payload(workspace_roots=[str(checkout)]),
            tmp_path,
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        ctx = out["additional_context"]
        assert "hookSpecificOutput" not in out
        assert 'project="myproject"' in ctx
        assert "memory_open_threads" in ctx
        assert "mcp__thalamus__" not in ctx
        assert "ToolSearch" not in ctx

        pins = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")
        assert pins == [
            {
                "session_id": "cur-sess-1",
                "scope": "main",
                "cwd": str(checkout),
                "room": "",
                # The grouping keys. `cwd` cannot group: a checkout and a directory
                # inside it are one project and sort as two, and several sessions in
                # one checkout share the string exactly and sort as one pile. Both
                # are resolved for the priming text above, so recording them costs a
                # jq argument, and the console has no other route to either.
                "repo_root": str(checkout),
                "project": "myproject",
                "ts": pins[0]["ts"],
            }
        ]

    def test_a_worktree_session_recalls_and_files_under_the_repository(self, tmp_path):
        """
        Scenario: a Cursor session opens a worktree of a repo as its workspace root.

        Verifications:
        - the primed project is the repository's name, not the worktree directory's
        - the pin ledger row the console groups the roster by carries the same

        Four implementations resolve this fact, in two languages, and they cannot
        drift: `transcripts.resolve_repo_root` decides what a session distills under,
        while this hook decides whose threads it recalls at start. Since the write
        path files a worktree's work under the repository, a hook resolving the
        worktree to itself asks for a project nothing is filed under — which returns
        empty rather than wrong, and an empty recall reads as "no prior work here".
        """
        checkout = tmp_path / "myproject"
        checkout.mkdir()
        for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "root"],
                     ["worktree", "add", "-q", str(tmp_path / "wt"), "-b", "side"]):
            # `-c` rather than `git config`: a machine with no global identity — a CI
            # runner, a fresh container — fails `commit` with exit 128 before this test
            # has said anything, and a throwaway repo is no reason to edit the
            # operator's own git configuration.
            subprocess.run(["git", "-c", "user.name=thalamus tests",
                            "-c", "user.email=tests@thalamus.invalid",
                            "-C", str(checkout), *args],
                           check=True, capture_output=True)

        result = run_hook(
            "session-start.sh",
            session_start_payload(workspace_roots=[str(tmp_path / "wt")]),
            tmp_path,
        )
        assert result.returncode == 0
        assert 'project="myproject"' in json.loads(result.stdout)["additional_context"]

        pin = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")[0]
        # Verifies: the roster groups this session with the repo's other sessions
        assert pin["project"] == "myproject"
        assert pin["repo_root"] == str(checkout)
        # Verifies: cwd still records where the session actually ran
        assert pin["cwd"] == str(tmp_path / "wt")

    def test_env_pin_is_announced_and_recorded(self, tmp_path):
        """
        Scenario: the session was launched with THALAMUS_SCOPE=literature
        (env is the only pin channel on Cursor — no agent picker).

        Verifications: the pin lands in the ledger and the context leads with
        the pinned-scope announcement.
        """
        result = run_hook(
            "session-start.sh",
            session_start_payload(),
            tmp_path,
            env={"THALAMUS_SCOPE": "literature"},
        )
        ctx = json.loads(result.stdout)["additional_context"]
        assert ctx.startswith("This session is pinned to expert scope `literature`")
        pins = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")
        assert pins[0]["scope"] == "literature"

    def test_background_agent_is_not_primed(self, tmp_path):
        result = run_hook(
            "session-start.sh",
            session_start_payload(is_background_agent=True),
            tmp_path,
        )
        assert json.loads(result.stdout) == {}
        assert not (tmp_path / ".thalamus" / "pins" / "pins.jsonl").exists()


class TestGremlinGuard:
    def test_blocks_doomed_traversal_with_cursor_permission_json(self, tmp_path):
        """
        Scenario: inline gremlin-python with no terminal step, arriving in
        Cursor's beforeShellExecution shape ({command}, not {tool_input}).

        Verifications:
        - the Claude Code guard's exit-2 protocol maps to permission=deny
        - the reason rides *both* message channels. Measured on
          `cursor/2026.08.11-e8db854`: the denial's tool result carries the
          `user_message` text and no occurrence of `agent_message`, so a guard
          that explains itself only through the documented agent channel blocks
          in silence — and a block with no reason is a stall.
        - the shared guard event log gets the block verdict (one log, two
          harnesses)
        """
        result = run_hook(
            "gremlin-guard.sh",
            {"command": DOOMED_GREMLIN, "cwd": "/w", "conversation_id": "c1"},
            tmp_path,
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out["permission"] == "deny"
        assert "terminal step" in out["agent_message"]
        assert "terminal step" in out["user_message"]

        guard_dir = tmp_path / ".thalamus" / "guards"
        events = read_jsonl(next(guard_dir.glob("*.jsonl")))
        assert events[-1]["verdict"] == "block"
        assert events[-1]["session_id"] == "c1"

    def test_allows_terminated_traversal(self, tmp_path):
        result = run_hook(
            "gremlin-guard.sh",
            {"command": DOOMED_GREMLIN.replace("g.V()", "g.V().to_list() #"),
             "conversation_id": "c1"},
            tmp_path,
        )
        assert json.loads(result.stdout) == {"permission": "allow"}
        events = read_jsonl(next((tmp_path / ".thalamus" / "guards").glob("*.jsonl")))
        assert events[-1]["verdict"] == "pass"

    def test_non_gremlin_command_passes_without_event(self, tmp_path):
        result = run_hook("gremlin-guard.sh", {"command": "ls -la"}, tmp_path)
        assert json.loads(result.stdout) == {"permission": "allow"}
        assert not (tmp_path / ".thalamus" / "guards").exists()


class TestGremlinTap:
    def test_gremlin_command_lands_as_bash_gremlin_trace(self, tmp_path):
        """
        Scenario: an executed inline gremlin command arrives in Cursor's
        afterShellExecution shape, with its single combined `output` string.

        Verifications: the trace record is byte-compatible with the Claude
        Code tap's — tool_name bash_gremlin, output on the stdout leg — so
        `eval sync` prices it with no harness awareness.
        """
        result = run_hook(
            "gremlin-tap.sh",
            {"command": DOOMED_GREMLIN, "output": "v[abc]", "duration": 40,
             "conversation_id": "c9", "cwd": "/w"},
            tmp_path,
        )
        assert result.returncode == 0
        traces = read_jsonl(next((tmp_path / ".thalamus" / "traces").glob("*.jsonl")))
        assert traces[-1]["tool_name"] == "bash_gremlin"
        assert traces[-1]["tool_response"] == "v[abc]"
        assert traces[-1]["session_id"] == "c9"

    def test_non_gremlin_command_leaves_no_trace(self, tmp_path):
        run_hook("gremlin-tap.sh", {"command": "git status", "output": "clean"}, tmp_path)
        assert not (tmp_path / ".thalamus" / "traces").exists()

    def test_an_empty_cwd_falls_back_to_the_workspace_root(self, tmp_path):
        """Cursor sends `cwd` as an empty string on shell payloads, not as null.

        jq's `//` falls through on `null` and `false` only, so the obvious
        `(.cwd // .workspace_roots[0])` idiom wrote an empty cwd into the ledgers
        for every such payload. Measured, not hypothesised: the guard rows from a
        live Cursor session all carry `cwd:""`.
        """
        run_hook(
            "gremlin-tap.sh",
            {"command": DOOMED_GREMLIN, "output": "v[abc]", "cwd": "",
             "workspace_roots": ["/repo"], "conversation_id": "c9"},
            tmp_path,
        )
        traces = read_jsonl(next((tmp_path / ".thalamus" / "traces").glob("*.jsonl")))
        assert traces[-1]["cwd"] == "/repo"


class TestMcpTap:
    def test_bare_tool_name_is_reprefixed_in_trace(self, tmp_path):
        """
        Scenario: Cursor reports a thalamus MCP call by bare name with the
        result under result_json.

        Verifications: the trace restores the mcp__thalamus__ prefix and maps
        result_json to tool_response — uniform records across harnesses.
        """
        result = run_hook(
            "mcp-tap.sh",
            {"tool_name": "memory_recall",
             "tool_input": {"query": "pin ledger"},
             "result_json": "## Recalled memory ...",
             "conversation_id": "c2"},
            tmp_path,
        )
        assert result.returncode == 0
        traces = read_jsonl(next((tmp_path / ".thalamus" / "traces").glob("*.jsonl")))
        assert traces[-1]["tool_name"] == "mcp__thalamus__memory_recall"
        assert traces[-1]["tool_input"] == {"query": "pin ledger"}
        assert traces[-1]["tool_response"] == "## Recalled memory ..."

    def test_foreign_mcp_tool_is_not_traced(self, tmp_path):
        run_hook(
            "mcp-tap.sh",
            {"tool_name": "list_issues", "tool_input": {}, "result_json": "[]"},
            tmp_path,
        )
        assert not (tmp_path / ".thalamus" / "traces").exists()


class TestPinEngaged:
    def test_first_prompt_marks_engaged_once(self, tmp_path):
        """
        Scenario: two prompts in the same Cursor conversation.

        Verifications: exactly one engaged event lands in the ledger
        (idempotent per session), and every response is {"continue": true} —
        this hook must never block a prompt.
        """
        payload = {"prompt": "hello", "conversation_id": "c3"}
        for _ in range(2):
            result = run_hook("pin-engaged.sh", payload, tmp_path)
            assert json.loads(result.stdout) == {"continue": True}
        pins = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")
        engaged = [p for p in pins if p.get("event") == "engaged"]
        assert len(engaged) == 1
        assert engaged[0]["session_id"] == "c3"


class TestSessionEnd:
    def test_records_undistilled_end_with_ledger_first_scope(self, tmp_path):
        """
        Scenario: a Cursor session that session-start pinned to `literature`
        ends from a shell whose env says main.

        Verifications:
        - the end record trusts the ledger over env (same rule as Claude Code)
        - distilled is explicitly false with the reason named — the
          missing Cursor transcript adapter must be visible in the record,
          not silent
        - the transcript_path evidence pointer survives
        """
        ledger = tmp_path / ".thalamus" / "pins" / "pins.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(
            json.dumps({"session_id": "c4", "scope": "literature", "cwd": "/w",
                        "ts": "2026-07-19T00:00:00Z"}) + "\n"
        )
        result = run_hook(
            "session-end.sh",
            {"session_id": "c4", "reason": "user_closed",
             "transcript_path": "/home/user/.cursor/transcripts/c4.json"},
            tmp_path,
        )
        assert result.returncode == 0
        ends = read_jsonl(tmp_path / ".thalamus" / "logs" / "cursor-session-end.jsonl")
        assert ends[-1]["scope"] == "literature"
        assert ends[-1]["distilled"] is False
        assert ends[-1]["transcript_path"] == "/home/user/.cursor/transcripts/c4.json"
        # The row is the pointer the later `extract --harness cursor` sweep reads,
        # so what it must carry is the pointer and the scope — not commentary. An
        # assertion on a prose note pins the note's wording rather than the
        # contract, and outlives whatever the note was explaining.
        assert ends[-1]["harness"] == "cursor"
        assert ends[-1]["session_id"] == "c4"


class TestDeferredInjection:
    """The spool: Cursor splits reading the prompt from injecting context, so
    beforeSubmitPrompt computes and postToolUse delivers.
    These are the tiers that had no Cursor carrier at all before."""

    def test_clock_is_delivered_on_the_next_tool_call(self, tmp_path):
        run_hook("timestamp.sh", {"session_id": "d1", "prompt": "hi"}, tmp_path)
        result = run_hook("inject.sh", {"session_id": "d1", "tool_name": "Read"}, tmp_path)
        assert result.returncode == 0
        assert "Current date and time" in json.loads(result.stdout)["additional_context"]

    def test_clock_is_rendered_at_delivery_not_at_spool_time(self, tmp_path):
        """The spooled marker must carry no timestamp — a clock rendered on the
        prompt and delivered a tool call later is the drift this tier prevents."""
        run_hook("timestamp.sh", {"session_id": "d2", "prompt": "hi"}, tmp_path)
        spooled = read_jsonl(tmp_path / ".thalamus" / "spool" / "d2.jsonl")
        assert spooled == [{"kind": "clock", "text": ""}]

    def test_conditioning_class_crosses_to_cursor(self, tmp_path):
        run_hook("conditioning.sh",
                 {"session_id": "d3", "prompt": "let's design a new component"}, tmp_path)
        result = run_hook("inject.sh", {"session_id": "d3", "tool_name": "Read"}, tmp_path)
        assert "ground-in-literature" in json.loads(result.stdout)["additional_context"]

    def test_firing_is_stamped_cursor_so_the_join_can_separate_harnesses(self, tmp_path):
        """`thalamus eval conditioning` must not average Cursor's delayed
        delivery in with Claude Code's immediate one."""
        run_hook("conditioning.sh",
                 {"session_id": "d4", "prompt": "let's design a new component"}, tmp_path)
        log = list((tmp_path / ".thalamus" / "conditioning").glob("*.jsonl"))[0]
        assert read_jsonl(log)[-1]["harness"] == "cursor"

    def test_conditioning_throttle_still_holds_across_the_adapter(self, tmp_path):
        for _ in range(2):
            run_hook("conditioning.sh",
                     {"session_id": "d5", "prompt": "let's design a thing"}, tmp_path)
        log = list((tmp_path / ".thalamus" / "conditioning").glob("*.jsonl"))[0]
        assert len([r for r in read_jsonl(log) if r["class"] == "design"]) == 1

    def test_spool_is_drained_exactly_once(self, tmp_path):
        run_hook("timestamp.sh", {"session_id": "d6", "prompt": "hi"}, tmp_path)
        first = run_hook("inject.sh", {"session_id": "d6", "tool_name": "Read"}, tmp_path)
        second = run_hook("inject.sh", {"session_id": "d6", "tool_name": "Read"}, tmp_path)
        assert "additional_context" in json.loads(first.stdout)
        assert json.loads(second.stdout) == {}

    def test_undelivered_classification_does_not_outlive_its_turn(self, tmp_path):
        """A turn that fires conditioning and then calls no tool must not deliver
        that classification against the *next* prompt — it was matched on text
        that is no longer live (RFC 9111 §4.2; STALE arXiv 2605.06527)."""
        run_hook("conditioning.sh",
                 {"session_id": "d9", "prompt": "let's design a new component"}, tmp_path)
        # no tool call this turn; next prompt arrives and matches no class
        run_hook("timestamp.sh", {"session_id": "d9", "prompt": "what time is it"}, tmp_path)
        run_hook("conditioning.sh", {"session_id": "d9", "prompt": "what time is it"}, tmp_path)
        delivered = json.loads(
            run_hook("inject.sh", {"session_id": "d9", "tool_name": "Read"}, tmp_path).stdout)
        assert "Current date and time" in delivered["additional_context"]
        assert "ground-in-literature" not in delivered["additional_context"]

    def test_a_live_classification_still_survives_to_the_first_tool_call(self, tmp_path):
        """The prune must not eat the current turn's own classification — the
        clock hook runs alongside it on the same prompt."""
        run_hook("timestamp.sh",
                 {"session_id": "d10", "prompt": "let's design a new component"}, tmp_path)
        run_hook("conditioning.sh",
                 {"session_id": "d10", "prompt": "let's design a new component"}, tmp_path)
        delivered = json.loads(
            run_hook("inject.sh", {"session_id": "d10", "tool_name": "Read"}, tmp_path).stdout)
        assert "ground-in-literature" in delivered["additional_context"]
        assert "Current date and time" in delivered["additional_context"]

    def test_no_spool_is_a_silent_no_op(self, tmp_path):
        result = run_hook("inject.sh", {"session_id": "never-prompted"}, tmp_path)
        assert result.returncode == 0
        assert json.loads(result.stdout) == {}

    def test_session_end_discards_undelivered_injection(self, tmp_path):
        """A turn that called no tool must not leak its injection into a later
        session, where it would be both stale and misattributed."""
        run_hook("timestamp.sh", {"session_id": "d7", "prompt": "hi"}, tmp_path)
        run_hook("session-end.sh", {"session_id": "d7", "reason": "user_closed"}, tmp_path)
        assert not (tmp_path / ".thalamus" / "spool" / "d7.jsonl").exists()

    def test_injection_does_not_double_count_as_a_retrieval_trace(self, tmp_path):
        """inject.sh rides postToolUse, which fires for every tool including MCP.
        It must never write a trace — mcp-tap.sh owns that, and a second writer
        would inflate every retrieval in `eval sync`."""
        run_hook("timestamp.sh", {"session_id": "d8", "prompt": "hi"}, tmp_path)
        run_hook("inject.sh",
                 {"session_id": "d8", "tool_name": "memory_recall",
                  "tool_input": {"query": "x"}, "tool_output": "hits"}, tmp_path)
        assert not (tmp_path / ".thalamus" / "traces").exists()


def test_every_cursor_script_is_wired_by_the_installer():
    """The installer's wiring is the single definition — `thalamus init` writes
    it to ~/.cursor/hooks.json with absolute paths, because user-scope hooks run
    from ~/.cursor/ and the checkout's old relative paths only ever resolved for
    a session whose workspace root was the checkout itself."""
    from thalamus.harness.install import CURSOR_HOOK_DIR, build_cursor_hook_block

    commands = {e["command"] for entries in build_cursor_hook_block().values() for e in entries}
    shipped = {p.name for p in HOOKS.glob("*.sh")} - {"resolve-scope.sh", "spool.sh"}
    assert shipped == {c.rsplit("/", 1)[1] for c in commands}
    assert all(c.startswith(str(CURSOR_HOOK_DIR)) for c in commands)


class TestWriteGuard:
    def test_denies_a_self_write_with_cursor_permission_json(self, tmp_path):
        """
        Scenario: the self-write command, arriving in Cursor's beforeShellExecution
        shape ({command}, not {tool_input}).

        Verifications:
        - the Claude Code guard's exit-2 protocol maps to permission=deny
        - the reason rides *both* message channels, for the reason gremlin-guard's
          adapter measured: the denial's tool result carries `user_message` and no
          occurrence of `agent_message`, so a guard explaining itself only through the
          documented agent channel blocks in silence, and a block with no reason is a
          stall

        The boundary is a decision about the graph (2026-08-03), and the graph does not
        care which harness ran the command — which is why this is wired rather than
        left as a Claude-only gap.
        """
        result = run_hook(
            "write-guard.sh",
            {"command": "uv run thalamus " + "write /tmp/session.yaml",
             "cwd": "/w", "conversation_id": "c1"},
            tmp_path,
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out["permission"] == "deny"
        assert "writes memory from inside a session" in out["agent_message"]
        assert "writes memory from inside a session" in out["user_message"]

    def test_allows_graph_maintenance_that_merely_shares_the_flag(self, tmp_path):
        for command in ("uv run thalamus repair-projects --write", "ls -la"):
            result = run_hook(
                "write-guard.sh",
                {"command": command, "cwd": "/w", "conversation_id": "c1"},
                tmp_path,
            )
            assert json.loads(result.stdout) == {"permission": "allow"}, command
