"""
The transcript-format rules: each one a reader's dependence on Claude Code's layout.

Interfaces: thalamus.harness.transcript_format (check_records, check_transcript,
            check_snapshots, report_findings), thalamus.cli._cmd_contract --transcripts
Infrastructure: tmp_path only — no graph, no harness, no model.
Scope: that each rule fires on the change it names and on nothing beside it. Every
       finding test has a control that differs in the one field under test, because a
       rule that fires on a clean transcript is the failure this checker exists to avoid.
"""

from __future__ import annotations

import argparse
import json

import pytest

from thalamus import cli
from thalamus.harness import transcript_format, transcripts
from thalamus.harness.transcript_format import check_records


def _lines(records) -> list[str]:
    return [json.dumps(record) for record in records]


def _turn(kind, content, n, **extra):
    return {"type": kind, "uuid": f"{kind}-{n}", "timestamp": f"2026-10-18T10:00:{n:02d}Z",
            "version": "2.1.302", "message": {"role": kind, "content": content}, **extra}


def _session(**prompt_extra):
    """A clean session as 2.1.302 writes one: a prompt, a tool call and its result."""
    return [
        _turn("user", "the governor is clamping too early", 1,
              origin={"kind": "human"}, promptSource="typed", **prompt_extra),
        _turn("assistant", [
            {"type": "thinking", "thinking": "look at the clamp"},
            {"type": "text", "text": "Reading it."},
            {"type": "tool_use", "id": "toolu_1", "name": "Read",
             "input": {"file_path": "src/governor.py"}},
        ], 2),
        _turn("user", [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "x"}], 3),
    ]


def _rules(records) -> list[str]:
    return [finding.rule for finding in check_records(_lines(records)).findings]


def test_a_clean_session_breaks_no_rule():
    report = check_records(_lines(_session()))
    assert report.findings == []
    assert report.records == 3
    assert report.versions == {"2.1.302"}


def test_a_new_flag_on_a_record_read_as_the_operator_is_a_finding():
    """
    Scenario: A release marks a harness-written user record with a flag no reader checks

    Verifications:
    - the record is reported, naming the flag
    - the same record with the flag false is not, so the value is what fires
    - a flag measured as neutral is not
    """
    report = check_records(_lines(_session(isRecapSummary=True)))
    assert [f.rule for f in report.findings] == ["operator-voice"]
    assert "isRecapSummary" in report.findings[0].detail

    assert _rules(_session(isRecapSummary=False)) == []
    assert _rules(_session(queueSkipSlashCommands=True)) == []


def test_a_new_origin_on_a_record_read_as_the_operator_is_a_finding():
    records = _session()
    records[0]["origin"] = {"kind": "scheduled-trigger"}
    assert _rules(records) == ["operator-voice"]

    # Verifies: a record the readers already skip is not checked for its origin
    records[0]["isMeta"] = True
    assert _rules(records) == []


def test_a_record_the_readers_skip_is_not_read_as_the_operator():
    """The compaction summary carries flags of its own, and is skipped by every reader."""
    summary = _turn("user", "This session is being continued", 4,
                    isCompactSummary=True, isVisibleInTranscriptOnly=True)
    assert _rules([*_session(), summary]) == []


def _compacted(*, summary_flagged=True, kept_again=False):
    records = _session()
    boundary = {"type": "system", "subtype": "compact_boundary", "uuid": "boundary",
                "version": "2.1.302",
                "compactMetadata": {"preservedMessages": {"uuids": ["assistant-2"]}}}
    summary = _turn("user", "This session is being continued", 4)
    if summary_flagged:
        summary["isCompactSummary"] = True
    records += [boundary, summary]
    if kept_again:
        records.append(_turn("assistant", [{"type": "text", "text": "Reading it."}], 2))
    return records


def test_a_compaction_is_checked_for_appending():
    """
    Scenario: The layout distillation's summary skip rests on (A0229)

    Verifications:
    - a boundary followed by its flagged summary, its kept turn earlier, is clean
    - an unflagged summary is reported: the skip would no longer find it
    - a kept turn written again after the boundary is reported: it would be read twice
    """
    assert _rules(_compacted()) == []
    assert "compaction" in _rules(_compacted(summary_flagged=False))
    assert _rules(_compacted(kept_again=True)) == ["compaction"]


