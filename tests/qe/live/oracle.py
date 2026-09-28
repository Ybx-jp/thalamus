"""Judge one live-tier cell from what it brought back. Runs on the host.

Stdlib only. The input is the collected HOME of one cell — `qe-live-evidence/` plus
the `.thalamus/` ledgers the product wrote there — and the `matrix.Config` it ran.
The output is one row per check: `pass`, `fail`, `known_red` (a failure naming a
filed issue), or `not_evaluated` with the reason its precondition did not hold.

## Two rules the checks keep

**An absence is only read beside its control.** "No guard row", "no Session", "the
file is not there" are each also what a hook that never ran produces. Every such
check here is paired with a disarmed session that must show the opposite, and the
config-level check `controls-held` fails the cell when a control did not.

**A check whose precondition the model did not supply is not evaluated.** A guard
cannot block a Write that was never attempted. Where a check depends on the model
having called a tool, the transcript is read for the call first, and if it is not
there the check says so rather than passing on the absence.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path

import matrix

PASS, FAIL, KNOWN, NOT_EVALUATED = "pass", "fail", "known_red", "not_evaluated"


@dataclass
class Result:
    check: str
    subject: str
    verdict: str
    detail: str
    issue: int = 0

    def as_dict(self) -> dict:
        return {"check": self.check, "subject": self.subject, "verdict": self.verdict,
                "detail": self.detail, "issue": self.issue}


class Evidence:
    """Everything one cell brought back, read once."""

    def __init__(self, home: Path):
        self.home = home
        ev = home / "qe-live-evidence"
        self.sessions = _json(ev / "sessions.json", [])
        graph = _json(ev / "graph.json", {"vertices": [], "edges": []})
        self.graph_present = (ev / "graph.json").is_file()
        self.vertices = {v.get("id"): v for v in graph.get("vertices", [])}
        self.edges = graph.get("edges", [])
        self.contract = _json(ev / "contract_check.json", {})
        self.init_check = _json(ev / "init_check.json", {})
        self.project_files = _json(ev / "project_files.json", {})
        self.personas = _json(ev / "personas.json", {})
        self.transcripts = _json(ev / "transcripts.json", {})
        self.guard_rows = []
        for path in sorted((home / ".thalamus" / "guards").glob("*.jsonl")):
            self.guard_rows += _jsonl(path)
        self.usage = _jsonl(ev / "codex-usage.jsonl")

    def out_edges(self, vid: str, label: str) -> list[dict]:
        return [e for e in self.edges if e.get("out") == vid and e.get("label") == label]

    def distill_log(self, sid: str) -> str:
        path = self.home / ".thalamus" / "logs" / f"session-end-{sid[:8]}.log"
        return path.read_text(errors="replace") if path.is_file() else ""

    def budget_state(self, sid: str) -> dict:
        return _json(self.home / ".thalamus" / "budget" / f"{sid}.json", {})


def _json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _jsonl(path: Path) -> list[dict]:
    rows = []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


# ------------------------------------------------------------------ per session


def session_vid(scope: str, sid: str) -> str:
    return f"scope:{scope}:session:{sid}"


_WRITE_MARKERS = ('"name":"Write"', '"name": "Write"', "apply_patch", "*** Add File")


def _write_calls(transcript: str | None) -> list[str]:
    """Each file-writing tool call, as the transcript line that carries it.

    One line is one call on both harnesses: a Claude `Write` names one path, a codex
    patch names every file it adds — which is why a denied path in a codex patch
    takes the paths beside it down too, and why the allowed-write check reads calls
    rather than paths.
    """
    return [line for line in (transcript or "").splitlines()
            if any(marker in line for marker in _WRITE_MARKERS)]


def attempted_writes(transcript: str | None, path: str) -> bool:
    """Did the model call a file-writing tool naming this path at all?"""
    return any(path in call for call in _write_calls(transcript))


def attempted_alone(transcript: str | None, path: str, denied: tuple[str, ...]) -> bool:
    """Was this path written in a call that named none of the denied paths?"""
    return any(path in call and not any(d in call for d in denied)
               for call in _write_calls(transcript))


_CALL_MARKERS = ("tool_use", "function_call", "custom_tool_call", "mcp_tool_call")


def called_tool(transcript: str | None, needle: str) -> bool:
    """A tool call naming `needle`, in either harness's transcript shape."""
    return any(needle in line and any(m in line for m in _CALL_MARKERS)
               for line in (transcript or "").splitlines())


