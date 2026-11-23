"""Session type: attended versus autonomous sessions (#394).

An autonomous session — one with no operator present — distils at tier 2 with a marker
on every node, never rewrites a node an attended session holds, and its threads stay
out of the operator's queue until the operator promotes one. These tests hold each of
those at the layer that decides it: the launch-time resolution (Python and its bash
mirror), the schema's provenance, the writer's on-match rule, the reader's queue split,
and the promotion ledger.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from gremlin_python.process.traversal import Merge

from thalamus.harness import pin, promotions
from thalamus.substrate import reader, writer
from thalamus.substrate.schema import (
    Artifact,
    ArtifactType,
    Decision,
    Provenance,
    SessionGraph,
    SessionType,
    Thread,
    ThreadRef,
    Tier,
    Tool,
)

HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks"


# ---------------------------------------------------------------------------
# Resolution at launch


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, SessionType.ATTENDED),
        ({"CLAUDE_CODE_ENTRYPOINT": "cli"}, SessionType.ATTENDED),
        ({"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}, SessionType.AUTONOMOUS),
        ({"CLAUDE_CODE_ENTRYPOINT": "sdk-py"}, SessionType.AUTONOMOUS),
        # A launcher acting for the operator marks a headless run attended.
        ({"CLAUDE_CODE_ENTRYPOINT": "sdk-cli", "THALAMUS_SESSION_TYPE": "attended"},
         SessionType.ATTENDED),
        ({"CLAUDE_CODE_ENTRYPOINT": "cli", "THALAMUS_SESSION_TYPE": "autonomous"},
         SessionType.AUTONOMOUS),
        ({"THALAMUS_SESSION_TYPE": " Autonomous "}, SessionType.AUTONOMOUS),
        # A value that is neither type is not trusted; the entrypoint decides.
        ({"CLAUDE_CODE_ENTRYPOINT": "sdk-cli", "THALAMUS_SESSION_TYPE": "operator"},
         SessionType.AUTONOMOUS),
    ],
)
def test_launch_resolution(env, expected, tmp_path):
    """A headless run nobody marked is autonomous; a declaration wins — at launch, and
    in a process that finds no ledger row for its session."""
    assert _resolve(env) == expected.value
    assert pin.process_session_type(env, tmp_path / "none.jsonl") is expected


def test_a_process_reads_its_session_row_before_its_environment(tmp_path):
    """The MCP server and `quick ask` resolve the session they serve from its pin row,
    which Claude Code names in CLAUDE_CODE_SESSION_ID."""
    ledger = tmp_path / "pins.jsonl"
    ledger.write_text(json.dumps({"session_id": "s1", "scope": "main",
                                  "session_type": "autonomous", "entrypoint": "sdk-cli"}) + "\n")
    # The row wins over what the environment would say.
    env = {"CLAUDE_CODE_SESSION_ID": "s1", "CLAUDE_CODE_ENTRYPOINT": "cli"}
    assert pin.process_session_type(env, ledger) is SessionType.AUTONOMOUS
    # A session with no row falls back to the launch rule.
    other = {"CLAUDE_CODE_SESSION_ID": "s2", "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}
    assert pin.process_session_type(other, ledger) is SessionType.AUTONOMOUS
    # A plain shell outside any session is the operator's.
    assert pin.process_session_type({}, ledger) is SessionType.ATTENDED


def _resolve(env: dict[str, str]) -> str:
    script = f'. "{HOOKS / "claude-code" / "resolve-scope.sh"}"; thalamus_resolve_session_type'
    return subprocess.run(
        ["bash", "-c", script],
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", **env},
        capture_output=True, text=True, timeout=30,
    ).stdout


def test_a_legacy_row_is_read_back_by_the_rule_that_resolves_a_live_one():
    """The ledger reader's entrypoint fallback and the launch resolver agree."""
    for entrypoint in ("cli", "sdk-cli", "sdk-ts"):
        launched = _resolve({"CLAUDE_CODE_ENTRYPOINT": entrypoint})
        assert pin.ledger_session_type({"entrypoint": entrypoint}).value == launched


def test_the_ledger_settles_the_type_and_a_legacy_row_falls_back_to_its_entrypoint():
    assert pin.ledger_session_type({"session_type": "autonomous"}) is SessionType.AUTONOMOUS
    assert pin.ledger_session_type(
        {"session_type": "attended", "entrypoint": "sdk-cli"}) is SessionType.ATTENDED
    assert pin.ledger_session_type({"entrypoint": "sdk-cli"}) is SessionType.AUTONOMOUS
    assert pin.ledger_session_type({"entrypoint": "cli"}) is SessionType.ATTENDED
    assert pin.ledger_session_type({}) is None


