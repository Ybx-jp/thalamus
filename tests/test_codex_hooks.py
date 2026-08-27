"""
Codex hook-suite tests (harness integration).

Interfaces: src/thalamus/harness/hooks/codex/*.sh, driven live (bash) with
synthetic stdin payloads shaped per codex's measured hook contract (codex-cli
0.147.0, 2026-08-17 — a live `codex exec` turn that ran a shell command, edited a
file and called an MCP tool, with every hook payload captured verbatim).
Infrastructure: tmp_path as $HOME so ledger/trace/guard writes are sandboxed; no
live graph, no codex.
Scope: the *delegation* boundary. Codex's payloads are Claude Code's, so almost
nothing here is an adapter — which makes the question different from the Cursor
suite's. There the risk was a reshape that got a field wrong; here it is a
delegation that looks like it worked. So these assert the record each hook is
supposed to leave, not its exit code, and they assert the two places codex
genuinely differs: a shell result arrives as one string, and its editing tool is
`apply_patch` with a patch envelope where Claude Code has a `file_path`.

This is contract conformance, not an end-to-end codex test: only a live codex run
can validate the payloads codex actually sends, and the header above records when
that was last done.
"""

import json
import shutil
import subprocess
from pathlib import Path


HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks" / "codex"

# `uv`'s real directory joins the sandboxed PATH, because `session-end.sh` checks for
# it before doing anything (`thalamus_require_binaries jq uv`) and takes the
# record-the-loss-and-exit path when it is absent. A fixed PATH that happened to
# exclude it would make every session-end assertion pass for the wrong reason — the
# hook would be reporting a broken box, not the decision under test.
_UV = shutil.which("uv")
PATH = ":".join(filter(None, [
    str(Path(_UV).parent) if _UV else "", "/usr/bin", "/bin", "/usr/local/bin",
]))

DOOMED_GREMLIN = (
    "python -c \"from gremlin_python.driver.driver_remote_connection import"
    " DriverRemoteConnection; g.V().has_label('Session')\""
)

# The patch envelope codex sends on `tool_input.command`, verbatim in shape: header
# lines in a declared grammar, an absolute path per header.
def patch(*files: tuple[str, str]) -> str:
    body = "".join(f"*** {verb}: {path}\n@@\n+x\n" for verb, path in files)
    return f"*** Begin Patch\n{body}*** End Patch"


def run_hook(script, payload, home, env=None):
    full_env = {"HOME": str(home), "PATH": PATH}
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
        timeout=60,
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def session_start_payload(**overrides):
    payload = {
        "session_id": "01a013aa-750f-7bc1-8f78-cd4ebc2cf434",
        "transcript_path": "/codex/sessions/2026/08/17/rollout-x-01a013aa.jsonl",
        "cwd": "/home/user/code/myproject",
        "hook_event_name": "SessionStart",
        "model": "gpt-5.6-terra",
        "permission_mode": "default",
        "source": "startup",
    }
    payload.update(overrides)
    return payload


class TestSessionStart:
    def test_primes_context_and_records_pin(self, tmp_path):
        """
        Scenario: a codex session starts in a checkout.

        Verifications:
        - stdout is Claude Code's envelope, because codex's is
          (`hookSpecificOutput.additionalContext`) — not Cursor's bare
          `additional_context`
        - the context names the *prefixed* tool names. Measured: codex registers
          MCP tools as `mcp__<server>__<tool>` and loads their schemas up front, so
          a session asked for `memory_open_threads` called
          `mcp__thalamus__memory_open_threads` directly
        - and it does NOT carry the Claude Code variant's deferred-tool step:
          naming ToolSearch to a harness that has no such mechanism is an
          instruction the agent cannot follow
        - the pin ledger gets one line in the shape both other harnesses write
        """
        checkout = tmp_path / "myproject"
        checkout.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=checkout, check=True, capture_output=True)

        result = run_hook("session-start.sh",
                          session_start_payload(cwd=str(checkout)), tmp_path)
        assert result.returncode == 0
        out = json.loads(result.stdout)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert 'project="myproject"' in ctx
        assert "mcp__thalamus__memory_open_threads" in ctx
        assert "ToolSearch" not in ctx

        pins = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")
        assert pins == [
            {
                "session_id": "01a013aa-750f-7bc1-8f78-cd4ebc2cf434",
                "scope": "main",
                "cwd": str(checkout),
                "room": "",
                "repo_root": str(checkout),
                "project": "myproject",
                "ts": pins[0]["ts"],
                # Empty, not absent: the payload's `transcript_path` names no file, so
                # the claim below could not read a discriminator and refused.
                "tmux_pane": "",
            }
        ]


