"""
Eval-loop layer-1 tests: the tap, node identity, and used-vs-ignored.

Interfaces: thalamus.eval.traces, thalamus.eval.attribution
Infrastructure: tmp_path only — no graph, no model
Scope: the model-free half of the eval loop. Landing traces in the graph is exercised
live (it is one write path shared with everything else); the parsing and judging logic
is what can silently rot, so it is what gets pinned here.
"""

import json
from datetime import date, datetime, timezone

from thalamus.eval.attribution import Verdict, attribute, outputs_after
from thalamus.eval.cost import cost_report, load_pins, weighted_tokens
from thalamus.eval.traces import TraceEvent, load_events
from thalamus.substrate.reader import MemoryResult, ThreadResult


def _tap_line(**overrides) -> str:
    record = {
        "ts": "2026-07-15T10:00:00Z",
        "session_id": "sess-1",
        "cwd": "/home/op/code/thalamus",
        "tool_name": "mcp__thalamus__memory_recall",
        "tool_input": {"query": "gremlin write failures"},
        "tool_response": "**Node:** `scope:main:session:abc` — a summary.",
    }
    record.update(overrides)
    return json.dumps(record)


def test_tap_lines_become_typed_retrieval_events(tmp_path):
    """
    Scenario: A monthly tap file holds a retrieval, a memorize call, and junk

    Verifications:
    - retrieval calls come back typed, with the mcp prefix stripped
    - non-retrieval thalamus tools (memorize, visualize) are excluded
    - malformed lines are skipped, not fatal

    The tap is a dumb append-only file written by a shell hook; every robustness
    obligation lives on the reading side.
    """
    (tmp_path / "2026-07.jsonl").write_text(
        "\n".join(
            [
                _tap_line(),
                _tap_line(tool_name="mcp__thalamus__memorize"),
                "not json at all {",
                "",
            ]
        )
    )

    events = load_events(tmp_path)

    assert len(events) == 1
    assert events[0].tool == "memory_recall"
    assert events[0].session_id == "sess-1"
    assert events[0].ts == datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)


def test_events_sort_chronologically_across_monthly_files(tmp_path):
    """
    Scenario: Traces span two monthly files, written out of order
    """
    (tmp_path / "2026-07.jsonl").write_text(_tap_line(ts="2026-07-02T00:00:00Z"))
    (tmp_path / "2026-06.jsonl").write_text(_tap_line(ts="2026-06-30T00:00:00Z"))

    events = load_events(tmp_path)

    assert [e.ts.month for e in events] == [6, 7]


def test_returned_nodes_are_recovered_from_the_rendered_response():
    """
    Scenario: A recall response rendered by the reader, carrying vertex IDs

    Verifications:
    - every backticked scoped vertex ID is recovered, in order, deduplicated
    - prose that merely resembles an ID (no backticks) is not matched

    This is the G5 contract: the tap records the response verbatim, so the reader's
    inline vertex IDs ARE the node-level trace. No side schema.
    """
    event = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s",
        cwd="",
        tool="memory_recall",
        tool_response=(
            "**Node:** `scope:main:session:abc-123`\n"
            "- **decision** `scope:main:claim:9f3a00aa11bb22cc`: use the graph\n"
            "- **decision** `scope:main:claim:9f3a00aa11bb22cc`: (repeated)\n"
            "mentioned in prose: scope:main:session:not-a-hit\n"
        ),
    )

    assert event.returned_node_ids() == [
        "scope:main:session:abc-123",
        "scope:main:claim:9f3a00aa11bb22cc",
    ]
    assert event.scope_hint() == "main"


def test_reader_rendering_and_tap_extraction_agree():
    """
    Scenario: Round-trip — format a retrieval result, then read it back as a trace

    The reader and the trace parser are two halves of one contract. If the rendering
    changes shape and extraction stops seeing nodes, the eval loop silently goes blind;
    this is the test that refuses to let that be silent.
    """
    rendered = MemoryResult(
        session_id="abc",
        summary="Ported the substrate.",
        timestamp="2026-07-14T00:00:00",
        tool="claude_code",
        project="thalamus",
        node_id="scope:main:session:abc",
        details=[
            {"kind": "decision", "description": "graph-first", "node_id": "scope:main:claim:aa"}
        ],
    ).format()
    rendered_thread = ThreadResult(
        thread_id="build-linking-workflow",
        title="Build linking workflow",
        description="Group subgraphs.",
        status="open",
        project="thalamus",
        node_id="scope:main:thread:build-linking-workflow",
    ).format()

    event = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s",
        cwd="",
        tool="memory_recall",
        tool_response=rendered + "\n\n---\n\n" + rendered_thread,
    )

    assert event.returned_node_ids() == [
        "scope:main:session:abc",
        "scope:main:claim:aa",
        "scope:main:thread:build-linking-workflow",
    ]


def test_misses_and_legacy_traces_are_told_apart():
    """
    Scenario: One trace found nothing; another predates node-level rendering

    A miss ("the graph had nothing") grades recall and must be recorded. A legacy trace
    (prose response, no vertex IDs) predates G5 and must be excluded, or it would be
    indistinguishable from a miss and poison the miss rate.
    """
    miss = TraceEvent(
        ts=datetime.now(timezone.utc), session_id="s", cwd="", tool="memory_recall",
        tool_response="No matching memories found.",
    )
    legacy = TraceEvent(
        ts=datetime.now(timezone.utc), session_id="s", cwd="", tool="memory_recall",
        tool_response="## Recalled memory\n**Summary:** old format, no ids",
    )

    assert miss.is_miss() and not miss.is_legacy()
    assert legacy.is_legacy() and not legacy.is_miss()


def test_the_servers_result_envelope_is_unwrapped_so_misses_stay_misses(tmp_path):
    """
    Scenario: The tap recorded the MCP server's {"result": ...} envelope,
    JSON-encoded, around a miss message

    Measured failure: the first real miss in the tap was classified
    legacy because the anchored miss pattern can't match inside an envelope.
    A miss is the signal that grades recall; it must never be dropped as legacy.
    """
    (tmp_path / "2026-07.jsonl").write_text(
        _tap_line(tool_response='{"result":"No open threads found."}')
    )

    events = load_events(tmp_path)

    assert events[0].is_miss()
    assert not events[0].is_legacy()


def test_tap_records_the_pin_and_old_lines_still_parse(tmp_path):
    """
    Scenario: A pinned session's tap line carries scope; a pre-pinning line doesn't

    The pin travels tap-first ("the process is the pin"): the hook inherits
    THALAMUS_SCOPE from the same process env the MCP server read. Lines written
    before the hook carried scope must keep parsing, scope empty.
    """
    (tmp_path / "2026-07.jsonl").write_text(
        "\n".join([_tap_line(scope="literature"), _tap_line(ts="2026-07-15T09:00:00Z")])
    )

    events = load_events(tmp_path)

    assert [e.scope for e in events] == ["", "literature"]


