"""The live tier's in-guest driver. Nothing here runs on the host.

Invoked by the cell producer's job as preparation steps and as the session:

    cell.py graph-dirs              (root)  lay out /opt/gremlin-server as compose does
    cell.py graph                           start the cell's own graph, wait for it
    cell.py materialize <config>            config dir, fixture project, policy, auth
    cell.py install <config>                `thalamus init --yes` for each harness
    cell.py run <config>                    the sessions, the distillation wait, evidence

Stdlib only, run by the image's `/usr/bin/python3`: the checkout's own venv is built
by a preparation step, and the driver must be able to say that step failed.

Everything the host needs comes back under `$HOME/qe-live-evidence/`, which is inside
the collected HOME workspace. Nothing is judged here — the oracle runs on the host,
against what this wrote, so it can also be run against poisoned evidence to show each
check can go red (`oracle_cases.py`).

## The graph

The layout is the documented one, reproduced without Docker: `config/` mounted at
`/opt/gremlin-server/conf/thalamus`, the graph file at
`/opt/gremlin-server/data/thalamus-graph.kryo`, the server started from
`/opt/gremlin-server` with `conf/thalamus/gremlin-server.yaml`. The path matters: the
durability flush is written against that one location (thalamus#148), and a cell that
put the graph elsewhere would reproduce that defect instead of measuring the write.

## Credentials

Two files arrive in a workspace that is never collected: `claude` and `openai`. Their
bytes are read into the session environment and never written anywhere else — a codex
API key is handed to `codex login --with-api-key` on stdin, and whatever auth file that
writes is deleted before the evidence is assembled. A value is never printed. The host
sweeps the collected HOME for the same bytes regardless.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
THALAMUS = HERE.parent.parent.parent
sys.path.insert(0, str(HERE))

import matrix  # noqa: E402

HOME = Path(os.environ.get("HOME", "/home/qelive"))
PROJECT = HOME / "project"
CONFIG = HOME / "thalamus-config"
EVIDENCE = HOME / "qe-live-evidence"
SECRETS = Path(os.environ.get("QE_LIVE_SECRETS", "/srv/qe-live-secrets"))
GREMLIN = Path("/opt/gremlin-server")
GRAPH_PORT = 8182

#: Per-session ceiling handed to `claude -p --max-budget-usd`, and the cell's total.
SESSION_BUDGET_USD = float(os.environ.get("QE_LIVE_SESSION_USD", "0.40"))
CELL_BUDGET_USD = float(os.environ.get("QE_LIVE_CELL_USD", "0.80"))
SESSION_TIMEOUT_S = 600
#: Every preparation step and the evidence collection, with no session and no
#: credential: proves the graph, the install and the dump before anything is spent.
SMOKE = os.environ.get("QE_LIVE_SMOKE") == "1"
DISTILL_WAIT_S = 900

#: JDK 17+ refuses Groovy's reflection into java.base unless it is opened, and the
#: failure is quiet: "Could not create GremlinScriptEngine", then `g` is unconfigured.
JAVA_OPENS = " ".join(
    f"--add-opens=java.base/{pkg}=ALL-UNNAMED"
    for pkg in ("java.io", "java.nio", "sun.nio.cs", "java.lang", "java.lang.invoke",
                "java.lang.reflect", "java.util", "java.util.concurrent",
                "java.util.concurrent.atomic", "java.net"))


def config_named(name: str) -> matrix.Config:
    return matrix.by_name(str(THALAMUS))[name]


def sh(argv: list[str], *, env: dict | None = None, cwd: Path | None = None,
       timeout: int = 900, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(argv, input=stdin, capture_output=True, text=True,
                          env=env, cwd=cwd, timeout=timeout, check=False)


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------- graph


def cmd_graph_dirs() -> int:
    """Root: the compose layout, owned by the session so the server can write it."""
    conf = GREMLIN / "conf" / "thalamus"
    conf.mkdir(parents=True, exist_ok=True)
    for name in ("gremlin-server.yaml", "tinkergraph.properties", "thalamus-graph.groovy"):
        shutil.copy2(THALAMUS / "config" / name, conf / name)
    (GREMLIN / "data").mkdir(parents=True, exist_ok=True)
    return sh(["chown", "-R", "1000:1000", str(GREMLIN)]).returncode


def cmd_graph() -> int:
    log = HOME / "gremlin-server.log"
    env = {**os.environ, "JAVA_OPTIONS": f"-Xms256m -Xmx1g {JAVA_OPENS}"}
    # setsid and every stream redirected: the preparation step waits for its pipes
    # to close, and a server holding one would hang the step until its timeout.
    with open(log, "ab") as out, open(os.devnull, "rb") as nul:
        subprocess.Popen(["bin/gremlin-server.sh", "conf/thalamus/gremlin-server.yaml"],
                         cwd=GREMLIN, env=env, stdin=nul, stdout=out, stderr=out,
                         start_new_session=True)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if port_open(GRAPH_PORT) and b"Channel started" in log.read_bytes():
            return 0
        time.sleep(2)
    sys.stderr.write(log.read_text(errors="replace")[-3000:])
    return 1


# --------------------------------------------------------------------- materialize


def _secret(name: str) -> str:
    path = SECRETS / name
    return path.read_text().strip() if path.is_file() else ""


def auth_env() -> dict[str, str]:
    """The session's model credentials, by the shape of what was handed over."""
    env: dict[str, str] = {}
    claude = _secret("claude")
    if claude.startswith("sk-ant-oat"):
        env["CLAUDE_CODE_OAUTH_TOKEN"] = claude
    elif claude:
        env["ANTHROPIC_API_KEY"] = claude
    return env