class TestThePaneClaim:
    """Which codex sessions may claim a tmux pane, and on what evidence.

    A claim decides who owns the console's read view for that window, so the cost of
    getting it wrong is asymmetric: an absent pane costs dispatch the ability to
    address a codex member, and a *wrong* one hands the operator's read view to a
    headless probe — measured 2026-08-10 on Claude Code as five hours of a window's
    read view lost to a two-message run.

    Nothing in codex's hook payload separates an interactive turn from `codex exec`;
    that is measured and remains true. The rollout's first record does, measured
    2026-08-22 across seven rollouts on this box (codex-cli 0.147.0 and 0.148.0), and
    it is what these gate on.
    """

    def rollout(self, tmp_path, originator, source, name="rollout.jsonl"):
        """A rollout whose first record is a `session_meta` in codex's measured shape."""
        path = tmp_path / name
        path.write_text(json.dumps({
            "type": "session_meta",
            "payload": {"originator": originator, "source": source,
                        "cli_version": "0.148.0", "session_id": "x"},
        }) + "\n")
        return path

    def test_an_interactive_tui_claims_its_pane(self, tmp_path):
        """`originator=codex-tui` with a plain `source=cli` is the roster window the
        operator is looking at, and the only shape that may claim."""
        transcript = self.rollout(tmp_path, "codex-tui", "cli")
        run_hook("session-start.sh",
                 session_start_payload(transcript_path=str(transcript)),
                 tmp_path, env={"TMUX_PANE": "%9"})
        pin = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")[0]
        assert pin["tmux_pane"] == "%9"

    def test_a_headless_exec_run_claims_nothing(self, tmp_path):
        """The case the hazard is about: `codex exec` shelled out of a roster window
        inherits that window's TMUX_PANE, and writes `originator=codex_exec`."""
        transcript = self.rollout(tmp_path, "codex_exec", "exec")
        run_hook("session-start.sh",
                 session_start_payload(transcript_path=str(transcript)),
                 tmp_path, env={"TMUX_PANE": "%9"})
        pin = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")[0]
        assert pin["tmux_pane"] == ""

    def test_a_subagent_claims_nothing_despite_the_tui_originator(self, tmp_path):
        """The reason the gate reads both fields. A subagent is spawned *by* a TUI and
        inherits `originator=codex-tui`, so `originator` alone would hand it the
        parent's read view — the nested case the hazard is entirely about. Its
        `source` is an object rather than the string `cli`, measured on 0.148.0."""
        transcript = self.rollout(tmp_path, "codex-tui",
                                  {"subagent": {"other": "guardian"}})
        run_hook("session-start.sh",
                 session_start_payload(transcript_path=str(transcript)),
                 tmp_path, env={"TMUX_PANE": "%9"})
        pin = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")[0]
        assert pin["tmux_pane"] == ""

    def test_no_tmux_pane_in_the_environment_claims_nothing(self, tmp_path):
        """A session outside tmux has no pane to claim, whatever its rollout says."""
        transcript = self.rollout(tmp_path, "codex-tui", "cli")
        run_hook("session-start.sh",
                 session_start_payload(transcript_path=str(transcript)), tmp_path)
        pin = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")[0]
        assert pin["tmux_pane"] == ""

    def test_an_unreadable_rollout_claims_nothing(self, tmp_path):
        """Fails closed. `transcript_path` is nullable in codex's own schema, and a
        session whose evidence cannot be read is not one to give a pane to."""
        for payload in (session_start_payload(transcript_path=""),
                        session_start_payload(transcript_path="/nope/missing.jsonl")):
            home = tmp_path / f"h{abs(hash(str(payload)))}"
            home.mkdir()
            run_hook("session-start.sh", payload, home, env={"TMUX_PANE": "%9"})
            pin = read_jsonl(home / ".thalamus" / "pins" / "pins.jsonl")[0]
            assert pin["tmux_pane"] == ""

    def test_a_rollout_whose_first_line_is_not_json_claims_nothing(self, tmp_path):
        """The gate parses, rather than pattern-matching a substring: a file that
        merely *contains* `codex-tui` is not a session_meta saying so."""
        transcript = tmp_path / "junk.jsonl"
        transcript.write_text("not json at all — codex-tui cli\n")
        run_hook("session-start.sh",
                 session_start_payload(transcript_path=str(transcript)),
                 tmp_path, env={"TMUX_PANE": "%9"})
        pin = read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")[0]
        assert pin["tmux_pane"] == ""

    def test_env_pin_is_announced_and_recorded(self, tmp_path):
        """Env is the only pin channel on codex: no agent picker, and no `agent_type`
        on its tool payloads."""
        result = run_hook("session-start.sh", session_start_payload(), tmp_path,
                          env={"THALAMUS_SCOPE": "literature"})
        ctx = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        assert ctx.startswith("This session is pinned to expert scope `literature`")
        assert read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")[0]["scope"] \
            == "literature"

    def test_a_claude_code_agent_in_the_environment_does_not_set_the_pin(self, tmp_path):
        """CLAUDE_CODE_AGENT can only reach a codex session by inheritance from some
        Claude Code process up the tree, where it names an agent *definition* codex
        never loaded. Honouring it would apply another persona's boundary to a session
        with none of its tooling."""
        result = run_hook("session-start.sh", session_start_payload(), tmp_path,
                          env={"CLAUDE_CODE_AGENT": "thalamus-qe"})
        ctx = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        assert "pinned to expert scope" not in ctx
        assert read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")[0]["scope"] == "main"

    def test_a_resumed_session_records_its_pin_and_is_not_primed(self, tmp_path):
        """Recording is unconditional, priming is not: a resumed session already
        carries its context, but the ledger row is what session-end resolves the
        distillation scope from and must exist for every source."""
        result = run_hook("session-start.sh",
                          session_start_payload(source="resume"), tmp_path)
        assert json.loads(result.stdout) == {}
        assert read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")