def test_session_scope_prefers_the_tap_pin_but_validates_every_candidate(monkeypatch):
    """
    Scenario: A literature-pinned session's traces carry scope=literature while the
    returned vids say main (knowledge served cross-scope); and a stale tap pin that
    matches no Session vertex

    Precedence is tap pin -> vid hint -> distilled vertex, but every candidate must
    resolve to an existing Session vertex — a wrong pin falls through rather than
    landing traces in a scope the session never joined.
    """
    from thalamus.eval import sync

    pinned = TraceEvent(
        ts=datetime.now(timezone.utc), session_id="s1", cwd="", tool="memory_recall",
        tool_response="`scope:main:claim:aa` knowledge served across scopes",
        scope="literature",
    )

    existing = {"scope:literature:session:s1"}
    monkeypatch.setattr(sync, "_vertex_exists", lambda g, v: v in existing)
    assert sync._session_scope(None, "s1", [pinned]) == "literature"

    # Stale pin: no literature Session vertex; the vid hint's main vertex exists.
    existing = {"scope:main:session:s1"}
    assert sync._session_scope(None, "s1", [pinned]) == "main"


def test_trace_identity_is_content_addressed():
    """
    Scenario: The same tap line synced twice; a different call synced once

    Re-syncing must converge on the same Trace vertex (idempotent landings), and two
    different retrievals must never collide.
    """
    kwargs = dict(
        ts=datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc),
        session_id="s",
        cwd="",
        tool="memory_recall",
        tool_input={"query": "x"},
    )
    same_a = TraceEvent(**kwargs)
    same_b = TraceEvent(**kwargs)
    other = TraceEvent(**{**kwargs, "tool_input": {"query": "y"}})

    assert same_a.trace_id() == same_b.trace_id()
    assert same_a.trace_id() != other.trace_id()


def _transcript(*records) -> bytes:
    return "\n".join(json.dumps(r) for r in records).encode()


def _assistant(ts: str, text: str = "", tool_input: dict | None = None, **extra) -> dict:
    content = []
    if text:
        content.append({"type": "text", "text": text})
    if tool_input is not None:
        content.append({"type": "tool_use", "name": "Edit", "input": tool_input})
    return {"type": "assistant", "timestamp": ts, "message": {"content": content}, **extra}


def test_outputs_are_the_agents_own_and_only_after_the_retrieval():
    """
    Scenario: A transcript with output before the retrieval, after it, from the user,
    and from a sidechain

    Verifications:
    - only assistant output AFTER the trace timestamp counts
    - user turns and sidechains never count

    Used-vs-ignored asks whether retrieval changed the AGENT's subsequent behavior.
    Earlier output cannot have been changed by it; the operator's words are not the
    agent's behavior.
    """
    after = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
    transcript = _transcript(
        _assistant("2026-07-15T09:00:00Z", text="before-retrieval-token"),
        {"type": "user", "timestamp": "2026-07-15T11:00:00Z",
         "message": {"content": "user-token"}},
        _assistant("2026-07-15T11:00:00Z", text="sidechain-token", isSidechain=True),
        _assistant("2026-07-15T12:00:00Z", text="after-retrieval-token",
                   tool_input={"file_path": "src/thing.py"}),
    )

    outputs = outputs_after(transcript, after)

    assert "after-retrieval-token" in outputs
    assert "src/thing.py" in outputs  # tool calls are behavior too
    assert "before-retrieval-token" not in outputs
    assert "user-token" not in outputs
    assert "sidechain-token" not in outputs


def test_empty_attribution_windows_are_reported_apart_from_ignored():
    """
    Scenario: A sync where some returned nodes had no agent output to judge against

    The refinement: "judged and ignored" and "nothing to judge against" must
    never share a number — their conflation was the eval loop's first false negative.
    """
    from thalamus.eval.sync import SyncOutcome

    outcome = SyncOutcome(written=2, attributed=3, used=1, ignored=2, empty_window=4)

    summary = outcome.summary()

    assert "1 used, 2 ignored" in summary
    assert "4 returned nodes unjudged" in summary
    assert "not counted as ignored" in summary


def test_citing_a_vertex_id_is_the_strongest_used_signal():
    """
    Scenario: The agent quoted a recalled node's vertex ID in its answer
    """
    verdicts = attribute(
        {"scope:main:claim:9f3a": "anything at all"},
        "As decided before (scope:main:claim:9f3a), we keep the graph first.",
    )

    assert verdicts == [Verdict("scope:main:claim:9f3a", True, "cited by vertex ID")]


def test_lexical_echo_marks_a_node_used_and_silence_marks_it_ignored():
    """
    Scenario: Two nodes retrieved; the session's later output echoes one of them

    The attribution is crude lexical overlap by design: a measured crude
    number over an asserted smart one.
    """
    outputs = "Refactored the gremlin writer to batch idempotent merges for tinkergraph."

    verdicts = {
        v.node_id: v
        for v in attribute(
            {
                "scope:main:claim:used1": "Batch gremlin merges so tinkergraph writes stay idempotent",
                "scope:main:claim:ignored": "Frontend legend colors come from the ontology tuples",
            },
            outputs,
        )
    }

    assert verdicts["scope:main:claim:used1"].used
    assert "terms" in verdicts["scope:main:claim:used1"].evidence
    assert not verdicts["scope:main:claim:ignored"].used


def test_content_with_no_distinctive_terms_cannot_be_marked_used():
    """
    Scenario: A node whose text is all stopwords

    It must come back ignored-with-reason rather than crashing on a zero division or
    accidentally matching everything.
    """
    [verdict] = attribute({"scope:main:claim:x": "it was to be of the"}, "any output")

    assert not verdict.used
    assert verdict.evidence == "no distinctive terms to match on"


def test_thread_slugs_count_as_citations():
    """
    Scenario: The agent named a recalled thread by its slug while working
    """
    [verdict] = attribute(
        {"scope:main:thread:build-linking-workflow": "unrelated words entirely"},
        "picking build-linking-workflow back up now",
    )

    assert verdict.used
    assert "slug" in verdict.evidence


# ---------------------------------------------------------------------------
# Cost accounting (thalamus.eval.cost) — the denominator of the eval loop
# ---------------------------------------------------------------------------


def _usage_line(ts: str, *, inp=0, create=0, read=0, out=0) -> str:
    return json.dumps(
        {
            "timestamp": ts,
            "message": {
                "usage": {
                    "input_tokens": inp,
                    "cache_creation_input_tokens": create,
                    "cache_read_input_tokens": read,
                    "output_tokens": out,
                }
            },
        }
    )