def cmd_materialize(name: str) -> int:
    config = config_named(name)
    # The config root: the manifests exactly as written, the presets, the sidecars.
    shutil.rmtree(CONFIG, ignore_errors=True)
    (CONFIG / "experts").mkdir(parents=True)
    (CONFIG / "presets").mkdir()
    for scope, text in config.manifests.items():
        (CONFIG / "experts" / f"{scope}.yaml").write_text(text)
    (CONFIG / "presets" / "cost.yaml").write_text(_yaml(matrix.COST_PRESETS))
    (CONFIG / "presets" / "budget.yaml").write_text(_yaml(matrix.BUDGET_PRESETS))
    for scope, body in config.mcp.items():
        (CONFIG / "mcp").mkdir(exist_ok=True)
        (CONFIG / "mcp" / f"{scope}.json").write_text(json.dumps(body, indent=2))
    for scope, skills in config.skills.items():
        for skill, text in skills.items():
            path = CONFIG / "skills" / scope / skill / "SKILL.md"
            path.parent.mkdir(parents=True)
            path.write_text(text)

    # The project the sessions work in. Not the thalamus checkout: that tree carries
    # its own project hooks, and a session run there would be measured against them.
    shutil.rmtree(PROJECT, ignore_errors=True)
    for sub in ("src", "notes"):
        (PROJECT / sub).mkdir(parents=True)
    (PROJECT / "README.md").write_text("# live-tier fixture project\n")
    (PROJECT / "src" / "app.py").write_text("print('fixture')\n")
    for argv in (["git", "init", "-q"], ["git", "add", "-A"],
                 ["git", "-c", "user.email=qe@live", "-c", "user.name=qe",
                  "commit", "-qm", "fixture"]):
        if sh(argv, cwd=PROJECT).returncode:
            print(f"fixture project: {' '.join(argv)} failed", file=sys.stderr)
            return 1

    # Distillation runs on Luna, through the stored policy — the path the console
    # writes — rather than a flag the hook never passes.
    policy = HOME / ".thalamus" / "extractor" / "policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(json.dumps({"version": 1, "passes": {"distill": matrix.DISTILL}}))

    if SMOKE:
        return 0
    openai = _secret("openai")
    if openai.startswith("{"):
        codex_home = HOME / ".codex"
        codex_home.mkdir(exist_ok=True)
        auth = codex_home / "auth.json"
        auth.write_text(openai)
        auth.chmod(0o600)
    elif openai:
        proc = sh(["codex", "login", "--with-api-key"], stdin=openai + "\n", timeout=60)
        if proc.returncode:
            print("codex login refused the key (exit "
                  f"{proc.returncode})", file=sys.stderr)
            return 1
    elif os.environ.get("QE_LIVE_CLAUDE_ONLY") != "1":
        print("no openai credential: distillation on Luna cannot run", file=sys.stderr)
        return 1
    if openai and not luna_answers():
        # No session will run, so nothing else would remove it before collection.
        (HOME / ".codex" / "auth.json").unlink(missing_ok=True)
        return 1
    if not auth_env():
        print("no claude credential: no session can run", file=sys.stderr)
        return 1
    return 0


