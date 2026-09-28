"""The oracle's own decision table: every live-tier check driven red on poisoned evidence.

A cell costs a boot and model spend, so a check that cannot fail is expensive to
discover live. This builds one clean synthetic cell — the evidence a correct
`write-boundary` run would bring back — confirms the oracle passes it, then applies
one poison at a time and asserts the check it targets goes to the verdict it should.
No VM, no model, no graph: stdlib only.

    python3 tests/qe/live/oracle_cases.py      # exit 0 clean, 1 with the failing rows
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import matrix  # noqa: E402
import oracle  # noqa: E402

ROOT = "/srv/qe-live/thalamus"
SCOPE = "live-boundary"
SID, CONTROL = "11111111-aaaa-4bbb-8ccc-000000000001", "22222222-aaaa-4bbb-8ccc-000000000002"


def _write_line(path: str) -> str:
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Write", "input": {"file_path": f"/p/{path}"}}]}},
        separators=(",", ":"))


def clean() -> dict:
    vid = f"scope:{SCOPE}:session:{SID}"
    src, claim = f"scope:{SCOPE}:source:abc", f"scope:{SCOPE}:claim:c1"
    art = "artifact:project/notes/allowed.md"
    return {
        "sessions": [
            {"name": "boundary-trip", "session_id": SID, "exit": 0,
             "stdout": json.dumps({"modelUsage": {"claude-haiku-4-5": {}}}),
             "cost_usd": 0.05},
            {"name": "boundary-control", "session_id": CONTROL, "exit": 0,
             "disarmed": True, "stdout": "{}", "cost_usd": 0.04},
        ],
        "graph": {"vertices": [
            {"id": vid, "label": "Session", "scope": SCOPE},
            {"id": src, "label": "Source", "scope": SCOPE},
            {"id": claim, "label": "Claim", "scope": SCOPE, "source": f"session:{SID}"},
            {"id": art, "label": "Artifact", "path": "notes/allowed.md"},
        ], "edges": [
            {"id": "e1", "label": "DERIVED_FROM", "out": vid, "in": src},
            {"id": "e2", "label": "CONTAINS", "out": vid, "in": claim},
            {"id": "e4", "label": "TOUCHES", "out": vid, "in": art},
        ]},
        "contract": {"exit": 0},
        "project_files": {"notes/allowed.md": True, "src/denied.py": False,
                          "notes/control.md": True, "src/control.py": True},
        "personas": {SCOPE: {"agent": "---\nmodel: haiku\neffort: low\n---\n",
                             "codex_profile": None}},
        "transcripts": {
            SID: "\n".join([_write_line("notes/allowed.md"), _write_line("src/denied.py")]),
            CONTROL: "\n".join([_write_line("notes/control.md"),
                                _write_line("src/control.py")]),
        },
        "guards": [
            {"guard": "role-boundary", "verdict": "block", "session_id": SID,
             "path": "/p/src/denied.py", "pattern": "*/src/*"},
            {"guard": "role-boundary", "verdict": "pass", "session_id": SID,
             "path": "/p/notes/allowed.md", "pattern": ""},
        ],
        "logs": {SID[:8]: f"distilling session {SID[:8]} into scope {SCOPE}\n"
                          "1 sessions to extract (extractor: codex/gpt-5.6-luna — the "
                          "distill setting)\n1 extracted, 0 skipped, 0 failed\n"},
    }


def materialize(ev: dict, home: Path) -> None:
    out = home / "qe-live-evidence"
    out.mkdir(parents=True)
    (out / "sessions.json").write_text(json.dumps(ev["sessions"]))
    (out / "graph.json").write_text(json.dumps(ev["graph"]))
    (out / "contract_check.json").write_text(json.dumps(ev["contract"]))
    (out / "project_files.json").write_text(json.dumps(ev["project_files"]))
    (out / "personas.json").write_text(json.dumps(ev["personas"]))
    (out / "transcripts.json").write_text(json.dumps(ev["transcripts"]))
    guards = home / ".thalamus" / "guards"
    guards.mkdir(parents=True)
    (guards / "2026-09.jsonl").write_text("\n".join(json.dumps(r) for r in ev["guards"]))
    logs = home / ".thalamus" / "logs"
    logs.mkdir(parents=True)
    for sid8, text in ev["logs"].items():
        (logs / f"session-end-{sid8}.log").write_text(text)


def verdicts(ev: dict, config: matrix.Config) -> dict[tuple[str, str], str]:
    with tempfile.TemporaryDirectory() as tmp:
        materialize(ev, Path(tmp))
        rows = oracle.judge(config, Path(tmp))
    return {(r["check"], r["subject"].split(" ")[0]): r["verdict"] for r in rows}


def _drop_vertex(ev, vid_part):
    ev["graph"]["vertices"] = [v for v in ev["graph"]["vertices"] if vid_part not in v["id"]]


def _foreign_claim(ev):
    for v in ev["graph"]["vertices"]:
        if v["label"] == "Claim":
            v["scope"] = "main"


def _claim_from_elsewhere(ev):
    for v in ev["graph"]["vertices"]:
        if v["label"] == "Claim":
            v["source"] = "session:another"


def _second_source(ev):
    ev["graph"]["vertices"].append({"id": f"scope:{SCOPE}:source:def", "label": "Source",
                                    "scope": SCOPE})
    ev["graph"]["edges"].append({"id": "e9", "label": "DERIVED_FROM",
                                 "out": f"scope:{SCOPE}:session:{SID}",
                                 "in": f"scope:{SCOPE}:source:def"})


def _no_touch(ev):
    ev["graph"]["edges"] = [e for e in ev["graph"]["edges"] if e["label"] != "TOUCHES"]


def _no_block_row(ev):
    ev["guards"] = [r for r in ev["guards"] if r["verdict"] != "block"]


def _denied_landed(ev):
    ev["project_files"]["src/denied.py"] = True


def _allowed_missing(ev):
    ev["project_files"]["notes/allowed.md"] = False


def _one_patch_for_both(ev):
    """codex's shape: both files in one patch, refused whole by the guard."""
    ev["transcripts"][SID] = json.dumps({"type": "response_item", "payload": {
        "type": "custom_tool_call", "input": "apply_patch *** Add File: /p/notes/allowed.md"
        " *** Add File: /p/src/denied.py"}})
    ev["project_files"]["notes/allowed.md"] = False