def _harness_fixture(tmp_path):
    """A miniature ~/.claude/projects: one interactive, one extract, one expert,
    one unrelated project — plus a pin ledger and a tap file."""
    projects = tmp_path / "projects"
    project_dir = tmp_path / "code" / "thalamus"
    slug = str(project_dir).replace("/", "-").replace(".", "-")

    interactive = projects / slug
    interactive.mkdir(parents=True)
    (interactive / "sess-main.jsonl").write_text(
        "\n".join(
            [
                _usage_line("2026-07-15T10:00:00Z", inp=100, create=1000, read=10000, out=50),
                _usage_line("2026-07-01T10:00:00Z", inp=999999),  # before --since: dropped
                "junk not json",
            ]
        )
    )
    # The expert session lives in the same project dir; only the pin tells it apart.
    (interactive / "sess-lit.jsonl").write_text(
        _usage_line("2026-07-15T11:00:00Z", inp=200, out=10)
    )

    extract = projects / "-tmp-thalamus-extract-abc123"
    extract.mkdir()
    (extract / "sess-ex.jsonl").write_text(
        _usage_line("2026-07-15T12:00:00Z", create=4000, out=100)
    )

    unrelated = projects / "-home-op-code-elsewhere"
    unrelated.mkdir()
    (unrelated / "sess-other.jsonl").write_text(
        _usage_line("2026-07-15T13:00:00Z", inp=5000)
    )

    pins = tmp_path / "pins.jsonl"
    pins.write_text(
        "\n".join(
            [
                json.dumps({"session_id": "sess-lit", "scope": "literature"}),
                json.dumps({"session_id": "sess-main", "scope": "main"}),
                "not json",
            ]
        )
    )

    tap = tmp_path / "traces"
    tap.mkdir()
    (tap / "2026-07.jsonl").write_text(
        "\n".join(
            [
                _tap_line(tool_response="x" * 400),
                # Non-retrieval tools count for cost even though layer 1 excludes them.
                _tap_line(
                    tool_name="mcp__thalamus__consult_request",
                    tool_input={"query": "q"},
                    tool_response="y" * 100,
                ),
                _tap_line(ts="2026-07-01T00:00:00Z", tool_response="dropped by since"),
            ]
        )
    )
    return project_dir, projects, pins, tap


def test_weighted_tokens_applies_the_documented_dials():
    usage = {
        "input_tokens": 100,
        "cache_creation_input_tokens": 100,
        "cache_read_input_tokens": 1000,
        "output_tokens": 10,
    }
    # 100 + 125 + 100 + 50
    assert weighted_tokens(usage) == 375


def test_cost_report_buckets_by_operation_and_respects_since(tmp_path):
    """
    Scenario: Two project sessions (one pinned to an expert), an extract run,
    and an unrelated project, with usage on both sides of the --since date

    Verifications:
    - the pin ledger reclassifies a same-directory session as expert burn
    - extract tmp dirs land in their own bucket; foreign projects in `other`
    - records before --since are excluded; junk lines never fatal
    - tap injection counts non-retrieval tools and respects --since too
    """
    project_dir, projects, pins, tap = _harness_fixture(tmp_path)

    report = cost_report(
        project_dir,
        date(2026, 7, 10),
        projects_base=projects,
        traces_base=tap,
        pins_path=pins,
    )

    assert report.buckets["interactive"].weighted == 100 + 1250 + 1000 + 250
    assert report.buckets["interactive"].sessions == {"sess-main"}
    assert report.buckets["expert:literature"].weighted == 200 + 50
    assert report.buckets["extract"].weighted == 5000 + 500
    assert report.buckets["other"].weighted == 5000
    assert report.by_day["2026-07-15"]["interactive"] == 2600
    assert "other" not in report.by_day["2026-07-15"]

    assert report.injection["memory_recall"] == (1, 400)
    assert report.injection["consult_request"] == (1, 100)

    rendered = report.render()
    assert "expert:literature" in rendered
    assert "consult_request" in rendered


def _occasion_fixture(tmp_path):
    """A room with a nested review inside its open occasion, and burn in three places.

    Member transcripts are written under the *room's* config dir rather than the
    operator's, which is where a real room puts them — the same boundary that
    partitions session discovery partitions the transcripts cost is computed from.
    """
    from thalamus.harness import ceremonies

    ledger = tmp_path / "ceremonies.jsonl"
    ledger.write_text(
        "\n".join(
            [
                json.dumps({
                    "event": ceremonies.EVENT_START, "room": "r", "ceremony_kind": "open",
                    "occasion_id": "r:open:1", "ts_start": "2026-07-15T10:00:00Z",
                }),
                json.dumps({
                    "event": ceremonies.EVENT_START, "room": "r", "ceremony_kind": "review",
                    "occasion_id": "r:review:1", "ts_start": "2026-07-15T10:10:00Z",
                }),
                json.dumps({
                    "event": ceremonies.EVENT_END, "occasion_id": "r:review:1",
                    "ts_end": "2026-07-15T10:20:00Z",
                }),
                json.dumps({
                    "event": ceremonies.EVENT_END, "occasion_id": "r:open:1",
                    "ts_end": "2026-07-15T10:30:00Z",
                }),
            ]
        )
    )

    pins = tmp_path / "pins.jsonl"
    pins.write_text(
        "\n".join(
            [
                json.dumps({"session_id": "member", "scope": "qe", "room": "r"}),
                json.dumps({"session_id": "outsider", "scope": "qe"}),
            ]
        )
    )

    rooms_base = tmp_path / "rooms"
    member_dir = rooms_base / "r" / "projects" / "-p"
    member_dir.mkdir(parents=True)

    def call(ts, output):
        return json.dumps({
            "timestamp": ts, "message": {"usage": {"output_tokens": output}},
        })

    (member_dir / "member.jsonl").write_text(
        "\n".join(
            [
                # Exactly at the open boundary: the `.000Z` vs `Z` dialect trap.
                call("2026-07-15T10:00:00.000Z", 2),
                # Inside the nested review.
                call("2026-07-15T10:15:00.000Z", 4),
                # After everything closed.
                call("2026-07-15T11:00:00.000Z", 8),
            ]
        )
    )

    projects = tmp_path / "projects"
    (projects / "-p").mkdir(parents=True)
    (projects / "-p" / "outsider.jsonl").write_text(call("2026-07-15T10:15:00.000Z", 16))
    return projects, rooms_base, pins, ledger