class TestSessionEnd:
    def test_it_distills_directly_with_no_settle_loop(self, tmp_path, monkeypatch):
        """
        Scenario: a codex session ends with its rollout on disk.

        Verifications:
        - the hook resolves the scope ledger-first and logs the distillation it is
          about to run, under the `session-end-<sid8>.log` name the console's
          distillation widget is a state machine over
        - it returns immediately, having forked the work

        No settle loop, and that is measured rather than assumed: the rollout was
        byte-identical at SessionEnd and at process exit (19 lines / 40361 bytes both
        times headless, 14 / 14 in the TUI), and the binary carries "failed to flush
        transcript before SessionEnd hook". Cursor's poll has no reason to be ported.
        """
        rollout = tmp_path / "rollout-2026-08-17T23-58-53-01a013aa.jsonl"
        rollout.write_text('{"type":"session_meta"}\n')
        ledger = tmp_path / ".thalamus" / "pins" / "pins.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps(
            {"session_id": "cx-1", "scope": "literature", "cwd": "/w",
             "room": "", "ts": "2026-08-17T00:00:00Z"}) + "\n")

        # `uv` shimmed so nothing spawns a real extraction: the subject is what the
        # hook decides and records, not what `thalamus extract` then does.
        shim = tmp_path / "bin"
        shim.mkdir()
        (shim / "uv").write_text("#!/bin/sh\necho \"uv $*\"\n")
        (shim / "uv").chmod(0o755)

        result = run_hook(
            "session-end.sh",
            {"session_id": "cx-1", "cwd": "/w", "hook_event_name": "SessionEnd",
             "reason": "other", "transcript_path": str(rollout)},
            tmp_path,
            env={"PATH": f"{shim}:{PATH}"},
        )
        assert result.returncode == 0

        log = tmp_path / ".thalamus" / "logs" / "session-end-cx-1.log"
        assert "distilling session cx-1 into scope literature" in log.read_text()

        # The forked command, read back off the shimmed uv's own echo. Verifies the
        # two flags that are codex's contract: the harness it distills as, and the
        # transcript path — the hook knows the exact file, and re-deriving it by
        # scanning the sessions tree for a matching id is a second chance to pick the
        # wrong one.
        deadline = __import__("time").time() + 20
        text = ""
        while __import__("time").time() < deadline:
            text = log.read_text()
            if "eval sync" in text:
                break
            __import__("time").sleep(0.2)
        assert "extract --harness codex" in text
        assert f"--transcript {rollout}" in text
        assert "--scope literature" in text
        assert "eval sync --write" in text

    def test_a_missing_rollout_with_a_ledger_row_is_recorded_as_a_fault(self, tmp_path):
        """`transcript_path` is nullable in codex's own schema. A ledger row means
        this was a real session, so a missing rollout is a loss worth surfacing —
        the console widget renders it as an error."""
        ledger = tmp_path / ".thalamus" / "pins" / "pins.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps({"session_id": "cx-2", "scope": "main"}) + "\n")

        run_hook("session-end.sh",
                 {"session_id": "cx-2", "cwd": "/w", "hook_event_name": "SessionEnd",
                  "reason": "other", "transcript_path": None},
                 tmp_path)
        log = tmp_path / ".thalamus" / "logs" / "session-end-cx-2.log"
        assert "nothing to distill" in log.read_text()

    def test_a_session_with_no_ledger_row_leaves_nothing_behind(self, tmp_path):
        """The residue rule: with neither a rollout nor a ledger row there is nothing
        to distill and nothing worth a log file. On Claude Code the same test keeps
        1234-of-1826 subagent logs out of the directory."""
        run_hook("session-end.sh",
                 {"session_id": "cx-3", "cwd": "/w", "hook_event_name": "SessionEnd",
                  "reason": "other", "transcript_path": "/nope.jsonl"},
                 tmp_path)
        assert not (tmp_path / ".thalamus" / "logs").exists()