def judge_session(s: matrix.Session, row: dict, ev: Evidence) -> list[Result]:
    out: list[Result] = []
    sid = row.get("session_id") or ""
    subject = f"{s.name} ({sid[:8] or 'no session id'})"
    known = dict(s.known)

    def add(check: str, ok: bool | None, detail: str) -> None:
        if ok is None:
            out.append(Result(check, subject, NOT_EVALUATED, detail))
        elif ok:
            out.append(Result(check, subject, PASS, detail))
        elif check in known:
            out.append(Result(check, subject, KNOWN, detail, known[check]))
        else:
            out.append(Result(check, subject, FAIL, detail))

    if row.get("skipped"):
        add("session-ran", None, row["skipped"])
        return out
    transcript = ev.transcripts.get(sid)
    ran = bool(sid) and row.get("exit") == 0 and transcript is not None
    add("session-ran", ran,
        f"exit {row.get('exit')}, transcript {'present' if transcript else 'absent'}"
        + ("" if ran else f"; stderr: {(row.get('stderr') or '')[-300:]}"))
    if not ran:
        return out

    if s.disarmed:
        return out + judge_control(s, sid, subject, transcript, ev)

    add("model-is-preset", *_model_check(s, row, transcript))

    vid = session_vid(s.scope, sid)
    session = ev.vertices.get(vid)
    add("distilled", session is not None and session.get("scope") == s.scope,
        f"{vid} {'present' if session else 'absent'}"
        + ("; distill wait timed out" if row.get("distill_wait_timed_out") else ""))

    log = ev.distill_log(sid)
    want = f"extractor: {matrix.DISTILL['harness']}/{matrix.DISTILL['model']}"
    add("distilled-on-luna", want in log if log else None,
        f"looked for `{want}` in the SessionEnd log"
        if log else "no SessionEnd log for this session")
    # The log is named by the id's first 8 characters. Another session's run landing
    # in it makes every line of it unattributable, the extractor line above included.
    headers = log.count("distilling session ")
    add("distill-log-is-its-own", headers == 1 if log else None,
        f"{headers} `distilling session` headers in session-end-{sid[:8]}.log")

    if session is not None:
        out += judge_edges(s, sid, subject, session, ev, add)

    if s.guard_rows:
        mine = [r for r in ev.guard_rows if r.get("session_id") == sid]
        missing = [spec for spec in s.guard_rows if not any(_row_matches(r, spec) for r in mine)]
        add("guard-rows", not missing,
            f"{len(mine)} rows for this session; missing: {missing}" if missing
            else f"{len(s.guard_rows)} expected rows present among {len(mine)}")

    if s.denied_writes or s.writes:
        denied = [w for w in s.denied_writes if attempted_writes(transcript, w)]
        if not denied:
            add("denied-writes-absent", None,
                "the model attempted none of the writes that should be denied")
        else:
            landed = [w for w in denied if ev.project_files.get(w)]
            add("denied-writes-absent", not landed,
                f"attempted {denied}; landed anyway: {landed}")
        allowed = [w for w in s.writes if w not in s.denied_writes]
        alone = [w for w in allowed if attempted_alone(transcript, w, s.denied_writes)]
        if allowed and not alone:
            add("allowed-writes-landed", None,
                "no permitted path was written in a call of its own — a call that "
                "also names a denied path is refused whole")
        elif alone:
            missing = [w for w in alone if not ev.project_files.get(w)]
            add("allowed-writes-landed", not missing,
                f"written alone {alone}; missing: {missing}")

    for needle in s.transcript_has:
        add("transcript-has", needle in transcript, f"`{needle}`")
    for needle in s.transcript_lacks:
        add("transcript-lacks", needle not in transcript, f"`{needle}`")

    if s.budget_stop:
        state = ev.budget_state(sid)
        main = (state.get("agents") or {}).get("main") or {}
        add("budget-stopped", bool(main.get("spent")) and main.get("denied", 0) >= 1,
            f"budget state: spent={main.get('spent')!r} denied={main.get('denied')}")
        ran_calls = transcript.count('"name":"Bash"') + transcript.count('"name": "Bash"')
        add("budget-held", None if not ran_calls else ran_calls >= 3,
            f"{ran_calls} Bash calls attempted against a cap of 2 "
            "(fewer than 3 means the cap was never approached)")
    return out


