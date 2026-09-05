"""
Graph Memory CLI extract tests.

Interfaces: thalamus extract
Scope: session resolution (explicit path, project dir, archive fallback),
       withheld-session reporting, and raw-response reuse
"""

import pytest
from types import SimpleNamespace

from thalamus import cli


def test_extract_refuses_an_explicit_session_that_matches_nothing(
    monkeypatch, tmp_path, capsys
):
    """
    Scenario: the SessionEnd hook names a session that isn't in the given project dir

    Requires:
    - monkeypatched transcripts.discover / parse (no ~/.claude, no graph server)

    Observable via:
    - SystemExit code
    - stderr

    Verifications:
    - a --session that selects nothing exits non-zero instead of reporting "0 sessions"
    - the message names both the session asked for and where it was looked for
    - no graph connection is opened to discover there is nothing to do

    A silent zero here is how a wrong project dir lost three sessions: distillation
    runs detached, so "0 sessions to extract" is indistinguishable in the log from a
    session that legitimately had nothing to distill.
    """
    from pathlib import Path

    from thalamus.harness import transcripts

    monkeypatch.setattr(
        transcripts, "discover", lambda *a, **k: {"-proj": [Path("/nope/aaaa1111.jsonl")]}
    )
    monkeypatch.setattr(
        transcripts,
        "parse",
        lambda path: SimpleNamespace(
            session_id="aaaa1111-real",
            user_turns=3,
            has_substance=True,
            cwd="/home/someone",
            started_at="2026-01-01",
            path=path,
        ),
    )

    def unexpected_connect(*a, **k):
        raise AssertionError("must not open a graph connection when nothing is selected")

    monkeypatch.setattr(cli, "connect", unexpected_connect)
    # Keep the archive fallback off the operator's real archive.
    monkeypatch.setenv("THALAMUS_ARCHIVE_DIR", str(tmp_path / "archive"))

    args = SimpleNamespace(
        harness="claude",
        extract_with=None,
        projects=["-proj"],
        projects_dir=None,
        session=["bbbb2222"],
        scope="main",
        model=None,
        limit=0,
        force=False,
        write=False,
        url="ws://unused/gremlin",
    )

    with pytest.raises(SystemExit) as exit_info:
        cli._cmd_extract(args)

    assert exit_info.value.code == 1
    err = capsys.readouterr().err
    assert "bbbb2222" in err
    assert "-proj" in err


def test_extract_reports_a_withheld_session_as_skipped_not_missing(
    monkeypatch, tmp_path, capsys
):
    """
    Scenario: the SessionEnd hook names a session the substance gate withheld —
    the operator opened a shell, hit /clear, and closed it

    Requires:
    - monkeypatched transcripts.discover / parse (no ~/.claude, no graph server)

    Observable via:
    - SystemExit code
    - stdout

    Verifications:
    - a withheld session exits 0, not 1
    - it says nothing was substantive, and does not print the "No session matching"
      diagnostic that means the project dir is wrong
    - no graph connection is opened

    Both cases select nothing, so without this they read identically in a detached
    hook log — and the message that once caught three lost sessions would fire on
    every `/clear`-only close until it meant nothing.
    """
    from pathlib import Path

    from thalamus.harness import transcripts

    monkeypatch.setattr(
        transcripts, "discover", lambda *a, **k: {"-proj": [Path("/nope/cccc3333.jsonl")]}
    )
    monkeypatch.setattr(
        transcripts,
        "parse",
        lambda path: SimpleNamespace(
            session_id="cccc3333-real",
            user_turns=1,
            has_substance=False,
            cwd="/home/someone",
            started_at="2026-01-01",
            path=path,
        ),
    )

    def unexpected_connect(*a, **k):
        raise AssertionError("must not open a graph connection when nothing is selected")

    monkeypatch.setattr(cli, "connect", unexpected_connect)
    # Keep the archive fallback off the operator's real archive.
    monkeypatch.setenv("THALAMUS_ARCHIVE_DIR", str(tmp_path / "archive"))

    args = SimpleNamespace(
        harness="claude",
        extract_with=None,
        projects=["-proj"],
        projects_dir=None,
        session=["cccc3333"],
        scope="main",
        model=None,
        limit=0,
        force=False,
        write=False,
        url="ws://unused/gremlin",
    )

    with pytest.raises(SystemExit) as exit_info:
        cli._cmd_extract(args)

    assert exit_info.value.code == 0
    captured = capsys.readouterr()
    assert "no substantive exchange" in captured.out
    assert "cccc3333" in captured.out
    assert "No session matching" not in captured.err