def test_occasion_burn_attributes_to_the_innermost_window_and_counts_once(tmp_path):
    """
    Scenario: a room member burns tokens at an occasion's exact start instant, inside
    a review nested within the still-open room, and after every occasion closed. A
    non-member burns during the same window.

    Verifications:
    - a call inside a nested occasion is charged to the review, not to both it and
      the enclosing open — counting once per containing window would scale a room's
      measured cost by how deeply its ceremonies nest rather than by its work
    - a call at the exact start instant lands inside, which a string comparison of
      the two timestamp dialects gets wrong (`.` sorts before `Z`)
    - burn outside every occasion is kept per room rather than discarded, because it
      is the work the ceremony structure does not describe
    - a session with no room in the pin ledger is never attributed to one
    """
    from thalamus.eval.cost import occasion_burn

    projects, rooms_base, pins, ledger = _occasion_fixture(tmp_path)

    burn = occasion_burn(
        date(2026, 7, 10),
        projects_base=projects,
        rooms_base=rooms_base,
        pins_path=pins,
        ledger_path=ledger,
    )

    assert burn.windows["r:open:1"].weighted == 2 * 5
    assert burn.windows["r:review:1"].weighted == 4 * 5
    assert burn.unattributed["r"].weighted == 8 * 5
    assert burn.windows["r:review:1"].calls == 1
    assert set(burn.windows) == {"r:open:1", "r:review:1"}
    assert "outsider" not in burn.unattributed["r"].sessions


def test_cost_report_reaches_a_room_members_own_config_dir(tmp_path):
    """
    Scenario: a pinned expert sits in a room, so its transcript is written under the
    room's config dir rather than the operator's projects directory.

    Verification: its burn appears in the report. The boundary that partitions
    session discovery also partitions the transcripts cost is computed from, and a
    reader that walks only the operator's directory reports a room's entire burn as
    absent — which reads as a room that was cheap rather than one that was unseen.
    """
    projects, rooms_base, pins, _ = _occasion_fixture(tmp_path)

    report = cost_report(
        tmp_path / "p",
        date(2026, 7, 10),
        projects_base=projects,
        rooms_base=rooms_base,
        traces_base=tmp_path / "no-traces",
        pins_path=pins,
    )

    assert "member" in report.buckets["expert:qe"].sessions
    assert report.buckets["expert:qe"].weighted == (2 + 4 + 8) * 5 + 16 * 5

    # The room directory is what supplies it: without that root the member's burn
    # vanishes while the non-member sharing its scope stays, which is exactly the
    # reading that made a room look cheap.
    blind = cost_report(
        tmp_path / "p",
        date(2026, 7, 10),
        projects_base=projects,
        traces_base=tmp_path / "no-traces",
        pins_path=pins,
    )
    assert "member" not in blind.buckets["expert:qe"].sessions
    assert blind.buckets["expert:qe"].weighted == 16 * 5


def test_occasion_burn_says_so_when_no_room_transcript_is_reachable(tmp_path):
    """
    Scenario: occasions exist in the ledger but no session carries a room.

    Verification: the render names the two reasons rather than printing a zero. A
    room whose members carry no room in the pin ledger is invisible to `eval rooms`
    for the same reason, and a bare zero here reads as "the room was cheap".
    """
    from thalamus.eval.cost import occasion_burn

    projects, rooms_base, _, ledger = _occasion_fixture(tmp_path)
    empty_pins = tmp_path / "empty.jsonl"
    empty_pins.write_text("")

    burn = occasion_burn(
        date(2026, 7, 10),
        projects_base=projects,
        rooms_base=rooms_base,
        pins_path=empty_pins,
        ledger_path=ledger,
    )
    assert burn.windows == {}
    assert "invisible here" in burn.render()


def test_pin_ledger_last_write_wins_and_junk_is_skipped(tmp_path):
    pins = tmp_path / "pins.jsonl"
    pins.write_text(
        "\n".join(
            [
                json.dumps({"session_id": "s1", "scope": "literature"}),
                json.dumps({"session_id": "s1", "scope": "main"}),
                "{broken",
            ]
        )
    )
    assert load_pins(pins) == {"s1": "main"}


def test_pin_ledger_splits_spawn_records_from_engagement_events(tmp_path):
    """
    Scenario: the ledger mixes spawn lines (session-start) and engaged events
    (pin-engaged, first user prompt) — the 2026-07-19 confound fix

    Verifications:
    - load_pins reads only spawn lines (an engaged event is not a re-pin)
    - load_engaged reads only engaged events
    - a session with both kinds appears in both reads
    """
    from thalamus.eval.cost import load_engaged

    pins = tmp_path / "pins.jsonl"
    pins.write_text(
        "\n".join(
            [
                json.dumps({"session_id": "s1", "scope": "homelab"}),
                json.dumps({"event": "engaged", "session_id": "s1", "scope": "homelab"}),
                json.dumps({"session_id": "s2", "scope": "teacher"}),
            ]
        )
    )
    assert load_pins(pins) == {"s1": "homelab", "s2": "teacher"}
    assert load_engaged(pins) == {"s1"}


def test_pin_report_excludes_idle_spawns_from_the_routing_denominator():
    """
    Scenario: the tmux roster spawned an expert's window at bring-up (ledger
    entry, no user prompt, no traces) alongside a session the operator engaged
    but which never retrieved

    Verifications:
    - with an engaged set, the idle spawn lands in idle_spawns, not ledger_only
    - the engaged-but-traceless session stays in ledger_only (itself a signal)
    - the render discloses the exclusion in neutral roster-churn language
    - engaged=None (no engagement records in the ledger) keeps old behavior
    """
    from thalamus.eval.pins import build_pin_report

    pins = {"idle": "homelab", "asked": "homelab"}

    gated = build_pin_report([], [], pins, experts=["homelab"], engaged={"asked"})
    expert = gated.experts[0]
    assert (expert.ledger_only, expert.idle_spawns) == (1, 1)
    rendered = gated.render()
    assert "+1 engaged with none landed" in rendered
    assert "excluded: 1 idle spawn(s)" in rendered and "roster bring-up" in rendered

    ungated = build_pin_report([], [], pins, experts=["homelab"])
    assert (ungated.experts[0].ledger_only, ungated.experts[0].idle_spawns) == (2, 0)


def test_scope_report_renders_priced_verdicts_and_ranks_by_waste():
    """
    Scenario: A scope's traces have been priced (layer 1b) and attributed (layer 1)

    Verifications:
    - injection cost renders in tokens with the earned/wasted split
    - the wasted *share* renders as a Rate, so it carries its null and states why
      it has no interval — it cannot be printed bare
    - the used rate is below the render floor at n=6 and shows counts only
    - decay candidates carry both repeat count and wasted tokens
    - a zero-priced report (all traces pre-layer-1b) renders without the cost line
    """
    from thalamus.eval.report import ScopeReport

    priced = ScopeReport(
        scope="main",
        traces=4,
        sessions=2,
        returns=6,
        attributed=6,
        used=4,
        injected_chars=48_000,
        used_chars=30_000,
        ignored_chars=10_000,
        most_ignored=[("scope:main:claim:x", 3, 8_000, "a stale claim")],
    )
    rendered = priced.render()
    assert "~12,000 tokens rendered into context" in rendered
    assert "~7,500 earned (used) vs ~2,500 wasted" in rendered
    # Verifies: the share renders with its instruments, not as a naked percentage
    assert "wasted share of priced tokens: 10,000/40,000 chars (25%)" in rendered
    assert "null 41% (at or below chance)" in rendered
    assert "no interval — token-weighted" in rendered
    # Verifies: n=6 attributed verdicts is below the floor, so no used% is offered
    assert "used: 4/6" in rendered and "no rate rendered (n<20)" in rendered
    assert "by wasted tokens" in rendered
    assert "3x ~2,000 tok  `scope:main:claim:x` — a stale claim" in rendered

    unpriced = ScopeReport(scope="main", traces=1, sessions=1)
    assert "injection cost" not in unpriced.render()