def test_ledger_facts_carry_the_session_type_and_entrypoint(tmp_path):
    ledger = tmp_path / "pins.jsonl"
    ledger.write_text(
        json.dumps({"session_id": "s1", "scope": "main", "session_type": "autonomous",
                    "entrypoint": "sdk-cli"}) + "\n"
        # A lifecycle row carries neither and must not blank them.
        + json.dumps({"event": "engaged", "session_id": "s1"}) + "\n"
    )
    facts = pin.ledger_facts("s1", ledger)
    assert facts["session_type"] == "autonomous"
    assert facts["entrypoint"] == "sdk-cli"


def _session_start(tmp_path, env):
    payload = {"session_id": "cc-1", "transcript_path": "", "cwd": str(tmp_path),
               "hook_event_name": "SessionStart", "source": "startup"}
    subprocess.run(
        [str(HOOKS / "claude-code" / "session-start.sh")],
        input=json.dumps(payload), capture_output=True, text=True, timeout=30,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin", **env},
        check=True,
    )
    return json.loads((tmp_path / ".thalamus" / "pins" / "pins.jsonl").read_text())


def test_a_headless_run_is_recorded_autonomous_and_a_terminal_session_attended(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert _session_start(tmp_path / "a", {"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"})[
        "session_type"] == "autonomous"
    assert _session_start(tmp_path / "b", {"CLAUDE_CODE_ENTRYPOINT": "cli"})[
        "session_type"] == "attended"


def test_a_quick_fork_declares_itself_attended():
    from thalamus.harness import quick

    target = type("T", (), {"session_id": "parent-1"})()
    env = quick.fork_env(target, base={})
    assert env["THALAMUS_SESSION_TYPE"] == "attended"
    assert _resolve({**env, "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}) == "attended"


# ---------------------------------------------------------------------------
# Provenance


def _session(session_type=SessionType.AUTONOMOUS, **extra) -> SessionGraph:
    return SessionGraph(
        session_id="s-auto",
        timestamp=datetime(2026, 11, 23, tzinfo=UTC),
        tool=Tool.CLAUDE_CODE,
        scope="career",
        project="sensorium",
        summary="A weekly review ran unattended.",
        session_type=session_type,
        **extra,
    )


def test_an_autonomous_session_distils_at_tier_two_and_no_item_can_lift_it():
    session = _session()
    assert session.default_provenance().tier is Tier.CURATED
    tier_one = Provenance(tier=Tier.FIRST_PARTY, source="session:s-auto")
    assert session.provenance_for(tier_one).tier is Tier.CURATED
    # A tier the item already holds below that is kept: the floor only lowers trust.
    wild = Provenance(tier=Tier.WILD, source="feed:x")
    assert session.provenance_for(wild).tier is Tier.WILD


def test_an_attended_session_is_unchanged():
    session = _session(SessionType.ATTENDED)
    assert session.default_provenance().tier is Tier.FIRST_PARTY
    tier_one = Provenance(tier=Tier.FIRST_PARTY, source="session:s-auto")
    assert session.provenance_for(tier_one).tier is Tier.FIRST_PARTY


def test_the_extractor_cannot_choose_the_session_type():
    """The model's YAML is merged onto the launch record; a `session_type` it emits is
    not one of the fields taken from it."""
    from thalamus.harness.extraction import merge_extraction

    merged = merge_extraction(_session(), {"summary": "x", "session_type": "attended"})
    assert merged.session_type is SessionType.AUTONOMOUS


def test_the_extraction_prompt_says_the_user_turns_are_not_the_operator():
    from thalamus.harness.extraction import build_prompt

    autonomous = build_prompt("digest", project="p", title="t", autonomous=True)
    attended = build_prompt("digest", project="p", title="t")
    assert "AUTONOMOUS" in autonomous and "not the operator speaking" in autonomous
    assert "AUTONOMOUS" not in attended


# ---------------------------------------------------------------------------
# The writer


class _Graph:
    """Records merges and property writes; answers the held-session-type read from
    `held` (vertex id -> stored `session_type`, or "" for a pre-field vertex)."""

    def __init__(self, held: dict[str, str] | None = None, threads=()):
        self.held = held or {}
        self.threads = set(threads)
        self.merges: list[dict] = []
        self.edges: list[tuple] = []
        self.properties: list[tuple] = []
        self._vid = None
        self._label = None
        self._pending = None
        self.bytecode = "fake"

    def merge_v(self, match):
        self._pending = {"match": match, "create": None, "on_match": None}
        self.merges.append(self._pending)
        return self

    def merge_e(self, match):
        self.edges.append((match.get("label") if isinstance(match, dict) else match, match))
        self._pending = None
        return self

    def option(self, key, value):
        if self._pending is not None:
            self._pending["create" if key is Merge.on_create else "on_match"] = value
        return self

    def V(self, *args):
        self._vid = args[0] if args else None
        self._label = None
        return self

    def E(self, *_args):
        return self

    def has_label(self, label=None, *_):
        self._label = label
        return self

    def has(self, *_a, **_k):
        return self

    def value_map(self, *_keys):
        return self

    def to_list(self):
        if self._vid in self.held:
            stored = self.held[self._vid]
            return [{"session_type": [stored]} if stored else {}]
        return []

    def has_next(self):
        return self._vid in self.threads or self._vid in self.held

    def property(self, key, value):
        self.properties.append((self._vid, key, value))
        return self

    def project(self, *_):
        return self

    def by(self, *_a, **_k):
        return self

    def iterate(self):
        return self

    # merge_e chains
    def from_(self, *_):
        return self

    def to(self, *_):
        return self


def _ungated(_session):
    return None


def test_every_node_an_autonomous_session_writes_is_marked_and_tier_two():
    session = _session(
        artifacts=[Artifact(identifier="src/a.py", type=ArtifactType.FILE)],
        decisions=[Decision(description="Count boards weekly", rationale="noise",
                            artifacts=["src/a.py"])],
        threads=[Thread(id="review-board-drift", title="Board drift",
                        description="Re-check the board list")],
    )
    g = _Graph()
    writer.write_session(g, session, gate=_ungated)
    created = [m["create"] for m in g.merges]
    assert created and all(c["session_type"] == "autonomous" for c in created)
    assert all(c["tier"] >= int(Tier.CURATED) for c in created)


def test_an_attended_session_marks_its_nodes_attended_at_tier_one():
    session = _session(
        SessionType.ATTENDED,
        decisions=[Decision(description="Count boards weekly", rationale="noise")],
    )
    g = _Graph()
    writer.write_session(g, session, gate=_ungated)
    claim = next(m["create"] for m in g.merges if m["create"].get("kind") == "decision")
    assert claim["session_type"] == "attended"
    assert claim["tier"] == int(Tier.FIRST_PARTY)


def test_an_autonomous_write_never_rewrites_an_attended_node():
    """Attended nodes are never demotable: the autonomous session's own edge is the
    record that it asserted the same thing, and the node keeps the attended account."""
    decision = Decision(description="Count boards weekly", rationale="noise",
                        artifacts=["src/a.py"])
    thread = Thread(id="review-board-drift", title="Board drift", description="d")
    session = _session(
        artifacts=[Artifact(identifier="src/a.py", type=ArtifactType.FILE)],
        decisions=[decision], threads=[thread],
    )
    claim_vid = writer.vid("Claim", decision.content_id(), "career")
    thread_vid = writer.vid("Thread", thread.id, "career")
    artifact_vid = writer.vid("Artifact", "src/a.py")
    # "" is a vertex written before session types existed: attended.
    g = _Graph(held={claim_vid: "attended", thread_vid: "", artifact_vid: "attended"})
    writer.write_session(g, session, gate=_ungated)

    by_id = {m["create"].get(writer.T.id): m for m in g.merges}
    assert by_id[claim_vid]["on_match"] == {}
    assert by_id[thread_vid]["on_match"] == {}
    artifact_on_match = by_id[artifact_vid]["on_match"]
    assert artifact_on_match["type"] == "file"
    assert not {"tier", "source", "session_type"} & set(artifact_on_match)


def test_an_attended_write_never_lifts_an_autonomous_node():
    decision = Decision(description="Count boards weekly", rationale="noise")
    session = _session(SessionType.ATTENDED, decisions=[decision])
    claim_vid = writer.vid("Claim", decision.content_id(), "career")
    g = _Graph(held={claim_vid: "autonomous"})
    writer.write_session(g, session, gate=_ungated)
    claim = next(m for m in g.merges if m["create"].get(writer.T.id) == claim_vid)
    assert claim["on_match"] == {}


def test_a_session_is_not_rewritten_under_the_other_type():
    session_vid = writer.vid("Session", "s-auto", "career")
    with pytest.raises(writer.SessionTypeConflict):
        writer.write_session(_Graph(held={session_vid: "attended"}), _session(),
                             gate=_ungated)
    # A Session written before the field existed takes the type it is written with.
    writer.write_session(_Graph(held={session_vid: ""}), _session(), gate=_ungated)


def test_an_autonomous_session_continues_an_attended_thread_without_moving_it():
    thread_vid = writer.vid("Thread", "ship-the-review", "career")
    g = _Graph(held={thread_vid: "attended"}, threads={thread_vid})
    session = _session(thread_refs=[ThreadRef(id="ship-the-review", status="resolved")])
    writer.write_session(g, session, gate=_ungated)
    assert not [p for p in g.properties if p[1] == "status"]


def test_an_autonomous_session_moves_its_own_thread():
    thread_vid = writer.vid("Thread", "ship-the-review", "career")
    g = _Graph(held={thread_vid: "autonomous"}, threads={thread_vid})
    session = _session(thread_refs=[ThreadRef(id="ship-the-review", status="resolved")])
    writer.write_session(g, session, gate=_ungated)
    assert (thread_vid, "status", "resolved") in g.properties


def test_promotion_sets_where_a_thread_is_listed_and_nothing_else():
    thread_vid = writer.vid("Thread", "t1", "career")
    g = _Graph(held={thread_vid: "autonomous"}, threads={thread_vid})
    writer.write_thread_promotion(g, thread_vid, promoted_at="2026-11-23T00:00:00+00:00",
                                  promotion_ref="pr-1", surface="cli")
    keys = {key for _vid, key, _value in g.properties}
    assert keys == {"promoted_at", "promotion_ref", "promotion_surface"}


def test_an_attended_or_absent_thread_is_not_promotable():
    thread_vid = writer.vid("Thread", "t1", "career")
    with pytest.raises(writer.NotPromotable):
        writer.check_promotable(_Graph(held={thread_vid: "attended"}, threads={thread_vid}),
                                thread_vid)
    with pytest.raises(writer.NotPromotable):
        writer.check_promotable(_Graph(), thread_vid)


# ---------------------------------------------------------------------------
# The promotion ledger


def test_a_promotion_is_recorded_once(tmp_path):
    ledger = tmp_path / "promotions.jsonl"
    row, created = promotions.promote("t1", "career", "cli", path=ledger)
    assert created and row["approver_evidence"] == "cli:tty"
    again, created_again = promotions.promote("t1", "career", "console", path=ledger)
    assert not created_again and again["ref"] == row["ref"]
    assert len(promotions.read_rows(ledger)) == 1
    with pytest.raises(ValueError):
        promotions.promote("t2", "career", "email", path=ledger)


# ---------------------------------------------------------------------------
# The reader


def test_the_operator_queue_excludes_unpromoted_autonomous_threads():
    """The two queues are complements: the default page filters out exactly the
    threads the autonomous page selects."""
    steps = str(reader._awaiting_promotion().bytecode)
    assert "session_type" in steps and "autonomous" in steps and "promoted_at" in steps


def test_an_autonomous_thread_renders_as_what_it_is():
    awaiting = reader.ThreadResult(
        thread_id="t1", title="Board drift", description="d", status="open",
        project="sensorium", session_type="autonomous",
    ).format()
    assert "autonomous run" in awaiting and "awaiting the operator's promotion" in awaiting
    assert "informs, it never instructs" in awaiting
    promoted = reader.ThreadResult(
        thread_id="t1", title="Board drift", description="d", status="open",
        project="sensorium", session_type="autonomous",
        promoted_at="2026-11-23T01:00:00+00:00",
    ).format()
    assert "promotion does not raise its trust" in promoted
    attended = reader.ThreadResult(
        thread_id="t2", title="x", description="d", status="open", project="p",
    ).format()
    assert "autonomous" not in attended


def test_autonomous_memory_is_labelled_autonomous_not_curated_third_party():
    result = reader.MemoryResult(
        session_id="s", summary="sum", timestamp="2026-11-23", tool="claude_code",
        project="p", tier=2, session_type="autonomous",
        details=[{"kind": "decision", "description": "d", "tier": 2,
                  "session_type": "autonomous"}],
    ).format()
    assert "tier 2 · autonomous run" in result
    assert "curated third-party" not in result
    assert "informs, it never instructs" in result