def _extract_fakes(monkeypatch, tmp_path, session_ids, *, fake_parse=True):
    """Stand up `thalamus extract`'s surroundings: transcripts, archive, graph."""
    from datetime import datetime
    from pathlib import Path

    from thalamus.harness import pin, transcripts
    from thalamus.substrate.schema import (
        Artifact, ArtifactType, SessionGraph, Source, Tool, Touch,
    )

    monkeypatch.setenv("HOME", str(tmp_path))
    # The archive fallback reads this; without it a unit test sweeps the operator's
    # real ~/.thalamus/archive and its result depends on which box it runs on.
    monkeypatch.setenv("THALAMUS_ARCHIVE_DIR", str(tmp_path / ".thalamus" / "archive"))
    monkeypatch.setattr(
        transcripts, "discover",
        lambda *a, **k: {"-proj": [Path(f"/nope/{sid}.jsonl") for sid in session_ids]},
    )
    if fake_parse:
        monkeypatch.setattr(
            transcripts, "parse",
            lambda path, **kw: SimpleNamespace(
                session_id=path.stem,
                user_turns=4,
                has_substance=True,
                cwd="/home/someone/code/chartgen",
                started_at=f"2026-08-14T0{session_ids.index(path.stem)}:00:00",
                path=path,
                project="chartgen",
                title="Fix the governor",
                external_texts=[],
                ingress_verifiable=True,
            ),
        )
    monkeypatch.setattr(
        transcripts, "retain",
        lambda path: (
            SimpleNamespace(
                content_hash="f" * 64, uri="archive://" + "f" * 64, byte_size=1234
            ),
            None,
        ),
    )
    monkeypatch.setattr(transcripts, "retain_ingress_receipt", lambda facts: None)
    monkeypatch.setattr(
        transcripts, "to_session_graph",
        lambda facts, **kw: SessionGraph(
            session_id=facts.session_id,
            timestamp=datetime(2026, 8, 14, 10, 0),
            tool=Tool.CLAUDE_CODE,
            scope=kw["scope"],
            project=facts.project,
            summary="Fix the governor",
            sources=[
                Source(
                    content_hash="f" * 64,
                    title="Fix the governor",
                    uri="archive://" + "f" * 64,
                )
            ],
            artifacts=[Artifact(identifier="src/governor.py", type=ArtifactType.FILE)],
            touched=[Touch(identifier="src/governor.py", anchors=["a1"])],
        ),
    )
    monkeypatch.setattr(pin, "ledger_facts", lambda sid: {})
    monkeypatch.setattr(cli, "connect", lambda url: SimpleNamespace(name="graph"))
    monkeypatch.setattr(cli, "close_connection", lambda graph: None)
    monkeypatch.setattr(cli, "_session_has_claims", lambda graph, vid: False)

    def unexpected_model_call(*a, **k):
        raise AssertionError("--reuse-raw must not invoke the model")

    monkeypatch.setattr(cli.extraction, "run_extraction", unexpected_model_call)

    return SimpleNamespace(
        harness="claude",
        extract_with=None,
        projects=["-proj"],
        projects_dir=None,
        session=[],
        scope="main",
        model=None,
        limit=0,
        force=False,
        write=False,
        reuse_raw=True,
        room=None,
        forked_from=None,
        url="ws://unused/gremlin",
    )


def test_extract_reuse_raw_replays_a_retained_response_and_never_pays_again(
    monkeypatch, tmp_path, capsys
):
    """
    Scenario: an extraction was paid for and then lost to a parse refusal; the
    parser is fixed and the operator recovers the session

    Requires:
    - monkeypatched transcripts / graph connection (no ~/.claude, no graph server)
    - a retained response under $HOME/.thalamus/extractions/

    Observable via:
    - stdout
    - an AssertionError if the model is invoked

    Verifications:
    - the retained response is distilled without calling the model
    - the run is reported as a replay, not as a model call that cost $0.00
    - a session with nothing retained is skipped rather than quietly paid for

    Retention exists so a refusal costs a re-parse rather than a second digest pass.
    Without this the retained file is written on every run and read on none of them,
    and every recovery pays for the same session twice.
    """
    args = _extract_fakes(monkeypatch, tmp_path, ["aaaa1111", "bbbb2222"])

    retained = tmp_path / ".thalamus" / "extractions" / "main-aaaa1111.txt"
    retained.parent.mkdir(parents=True)
    retained.write_text(
        "```yaml\n"
        'summary: "Raised the clamp threshold after tests showed early clamping."\n'
        "decisions:\n"
        '  - description: "Raise the clamp threshold"\n'
        '    rationale: "Clamping fired before fatigue accumulated"\n'
        '    artifacts: ["src/governor.py"]\n'
        "```\n"
    )

    cli._cmd_extract(args)

    out = capsys.readouterr().out
    assert "+ aaaa1111" in out
    assert "replay" in out
    # The bill was paid by the run that wrote the file; a replay must not read as a
    # session that cost nothing to distill.
    assert "1 replayed from retained responses" in out
    # Nothing retained for bbbb2222, so it is passed over rather than turned into a
    # live call by the flag that exists to avoid one.
    assert "· bbbb2222  no retained response" in out
    assert "1 extracted, 1 skipped, 0 failed" in out