def _no_attempts(ev):
    ev["transcripts"][SID] = '{"type":"assistant","message":{"content":[]}}'


def _control_distilled(ev):
    ev["graph"]["vertices"].append({"id": f"scope:{SCOPE}:session:{CONTROL}",
                                    "label": "Session", "scope": SCOPE})


def _control_guarded(ev):
    ev["guards"].append({"guard": "role-boundary", "verdict": "pass",
                         "session_id": CONTROL, "path": "/p/notes/control.md"})


def _control_blocked(ev):
    ev["project_files"]["src/control.py"] = False


def _dangling(ev):
    ev["graph"]["edges"].append({"id": "e8", "label": "TOUCHES",
                                 "out": f"scope:{SCOPE}:session:{SID}", "in": "artifact:gone"})


def _other_extractor(ev):
    ev["logs"][SID[:8]] = "1 sessions to extract (extractor: claude/sonnet — own harness)\n"


def _shared_log(ev):
    ev["logs"][SID[:8]] = ev["logs"][SID[:8]] * 2


def _opus_session(ev):
    ev["sessions"][0]["stdout"] = json.dumps({"modelUsage": {"claude-opus-5-5": {},
                                                             "claude-haiku-4-5": {}}})


def _preset_not_projected(ev):
    ev["personas"][SCOPE]["agent"] = "---\nmodel: inherit\n---\n"


def _contract_red(ev):
    ev["contract"] = {"exit": 1, "stdout": "1 violation"}


def _session_failed(ev):
    ev["sessions"][0]["exit"] = 1


#: (poison, check, subject, expected verdict)
CASES = [
    (_drop_vertex_session := (lambda ev: _drop_vertex(ev, ":session:" + SID)),
     "distilled", "boundary-trip", oracle.FAIL),
    (_foreign_claim, "claims-contained-and-scoped", "boundary-trip", oracle.FAIL),
    (_foreign_claim, "no-scope-leak", "boundary-trip", oracle.FAIL),
    (_claim_from_elsewhere, "claims-contained-and-scoped", "boundary-trip", oracle.FAIL),
    (_second_source, "session-derives-from-one-source", "boundary-trip", oracle.FAIL),
    (_no_touch, "written-files-touched", "boundary-trip", oracle.FAIL),
    (_no_block_row, "guard-rows", "boundary-trip", oracle.FAIL),
    (_denied_landed, "denied-writes-absent", "boundary-trip", oracle.FAIL),
    (_no_attempts, "denied-writes-absent", "boundary-trip", oracle.NOT_EVALUATED),
    (_allowed_missing, "allowed-writes-landed", "boundary-trip", oracle.FAIL),
    (_one_patch_for_both, "allowed-writes-landed", "boundary-trip", oracle.NOT_EVALUATED),
    (_one_patch_for_both, "denied-writes-absent", "boundary-trip", oracle.PASS),
    (_control_distilled, "control-undistilled", "boundary-control", oracle.FAIL),
    (_control_guarded, "control-no-guard-rows", "boundary-control", oracle.FAIL),
    (_control_blocked, "control-writes-landed", "boundary-control", oracle.FAIL),
    (_dangling, "edges-resolve", "write-boundary", oracle.FAIL),
    (_other_extractor, "distilled-on-luna", "boundary-trip", oracle.FAIL),
    (_opus_session, "model-is-preset", "boundary-trip", oracle.FAIL),
    (_shared_log, "distill-log-is-its-own", "boundary-trip", oracle.FAIL),
    (_preset_not_projected, "persona-carries-preset", SCOPE, oracle.FAIL),
    (_contract_red, "contract-check", "write-boundary", oracle.FAIL),
    (_session_failed, "session-ran", "boundary-trip", oracle.FAIL),
]


def main() -> int:
    config = matrix.by_name(ROOT)["write-boundary"]
    failures = []
    base = verdicts(clean(), config)
    not_passing = {k: v for k, v in base.items() if v != oracle.PASS}
    if not_passing:
        failures.append(f"clean evidence is not all-pass: {not_passing}")
    for poison, check, subject, want in CASES:
        ev = copy.deepcopy(clean())
        poison(ev)
        got = verdicts(ev, config).get((check, subject))
        if got != want:
            failures.append(f"{getattr(poison, '__name__', poison)} -> {check} "
                            f"[{subject}]: got {got}, want {want}")

    # A failure the matrix tags with an issue is known_red, not a new failure.
    typo = matrix.Config(
        name="t", summary="", manifests={"live-typo": ""},
        sessions=(matrix.Session(name="boundary-trip", scope=SCOPE, prompt="",
                                 writes=("src/denied.py",),
                                 denied_writes=("src/denied.py",),
                                 known=(("denied-writes-absent", 999),)),))
    ev = clean()
    _denied_landed(ev)
    got = verdicts(ev, typo).get(("denied-writes-absent", "boundary-trip"))
    if got != oracle.KNOWN:
        failures.append(f"known tag: got {got}, want {oracle.KNOWN}")

    for line in failures:
        print("FAIL", line)
    print(f"{len(CASES) + 2 - len(failures)}/{len(CASES) + 2} oracle cases hold")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