class TestShellSurface:
    """`Bash`, and it is measured. The rollout says every codex tool call is a
    `custom_tool_call` named `exec` carrying a JavaScript program; the hook payload
    says `{"tool_name": "Bash", "tool_input": {"command": …}}`. The hook layer is what
    a matcher is matched against, so it is the one these follow."""

    def test_the_guard_blocks_with_claude_codes_exit_two_protocol(self, tmp_path):
        """No permission JSON to build: exit 2 plus stderr is codex's documented
        blocking channel, the same one the real guard already speaks."""
        result = run_hook(
            "gremlin-guard.sh",
            {"hook_event_name": "PreToolUse", "tool_name": "Bash",
             "tool_input": {"command": DOOMED_GREMLIN},
             "session_id": "cx-9", "cwd": "/w", "turn_id": "t1"},
            tmp_path,
        )
        assert result.returncode == 2
        assert "terminal step" in result.stderr
        events = read_jsonl(next((tmp_path / ".thalamus" / "guards").glob("*.jsonl")))
        assert events[-1]["verdict"] == "block"
        assert events[-1]["session_id"] == "cx-9"

    def test_a_terminated_traversal_passes(self, tmp_path):
        result = run_hook(
            "gremlin-guard.sh",
            {"hook_event_name": "PreToolUse", "tool_name": "Bash",
             "tool_input": {"command": DOOMED_GREMLIN.replace("g.V()", "g.V().to_list() #")},
             "session_id": "cx-9", "cwd": "/w"},
            tmp_path,
        )
        assert result.returncode == 0
        events = read_jsonl(next((tmp_path / ".thalamus" / "guards").glob("*.jsonl")))
        assert events[-1]["verdict"] == "pass"

    def test_the_write_guard_denies_a_self_write(self, tmp_path):
        result = run_hook(
            "write-guard.sh",
            {"hook_event_name": "PreToolUse", "tool_name": "Bash",
             "tool_input": {"command": "uv run thalamus " + "write /tmp/session.yaml"},
             "session_id": "cx-9", "cwd": "/w"},
            tmp_path,
        )
        assert result.returncode == 2
        assert "writes memory from inside a session" in result.stderr

    def test_a_single_output_string_lands_on_the_stdout_leg_of_the_trace(self, tmp_path):
        """
        Scenario: an executed inline gremlin command, with codex's shell result.

        The one place codex's payload is not literally Claude Code's: the result is
        a single string where Claude Code sends `{stdout, stderr, …}`. The real tap
        reads `.tool_response.stdout`, so an unreshaped payload would record every
        ad-hoc gremlin query with an empty response — priced at zero injected chars
        and read as a traversal that returned nothing, which is the exact failure the
        gremlin skill exists to prevent.
        """
        result = run_hook(
            "gremlin-tap.sh",
            {"hook_event_name": "PostToolUse", "tool_name": "Bash",
             "tool_input": {"command": DOOMED_GREMLIN},
             "tool_response": "v[abc]\n",
             "session_id": "cx-9", "cwd": "/w", "turn_id": "t1"},
            tmp_path,
        )
        assert result.returncode == 0
        traces = read_jsonl(next((tmp_path / ".thalamus" / "traces").glob("*.jsonl")))
        assert traces[-1]["tool_name"] == "bash_gremlin"
        assert traces[-1]["tool_response"] == "v[abc]\n"
        assert traces[-1]["session_id"] == "cx-9"

    def test_a_non_gremlin_command_leaves_no_trace(self, tmp_path):
        run_hook("gremlin-tap.sh",
                 {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                  "tool_input": {"command": "git status"}, "tool_response": "clean",
                  "session_id": "cx-9"},
                 tmp_path)
        assert not (tmp_path / ".thalamus" / "traces").exists()

    def test_a_validated_query_is_staged_from_a_string_response_too(self, tmp_path):
        """recipe-stage's admission threshold is "it RAN and RETURNED something", so
        the same reshape decides between a staged recipe and silence."""
        run_hook(
            "recipe-stage.sh",
            {"hook_event_name": "PostToolUse", "tool_name": "Bash",
             "tool_input": {"command": DOOMED_GREMLIN.replace("g.V()", "g.V().to_list() #")},
             "tool_response": "[v[123], v[456]]\n", "session_id": "cx-9", "cwd": "/w"},
            tmp_path,
        )
        staged = read_jsonl(tmp_path / ".thalamus" / "recipes" / "staged.jsonl")
        assert staged[-1]["surface"] == "gremlin-python"
        assert staged[-1]["response_chars"] > 0