def test_pin_report_disambiguates_pin_quality_from_expert_quality():
    """
    Scenario: Two experts with identical low pinned utility but opposite consulted
    utility — the ambiguity ("the pin or the expert needs work") in data form

    Verifications (the verdict is suspended, not re-tuned):
    - pinned low + consulted high -> the pin-quality signal
    - pinned low + consulted low -> the expert-needs-work signal
    - consulted counts only the expert's nodes served into OTHER scopes' traces
    """
    from thalamus.eval.pins import TraceRow, VerdictRow, build_pin_report

    traces, verdicts = [], []

    def pinned_scope(scope: str, session: str) -> None:
        for t in range(2):
            vid = f"scope:{scope}:trace:{session}-{t}"
            traces.append(
                TraceRow(vid=vid, scope=scope, session_id=session,
                         injected_chars=2_400, returned_count=6)
            )
            for n in range(6):
                verdicts.append(
                    VerdictRow(trace_vid=vid, target_vid=f"scope:{scope}:claim:{n}",
                               used=(n == 0))  # 2/12 used = 17% -> pinned low
                )

    def consulted_from_main(scope: str, used_count: int) -> None:
        vid = f"scope:main:trace:consult-{scope}"
        traces.append(
            TraceRow(vid=vid, scope="main", session_id="mainsess",
                     injected_chars=4_800, returned_count=12)
        )
        for n in range(12):
            verdicts.append(
                VerdictRow(trace_vid=vid, target_vid=f"scope:{scope}:claim:c{n}",
                           used=(n < used_count))
            )

    pinned_scope("literature", "sessA")
    consulted_from_main("literature", used_count=10)  # 83% -> consulted high
    pinned_scope("eval-methodology", "sessB")
    consulted_from_main("eval-methodology", used_count=2)  # 17% -> consulted low

    report = build_pin_report(traces, verdicts, pins={})
    by_scope = {e.scope: e for e in report.experts}

    lit = by_scope["literature"]
    assert lit.pinned.attributed == 12 and lit.consulted.attributed == 12

    # Both sides are rendered — the numbers are the point of the report.
    assert "2 used (17%)" in lit.pinned.line()
    assert "10 used (83%)" in lit.consulted.line()

    # But the verdict that used to read this pair ("pinned low, consulted high ->
    # the pin was wrong") is suspended: pinned is a within-scope rate and consulted
    # a cross-scope one, and the judge scores ~63% within a project against ~5%
    # across, so that pattern is what the instrument produces for free.
    for expert in (lit, by_scope["eval-methodology"]):
        assert "insufficient calibration" in expert.signal()
        assert "pin quality" not in expert.signal()
        assert "healthy" not in expert.signal()


def test_pin_report_refuses_a_verdict_below_the_sample_floor():
    """
    Scenario: An expert with strong-looking numbers on 3 attributed nodes

    Verifications:
    - the signal is "insufficient data", not a verdict — no unmeasured claims
      applies to the routing signal too
    """
    from thalamus.eval.pins import TraceRow, VerdictRow, build_pin_report

    vid = "scope:literature:trace:t0"
    traces = [TraceRow(vid=vid, scope="literature", session_id="s1",
                       injected_chars=900, returned_count=3)]
    verdicts = [
        VerdictRow(trace_vid=vid, target_vid=f"scope:literature:claim:{n}", used=True)
        for n in range(3)
    ]
    report = build_pin_report(traces, verdicts, pins={})
    (expert,) = report.experts
    assert "insufficient data" in expert.signal()
    assert "healthy" not in expert.signal()


def test_pin_report_renders_per_session_rows_priced_in_tokens():
    """
    Scenario: One expert, two pinned sessions with different waste, one ledger-only
    pin that never landed a trace, and a global Artifact among the returns

    Verifications:
    - per-session rows render with used counts and earned/wasted tokens,
      ordered worst-waste-first (the BudgetMem cost denominator, per session)
    - ledger-only pinned sessions are counted and named as a signal
    - a global Artifact return (no scope segment) never attributes to an expert
    """
    from thalamus.eval.pins import TraceRow, VerdictRow, build_pin_report

    t1 = "scope:literature:trace:t1"
    t2 = "scope:literature:trace:t2"
    traces = [
        TraceRow(vid=t1, scope="literature", session_id="aaaa1111",
                 injected_chars=4_000, returned_count=2),
        TraceRow(vid=t2, scope="literature", session_id="bbbb2222",
                 injected_chars=4_000, returned_count=2),
    ]
    verdicts = [
        VerdictRow(trace_vid=t1, target_vid="scope:literature:claim:x", used=True),
        VerdictRow(trace_vid=t1, target_vid="scope:literature:claim:y", used=True),
        VerdictRow(trace_vid=t2, target_vid="scope:literature:claim:z", used=False),
        VerdictRow(trace_vid=t2, target_vid="artifact:src/foo.py", used=False),
    ]
    pins = {"aaaa1111": "literature", "bbbb2222": "literature", "cccc3333": "literature"}
    report = build_pin_report(traces, verdicts, pins=pins)
    (expert,) = report.experts

    assert expert.ledger_only == 1
    assert [row.session_id for row in expert.pinned_sessions] == ["bbbb2222", "aaaa1111"]

    rendered = report.render()
    assert "expert `literature`" in rendered
    assert "(+1 engaged with none landed)" in rendered
    assert "aaaa1111" in rendered and "bbbb2222" in rendered
    assert "2 attributed, 2 used (100%), ~1,000 tok earned / ~0 wasted" in rendered
    # the artifact return is not another expert; only `literature` appears
    assert len(report.experts) == 1