def _model_check(s: matrix.Session, row: dict, transcript: str) -> tuple[bool | None, str]:
    want = matrix.LIGHT_MODEL[s.harness]
    if s.harness == "claude":
        try:
            usage = json.loads(row.get("stdout") or "{}").get("modelUsage") or {}
        except ValueError:
            usage = {}
        if not usage:
            return None, "claude -p reported no modelUsage"
        # Every model the main loop billed must be the preset's; a hook's own model
        # call is not the session's.
        wrong = [m for m in usage if want not in m]
        return not wrong, f"modelUsage {sorted(usage)}; preset wants *{want}*"
    models = set()
    for line in transcript.splitlines():
        if '"turn_context"' in line or '"model"' in line:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            payload = event.get("payload") or {}
            if isinstance(payload, dict) and payload.get("model"):
                models.add(payload["model"])
    if not models:
        return None, "no model recorded in the codex rollout"
    return models == {want}, f"rollout models {sorted(models)}; preset wants {want}"


def judge_edges(s, sid, subject, session, ev: Evidence, add) -> list[Result]:
    vid = session["id"]
    sources = ev.out_edges(vid, "DERIVED_FROM")
    source_ok = (len(sources) == 1
                 and (ev.vertices.get(sources[0]["in"]) or {}).get("scope") == s.scope)
    add("session-derives-from-one-source", source_ok,
        f"{len(sources)} DERIVED_FROM edges; targets "
        f"{[e['in'] for e in sources]}")

    contains = ev.out_edges(vid, "CONTAINS")
    claims = [ev.vertices.get(e["in"]) or {"id": e["in"]} for e in contains]
    # An episodic claim's provenance is its `source` property naming the session it
    # was distilled from; DERIVED_FROM edges are for claims derived from a Source or
    # Chunk (ingest), which a distilled session's claims are not.
    bad = [c["id"] for c in claims
           if not str(c["id"]).startswith(f"scope:{s.scope}:claim:")
           or c.get("scope") != s.scope
           or c.get("source") != f"session:{sid}"]
    add("claims-contained-and-scoped",
        (bool(claims) or not s.claims_expected) and not bad,
        f"{len(claims)} claims; unscoped or not sourced to this session: {bad}")

    touched = [ev.vertices.get(e["in"]) or {} for e in ev.out_edges(vid, "TOUCHES")]
    landed = [w for w in s.writes if ev.project_files.get(w) and w not in s.denied_writes]
    missing = [w for w in landed
               if not any(str(a.get("path") or a.get("identifier") or "").endswith(w)
                          for a in touched)]
    if landed:
        add("written-files-touched", not missing,
            f"{len(touched)} Artifacts touched; written but not touched: {missing}")

    spawned = [ev.vertices.get(e["in"]) or {} for e in ev.out_edges(vid, "SPAWNS")]
    leaks = [t.get("id") for t in spawned if t.get("scope") != s.scope]
    neighbours = [ev.vertices.get(e["in"]) or {} for e in ev.edges if e.get("out") == vid]
    leaks += [n.get("id") for n in neighbours
              if n.get("label") not in ("Artifact",) and n.get("scope") not in (s.scope,)]
    add("no-scope-leak", not leaks,
        f"{len(neighbours)} neighbours, {len(spawned)} threads; foreign-scoped: {leaks}")

    if s.traced:
        traces = ev.out_edges(vid, "QUERIES")
        called = called_tool(ev.transcripts.get(sid), "memory_recall")
        add("trace-landed", bool(traces) if called else None,
            f"{len(traces)} QUERIES edges" if called
            else "the model never called thalamus memory_recall")
    return []


def _row_matches(row: dict, spec: tuple[str, str, str, str]) -> bool:
    guard, verdict, field, pattern = spec
    return (row.get("guard") == guard and row.get("verdict") == verdict
            and fnmatch.fnmatch(str(row.get(field) or ""), pattern))