class TestMcpSurface:
    def test_a_thalamus_call_is_traced_with_no_reshaping(self, tmp_path):
        """
        Scenario: an MCP retrieval, in the payload codex actually sends.

        Cursor needed `mcp-tap.sh` to re-prefix a bare tool name and move
        `result_json` onto `tool_response`. Codex needs neither: measured against a
        live run with the server registered through `codex mcp add`, the payload
        carries `mcp__thalamus__memory_open_threads` and a
        `{"content": [{"type": "text", …}]}` response — Claude Code's naming and
        Claude Code's envelope. So the trace must land through the real script under
        its own name, not through a rename.
        """
        result = run_hook(
            "post-tool-use.sh",
            {"hook_event_name": "PostToolUse",
             "tool_name": "mcp__thalamus__memory_open_threads",
             "tool_input": {"project": "thalamus"},
             "tool_response": {"content": [{"type": "text", "text": "## open thread"}]},
             "tool_use_id": "call_1", "session_id": "cx-9", "cwd": "/w", "turn_id": "t1"},
            tmp_path,
        )
        assert result.returncode == 0
        traces = read_jsonl(next((tmp_path / ".thalamus" / "traces").glob("*.jsonl")))
        assert traces[-1]["tool_name"] == "mcp__thalamus__memory_open_threads"
        assert traces[-1]["tool_response"]["content"][0]["text"] == "## open thread"

    def test_a_foreign_mcp_tool_is_not_traced(self, tmp_path):
        run_hook("post-tool-use.sh",
                 {"hook_event_name": "PostToolUse", "tool_name": "mcp__penpot__get_file",
                  "tool_input": {}, "tool_response": {}, "session_id": "cx-9"},
                 tmp_path)
        assert not (tmp_path / ".thalamus" / "traces").exists()


