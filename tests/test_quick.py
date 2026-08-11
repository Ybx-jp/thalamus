"""
Quick-protocol tests (docs/02 — the second consultation tier, docs/07 — its launch
mechanics).

Interfaces: thalamus.harness.quick, thalamus.harness.consultation.open_exchange/
refuse_reason
Infrastructure: none; a fake graph, fake session descriptors on tmp_path, and a fake
subprocess runner. No `claude` is launched.
Scope: the launcher's obligations, each of which lab/049 measured as failing
silently — target resolution against the live roster (never the pin ledger), the
parent's own `--agent`, `THALAMUS_FORKED_FROM`, both cache fields, the login notice
that arrives as a well-formed answer with exit 0, and the delta that keeps a fork
from re-asserting its parent's episode.

Grounding: the exchange record is execution provenance for a multi-agent
collaboration step (arXiv 2606.04990) and the citation gate is a write-path defense
(arXiv 2606.04329) — the lighter tier keeps both, which is what these tests pin.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from gremlin_python.process.traversal import Merge

from thalamus.contract.manifest import ExpertManifest
from thalamus.harness import consultation, quick
from thalamus.harness.consultation import exchange_vid


# --------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------


class FakeGraph:
    """Just enough traversal surface for write_exchange, close_exchange, load_exchange."""

    def __init__(self, vertices: dict[str, dict] | None = None):
        self.vertices = dict(vertices or {})
        self.edges: list[dict] = []

    def V(self, vid=None):
        return _VertexChain(self, vid)

    def merge_v(self, spec):
        record = {"spec": spec, "on_create": {}}
        self._pending = record
        return _MergeChain(self, record)

    def merge_e(self, spec):
        record = {"spec": dict(spec), "properties": {}}
        self.edges.append(record)
        return _MergeChain(self, record, properties_key="properties")


class _MergeChain:
    def __init__(self, graph, record, properties_key="on_create"):
        self.graph = graph
        self.record = record
        self.properties_key = properties_key
        self.bytecode = "fake"

    def option(self, key, value):
        if key is Merge.on_create:
            self.record[self.properties_key] = dict(value)
        return self

    def iterate(self):
        spec = self.record.get("spec") or {}
        vid = next((v for k, v in spec.items() if str(k) == "T.id"), None)
        if vid is None:  # T.id is an enum key; find it by value shape instead
            vid = next(
                (v for v in spec.values() if isinstance(v, str) and v.startswith("scope:")),
                None,
            )
        if vid and self.properties_key == "on_create":
            props = {
                k: v for k, v in self.record["on_create"].items() if isinstance(k, str)
            }
            self.graph.vertices.setdefault(vid, {"label": "Exchange"}).update(props)
        return self


class _VertexChain:
    def __init__(self, graph, vid):
        self.graph = graph
        self.vid = vid
        self.keys: tuple[str, ...] = ()
        self.bytecode = "fake"

    def has_label(self, label):
        vertex = self.graph.vertices.get(self.vid)
        if vertex is not None and vertex.get("label") != label:
            self.vid = None
        return self

    def value_map(self, *keys):
        self.keys = keys
        return self

    def limit(self, _n):
        return self

    def to_list(self):
        vertex = self.graph.vertices.get(self.vid)
        if vertex is None:
            return []
        return [{k: [vertex[k]] for k in self.keys if k in vertex}]

    def has_next(self):
        return self.vid in self.graph.vertices

    def property(self, key, value):
        vertex = self.graph.vertices.get(self.vid)
        if vertex is not None:
            vertex[key] = value
        return self

    def iterate(self):
        return self


def write_descriptor(
    config_dir: Path,
    *,
    pid: int,
    session_id: str,
    agent: str = "",
    status: str = "idle",
    cwd: str = "/home/ybx/code/thalamus",
    proc_start: str | None = None,
    updated_at: int = 0,
    key: str = "",
) -> Path:
    """One `$CLAUDE_CONFIG_DIR/sessions/<pid>.json`, in the harness's own shape.

    `key` names the file independently of `pid`, which is how two descriptors can
    both claim a live process: every test here uses the test runner's own pid,
    because that is the one pid guaranteed to be alive with a readable `procStart`.
    """
    sessions = config_dir / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    path = sessions / f"{key or pid}.json"
    path.write_text(
        json.dumps(
            {
                "pid": pid,
                "sessionId": session_id,
                "cwd": cwd,
                "procStart": proc_start if proc_start is not None else quick._proc_start(pid),
                "agent": agent,
                "name": f"n-{pid}",
                "status": status,
                "updatedAt": updated_at,
            }
        )
    )
    return path


def envelope(**overrides) -> str:
    base = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "The answer, citing `scope:homelab:claim:abc`.",
        "session_id": "fork-sid",
        "total_cost_usd": 0.037,
        "duration_ms": 52_000,
        "num_turns": 3,
        "usage": {
            "input_tokens": 15,
            "output_tokens": 400,
            "cache_read_input_tokens": 121_938,
            "cache_creation_input_tokens": 0,
        },
    }
    base.update(overrides)
    return json.dumps(base)


def fake_runner(stdout: str, returncode: int = 0, stderr: str = ""):
    calls: list[dict] = []

    def run(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    run.calls = calls
    return run


# --------------------------------------------------------------------------------------
# Target resolution — the live roster, never the pin ledger
# --------------------------------------------------------------------------------------


def test_a_dead_session_is_not_a_target(tmp_path):
    """
    Scenario: A descriptor file survives the process it described (a kill, not a
    clean exit), and a second names a live process

    Verifications:
    - the stale descriptor is filtered out by the procStart check
    - only the live session is offered

    The pin ledger has no exit event, which is why targets resolve here at all — but
    the descriptor directory is only *close* to the truth, so liveness is pid plus
    procStart against /proc, which also defeats pid reuse (lab/049).
    """
    write_descriptor(
        tmp_path, pid=os.getpid(), session_id="dead", agent="thalamus-homelab",
        proc_start="1", key="dead",
    )
    write_descriptor(
        tmp_path, pid=os.getpid(), session_id="alive", agent="thalamus-homelab",
        key="alive",
    )

    live = quick.live_sessions(tmp_path)

    assert [s.session_id for s in live] == ["alive"]


def test_resolve_target_refuses_zero_rather_than_picking(tmp_path):
    """
    Scenario: No live session is pinned to the requested scope

    Verifications:
    - the refusal names the scope and points at the two real remedies
    - it lists the expert scopes that *are* live

    Forking a dead session's transcript asks a snapshot while closing an exchange
    that reads as a live consultation.
    """
    write_descriptor(tmp_path, pid=os.getpid(), session_id="a", agent="thalamus-teacher")

    with pytest.raises(quick.QuickRefused) as excinfo:
        quick.resolve_target("literature", tmp_path)

    assert "no live session is pinned to scope `literature`" in str(excinfo.value)
    assert "teacher" in str(excinfo.value)


def test_resolve_target_refuses_two_rather_than_picking(tmp_path):
    """
    Scenario: Two live sessions share the requested expert scope

    Verifications:
    - the refusal names both, by session prefix and pid

    Two same-scope members of one room share a `<room>-<scope>` name, so a caller
    cannot address them apart anyway; picking would silently consult whichever the
    filesystem listed first.
    """
    write_descriptor(
        tmp_path, pid=os.getpid(), session_id="one", agent="thalamus-homelab", key="one"
    )
    write_descriptor(
        tmp_path, pid=os.getpid(), session_id="two", agent="thalamus-homelab", key="two"
    )

    with pytest.raises(quick.QuickRefused) as excinfo:
        quick.resolve_target("homelab", tmp_path)

    assert "2 live sessions" in str(excinfo.value)


def test_between_turns_is_busy_or_not(tmp_path):
    """
    Scenario: The harness reports three resting states and one working one

    Verifications:
    - `busy` is the only status that is not between turns

    A mid-turn fork costs 13x the post-turn price and misses the message body the
    parent is still writing — but an *unrecognised* status must not be read as
    mid-turn, or a cheap call turns into a refusal for no reason.
    """
    statuses = {"idle": True, "waiting": True, "": True, "busy": False}
    for index, (status, expected) in enumerate(statuses.items()):
        write_descriptor(
            tmp_path, pid=os.getpid(), session_id=f"s{index}",
            agent="thalamus-homelab", status=status, key="one",
        )
        session = quick.live_sessions(tmp_path)[0]
        assert session.between_turns is expected, status


def test_a_busy_parent_is_forked_not_refused(tmp_path):
    """
    Scenario: The only live session for the scope is mid-turn, and the caller does not
    ask to wait

    Verifications:
    - the busy target is returned, immediately, with no sleeping

    Non-interruption is the reason this tier forks rather than messaging the expert.
    An expert that has to be free before it can be consulted is an expert you
    interrupted, so `busy` is the case the design is *for* — its 13x price and its
    missed message body are recorded, not enforced.
    """
    write_descriptor(
        tmp_path, pid=os.getpid(), session_id="busy-one",
        agent="thalamus-homelab", status="busy",
    )
    slept: list[float] = []

    target = quick.await_target(
        "homelab", wait=0, config_dir_override=tmp_path, sleeper=slept.append
    )

    assert target.session_id == "busy-one"
    assert target.between_turns is False
    assert slept == []


def test_waiting_is_offered_and_gives_up_by_forking(tmp_path):
    """
    Scenario: The caller passes --wait, and the parent lands its turn partway through;
    then a second caller waits out the full deadline on a parent that never does

    Verifications:
    - the wait ends the moment the parent is between turns
    - an expired deadline forks the busy parent rather than refusing

    Waiting spends the caller's latency — the endpoint the tier is justified on — to
    save the fork's dollars, so it is the optimisation and never the gate. A deadline
    that expires means the optimisation did not pay off, not that the consultation
    failed.
    """
    descriptor = write_descriptor(
        tmp_path, pid=os.getpid(), session_id="p", agent="thalamus-homelab",
        status="busy",
    )
    calls: list[float] = []

    def land_the_turn(seconds):
        calls.append(seconds)
        if len(calls) == 2:
            write_descriptor(
                tmp_path, pid=os.getpid(), session_id="p",
                agent="thalamus-homelab", status="idle",
            )

    landed = quick.await_target(
        "homelab", wait=60, config_dir_override=tmp_path, poll=0, sleeper=land_the_turn
    )
    assert landed.between_turns and len(calls) == 2

    descriptor.write_text(descriptor.read_text().replace('"idle"', '"busy"'))
    expired = quick.await_target(
        "homelab", wait=1, config_dir_override=tmp_path, poll=0.5,
        sleeper=time.sleep,
    )
    assert expired.between_turns is False


def test_scope_comes_from_the_launch_agent(tmp_path):
    """
    Scenario: One session was launched with an expert agent, one with none

    Verifications:
    - scope is read off the `thalamus-` agent prefix
    - an unpinned session has an empty scope and is never an expert target
    """
    write_descriptor(
        tmp_path, pid=os.getpid(), session_id="pinned", agent="thalamus-homelab", key="a"
    )
    write_descriptor(tmp_path, pid=os.getpid(), session_id="plain", agent="", key="b")

    scopes = {s.session_id: s.scope for s in quick.live_sessions(tmp_path)}

    assert scopes == {"pinned": "homelab", "plain": ""}


# --------------------------------------------------------------------------------------
# The launch line — obligations `--resume` does not carry
# --------------------------------------------------------------------------------------


def _target(**overrides) -> quick.LiveSession:
    fields = {
        "session_id": "parent-sid",
        "pid": 42,
        "proc_start": "1",
        "cwd": "/home/ybx/code/thalamus",
        "agent": "thalamus-homelab",
        "name": "room-homelab",
        "status": "idle",
        "updated_at": 0,
        "descriptor": Path("/dev/null"),
    }
    fields.update(overrides)
    return quick.LiveSession(**fields)


def test_the_fork_carries_the_parents_agent_and_a_preassigned_id():
    """
    Scenario: The launcher builds the fork's command line

    Verifications:
    - `--agent thalamus-<scope>` is present, taken from the parent's own scope
    - `--resume <parent>` and `--fork-session` are both there
    - the fork's session id is assigned rather than parsed out of the envelope

    Omitting `--agent` is the failure mode with no symptom: the fork still reads the
    *pinned* prefix and answers in the expert's voice, while its ledger row records
    `scope=main, agent=""` (lab/049).
    """
    argv = quick.fork_argv(_target(), "homelab", "fork-uuid")

    assert "--fork-session" in argv
    assert argv[argv.index("--resume") + 1] == "parent-sid"
    assert argv[argv.index("--agent") + 1] == "thalamus-homelab"
    assert argv[argv.index("--session-id") + 1] == "fork-uuid"


def test_the_fork_carries_whatever_preconditions_the_harness_declares(monkeypatch):
    """
    Scenario: the launched harness declares a precondition for running headless

    Verifications:
    - a declared precondition reaches the launch line
    - it precedes the flags it is a precondition of

    This is the lab/054 seam, which is invisible while Claude Code declares none: a
    launch line rebuilt from `binary` reads correct and silently drops the flag the
    harness refuses to start without. Cursor's `--trust` reached extraction and no
    other call site for exactly that reason.
    """
    from dataclasses import replace

    from thalamus.harness import agents

    declared = replace(agents.cli_for("claude"), headless_preconditions=("--trust",))
    monkeypatch.setattr(agents, "AGENT_CLIS", {**agents.AGENT_CLIS, "claude": declared})

    argv = quick.fork_argv(_target(), "homelab", "fork-uuid")

    assert "--trust" in argv
    assert argv.index("--trust") < argv.index("--resume")


def test_the_fork_inherits_the_room_and_is_told_its_parent():
    """
    Scenario: A caller inside a room launches a fork

    Verifications:
    - THALAMUS_FORKED_FROM names the parent session
    - CLAUDE_CONFIG_DIR is passed through untouched, so the fork lands in the room's
      projects/ with the launcher doing nothing

    `forked_from` is the field whose absence turns a fork into a fake independent
    witness; the harness tells the forked process nothing about the session it was
    resumed from, so only the launcher can record it.
    """
    env = quick.fork_env(_target(), {"CLAUDE_CONFIG_DIR": "/home/ybx/.thalamus/rooms/r"})

    assert env["THALAMUS_FORKED_FROM"] == "parent-sid"
    assert env["CLAUDE_CONFIG_DIR"] == "/home/ybx/.thalamus/rooms/r"


def test_the_fork_runs_in_the_parents_cwd():
    """
    Scenario: The launcher runs the fork

    Verifications:
    - cwd is the parent's, from the roster entry

    A temp dir files the transcript under a project dir `discover()` withholds, and
    the "Unknown project dir(s)" exit lands in a detached log — so it fails silently.
    """
    runner = fake_runner(envelope())

    quick.run_fork(_target(cwd="/srv/box"), "homelab", "q", runner=runner)

    assert runner.calls[0]["cwd"] == "/srv/box"


def test_both_cache_fields_are_recorded():
    """
    Scenario: A fork of a just-active parent reads the whole prefix from cache

    Verifications:
    - read and creation token counts are both kept
    - cache_hit is the ratio, and the price dict carries every field

    A cost figure taken without `cache_read_input_tokens` measured the one regime the
    protocol never runs in, and was wrong by 16x.
    """
    run = quick.run_fork(_target(), "homelab", "q", runner=fake_runner(envelope()))

    assert run.cache_read_input_tokens == 121_938
    assert run.cache_creation_input_tokens == 0
    assert run.cache_hit == 1.0
    price = run.price()
    assert price["cache_read_input_tokens"] == 121_938
    assert price["cost_usd"] == 0.037
    assert price["wall_ms"] >= 0


def test_a_login_notice_is_not_an_answer():
    """
    Scenario: The launcher shells into a config dir it is not authenticated for

    Verifications:
    - the well-formed envelope with exit 0 is refused, not recorded as an answer

    Found by accident (lab/049): the result string needs checking, not just the exit
    code.
    """
    payload = envelope(result="Not logged in · Please run /login", num_turns=1)

    with pytest.raises(quick.QuickRefused) as excinfo:
        quick.run_fork(_target(), "homelab", "q", runner=fake_runner(payload))

    assert "login notice" in str(excinfo.value)


def test_the_question_arrives_inside_a_frame_break():
    """
    Scenario: The launcher renders the prompt

    Verifications:
    - the wrapper says a different session is asking, and names the calling scope
    - the grant, the brief's absence, and both obligations are stated

    One measured fork read a bare appended question as a prompt injection into its
    parent's frame, declined it, and summarised the parent's open tasks instead.
    """
    prompt = quick.fork_prompt(
        ticket="abc123", question="Which port does the console bind?",
        from_scope="main", scope="homelab", grant="fork of X",
    )

    assert "not a continuation" in prompt
    assert "`main`" in prompt and "`homelab`" in prompt
    assert "No brief was served" in prompt
    assert 'ticket="abc123"' in prompt


def test_the_prompt_counts_as_a_user_turn(tmp_path):
    """
    Scenario: The fork's delta is parsed for distillation, and its only user record
    is the launcher's prompt

    Verifications:
    - `transcripts.parse` counts it as a turn

    A `<`-prefixed user record is harness scaffolding rather than a turn, so a prompt
    that opens with the frame-break tag gives the delta zero user turns and
    extraction declines it as a non-conversation. Measured on the first live call: it
    answered correctly and distilled nothing. Asserted against the parser itself, not
    against a restatement of its rule.
    """
    from thalamus.harness import transcripts

    prompt = quick.fork_prompt(
        ticket="abc123", question="q?", from_scope="main", scope="homelab", grant="g"
    )
    path = _transcript(
        tmp_path / "p" / "fork.jsonl",
        [{"uuid": "u1", "type": "user", "cwd": "/home/ybx/code/thalamus",
          "message": {"role": "user", "content": prompt}}],
    )

    assert transcripts.parse(path).user_turns == 1


def test_the_fork_is_told_not_to_close_the_exchange():
    """
    Scenario: The launcher renders the prompt

    Verifications:
    - the fork is told its reply is the answer, and not to call consult_answer

    Closing is acceptance, and acceptance is downstream of the ledger check: a fork
    that burns its own ticket through the MCP tool closes the exchange before the
    check that would have gated it can run.
    """
    prompt = quick.fork_prompt(
        ticket="abc123", question="q?", from_scope="main", scope="homelab", grant="g"
    )

    assert "Do NOT call `consult_answer`" in prompt


# --------------------------------------------------------------------------------------
# The ledger assertion — the divergence with no other symptom
# --------------------------------------------------------------------------------------


def _pins(tmp_path: Path, *rows: dict) -> Path:
    path = tmp_path / "pins.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def test_ledger_assertion_catches_the_silently_unpinned_fork(tmp_path):
    """
    Scenario: A fork was launched without `--agent`, so it filed as main

    Verifications:
    - the scope divergence and the missing agent are both reported
    - the answer's text is not consulted, because it looks correct either way
    """
    pins = _pins(
        tmp_path,
        {"session_id": "fork-sid", "scope": "main", "agent": "", "forked_from": "parent-sid"},
    )

    issues = quick.assert_ledger("fork-sid", "homelab", "parent-sid", pins)

    assert any("scope `main`" in issue for issue in issues)
    assert any("agent `(none)`" in issue for issue in issues)


def test_ledger_assertion_catches_a_fork_filing_as_independent(tmp_path):
    """
    Scenario: THALAMUS_FORKED_FROM was not set, so the fork records no parent

    Verifications:
    - the missing link is reported in the terms that make it matter — agreement with
      the parent would otherwise read as independent corroboration
    """
    pins = _pins(
        tmp_path,
        {"session_id": "fork-sid", "scope": "homelab", "agent": "thalamus-homelab",
         "forked_from": ""},
    )

    issues = quick.assert_ledger("fork-sid", "homelab", "parent-sid", pins)

    assert len(issues) == 1
    assert "independent corroboration" in issues[0]


def test_a_clean_fork_asserts_clean(tmp_path):
    """
    Scenario: The launcher met all three obligations, and the ledger agrees

    Verifications:
    - no divergences, and last-row-wins across an earlier stale row
    """
    pins = _pins(
        tmp_path,
        {"session_id": "fork-sid", "scope": "main", "agent": "", "forked_from": ""},
        {"session_id": "fork-sid", "scope": "homelab", "agent": "thalamus-homelab",
         "forked_from": "parent-sid"},
    )

    assert quick.assert_ledger("fork-sid", "homelab", "parent-sid", pins) == []


def test_the_engaged_lifecycle_row_does_not_overwrite_the_pin_row(tmp_path):
    """
    Scenario: `pin-engaged.sh` appends its `{event: "engaged"}` row after the fork's
    pin row, carrying scope but no agent and no forked_from

    Verifications:
    - the assertion reads the pin row, not the lifecycle row, and finds it clean

    Measured on the first live quick call: the ledger row was correct and the
    assertion said the launcher had met none of its obligations, because last-wins
    across both row shapes reads the two missing fields as empty.
    """
    pins = _pins(
        tmp_path,
        {"session_id": "fork-sid", "scope": "homelab", "agent": "thalamus-homelab",
         "forked_from": "parent-sid"},
        {"event": "engaged", "session_id": "fork-sid", "scope": "homelab"},
    )

    assert quick.assert_ledger("fork-sid", "homelab", "parent-sid", pins) == []


def test_a_missing_ledger_row_is_a_divergence_not_a_pass(tmp_path):
    """
    Scenario: SessionStart never fired for the fork

    Verifications:
    - the absence is reported, rather than read as "nothing wrong"

    Silence and "verified clean" are the same bytes otherwise, and only one of them
    is auditable.
    """
    issues = quick.assert_ledger("fork-sid", "homelab", "parent-sid", tmp_path / "none.jsonl")

    assert len(issues) == 1
    assert "no pin-ledger row" in issues[0]


# --------------------------------------------------------------------------------------
# The delta — a fork's transcript is its parent's, restamped
# --------------------------------------------------------------------------------------


def _transcript(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def test_the_delta_is_an_exact_uuid_set_difference(tmp_path):
    """
    Scenario: A fork's JSONL restamps every one of its parent's records with the
    fork's own sessionId, keeping the parent's message UUIDs verbatim

    Verifications:
    - inherited records are dropped however new their timestamps look
    - only the fork's own turn survives

    Distilling the whole file mints a second Session re-asserting the parent's
    episode and archives a second near-identical Source the archive cannot dedup.
    """
    parent = _transcript(
        tmp_path / "p" / "parent.jsonl",
        [{"uuid": "u1", "sessionId": "parent", "timestamp": "2026-08-09T00:00:00Z"},
         {"uuid": "u2", "sessionId": "parent", "timestamp": "2026-08-09T00:01:00Z"}],
    )
    fork = _transcript(
        tmp_path / "p" / "fork.jsonl",
        [{"uuid": "u1", "sessionId": "fork", "timestamp": "2026-08-09T09:00:00Z"},
         {"uuid": "u2", "sessionId": "fork", "timestamp": "2026-08-09T09:00:01Z"},
         {"uuid": "u3", "sessionId": "fork", "timestamp": "2026-08-09T09:00:02Z"}],
    )

    kept = [json.loads(line) for line in quick.delta_records(fork, parent)]

    assert [r["uuid"] for r in kept] == ["u3"]


def test_staging_the_delta_preserves_the_project_dir_name(tmp_path):
    """
    Scenario: A fork's transcript is staged for distillation

    Verifications:
    - the staged file keeps its project dir name and its own filename, so
      `extract --projects-dir <root> -- <dir>` runs unchanged
    """
    projects = tmp_path / "projects"
    _transcript(projects / "-home-ybx-code-thalamus" / "parent.jsonl", [{"uuid": "u1"}])
    fork = _transcript(
        projects / "-home-ybx-code-thalamus" / "fork.jsonl",
        [{"uuid": "u1"}, {"uuid": "u2"}],
    )

    root = quick.stage_delta(fork, "parent", tmp_path / "forks")

    staged = root / "-home-ybx-code-thalamus" / "fork.jsonl"
    assert staged.is_file()
    assert [json.loads(line)["uuid"] for line in staged.read_text().splitlines()] == ["u2"]


def test_staging_refuses_when_the_parent_transcript_is_gone(tmp_path):
    """
    Scenario: The parent's transcript has been rotated away

    Verifications:
    - staging refuses rather than falling back to the whole file

    Not distilling this fork is a better outcome than re-asserting its parent's
    episode as a second Session.
    """
    projects = tmp_path / "projects"
    fork = _transcript(projects / "proj" / "fork.jsonl", [{"uuid": "u2"}])

    with pytest.raises(quick.QuickRefused) as excinfo:
        quick.stage_delta(fork, "parent", tmp_path / "forks")

    assert "refusing to distill the fork whole" in str(excinfo.value)


def test_fresh_recalls_are_counted_from_the_forks_own_records():
    """
    Scenario: The fork recalls once with the ticket, once without, and calls a
    non-memory tool

    Verifications:
    - only in-ticket thalamus calls count

    The tier's third obligation is what converts warmth from retrieval replacement
    into cache revalidation; counted from the records rather than from the answer's
    prose, so it cannot be satisfied by claiming to have recalled.
    """
    records = [
        json.dumps({"message": {"content": [
            {"type": "tool_use", "name": "mcp__thalamus__memory_recall",
             "input": {"query": "x", "ticket": "abc123"}},
            {"type": "tool_use", "name": "mcp__thalamus__memory_recall",
             "input": {"query": "y"}},
            {"type": "tool_use", "name": "Read", "input": {"ticket": "abc123"}},
        ]}}),
    ]

    assert quick.count_fresh_recalls(records, "abc123") == 1


# --------------------------------------------------------------------------------------
# End to end — the record the tier keeps
# --------------------------------------------------------------------------------------


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """A consultable `homelab` expert, one live session, and no real subprocess."""
    manifest = ExpertManifest(scope="homelab", name="Homelab", domain="self-hosting")
    monkeypatch.setattr(consultation, "available_scopes", lambda: ["homelab", "main"])
    monkeypatch.setattr(consultation, "load_manifest", lambda scope: manifest)
    write_descriptor(
        tmp_path, pid=os.getpid(), session_id="parent-sid", agent="thalamus-homelab"
    )
    # The parent has had at least one turn, so there is a conversation to resume —
    # the difference between a live session and a forkable one.
    _transcript(
        tmp_path / "projects" / "-home-ybx-code-thalamus" / "parent-sid.jsonl",
        [{"uuid": "u1", "type": "user", "message": {"role": "user", "content": "hi"}}],
    )
    return tmp_path


def _cited_graph() -> FakeGraph:
    return FakeGraph({"scope:homelab:claim:abc": {"label": "Claim", "description": "x"}})


def test_a_quick_exchange_records_the_briefs_absence_and_prices_itself(wired, monkeypatch):
    """
    Scenario: A main-pinned caller consults a live homelab expert by fork

    Verifications:
    - the Exchange is minted `protocol: quick` with `brief_served: False` and the
      degenerate grant, before the fork runs
    - the parent session, the fork session and the parent's recency ride the record
    - the answer closes through the unchanged citation gate
    - both cache fields and the wall clock land on the exchange

    Silence and "no brief served" are the same bytes, and only one is auditable
    (docs/02); the entire justification for the tier is a latency claim, so an
    exchange that does not log its own cost makes that claim unfalsifiable.
    """
    graph = _cited_graph()
    pins = _pins(
        wired,
        {"session_id": "fork-sid", "scope": "homelab", "agent": "thalamus-homelab",
         "forked_from": "parent-sid"},
    )

    result = quick.consult(
        graph, "homelab", "Which port does the console bind?", "main",
        config_dir_override=wired, pins_file=pins,
        runner=fake_runner(envelope()),
    )

    record = graph.vertices[exchange_vid(result.ticket)]
    assert record["protocol"] == "quick"
    assert record["brief_served"] is False
    assert record["grant"].startswith("fork of session parent-sid")
    assert record["parent_session"] == "parent-sid"
    assert record["fork_session"] == "fork-sid"
    assert record["cache_read_input_tokens"] == 121_938
    assert record["status"] == "answered"
    assert record["closed_by"] == "launcher"
    assert result.accepted


def test_a_fork_that_closes_its_own_ticket_is_recorded_as_having_done_so(wired):
    """
    Scenario: The fork calls consult_answer itself despite being told not to, closing
    the exchange before the launcher's ledger check runs

    Verifications:
    - the answer stands, and `closed_by` records that the fork closed it
    - the report says the citations validated and the ordering did not

    Closing is acceptance, and acceptance is downstream of the ledger check — a gate
    the answerer can step around is a gate that reports what happened rather than one
    that prevents it, and the record has to say which.
    """
    graph = _cited_graph()
    pins = _pins(
        wired,
        {"session_id": "fork-sid", "scope": "homelab", "agent": "thalamus-homelab",
         "forked_from": "parent-sid"},
    )

    def runner(argv, **kwargs):
        for vertex in graph.vertices.values():
            if vertex.get("label") == "Exchange":
                vertex["status"] = "answered"
        return subprocess.CompletedProcess(argv, 0, envelope(), "")

    result = quick.consult(
        graph, "homelab", "q?", "main",
        config_dir_override=wired, pins_file=pins, runner=runner,
    )

    record = graph.vertices[exchange_vid(result.ticket)]
    assert record["closed_by"] == "fork"
    assert result.accepted
    assert "ordering did not" in result.close_report


def test_a_diverged_ledger_row_blocks_acceptance(wired):
    """
    Scenario: The fork answered well, but filed as scope `main`

    Verifications:
    - the exchange stays open and the answer is not accepted
    - the divergence is recorded on the exchange, not only printed

    The model side is right and only the record side is wrong — the failure with no
    symptom, and the one that quietly moves an expert's episode across a scope
    boundary.
    """
    graph = _cited_graph()
    pins = _pins(
        wired,
        {"session_id": "fork-sid", "scope": "main", "agent": "", "forked_from": ""},
    )

    result = quick.consult(
        graph, "homelab", "Which port does the console bind?", "main",
        config_dir_override=wired, pins_file=pins,
        runner=fake_runner(envelope()),
    )

    record = graph.vertices[exchange_vid(result.ticket)]
    assert record["status"] == "open"
    assert "ledger_assert" in record
    assert not result.accepted


def test_an_uncitable_answer_leaves_the_ticket_open(wired):
    """
    Scenario: The fork answers from inherited context without citing anything

    Verifications:
    - the close is rejected and the exchange stays open
    - the cost is recorded anyway, because it was still spent

    The lighter tier does not get to bend the audit: `contract check` constrains
    Exchange status, not protocol, and its one real invariant is that an answered
    exchange cites something (arXiv 2606.04329).
    """
    graph = _cited_graph()
    pins = _pins(
        wired,
        {"session_id": "fork-sid", "scope": "homelab", "agent": "thalamus-homelab",
         "forked_from": "parent-sid"},
    )

    result = quick.consult(
        graph, "homelab", "Which port does the console bind?", "main",
        config_dir_override=wired, pins_file=pins,
        runner=fake_runner(envelope(result="Port 8443, I remember it.")),
    )

    record = graph.vertices[exchange_vid(result.ticket)]
    assert record["status"] == "open"
    assert record["cost_usd"] == 0.037
    assert not result.accepted
    assert result.close_report.startswith("Rejected")


def test_a_live_session_that_never_had_a_turn_is_not_forkable(wired):
    """
    Scenario: An expert was spawned seconds ago and has not been spoken to

    Verifications:
    - the refusal fires before the exchange is minted, so nothing is spent
    - no fork is launched

    A session registers in the live roster the moment it starts and files no transcript
    until its first turn, so `--resume` exits 1 with `No conversation found`. Measured
    on the roster this launcher was verified against, where three of four live experts
    were in exactly this state.
    """
    graph = FakeGraph()
    runner = fake_runner(envelope())
    (wired / "projects" / "-home-ybx-code-thalamus" / "parent-sid.jsonl").unlink()

    with pytest.raises(quick.QuickRefused) as excinfo:
        quick.consult(
            graph, "homelab", "q?", "main",
            config_dir_override=wired, runner=runner,
        )

    assert "no conversation yet" in str(excinfo.value)
    assert runner.calls == []
    assert graph.vertices == {}


def test_a_fork_that_dies_leaves_an_explained_open_exchange(wired):
    """
    Scenario: The fork returns a login notice instead of an answer

    Verifications:
    - the refusal propagates, and the open exchange records why

    "Never answered" and "answered by a login notice" are the same open row
    otherwise, and only one of them is a bug in the launcher.
    """
    graph = _cited_graph()
    payload = envelope(result="Not logged in · Please run /login", num_turns=1)

    with pytest.raises(quick.QuickRefused):
        quick.consult(
            graph, "homelab", "q?", "main",
            config_dir_override=wired, runner=fake_runner(payload),
        )

    exchange = next(
        v for k, v in graph.vertices.items() if k.startswith("scope:main:exchange:")
    )
    assert exchange["status"] == "open"
    assert "login notice" in exchange["fork_error"]


def test_consulting_a_scope_with_no_manifest_spends_nothing(wired):
    """
    Scenario: The caller names something that is not an expert

    Verifications:
    - the refusal is the same one the full ticket gives, and no fork is launched

    The quick protocol is a second tier of one exchange, not a second protocol.
    """
    runner = fake_runner(envelope())

    with pytest.raises(quick.QuickRefused):
        quick.consult(
            FakeGraph(), "nosuch", "q?", "main",
            config_dir_override=wired, runner=runner,
        )

    assert runner.calls == []