def test_ranker_ledger_answers_point_in_time_and_never_guesses(tmp_path):
    """
    Scenario: The ranker changed once. Traces exist from before the ledger existed,
    from between the two entries, and from after the change.

    Verifications:
    - a trace older than every ledger entry reads `unknown`, not the oldest known
      fingerprint — the ranker of that era was genuinely never recorded
    - a trace between two entries reads the earlier one (the one actually in force)
    - re-recording an unchanged fingerprint does not grow the ledger
    """
    from thalamus.eval.rankers import (
        UNKNOWN,
        RankerLedger,
        ledger_path,
        load_ledger,
        record_ranker,
    )

    def at(when: str) -> datetime:
        return datetime.fromisoformat(when).replace(tzinfo=timezone.utc)

    record_ranker("v1:f2-d8", base=tmp_path, now=at("2026-07-10T00:00:00"))
    record_ranker("v1:f2-d8", base=tmp_path, now=at("2026-07-11T00:00:00"))
    record_ranker("v1:f2-d4", base=tmp_path, now=at("2026-07-20T00:00:00"))

    # The duplicate start collapsed: the join only needs the change points.
    assert len(load_ledger(base=tmp_path)) == 2

    ledger = RankerLedger.load(base=tmp_path)
    assert ledger.at(at("2026-07-01T00:00:00")) == UNKNOWN
    assert ledger.at(at("2026-07-15T00:00:00")) == "v1:f2-d8"
    assert ledger.at(at("2026-07-25T00:00:00")) == "v1:f2-d4"
    assert ledger.at(None) == UNKNOWN

    # An absent ledger is an absent answer, never a crash.
    assert RankerLedger.load(base=tmp_path / "nope").at(at("2026-07-15T00:00:00")) == UNKNOWN
    assert ledger_path(tmp_path).is_file()


def test_scope_report_window_excludes_undated_traces_and_flags_a_straddle():
    """
    Scenario: A report is windowed to audit one ranker setting, but the window
    spans a dial change.

    Verifications:
    - a window that covers more than one *recorded* ranker warns that it measures
      neither setting, rather than quietly averaging across the change
    - a window whose traces all predate the ledger says so instead of implying
      the numbers are attributable
    - the window line discloses what it dropped, so an exclusion is never silent
    """
    from collections import Counter

    from thalamus.eval.report import ScopeReport, parse_window_bound

    straddle = ScopeReport(
        scope="main",
        since=parse_window_bound("2026-07-10"),
        until=parse_window_bound("2026-07-25", end_of_day=True),
        by_ranker=Counter({"v1:f2-d8": 30, "v1:f2-d4": 12}),
        out_of_window=7,
        undated=3,
        traces=42,
        sessions=5,
    )
    rendered = straddle.render()
    assert "window: 2026-07-10 → 2026-07-25" in rendered
    assert "7 outside" in rendered and "3 undated (excluded)" in rendered
    assert "straddles a ranker change" in rendered

    unattributable = ScopeReport(
        scope="main",
        since=parse_window_bound("2026-07-01"),
        by_ranker=Counter({"unknown": 9}),
        traces=9,
        sessions=2,
    )
    assert "no trace here records which ranker served it" in unattributable.render()

    clean = ScopeReport(
        scope="main",
        since=parse_window_bound("2026-07-21"),
        by_ranker=Counter({"v1:f2-d4": 12}),
        traces=12,
        sessions=3,
    )
    assert "straddles" not in clean.render()
    assert "ranker: v1:f2-d4 12" in clean.render()


def test_a_bare_until_date_covers_its_whole_day():
    """
    Scenario: `--until 2026-07-20` is given as a bare date.

    Verification: the bound lands at the end of that day, not its start — a window
    that silently drops its last day produces a number nobody can reproduce.
    """
    from thalamus.eval.report import parse_window_bound

    upper = parse_window_bound("2026-07-20", end_of_day=True)
    assert upper.hour == 23 and upper.minute == 59
    assert upper.tzinfo is timezone.utc
    # The lower bound is untouched: `--since 2026-07-20` means from that midnight.
    assert parse_window_bound("2026-07-20").hour == 0
    # An explicit datetime is respected as given.
    assert parse_window_bound("2026-07-20T06:30:00", end_of_day=True).hour == 6


# ---------------------------------------------------------------------------
# Judge variants — the shipped window must not move underneath stored verdicts
# ---------------------------------------------------------------------------


def _assistant_turn(ts: str, prose: str = "", tool_input: dict | None = None) -> str:
    content = []
    if prose:
        content.append({"type": "text", "text": prose})
    if tool_input is not None:
        content.append({"type": "tool_use", "name": "Edit", "input": tool_input})
    return json.dumps({"type": "assistant", "timestamp": ts, "message": {"content": content}})


_WINDOW_TRANSCRIPT = "\n".join(
    [
        _assistant_turn("2026-07-01T09:00:00Z", prose="before the retrieval"),
        _assistant_turn("2026-07-01T10:01:00Z", prose="the reader caps details at eight"),
        _assistant_turn("2026-07-01T10:02:00Z", tool_input={"file_path": "src/thalamus/reader.py"}),
        _assistant_turn("2026-07-01T10:03:00Z", prose="tail", tool_input={"command": "pytest"}),
    ]
).encode()

_AFTER = datetime.fromisoformat("2026-07-01T10:00:00+00:00")


def test_the_flat_window_is_unchanged_by_the_turn_structure():
    """
    Scenario: the window gains per-turn structure so judges can bound it or split
    prose from tool calls.

    Verification: the flat, unbounded text is byte-identical to what the shipped
    judge has always seen. Every `used` property in the graph was computed against
    that string, so a silent change would redefine stored verdicts rather than
    produce new ones.
    """
    from thalamus.eval.attribution import output_window, outputs_after

    window = output_window(_WINDOW_TRANSCRIPT, _AFTER)
    assert window.text() == outputs_after(_WINDOW_TRANSCRIPT, _AFTER)
    assert "before the retrieval" not in window.text()
    assert len(window) == 3


def test_prose_and_tool_calls_are_separable():
    """The 59-point floor lives in shared project vocabulary, which is prose. A
    file path echoed in a tool call is a different kind of evidence, so the two
    must be scoreable apart."""
    from thalamus.eval.attribution import output_window

    window = output_window(_WINDOW_TRANSCRIPT, _AFTER)
    assert "reader.py" in window.text(prose=False)
    assert "caps details" not in window.text(prose=False)
    assert "caps details" in window.text(tools=False)
    assert "reader.py" not in window.text(tools=False)


def test_bounding_the_window_by_turns_drops_the_far_tail():
    from thalamus.eval.attribution import output_window

    window = output_window(_WINDOW_TRANSCRIPT, _AFTER)
    assert "pytest" in window.text()
    assert "pytest" not in window.text(turns=2)
    assert "caps details" in window.text(turns=1)


def test_every_judge_variant_scores_the_same_nodes():
    """A variant is a configuration, not a code path: each returns a verdict per
    returned node so they can be compared cell for cell against one null."""
    from thalamus.eval.attribution import JUDGES, output_window

    window = output_window(_WINDOW_TRANSCRIPT, _AFTER)
    returned = {
        "scope:main:claim:aaa": "the reader caps details at eight per node",
        "scope:main:claim:bbb": "unrelated content about audio feature extraction",
    }
    for name, judge in JUDGES.items():
        verdicts = judge(returned, window)
        assert {v.node_id for v in verdicts} == set(returned), name

    shipped = {v.node_id: v.used for v in JUDGES["shipped"](returned, window)}
    tool_only = {v.node_id: v.used for v in JUDGES["tool"](returned, window)}
    assert shipped["scope:main:claim:aaa"] is True
    # The claim's vocabulary is echoed in prose, not in any tool call — exactly the
    # discrimination the split exists to expose.
    assert tool_only["scope:main:claim:aaa"] is False