class TestRoleGuardOnApplyPatch:
    """The one real adapter in the directory.

    Codex's editing tool is `apply_patch` and its argument is a patch envelope: no
    `file_path`, and several files in one call. The guard decides about one target,
    so the adapter lifts each path out of the envelope's own header grammar — parsing
    a declared spec, not guessing at a string, which is the same line
    `harness/transcripts.py` draws when it refuses to infer touched files from a
    shell command.
    """

    def _payload(self, command, **over):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                   "tool_input": {"command": command},
                   "session_id": "cx-9", "cwd": "/home/user/code/myproject",
                   "turn_id": "t1"}
        payload.update(over)
        return payload

    def test_a_denied_path_anywhere_in_the_patch_denies_the_whole_call(self, tmp_path):
        """apply_patch applies atomically, so a partial verdict has no meaning: either
        every file it names may be written or the call may not run. The permitted file
        comes first here deliberately — a loop that stopped at the first allow would
        pass this."""
        result = run_hook(
            "role-guard.sh",
            self._payload(patch(("Update File", "/repo/docs/notes.md"),
                                ("Update File", "/repo/src/thalamus/cli.py"))),
            tmp_path,
            env={"THALAMUS_SCOPE": "qe"},
        )
        assert result.returncode == 2
        assert "/repo/src/thalamus/cli.py" in result.stderr

    def test_the_guard_row_names_apply_patch_rather_than_a_claude_code_editor(self, tmp_path):
        """The guard ledger is read as evidence. Translating the tool to `Write` to
        fit the Claude Code matcher would put a tool codex does not have into it."""
        run_hook("role-guard.sh",
                 self._payload(patch(("Update File", "/repo/src/thalamus/cli.py"))),
                 tmp_path, env={"THALAMUS_SCOPE": "qe"})
        events = read_jsonl(next((tmp_path / ".thalamus" / "guards").glob("*.jsonl")))
        assert events[-1]["tool"] == "apply_patch"
        assert events[-1]["kind"] == "path"
        assert events[-1]["path"] == "/repo/src/thalamus/cli.py"

    def test_every_header_verb_is_read(self, tmp_path):
        """Add, Delete and a rename's destination are writes too; a matcher that saw
        only `Update File` would let a scope create or delete inside its own deny."""
        for verb in ("Add File", "Delete File", "Move to"):
            result = run_hook(
                "role-guard.sh",
                self._payload(patch((verb, "/repo/src/thalamus/new.py"))),
                tmp_path, env={"THALAMUS_SCOPE": "qe"},
            )
            assert result.returncode == 2, verb

    def test_a_relative_target_is_resolved_against_the_cwd(self, tmp_path):
        """A deny_glob like `*/src/*` is matched against the path as written, so
        `src/foo.py` would slip a boundary that `<repo>/src/foo.py` hits."""
        run_hook("role-guard.sh",
                 self._payload(patch(("Update File", "src/thalamus/cli.py")),
                               cwd="/repo"),
                 tmp_path, env={"THALAMUS_SCOPE": "qe"})
        events = read_jsonl(next((tmp_path / ".thalamus" / "guards").glob("*.jsonl")))
        assert events[-1]["path"] == "/repo/src/thalamus/cli.py"

    def test_a_permitted_patch_passes(self, tmp_path):
        result = run_hook(
            "role-guard.sh",
            self._payload(patch(("Update File", "/repo/docs/notes.md"))),
            tmp_path, env={"THALAMUS_SCOPE": "qe"},
        )
        assert result.returncode == 0

    def test_an_mcp_tool_is_passed_through_untouched(self, tmp_path):
        """Codex prefixes MCP tools exactly as Claude Code does, so the capability
        boundary over a named server's surface needs no translation — and the
        adapter must not invent one."""
        result = run_hook(
            "role-guard.sh",
            {"hook_event_name": "PreToolUse", "tool_name": "mcp__penpot__create_shape",
             "tool_input": {}, "session_id": "cx-9", "cwd": "/w"},
            tmp_path, env={"THALAMUS_SCOPE": "qe"},
        )
        assert result.returncode == 2
        events = read_jsonl(next((tmp_path / ".thalamus" / "guards").glob("*.jsonl")))
        assert events[-1]["tool"] == "mcp__penpot__create_shape"
        assert events[-1]["kind"] == "tool"


