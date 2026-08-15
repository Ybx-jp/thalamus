"""
Graph Memory CLI viewer launch tests.

Interfaces: thalamus visualize FILE
Infrastructure: mocked Uvicorn server
Scope: pending-session viewer construction and launch configuration
"""

import pytest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from thalamus import cli


def test_visualize_starts_local_viewer_with_pending_session(monkeypatch, capsys):
    """
    Scenario: Launch an interactive preview from session YAML

    Requires:
    - fixture: tests/fixtures/sample_session.yaml
    - infrastructure: mocked Uvicorn server

    Observable via:
    - uvicorn.run application and arguments
    - GET /api/previews/current

    Verifications:
    - visualize starts Uvicorn on the requested host and port
    - the launched application contains the requested pending session
    - --no-open suppresses browser launch
    """
    captured = {}

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    def unexpected_browser_open(_url):
        raise AssertionError("browser must not open with --no-open")

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.setattr(cli.webbrowser, "open", unexpected_browser_open)
    args = SimpleNamespace(
        file=cli.Path("tests/fixtures/sample_session.yaml"),
        host="127.0.0.1",
        port=43123,
        no_open=True,
    )

    cli._cmd_visualize(args)

    # Verifies: visualize starts Uvicorn on the requested host and port
    assert captured["kwargs"] == {
        "host": "127.0.0.1",
        "port": 43123,
        "log_level": "warning",
    }
    client = TestClient(captured["app"])
    response = client.get("/api/previews/current")
    # Verifies: the launched application contains the requested pending session
    assert response.status_code == 200
    assert any(
        node["id"] == "scope:main:session:fixture-session-0001"
        for node in response.json()["nodes"]
    )
    # Verifies: --no-open suppresses browser launch
    assert "Thalamus viewer: http://127.0.0.1:43123" in capsys.readouterr().out


def test_visualize_without_file_connects_to_the_persisted_memory_graph(monkeypatch, capsys):
    """
    Scenario: Launch the memory explorer without a pending session file

    Requires:
    - infrastructure: mocked graph connection and Uvicorn server

    Observable via:
    - connect, close_connection, and Uvicorn application arguments

    Verifications:
    - visualize connects the configured persisted graph and injects it into the viewer
    - the graph connection is closed after the viewer server exits
    """
    graph = object()
    captured = {}

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli, "connect", lambda url: graph)
    monkeypatch.setattr(cli, "close_connection", lambda connection: captured.setdefault("closed", connection))
    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    args = SimpleNamespace(
        file=None,
        url="ws://graph.example.test/gremlin",
        host="127.0.0.1",
        port=43123,
        no_open=True,
    )

    cli._cmd_visualize(args)

    # Verifies: visualize connects the configured persisted graph and injects it into the viewer
    assert captured["app"].state.graph is graph
    assert captured["kwargs"]["port"] == 43123
    # Verifies: the graph connection is closed after the viewer server exits
    assert captured["closed"] is graph
    assert "Thalamus viewer: http://127.0.0.1:43123" in capsys.readouterr().out


def test_extract_refuses_an_explicit_session_that_matches_nothing(monkeypatch, capsys):
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

    args = SimpleNamespace(
        harness="claude",
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


def test_extract_reports_a_withheld_session_as_skipped_not_missing(monkeypatch, capsys):
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

    args = SimpleNamespace(
        harness="claude",
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


def _extract_fakes(monkeypatch, tmp_path, session_ids):
    """Stand up `thalamus extract`'s surroundings: transcripts, archive, graph."""
    from datetime import datetime
    from pathlib import Path

    from thalamus.harness import pin, transcripts
    from thalamus.substrate.schema import (
        Artifact, ArtifactType, SessionGraph, Source, Tool, Touch,
    )

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        transcripts, "discover",
        lambda *a, **k: {"-proj": [Path(f"/nope/{sid}.jsonl") for sid in session_ids]},
    )
    monkeypatch.setattr(
        transcripts, "parse",
        lambda path: SimpleNamespace(
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