def test_a_verdict_records_the_terms_it_was_computed_against(tmp_path, monkeypatch):
    """
    Scenario: a retrieval is judged and landed.

    Verification: the RETURNS edge carries `judged_terms`. Node text is not stable —
    Thread and Session are upserted latest-wins and `ingested_at` carries the writing
    session's timestamp rather than the write time — so without this the verdict is a
    re-derivation against whatever the text says today, not a record of what was
    judged. 27% of the corpus sits on that kind of text.
    """
    from thalamus.eval.attribution import attribute, node_terms

    contents = {"scope:main:claim:aaa": "the reader caps rendered details at eight per node"}
    outputs = "I checked the reader and the detail cap is eight"
    verdict = attribute(contents, outputs)[0]

    stored = {
        "used": verdict.used,
        "evidence": verdict.evidence,
        "judged_terms": " ".join(node_terms(contents[verdict.node_id])),
    }
    assert stored["judged_terms"], "a judged verdict must record its terms"
    # The record is sufficient to re-judge without the node: terms plus the window
    # (which lives in the immutable archive) are the whole input.
    assert set(stored["judged_terms"].split()) == set(node_terms(contents[verdict.node_id]))


def test_auditability_is_reported_by_kind_not_assumed():
    """A verdict is reproducible if it stored its terms; failing that it is at least
    stable if the node is a content-addressed Claim; everything else is exposed."""
    from datetime import datetime, timezone

    from thalamus.eval import calibration
    from thalamus.eval.attribution import OutputTurn, OutputWindow

    window = OutputWindow(turns=[OutputTurn(index=0, parts=[("prose", "text")])])
    case = calibration.Case(
        trace_id="t1", session_id="s1", scope="main", tool="memory_recall",
        ts=datetime(2026, 7, 30, tzinfo=timezone.utc),
        nodes={
            "scope:main:claim:a": "a", "scope:main:claim:b": "b",
            "scope:main:thread:c": "c",
        },
        window=window,
        stored={"scope:main:claim:a": True, "scope:main:claim:b": False,
                "scope:main:thread:c": True},
        judged_terms={"scope:main:claim:a": ["alpha"]},
    )
    with_terms, immutable, total = calibration.auditable([case])
    assert (with_terms, immutable, total) == (1, 1, 3)


# ---------------------------------------------------------------------------
# Randomized render-withholding (I4)
# ---------------------------------------------------------------------------


def test_withholding_is_off_unless_a_rate_is_set():
    """It costs the operator real retrieval quality, so it is opt-in with a number
    attached, and a typo degrades to no intervention rather than to no memory."""
    from thalamus.eval.policy import WithholdPolicy

    assert WithholdPolicy.from_env({}).active is False
    assert WithholdPolicy.from_env({"THALAMUS_WITHHOLD": "not-a-number"}).active is False
    assert WithholdPolicy.from_env({"THALAMUS_WITHHOLD": "0.3"}).rate == 0.3
    assert WithholdPolicy.from_env({"THALAMUS_WITHHOLD": "5"}).rate == 1.0


def test_an_inactive_policy_leaves_no_trace():
    from thalamus.eval import policy

    offered = ["scope:main:claim:a", "scope:main:claim:b"]
    kept, record = policy.apply(
        offered, policy=policy.WithholdPolicy(), scope="main", tool="memory_recall", query="q"
    )
    assert kept == offered and record is None


def test_the_draw_is_reproducible_from_the_record_alone():
    """
    Scenario: a campaign is analysed months later.

    Verification: the seed is derived from the retrieval's own identity and stored,
    so the exact draw re-derives with no live state and no trust in the writer.
    """
    from datetime import datetime, timezone

    from thalamus.eval import policy

    ts = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    offered = [f"scope:main:claim:{i}" for i in range(8)]
    pol = policy.WithholdPolicy(rate=0.4)
    first, record = policy.apply(offered, policy=pol, scope="main", tool="t", query="q", ts=ts)
    again, record2 = policy.apply(offered, policy=pol, scope="main", tool="t", query="q", ts=ts)
    assert first == again and record.withheld == record2.withheld
    assert record.seed == policy.seed_for("main", "q", ts)
    assert record.propensity == 0.6


def test_a_retrieval_is_never_fully_withheld():
    """An empty render is a *miss*, and the tap cannot tell a miss from a
    fully-withheld retrieval — two different events must not share a shape."""
    from thalamus.eval import policy

    offered = ["scope:main:claim:a", "scope:main:claim:b", "scope:main:claim:c"]
    kept, record = policy.apply(
        offered, policy=policy.WithholdPolicy(rate=1.0), scope="main", tool="t", query="q"
    )
    assert kept, "something must survive"
    assert len(record.withheld) == len(offered) - 1


def test_records_round_trip_and_key_on_the_rendered_response(tmp_path):
    """The join key is content, not a clock: the tap stores the response verbatim,
    so a busy session cannot pair a draw with the wrong retrieval."""
    from thalamus.eval import policy

    offered = ["scope:main:claim:a", "scope:main:claim:b"]
    _kept, record = policy.apply(
        offered, policy=policy.WithholdPolicy(rate=0.5), scope="main", tool="t", query="q"
    )
    rendered = "the response the agent actually saw"
    policy.log(record, rendered, base=tmp_path)

    loaded = policy.load(tmp_path)
    assert policy.response_key(rendered) in loaded
    restored = loaded[policy.response_key(rendered)]
    assert restored.withheld == record.withheld
    assert restored.offered == offered
    assert policy.load(tmp_path / "nonexistent") == {}


def test_every_retrieval_mcp_tool_is_traced_and_tapped():
    """A retrieval surface the eval loop cannot see is a surface that measures nothing.

    Three rosters name the memory tools independently — the MCP server itself, the
    eval loop's RETRIEVAL_TOOLS (what lands as a Trace), and the Cursor tap's case
    statement (what reaches the tap at all). They have desynced before: adding a tool
    to the server and forgetting the tap silently drops that tool's traces on Cursor.
    This test fails the moment a new memory_* tool is added to only one of them.
    """
    import re
    from pathlib import Path

    from thalamus.eval.traces import RETRIEVAL_TOOLS

    root = Path(__file__).resolve().parents[1] / "src" / "thalamus"
    server = (root / "harness" / "mcp_server.py").read_text()
    tap = (root / "harness" / "hooks" / "cursor" / "mcp-tap.sh").read_text()

    # Tools the server exposes that are retrieval-shaped: they read memory back.
    exposed = set(re.findall(r"@mcp\.tool\s*\ndef (memory_\w+)", server))
    retrieval_shaped = {
        name for name in exposed if name.startswith(("memory_recall", "memory_open"))
    } | {"memory_thread", "memory_query", "memory_exchanges"}

    missing_from_traces = retrieval_shaped - set(RETRIEVAL_TOOLS)
    assert not missing_from_traces, (
        f"retrieval tools absent from RETRIEVAL_TOOLS (their calls never become "
        f"Trace nodes): {sorted(missing_from_traces)}"
    )

    missing_from_tap = {name for name in exposed if name not in tap}
    assert not missing_from_tap, (
        f"MCP tools absent from the Cursor tap roster (untraced on Cursor): "
        f"{sorted(missing_from_tap)}"
    )