class TestPromptTiers:
    """Delivered on the event that read the prompt. Cursor needed a spool because
    `beforeSubmitPrompt` cannot inject; codex's UserPromptSubmit both reads `prompt`
    and honours `additionalContext`, so there is no delivery lag and no spool."""

    def _prompt(self, text, session="cx-p"):
        return {"hook_event_name": "UserPromptSubmit", "session_id": session,
                "cwd": "/w", "prompt": text, "turn_id": "t1",
                "model": "gpt-5.6-terra", "permission_mode": "default"}

    def test_the_clock_is_injected_on_the_same_turn(self, tmp_path):
        result = run_hook("timestamp.sh", self._prompt("hi"), tmp_path)
        out = json.loads(result.stdout)
        assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
        assert "Current date and time" in out["hookSpecificOutput"]["additionalContext"]

    def test_a_conditioning_class_fires_and_is_stamped_codex(self, tmp_path):
        """`thalamus eval conditioning` joins on the harness, so codex's firings must
        not be averaged in with the other two."""
        result = run_hook("conditioning.sh",
                          self._prompt("let's design a new component"), tmp_path)
        assert "ground-in-literature" in \
            json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        log = next((tmp_path / ".thalamus" / "conditioning").glob("*.jsonl"))
        assert read_jsonl(log)[-1]["harness"] == "codex"

    def test_the_throttle_still_holds_across_the_delegation(self, tmp_path):
        for _ in range(2):
            run_hook("conditioning.sh",
                     self._prompt("let's design a thing", session="cx-t"), tmp_path)
        log = next((tmp_path / ".thalamus" / "conditioning").glob("*.jsonl"))
        assert len([r for r in read_jsonl(log) if r["class"] == "design"]) == 1

    def test_the_first_prompt_marks_engaged_once(self, tmp_path):
        for _ in range(2):
            result = run_hook("pin-engaged.sh", self._prompt("hello", "cx-e"), tmp_path)
            assert result.returncode == 0
        engaged = [p for p in read_jsonl(tmp_path / ".thalamus" / "pins" / "pins.jsonl")
                   if p.get("event") == "engaged"]
        assert len(engaged) == 1
        assert engaged[0]["session_id"] == "cx-e"


class TestTheSandboxLeavesNoMemory:
    """A headless extraction run is a full codex session to codex — it fires these
    hooks — so unguarded, the hooks that make memory fire inside the machinery that
    makes memory. Every script must decline when the marker is set, including the
    ones that only delegate: a guard checked in the delegator and not the delegate
    would still write the delegate's record."""

    def test_every_hook_declines_inside_a_sandbox(self, tmp_path):
        payloads = {
            "session-start.sh": session_start_payload(),
            "session-end.sh": {"session_id": "s", "cwd": "/w",
                               "transcript_path": "/nope", "hook_event_name": "SessionEnd"},
            "timestamp.sh": {"session_id": "s", "prompt": "hi",
                             "hook_event_name": "UserPromptSubmit"},
            "conditioning.sh": {"session_id": "s", "prompt": "let's design a component",
                                "hook_event_name": "UserPromptSubmit"},
            "pin-engaged.sh": {"session_id": "s", "prompt": "hi",
                               "hook_event_name": "UserPromptSubmit"},
            "gremlin-guard.sh": {"tool_name": "Bash",
                                 "tool_input": {"command": DOOMED_GREMLIN},
                                 "session_id": "s", "hook_event_name": "PreToolUse"},
            "write-guard.sh": {"tool_name": "Bash",
                               "tool_input": {"command": "uv run thalamus "
                                                         "write /tmp/x.yaml"},
                               "session_id": "s", "hook_event_name": "PreToolUse"},
            "room-command-guard.sh": {"tool_name": "Bash",
                                      "tool_input": {"command": "tmux send-keys -t %0 hi"},
                                      "session_id": "s", "hook_event_name": "PreToolUse"},
            "role-guard.sh": {"tool_name": "apply_patch",
                              "tool_input": {"command": patch(
                                  ("Update File", "/repo/src/thalamus/cli.py"))},
                              "session_id": "s", "cwd": "/repo",
                              "hook_event_name": "PreToolUse"},
            "gremlin-tap.sh": {"tool_name": "Bash",
                               "tool_input": {"command": DOOMED_GREMLIN},
                               "tool_response": "v[abc]", "session_id": "s",
                               "hook_event_name": "PostToolUse"},
            "recipe-stage.sh": {"tool_name": "Bash",
                                "tool_input": {"command": DOOMED_GREMLIN},
                                "tool_response": "[v[1]]", "session_id": "s",
                                "hook_event_name": "PostToolUse"},
            "post-tool-use.sh": {"tool_name": "mcp__thalamus__memory_recall",
                                 "tool_input": {}, "tool_response": {},
                                 "session_id": "s", "hook_event_name": "PostToolUse"},
        }
        for script, payload in payloads.items():
            result = run_hook(script, payload, tmp_path,
                              env={"THALAMUS_SANDBOX": "1", "THALAMUS_SCOPE": "qe"})
            assert result.returncode == 0, f"{script} did not decline: {result.stderr[:200]}"
        assert not (tmp_path / ".thalamus").exists(), \
            "a sandboxed run left a record behind"