def judge_control(s, sid, subject, transcript, ev: Evidence) -> list[Result]:
    """A disarmed session must show the opposite of every armed-session check."""
    out = []
    out.append(Result(
        "control-undistilled", subject,
        PASS if session_vid(s.scope, sid) not in ev.vertices else FAIL,
        "hooks disarmed: no Session may be written"))
    rows = [r for r in ev.guard_rows if r.get("session_id") == sid]
    out.append(Result("control-no-guard-rows", subject, PASS if not rows else FAIL,
                      f"{len(rows)} guard rows"))
    attempted = [w for w in s.writes if attempted_writes(transcript, w)]
    if attempted:
        missing = [w for w in attempted if not ev.project_files.get(w)]
        out.append(Result("control-writes-landed", subject,
                          PASS if not missing else FAIL,
                          f"attempted {attempted}; not landed {missing}"))
    else:
        out.append(Result("control-writes-landed", subject, NOT_EVALUATED,
                          "the model attempted none of the writes"))
    return out


# ------------------------------------------------------------------- per config


def judge_config(config: matrix.Config, ev: Evidence) -> list[Result]:
    out: list[Result] = []
    subject = config.name
    if not ev.graph_present:
        out.append(Result("graph-dumped", subject, FAIL, "no graph.json came back"))
    else:
        dangling = [e.get("id") for e in ev.edges
                    if e.get("out") not in ev.vertices or e.get("in") not in ev.vertices]
        out.append(Result("edges-resolve", subject, PASS if not dangling else FAIL,
                          f"{len(ev.edges)} edges, {len(ev.vertices)} vertices; "
                          f"dangling: {dangling[:10]}"))
    contract_exit = ev.contract.get("exit")
    out.append(Result("contract-check", subject,
                      PASS if contract_exit == 0 else FAIL,
                      f"exit {contract_exit}: {(ev.contract.get('stdout') or '')[-400:]}"))

    for scope in config.manifests:
        persona = ev.personas.get(scope) or {}
        harnesses = {s.harness for s in config.sessions if s.scope == scope}
        if "claude" in harnesses:
            agent = persona.get("agent") or ""
            want = f"model: {matrix.LIGHT_MODEL['claude']}"
            out.append(Result("persona-carries-preset", f"{scope} agent",
                              PASS if want in agent else FAIL,
                              f"looked for `{want}` in the generated agent file"
                              if agent else "no agent file generated"))
        if "codex" in harnesses:
            profile = persona.get("codex_profile") or ""
            want = f'model = "{matrix.LIGHT_MODEL["codex"]}"'
            out.append(Result("persona-carries-preset", f"{scope} codex profile",
                              PASS if want in profile else FAIL,
                              f"looked for `{want}` in the generated profile"
                              if profile else "no codex profile generated"))
        for server in (config.mcp.get(scope) or {}).get("mcpServers", {}):
            agent = persona.get("agent") or ""
            out.append(Result("persona-arms-mcp", f"{scope} agent",
                              PASS if f"{server}:" in agent else FAIL,
                              f"looked for server `{server}` in the agent frontmatter"))
    return out


def judge(config: matrix.Config, home: Path) -> list[dict]:
    ev = Evidence(home)
    results = judge_config(config, ev)
    by_name = {r.get("name"): r for r in ev.sessions}
    for session in config.sessions:
        row = by_name.get(session.name)
        if row is None:
            results.append(Result("session-ran", session.name, FAIL,
                                  "the driver recorded no row for this session"))
            continue
        results += judge_session(session, row, ev)
    return [r.as_dict() for r in results]


def spend(home: Path, luna_usd_per_mtok: tuple[float, float, float]) -> dict:
    """What the cell spent: Claude as `claude -p` priced it, codex from token counts.

    `luna_usd_per_mtok` is (input, cached input, output) per million tokens, supplied
    by the caller — the price is the operator's figure, not this module's.
    """
    ev = Evidence(home)
    claude = sum(r.get("cost_usd") or 0.0 for r in ev.sessions)
    tokens = {"input": 0, "cached": 0, "output": 0}
    for row in ev.usage:
        usage = row.get("usage") or {}
        cached = int(usage.get("cached_input_tokens") or 0)
        tokens["cached"] += cached
        tokens["input"] += int(usage.get("input_tokens") or 0) - cached
        tokens["output"] += int(usage.get("output_tokens") or 0)
    rate_in, rate_cached, rate_out = luna_usd_per_mtok
    codex = (tokens["input"] * rate_in + tokens["cached"] * rate_cached
             + tokens["output"] * rate_out) / 1e6
    return {"claude_usd": round(claude, 4), "codex_usd": round(codex, 4),
            "codex_tokens": tokens, "codex_calls": len(ev.usage),
            "total_usd": round(claude + codex, 4)}