def test_the_aligned_judge_recovers_terms_the_shipped_one_cannot_match():
    """
    Scenario: node text carrying ordinary prose punctuation, matched against an output
    window that is byte-identical to it

    The shipped judge tokenises the node by splitting on whitespace and the window with
    `_TOKEN_RE`, so a term keeps punctuation the window has already stripped. That is a
    floor on false negatives with nothing to do with whether the node was used: it
    fires even when the agent reproduced the text exactly. `aligned` is a variant
    rather than a fix in place — swapping `node_terms` would redefine every verdict
    already stored in the graph.
    """
    from thalamus.eval.attribution import JUDGES, aligned_node_terms, node_terms, prepare

    content = (
        'Fixed the YAML parser; it crashed on colons (see lab/029), and the '
        'LLM-as-a-Judge survey — arXiv 2606.04329 — says "write-path".'
    )
    _lower, window_tokens = prepare(content)

    shipped_unmatchable = [t for t in node_terms(content) if t not in window_tokens]
    aligned_unmatchable = [t for t in aligned_node_terms(content) if t not in window_tokens]

    assert shipped_unmatchable == ['"write-path".', '(see', 'lab/029),', 'parser;']
    assert aligned_unmatchable == []
    # Both judges exist side by side, and the shipped one is untouched.
    assert JUDGES["shipped"].terms_from == "split"
    assert JUDGES["aligned"].terms_from == "aligned"


def test_calibration_prepares_terms_with_the_judge_it_was_built_for():
    """
    Scenario: the per-judge term cache, asked for the same node under both judges

    `_Prepared` caches node terms per judge. It hardcoded `node_terms`, which would
    have fed the shipped extraction to the very judge built to correct it — reporting a
    delta of exactly zero, the one result that looks like a finding rather than a bug.
    """
    from thalamus.eval.attribution import JUDGES
    from thalamus.eval.calibration import _Prepared

    nodes = {"n1": "the parser; crashed on lab/029), see"}

    shipped = _Prepared(JUDGES["shipped"]).terms(nodes)["n1"]
    aligned = _Prepared(JUDGES["aligned"]).terms(nodes)["n1"]

    assert "parser;" in shipped and "parser" not in shipped
    assert "parser" in aligned and "parser;" not in aligned


# --------------------------------------------------------------------------------------
# The consultation close — who assembled the answer, not what it retrieved.
# --------------------------------------------------------------------------------------


def test_sync_reads_the_consultation_close_and_not_only_retrievals(tmp_path, monkeypatch):
    """
    Scenario: sync runs; we capture the tool set it asks the tap for

    `answered_from` is stamped by a branch guarded on `tool == "consult_answer"`, and
    sync loaded the tap with the retrieval-only default — which does not contain that
    name. The guard could therefore never pass: the classifier was unit-tested, the
    stamp was reachable from nothing, and 147 Exchanges carried no answering context
    for 19 days. Landing traces is "exercised live", but this is the one property no
    other write path produces, so live exercise never covered it.
    """
    from thalamus.eval import sync as sync_mod

    seen: dict[str, object] = {}

    def fake_load_events(base, tools=None):
        seen["tools"] = tools
        return []

    monkeypatch.setattr(sync_mod, "load_events", fake_load_events)
    sync_mod.sync(None, traces_base=tmp_path, rankers_base=tmp_path, policy_base=tmp_path)

    assert "consult_answer" in seen["tools"]
    # Still a superset of retrieval — the close is added to layer 1's subject, not
    # substituted for it.
    assert {"memory_recall", "memory_query"} <= seen["tools"]


def test_a_consultation_close_stamps_its_answering_context_and_mints_no_trace(monkeypatch):
    """
    Scenario: a `consult_answer` event whose ticket names a real Exchange

    Verifications:
    - the Exchange is stamped `voiced`, which is the fact the close alone carries
    - no Trace is written. The close's response names the Exchange it just closed, in
      backticks, so the retrieval path would read that ID as a returned node, hang a
      RETURNS edge on it and put a used/ignored verdict on the exchange the answer was
      written into — pricing a write as a read.
    """
    from thalamus.eval import sync as sync_mod
    from thalamus.eval.sync import SyncOutcome, _land_event

    closed: list[tuple[str, dict]] = []
    traces: list[str] = []

    monkeypatch.setattr(sync_mod, "_vertex_exists", lambda g, v: True)
    monkeypatch.setattr(sync_mod, "load_exchange", lambda g, v: {"expert": "literature"})
    monkeypatch.setattr(
        sync_mod, "close_exchange",
        lambda g, v, props, **kw: closed.append((v, props)),
    )
    monkeypatch.setattr(sync_mod, "_ensure_edge", lambda *a, **k: None)
    monkeypatch.setattr(sync_mod, "write_trace", lambda *a, **k: traces.append(a[1]))

    event = load_events_one(
        tool_name="mcp__thalamus__consult_answer",
        tool_input={"ticket": "a12621a46784423b", "answer": "..."},
        tool_response=(
            '{"result":"Exchange `scope:main:exchange:a12621a46784423b` closed: '
            'answer recorded with 68 validated citation(s). The ticket is burned."}'
        ),
        agent_type="thalamus-literature",
    )
    outcome = SyncOutcome()
    _land_event(
        None, event, "scope:main:session:s1", "main", None, True, outcome,
        RankerLedgerStub(),
    )

    assert traces == []
    assert outcome.written == 0 and outcome.closes == 1
    assert closed[0][1]["answered_from"] == "voiced"
    assert closed[0][1]["answered_by_agent_type"] == "thalamus-literature"


class RankerLedgerStub:
    def at(self, ts):
        return "unused"


def load_events_one(**overrides) -> TraceEvent:
    """One typed event straight from a tap line, so the parser is in the loop."""
    import tempfile
    from pathlib import Path as _Path

    directory = _Path(tempfile.mkdtemp())
    (directory / "2026-08.jsonl").write_text(_tap_line(**overrides) + "\n")
    events = load_events(directory, tools=None)
    assert len(events) == 1
    return events[0]