def test_every_codex_script_is_wired_by_the_installer():
    """The installer's table is the single definition, and on codex it is the *only*
    one: `$CODEX_HOME/hooks.json` is the one file codex loads hooks from, and codex
    does not read `~/.claude/settings.json` at all — so a script shipped here and
    absent from the table does not run through any other path."""
    from thalamus.harness.install import CODEX_HOOK_DIR, build_codex_hook_block

    commands = {h["command"] for groups in build_codex_hook_block().values()
                for g in groups for h in g["hooks"]}
    shipped = {p.name for p in HOOKS.glob("*.sh")} - {"resolve-scope.sh"}
    assert shipped == {c.rsplit("/", 1)[1] for c in commands}
    assert all(c.startswith(str(CODEX_HOOK_DIR)) for c in commands)


def test_the_sourced_library_is_not_executable():
    """`resolve-scope.sh` is sourced, never run. An executable bit on it invites a
    hooks.json entry that would exit immediately having done nothing, and
    `verify_codex`'s executable check would then be asserting the wrong thing about
    it."""
    import os

    assert not os.access(HOOKS / "resolve-scope.sh", os.X_OK)


class TestCodexRoleGuardReadsItsPayloadThroughTheSharedGate:
    """It was the last entry point still parsing its own stdin.

    The three shell guards on this harness `exec` into their Claude Code twins and so
    inherit that prologue, but `role-guard.sh` is a real adapter — it reads
    `tool_name` itself to decide whether to handle `apply_patch` or delegate. Under
    `set -euo pipefail` a payload jq refused killed it at that first read, with jq's
    exit code rather than the blocking one, and codex reads only 2 as a denial.
    """

    def _run_raw(self, stdin, home):
        return subprocess.run(
            [str(HOOKS / "role-guard.sh")], input=stdin, capture_output=True,
            text=True, timeout=60,
            env={"HOME": str(home), "PATH": PATH, "THALAMUS_SCOPE": "main"},
        )

    def test_malformed_json_blocks_with_the_blocking_code(self, tmp_path):
        result = self._run_raw('{"tool_name": "apply_patch", broken', tmp_path)

        assert result.returncode == 2, result.stderr
        assert "not valid JSON" in result.stderr
        assert "role-guard.sh" in result.stderr

    def test_an_empty_payload_blocks(self, tmp_path):
        result = self._run_raw("", tmp_path)

        assert result.returncode == 2, result.stderr
        assert "payload was empty" in result.stderr

    def test_a_readable_patch_outside_an_owned_path_is_still_allowed(self, tmp_path):
        """The control: the gate is on the read, not on the verdict."""
        result = run_hook("role-guard.sh",
                          {"tool_name": "apply_patch",
                           "tool_input": {"command": patch(("Update", str(tmp_path / "notes.md")))},
                           "cwd": str(tmp_path)},
                          tmp_path, env={"THALAMUS_SCOPE": "main"})

        assert result.returncode == 0, result.stderr