def test_a_kept_turn_missing_from_before_the_boundary_is_a_finding():
    records = _compacted()
    records[3]["compactMetadata"]["preservedMessages"]["uuids"] = ["never-written"]
    assert _rules(records) == ["compaction"]


def test_a_block_type_no_reader_has_decided_about_is_a_finding():
    records = _session()
    records[1]["message"]["content"].append({"type": "citation_card", "text": "dropped"})
    assert _rules(records) == ["block-type"]


def test_a_tool_result_must_answer_an_earlier_call():
    records = _session()
    records[2]["message"]["content"][0]["tool_use_id"] = "toolu_unknown"
    assert _rules(records) == ["tool-linkage"]

    # Verifies: a call that renamed its id field breaks the call, not just the linkage
    records = _session()
    del records[1]["message"]["content"][2]["id"]
    assert _rules(records)[0] == "tool-fields"


def test_a_turn_without_its_envelope_is_a_finding():
    records = _session()
    del records[0]["uuid"]
    records[1]["timestamp"] = "yesterday"
    assert _rules(records) == ["envelope", "envelope"]


def test_content_in_a_shape_no_reader_reads_is_a_finding():
    records = _session()
    records[0]["message"]["content"] = {"parts": ["the governor is clamping too early"]}
    assert _rules(records) == ["content-shape"]


def test_two_snapshots_of_one_session_must_be_a_prefix(tmp_path):
    first = _lines(_session())
    for name, lines in (("aa/one.jsonl", first[:2]), ("bb/two.jsonl", first)):
        path = tmp_path / name
        path.parent.mkdir(parents=True)
        path.write_text("".join(f"{json.dumps({**json.loads(line), 'sessionId': 's1'})}\n"
                                for line in lines))
    assert transcript_format.check_snapshots(tmp_path) == (1, [])

    # Verifies: rewriting the earlier bytes in the later snapshot is reported
    later = tmp_path / "bb" / "two.jsonl"
    later.write_text(later.read_text().replace("clamping too early", "clamping late!!!"))
    pairs, broken = transcript_format.check_snapshots(tmp_path)
    assert pairs == 1 and len(broken) == 1


def test_findings_reach_the_log_and_stderr_and_a_clean_run_writes_nothing(tmp_path, capsys):
    log = tmp_path / "transcript-format.log"
    clean = transcript_format.check_records(_lines(_session()))
    assert transcript_format.report_findings(clean, "session aaaa", log_path=log) == ""
    assert not log.exists()

    dirty = transcript_format.check_records(_lines(_session(isRecapSummary=True)))
    summary = transcript_format.report_findings(dirty, "session aaaa", log_path=log)
    assert "1 record(s)" in summary
    assert "isRecapSummary" in log.read_text()
    assert "isRecapSummary" in capsys.readouterr().err


def _contract_check(monkeypatch, tmp_path, records):
    project = tmp_path / "projects" / "proj"
    project.mkdir(parents=True)
    (project / "s1.jsonl").write_text("\n".join(_lines(records)) + "\n")
    monkeypatch.setattr(transcripts, "CLAUDE_PROJECTS", tmp_path / "projects")
    monkeypatch.setenv("THALAMUS_ARCHIVE_DIR", str(tmp_path / "archive"))
    args = argparse.Namespace(contract_command="check", transcripts=True,
                              capabilities=False, experts=False)
    cli._cmd_contract(args, None)


def test_contract_check_transcripts_passes_a_clean_box(monkeypatch, tmp_path, capsys):
    _contract_check(monkeypatch, tmp_path, _session())
    out = capsys.readouterr().out
    assert "Checked 1 transcript(s)" in out
    assert "Transcript format OK" in out


def test_contract_check_transcripts_fails_on_a_finding(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit) as exited:
        _contract_check(monkeypatch, tmp_path, _session(isRecapSummary=True))
    assert exited.value.code == 1
    assert "isRecapSummary" in capsys.readouterr().out