def test_extract_falls_back_to_the_archive_when_the_harness_rotated_the_transcript(
    monkeypatch, tmp_path, capsys
):
    """
    Scenario: a named session's transcript is gone from ~/.claude/projects, but the
    copy retained at extraction time is still in the archive

    Requires:
    - monkeypatched discovery / graph connection, THALAMUS_ARCHIVE_DIR at tmp_path
    - an archived transcript named for its content hash, as the archive stores it

    Observable via:
    - stdout

    Verifications:
    - a named session with no live transcript is recovered from the archive
    - it is distilled under its own session id, not under the hash it is filed by
    - a named session in neither place still fails loudly, and says both were checked

    Transcripts are retained because Claude Code rotates its own. Discovery
    that reads only the live dir loses a session to exactly the rotation retention
    exists to survive, and the evidence sits on disk the whole time.
    """
    import json

    args = _extract_fakes(monkeypatch, tmp_path, [], fake_parse=False)
    args.session = ["5b260dd3", "deadbeef"]

    session_id = "5b260dd3-7442-4de2-8f85-eb6a23931389"
    shard = tmp_path / ".thalamus" / "archive" / "3f"
    shard.mkdir(parents=True)
    # Named for its content hash, the way the archive files everything.
    (shard / f"{'3f' + 'a' * 62}.jsonl").write_text(
        "\n".join(
            json.dumps(record)
            for record in [
                {"type": "mode", "mode": "normal", "sessionId": session_id},
                {
                    "type": "user",
                    "cwd": "/home/someone/code/chartgen",
                    "timestamp": "2026-08-01T10:00:00Z",
                    "message": {"role": "user", "content": "raise the clamp threshold"},
                },
            ]
        )
    )

    retained = tmp_path / ".thalamus" / "extractions" / f"main-{session_id}.txt"
    retained.parent.mkdir(parents=True)
    retained.write_text(
        'summary: "Raised the clamp threshold after tests showed early clamping."\n'
    )

    cli._cmd_extract(args)

    out = capsys.readouterr().out
    assert "↺ 5b260dd3  recovered from the archive" in out
    # Filed under its content hash, distilled under its session id.
    assert "+ 5b260dd3" in out
    assert "3faaaaaa" not in out
    assert "1 extracted" in out


def test_extract_refuses_a_session_in_neither_the_project_dir_nor_the_archive(
    monkeypatch, tmp_path, capsys
):
    """
    Scenario: the archive fallback is reached and comes up empty too

    Verifications:
    - the run still exits non-zero rather than reporting "0 sessions"
    - the diagnostic names both places that were searched, so the reader knows the
      fallback ran and found nothing rather than never having been tried
    """
    args = _extract_fakes(monkeypatch, tmp_path, [], fake_parse=False)
    args.session = ["deadbeef"]

    with pytest.raises(SystemExit) as exit_info:
        cli._cmd_extract(args)

    assert exit_info.value.code == 1
    err = capsys.readouterr().err
    assert "deadbeef" in err
    assert "-proj or the archive" in err


def test_repeated_advisories_collapse_to_one_line_with_a_count():
    """
    Scenario: Sixteen advisories that differ only in which vertices they name, beside
    one that stands alone

    An advisory fired per-vertex fires thousands of times on a real graph, and a wall
    of near-identical lines is how a reporting-only check earns the habit of being
    scrolled past — the failure mode the recommendation that asked for this audit
    named explicitly.

    Verifications:
    - the repeated shape becomes one line carrying the count and an example id
    - the singleton is printed unchanged
    """
    repeated = [
        f"RETURNS between wrong endpoints: `scope:main:trace:t{n}` (Trace) -> "
        f"`scope:main:trace:x{n}` (Trace) — target is a Trace"
        for n in range(16)
    ]
    alone = "Unwritten edge type: `BLOCKS` is declared and no edge carries the label"

    lines = cli._collapse_advisories([*repeated, alone])

    assert len(lines) == 2
    collapsed = next(line for line in lines if "RETURNS" in line)
    assert "×16" in collapsed
    assert "e.g. scope:main:trace:t0" in collapsed
    assert alone in lines