def luna_answers() -> bool:
    """One tiny call on the distillation model, the way extract makes it.

    Every session's distillation depends on it, so a credential or model the API
    refuses stops the cell here — before any Claude session is paid for — with codex's
    own words in the preparation report, rather than as N identical distillation
    failures afterwards.
    """
    with tempfile.TemporaryDirectory(prefix="qe-live-luna-") as tmp:
        proc = sh(["codex", "exec", "--json", "--model", matrix.DISTILL["model"],
                   "--skip-git-repo-check", "--ephemeral"],
                  cwd=Path(tmp), stdin="Reply with the single word OK.\n", timeout=180)
    if proc.returncode == 0 and "turn.completed" in proc.stdout:
        return True
    print(f"luna probe: codex exit {proc.returncode}\nstdout: {proc.stdout[-1500:]}\n"
          f"stderr: {proc.stderr[-1500:]}", file=sys.stderr)
    return False


def _yaml(presets: dict) -> str:
    lines = []
    for name, sets in presets.items():
        lines.append(f"{name}:")
        lines += [f"  {key}: {value}" for key, value in sets.items()]
    return "\n".join(lines) + "\n"


def thalamus_argv(*args: str) -> list[str]:
    return [str(THALAMUS / ".venv" / "bin" / "thalamus"), *args]


def cmd_install(name: str) -> int:
    config = config_named(name)
    report = {}
    for harness in config.harnesses:
        proc = sh(thalamus_argv("init", "--yes", "--harness", harness),
                  cwd=THALAMUS, timeout=600)
        report[harness] = {"exit": proc.returncode, "stdout": proc.stdout[-3000:],
                           "stderr": proc.stderr[-3000:]}
        if proc.returncode:
            print(json.dumps(report[harness]), file=sys.stderr)
            return proc.returncode
    return 0


# ----------------------------------------------------------------------------- run


def session_argv(session: matrix.Session, sid: str, budget: float) -> list[str]:
    if session.harness == "codex":
        # Hook trust is codex's own persisted state and cannot be recomputed here
        # (`install.codex_trust_keys`), so the operator's interactive approval is
        # replaced by the flag codex provides for automation. What this does NOT
        # test is the trust path itself.
        return ["codex", "exec", "--profile", f"thalamus-{session.scope}", "--json",
                "--dangerously-bypass-hook-trust",
                "--dangerously-bypass-approvals-and-sandbox", session.prompt]
    return ["claude", "-p", "--agent", f"thalamus-{session.scope}",
            "--session-id", sid, "--output-format", "json",
            "--dangerously-skip-permissions", "--max-budget-usd", f"{budget:.2f}",
            session.prompt]


def run_session(session: matrix.Session, spent: float) -> dict:
    sid = str(uuid.uuid4())
    budget = min(SESSION_BUDGET_USD, max(CELL_BUDGET_USD - spent, 0.0))
    row: dict = {"name": session.name, "scope": session.scope, "harness": session.harness,
                 "disarmed": session.disarmed, "requested_session_id": sid}
    if budget < 0.05:
        row["skipped"] = f"cell budget spent (${spent:.2f} of ${CELL_BUDGET_USD:.2f})"
        return row
    env = {**os.environ, **auth_env(), "THALAMUS_SCOPE": session.scope,
           "THALAMUS_CONFIG_DIR": str(CONFIG)}
    if session.disarmed:
        env["THALAMUS_SANDBOX"] = "1"
    started = time.monotonic()
    try:
        proc = sh(session_argv(session, sid, budget), env=env, cwd=PROJECT,
                  timeout=SESSION_TIMEOUT_S)
        row.update(exit=proc.returncode, stdout=proc.stdout[-200_000:],
                   stderr=proc.stderr[-4000:])
    except subprocess.TimeoutExpired:
        row.update(exit=124, stdout="", stderr="session timed out")
    row["elapsed_s"] = round(time.monotonic() - started, 1)
    row["session_id"] = _session_id(session, row, sid)
    row["cost_usd"] = _claude_cost(row) if session.harness == "claude" else None
    return row


def _session_id(session: matrix.Session, row: dict, sid: str) -> str:
    if session.harness == "claude":
        return sid
    for line in (row.get("stdout") or "").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            return str(event.get("thread_id") or "")
    return ""