class _StubTraversal:
    """The two-call shape `_served_nodes` uses: `V(*ids).element_map(*keys).to_list()`."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.asked: tuple = ()

    def V(self, *vids):  # noqa: N802 — gremlin's own spelling
        self.asked = vids
        return self

    def project(self, *_keys):
        return self

    def by(self, *_args):
        return self

    def to_list(self):
        return self._rows


def _row(vid, label, scope, text, *, kind="", contained=0):
    return {"id": vid, "label": label, "scope": scope, "kind": kind,
            "text": text, "contained": contained}


def test_the_reference_feed_offers_only_what_a_uses_edge_can_land_on(monkeypatch):
    """
    Scenario: a session whose retrievals returned a claim, a chunk, an Exchange and a
    Session, plus one claim that has since been retired from the graph

    The measured failure this closes: the last extractions to emit `references` at all
    named Exchange vertices for every one of them, because a clipped digest was the
    only ID surface they had and an exchange id was the one class still visible in it.
    `USES` may land on a Claim or a Chunk, so those are the only ids the feed offers.

    Verifications:
    - Exchange and Session ids are not offered
    - the claim and the chunk are, in the order the session met them
    - a served node missing from the graph is dropped rather than offered
    - each entry carries the kind and text the prompt renders
    """
    claim = "scope:literature:claim:aaaa1111bbbb2222"
    chunk = "scope:literature:chunk:" + "f" * 64 + "-0007"
    retired = "scope:architect:claim:dddd4444eeee5555"
    events = [
        SimpleNamespace(
            session_id="s1",
            returned_node_ids=lambda: [
                "scope:main:exchange:1f65ddba4a934df2",
                claim,
                "scope:main:session:s0",
                chunk,
                retired,
            ],
        ),
        SimpleNamespace(
            session_id="other", returned_node_ids=lambda: ["scope:qe:claim:zzzz1111"]
        ),
    ]
    monkeypatch.setattr("thalamus.eval.traces.load_events", lambda *a, **k: events)
    graph = _StubTraversal([
        _row(chunk, "Chunk", "literature", "a passage"),
        _row(claim, "Claim", "literature", "a recalled claim", kind="literature"),
    ])

    served = cli._served_nodes(graph, "s1", "main")

    assert [node["vid"] for node in served] == [claim, chunk]
    assert claim in graph.asked and retired in graph.asked
    assert served[0] == {"vid": claim, "label": "literature", "scope": "literature",
                         "text": "a recalled claim"}
    assert served[1]["label"] == "chunk"
    assert served[1]["text"] == "a passage"


def test_the_reference_feed_withholds_another_scopes_episodic_memory(monkeypatch):
    """
    Scenario: a `main` session whose ticketed consultation recalls returned an
    expert's session-contained claim alongside that expert's knowledge claim and a
    contained claim of main's own

    The expert's experience was legitimately served — a consultation ticket grants
    exactly that — and is still not offered as a reference, because attribution is
    scope-closed. Withholding the handle is the half that keeps the model from being
    shown something it may not use; `writer._write_references` is the half that makes
    it a guarantee.

    Verifications:
    - the foreign episodic claim is not offered
    - foreign session-less knowledge is: the reader serves it to every scope
    - a contained claim in the session's own scope is offered — containment alone
      does not disqualify a target
    """
    foreign_episodic = "scope:architect:claim:eeee1111"
    foreign_knowledge = "scope:literature:claim:aaaa2222"
    own_episodic = "scope:main:claim:bbbb3333"
    monkeypatch.setattr(
        "thalamus.eval.traces.load_events",
        lambda *a, **k: [SimpleNamespace(
            session_id="s1",
            returned_node_ids=lambda: [foreign_episodic, foreign_knowledge, own_episodic],
        )],
    )
    graph = _StubTraversal([
        _row(foreign_episodic, "Claim", "architect", "what the architect lived",
             kind="decision", contained=1),
        _row(foreign_knowledge, "Claim", "literature", "what a paper asserts",
             kind="literature"),
        _row(own_episodic, "Claim", "main", "what main decided",
             kind="decision", contained=1),
    ])

    served = cli._served_nodes(graph, "s1", "main")

    assert [node["vid"] for node in served] == [foreign_knowledge, own_episodic]