def _claude_cost(row: dict) -> float | None:
    try:
        return float(json.loads(row.get("stdout") or "{}").get("total_cost_usd"))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def wait_for_distillation(rows: list[dict]) -> None:
    """Until every armed session's SessionEnd log says extract finished, or time's up.

    The hook runs detached and writes nothing to the session, so the log is the only
    place its end is observable. Eval sync follows extract in the same detached shell,
    so a short settle after the extract line lets the Trace land too.
    """
    logs = HOME / ".thalamus" / "logs"
    deadline = time.monotonic() + DISTILL_WAIT_S
    pending = {r["session_id"] for r in rows
               if r.get("session_id") and not r.get("disarmed") and not r.get("skipped")}
    while pending and time.monotonic() < deadline:
        for sid in list(pending):
            log = logs / f"session-end-{sid[:8]}.log"
            text = log.read_text(errors="replace") if log.is_file() else ""
            if " extracted, " in text and " failed" in text:
                pending.discard(sid)
            elif "not distilling" in text or "nothing to distill" in text:
                pending.discard(sid)
        time.sleep(5)
    time.sleep(30 if not pending else 0)
    for row in rows:
        row["distill_wait_timed_out"] = row.get("session_id") in pending


def collect(config: matrix.Config, rows: list[dict]) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "sessions.json").write_text(json.dumps(rows, indent=2))

    env = {**os.environ, "THALAMUS_CONFIG_DIR": str(CONFIG)}
    proc = sh([str(THALAMUS / ".venv" / "bin" / "python"), str(HERE / "graph_dump.py"),
               str(EVIDENCE / "graph.json")], env=env, timeout=300)
    (EVIDENCE / "graph_dump.log").write_text(proc.stdout + proc.stderr)
    proc = sh(thalamus_argv("contract", "check"), env=env, cwd=THALAMUS, timeout=600)
    (EVIDENCE / "contract_check.json").write_text(json.dumps(
        {"exit": proc.returncode, "stdout": proc.stdout[-20000:],
         "stderr": proc.stderr[-4000:]}, indent=2))
    proc = sh(thalamus_argv("init", "--check", "--json"), env=env, cwd=THALAMUS,
              timeout=300)
    (EVIDENCE / "init_check.json").write_text(json.dumps(
        {"exit": proc.returncode, "stdout": proc.stdout[-40000:],
         "stderr": proc.stderr[-4000:]}, indent=2))

    # The files each session was asked to write, as the project now holds them.
    wanted = sorted({w for s in config.sessions for w in s.writes})
    (EVIDENCE / "project_files.json").write_text(json.dumps(
        {w: (PROJECT / w).is_file() for w in wanted}, indent=2))

    # Generated personas: what the cost preset and the MCP sidecar projected to.
    personas = {}
    for scope in config.manifests:
        agent = HOME / ".claude" / "agents" / f"thalamus-{scope}.md"
        profile = HOME / ".codex" / f"thalamus-{scope}.config.toml"
        personas[scope] = {
            "agent": agent.read_text() if agent.is_file() else None,
            "codex_profile": profile.read_text() if profile.is_file() else None,
        }
    (EVIDENCE / "personas.json").write_text(json.dumps(personas, indent=2))

    # Transcripts, so the oracle can see what hook context reached each model.
    transcripts = {}
    for row in rows:
        sid = row.get("session_id")
        if not sid:
            continue
        hits = list((HOME / ".claude" / "projects").rglob(f"{sid}.jsonl"))
        hits += [p for p in (HOME / ".codex" / "sessions").rglob("*.jsonl")
                 if sid in p.name]
        transcripts[sid] = hits[0].read_text(errors="replace")[-400_000:] if hits else None
    (EVIDENCE / "transcripts.json").write_text(json.dumps(transcripts))


def cmd_run(name: str) -> int:
    config = config_named(name)
    rows: list[dict] = []
    spent = 0.0
    for session in () if SMOKE else config.sessions:
        row = run_session(session, spent)
        spent += row.get("cost_usd") or 0.0
        rows.append(row)
        print(f"{session.name}: exit {row.get('exit')} "
              f"sid {str(row.get('session_id'))[:8]} "
              f"${row.get('cost_usd') or 0:.3f} {row.get('elapsed_s')}s", flush=True)
    wait_for_distillation(rows)
    try:
        collect(config, rows)
    finally:
        # The one credential file this driver caused to exist. Not evidence, and not
        # something the collected HOME may carry back.
        (HOME / ".codex" / "auth.json").unlink(missing_ok=True)
    return 0


def main() -> int:
    verb, *rest = sys.argv[1:]
    if verb == "graph-dirs":
        return cmd_graph_dirs()
    if verb == "graph":
        return cmd_graph()
    if verb == "materialize":
        return cmd_materialize(rest[0])
    if verb == "install":
        return cmd_install(rest[0])
    if verb == "run":
        return cmd_run(rest[0])
    print(f"unknown verb {verb!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
