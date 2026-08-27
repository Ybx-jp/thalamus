"""The executable half of the oracle. Runs in the guest, stdlib only.

`spec.CHECKS` says what must be true and why; this says how to find out. They are kept
apart because the spec has to be readable on both sides of the boundary — the host reads
it to plan a matrix, the guest reads it to know what it is asserting — while the finding
out is guest-only work that needs a filesystem, a process table and a port.

**The oracle imports `verify()` rather than parsing its printout.** `thalamus init` has
no `--json` and no porcelain mode, so the alternative was scraping human text for glyphs.
`install.verify()` returns `list[Check]` with `name/ok/detail/advisory/pending`, which is
the same data the printout is rendered *from*, so reading it directly removes a whole
class of false finding where a wording change reads as a defect. The one place the
rendered text is still parsed is the marker check, because there the rendering IS the
subject.

**Coverage is accounted for, never assumed.** Every name in `spec.CHECKS` appears in
exactly one of `EVALUATORS` or `DEFERRED`, and `lint.py` fails if that stops being true.
A check that quietly has no implementation would land in `not_evaluated` with no reason,
which is indistinguishable from one whose evidence was missing on the day — and telling
those apart is the whole difference between "we did not look" and "we looked and could
not see".

**A pass must state what its control observed.** `ok()` refuses to build a passing result
from an empty control string. That is the suite's own rule made mechanical rather than
left to the author's memory: an absence-assertion whose control did not run has not
passed, it has failed to look. `spec.Check.control` says in prose what the control must
be; the string handed to `ok()` says what it actually saw this run.

Two entry points:

    python3 checks.py snapshot <label>    # record the box's state at a phase boundary
    python3 checks.py evaluate            # emit the findings as JSON on stdout

Snapshots exist because most of these checks are differential. "No thalamus artifact is
present" means nothing without the same probe reporting PRESENT after the install, and
"the second init added no wiring" means nothing unless the first init wrote some. They
must run as the guest user, not as root: `verify()` reads `Path.home()`, so a snapshot
taken as root describes `/root` and every check downstream would be reading a home the
install never touched.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spec  # noqa: E402

ARTIFACTS = Path(os.environ.get("QE_ARTIFACTS", "/tmp/qe-artifacts"))
HOME = Path(os.environ.get("QE_GUEST_HOME", "/home/ubuntu"))
REPO = Path(os.environ.get("QE_REPO", str(HOME / "thalamus")))
CONFIG_NAME = os.environ.get("QE_CONFIG", "baseline")


def _config_removes() -> tuple[str, ...]:
    """What this cell's config took off PATH, read from the spec the guest carries."""
    for config in spec.CONFIGS:
        if config.name == CONFIG_NAME:
            return config.removes
    return ()

CONSOLE_HOST = "127.0.0.1"
#: Overridable because a hardcoded port collides with a real console on any box
#: that runs one. A cell that probes someone else's console reports on it.
CONSOLE_PORT = int(os.environ.get("QE_CONSOLE_PORT", "8378"))
GRAPH_PORT = 8182

PASS = "pass"
FAIL = "fail"
NOT_EVALUATED = "not_evaluated"

#: The five markers `init --check` renders, from install.py:590-601 and the legend at
#: docs/getting-started.md:108-122. `✗` is the only one that fails the run.
MARK_OK = "✓"        # ✓ verified by running it
MARK_PENDING = "○"   # ○ not installed yet — never fails the run
MARK_ADVISORY = "!"  # ! an advisory about the environment, and it is TRUE
MARK_BLOCKED = "?"   # ? the check could not run: nobody looked, the answer is unknown
MARK_FAIL = "✗"      # ✗ in place and wrong — only these fail

#: Every marker the renderer can emit, and the alphabet `CHECK_LINE` is built from.
#: Derived rather than restated: a marker constant that the line regex did not know
#: about was invisible to this whole file — a check moving onto it did not become an
#: unmatched line, it stopped being parsed at all, and every count drawn from
#: `parse_check_lines` shortened silently. That is what `?` did before it was added
#: here, and one alphabet is what stops it recurring.
MARKS = (MARK_OK, MARK_PENDING, MARK_ADVISORY, MARK_BLOCKED, MARK_FAIL)

#: Line shape, install.py:601: two spaces, marker, space, name, ": ", detail.
CHECK_LINE = re.compile(r"^  ([" + "".join(MARKS) + r"]) ([^:]+): (.*)$")

#: The substring install.py:623-626 uses to recognise its own hook entries.
OUR_HOOK_MARKER = "thalamus/harness/hooks"

#: install.py:131 declares 13 scripts across 17 entries in HOOK_WIRING.
EXPECTED_HOOK_ENTRIES = 17

#: The rendering a HEALTHY MCP registration produces: a backticked server name, the
#: word `in`, one location, and nothing after it. Every unhealthy branch appends a
#: clause. Matching the healthy shape is stable under rewording of the diagnoses;
#: enumerating the diagnoses is not. Used by `check_moved_checkout_is_named`.
_HEALTHY_MCP_DETAIL = re.compile(r"^`[\w-]+` in \S+$")


@dataclass
class Result:
    state: str
    detail: str
    #: What the positive control observed this run. Mandatory on a pass.
    control: str = ""


def ok(detail: str, control: str) -> Result:
    """A passing result, which must say what its control saw.

    An empty control is a programming error in this file, not a guest condition, so it
    degrades to `not_evaluated` rather than raising: one badly written check must not
    take the whole cell's verdict down with it.
    """
    if not control.strip():
        return Result(NOT_EVALUATED,
                      "a pass was claimed with no control observation, so it cannot be "
                      "distinguished from a check that looked at nothing")
    return Result(PASS, detail, control)


def bad(detail: str, control: str = "") -> Result:
    return Result(FAIL, detail, control)


def skip(reason: str) -> Result:
    return Result(NOT_EVALUATED, reason)


# ---------------------------------------------------------------------------------
# Reading the box
# ---------------------------------------------------------------------------------

#: Paths whose mere existence means the box has seen the project.
PROJECT_ARTIFACTS = (
    ".thalamus", "thalamus", ".claude/settings.json", ".cursor", ".codex",
)

#: `.claude.json` is judged on content, for the same reason the host's golden gate does:
#: the agent CLI's installer writes it, and the golden image is supposed to have the CLI
#: installed. Measured 2026-08-21 — the first version of this check counted its presence
#: and reported the image the matrix is built to boot as a box that had already seen the
#: project. What means "seen" is project state: `mcpServers` (what `thalamus init` writes
#: via `claude mcp add`), `projects`, or the name anywhere in the file.
AGENT_STATE_FILE = ".claude.json"
AGENT_STATE_PROJECT_KEYS = ("mcpServers", "projects")


def agent_state_is_dirty(path: Path) -> bool:
    """Whether `.claude.json` carries project state, as opposed to install metadata."""
    try:
        text = path.read_text()
    except OSError:
        return False
    try:
        data = json.loads(text)
    except ValueError:
        return True          # unreadable is a finding, never a clean pass
    if not isinstance(data, dict):
        return True
    if any(data.get(key) for key in AGENT_STATE_PROJECT_KEYS):
        return True
    return "thalamus" in text.lower()

#: Dumps `verify()` structurally. Run inside the checkout's venv, as the guest user.
_VERIFY_DUMP = (
    "import json;"
    "from thalamus.harness.install import verify;"
    "print(json.dumps([{'name': c.name, 'ok': c.ok, 'detail': c.detail,"
    " 'advisory': c.advisory, 'pending': c.pending} for c in verify()]))"
)

_SCOPES_DUMP = (
    "import json;"
    "from thalamus.contract.manifest import available_scopes;"
    "print(json.dumps(available_scopes()))"
)


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _listdir(path: Path) -> list[str]:
    try:
        return sorted(p.name for p in path.iterdir())
    except OSError:
        return []


def run(argv: list[str], timeout: int = 180, cwd: Path | None = None,
        env: dict | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              cwd=None if cwd is None else str(cwd),
                              env={**os.environ, **(env or {})})
    except FileNotFoundError:
        return 127, f"{argv[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _venv_python() -> Path:
    return REPO / ".venv" / "bin" / "python"


def _dump(code: str, env: dict | None = None):
    """Run a one-liner in the checkout's venv and parse its JSON, or None."""
    return _dump_from(_venv_python(), code, env=env)


def _dump_from(python: Path, code: str, env: dict | None = None,
               cwd: Path | None = None):
    """The same, from an interpreter named explicitly.

    The wheel probe reads `contract.paths` out of a venv that is not the checkout's,
    and it has to be the same reader: two spellings of "ask the package where it
    thinks it is" would eventually answer differently for a reason that is about the
    two spellings. `cwd` is a parameter for that probe's sake — `python -c` puts the
    working directory on `sys.path`, so a wheel interrogated from inside the checkout
    could answer for a package the checkout holds rather than the one installed.
    """
    if not python.exists():
        return None
    rc, out = run([str(python), "-c", code], cwd=REPO if cwd is None else cwd, env=env)
    if rc != 0:
        return None
    for line in reversed(out.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def _hook_entries() -> list[dict]:
    """Every hook entry in the user settings file, flattened.

    install.py:664 writes `{"type": "command", "command": "<abs path>"}` — a bare path,
    no arguments and no shell, so the command needs no splitting to be treated as a file.
    """
    settings = _read_json(HOME / ".claude" / "settings.json") or {}
    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "command" and isinstance(node.get("command"), str):
                found.append(node)
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(settings.get("hooks", {}))
    return found


def _our_hooks() -> list[str]:
    return [e["command"] for e in _hook_entries() if OUR_HOOK_MARKER in e["command"]]


def _shipped_skills() -> list[str]:
    """The skills the checkout ships, by the same rule install.shipped_skills (:1082) uses."""
    root = REPO / "src" / "thalamus" / "harness" / "skills"
    out = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return out
    for entry in entries:
        skill = entry / "SKILL.md"
        try:
            if skill.is_file() and skill.read_text().startswith("---"):
                out.append(entry.name)
        except OSError:
            continue
    return out


def _skill_links() -> dict[str, str]:
    root = HOME / ".claude" / "skills"
    out: dict[str, str] = {}
    try:
        entries = list(root.iterdir())
    except OSError:
        return out
    for entry in entries:
        if entry.is_symlink():
            try:
                out[entry.name] = os.readlink(entry)
            except OSError:
                out[entry.name] = "<unreadable>"
    return out


def _dangling_skill_links() -> list[str]:
    root = HOME / ".claude" / "skills"
    return sorted(name for name in _skill_links()
                  if not (root / name).exists())


def tcp_open(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_get(path: str, timeout: float = 10.0) -> tuple[int, int]:
    """(status, body length). Status 0 means the request could not be made."""
    url = f"http://{CONSOLE_HOST}:{CONSOLE_PORT}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, len(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, len(exc.read())
        except OSError:
            return exc.code, 0
    except (urllib.error.URLError, OSError, ValueError):
        return 0, 0


def _shell_assets() -> list[str]:
    """The service worker's precache list, read out of sw.js.

    sw.js:12-20 declares `const SHELL = [...]` with entries relative to the worker, so
    `./` is the app root and the rest take a leading slash to become server paths.
    """
    sw = REPO / "src" / "thalamus" / "console" / "static" / "sw.js"
    try:
        text = sw.read_text()
    except OSError:
        return []
    match = re.search(r"const SHELL\s*=\s*\[(.*?)\]", text, re.S)
    if not match:
        return []
    out = []
    for raw in re.findall(r'"([^"]+)"', match.group(1)):
        out.append("/" if raw == "./" else "/" + raw.lstrip("./"))
    return out


# ---------------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------------

def snapshot(label: str) -> dict:
    state = {
        "label": label,
        "artifacts_present": {
            **{n: (HOME / n).exists() for n in PROJECT_ARTIFACTS},
            AGENT_STATE_FILE: agent_state_is_dirty(HOME / AGENT_STATE_FILE),
        },
        "our_hooks": _our_hooks(),
        "all_hook_entries": len(_hook_entries()),
        "skill_links": _skill_links(),
        "dangling_skill_links": _dangling_skill_links(),
        "shipped_skills": _shipped_skills(),
        "agents": _listdir(HOME / ".claude" / "agents"),
        "venv_cli": (REPO / ".venv" / "bin" / "thalamus").exists(),
    }
    if label in ("installed", "reinstalled"):
        state["verify"] = _dump(_VERIFY_DUMP)
    if label == "console":
        state["console"] = _console_probe()
    if label == "wheel":
        state["wheel"] = _wheel_probe()
    if label == "graph-ready":
        state["port_open"] = tcp_open("127.0.0.1", GRAPH_PORT)
        state["query_ok"] = _graph_answers()
    if label == "scopes":
        state["scopes_default"] = _dump(_SCOPES_DUMP)
        # The control: an explicit config dir must resolve a DIFFERENT set, or the
        # probe is not reading the override at all and would report the same number
        # whatever the box holds.
        alt = ARTIFACTS / "alt-config" / "experts"
        alt.mkdir(parents=True, exist_ok=True)
        (alt / "zz-control-scope.yaml").write_text("scope: zz-control-scope\n")
        state["scopes_override"] = _dump(
            _SCOPES_DUMP, env={"THALAMUS_CONFIG_DIR": str(alt.parent)})
        state["tracked_manifests"] = _tracked_manifest_count()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / f"snap-{label}.json").write_text(json.dumps(state, indent=2))
    return state


def _graph_answers() -> bool:
    """Whether the cell's graph answers a query, not merely accepts a connection.

    The distinction is the whole of issue #55: a port that accepts while the server is
    still starting is what makes "the graph is down" the wrong diagnosis.
    """
    result = _dump(
        "import json;"
        "from thalamus.substrate.writer import connect;"
        "g = connect();"
        "print(json.dumps(bool(g.V().limit(1).toList()) or True))"
    )
    return result is True


def _tracked_manifest_count() -> int | None:
    rc, out = run(["git", "ls-files", "config/experts"], cwd=REPO, timeout=60)
    if rc != 0:
        return None
    return len([ln for ln in out.splitlines() if ln.strip().endswith(".yaml")])


def _console_probe() -> dict:
    """Fetch the shell and a path the server does not serve.

    The 404 control is not decoration. A server answering 200 for everything satisfies
    every asset assertion in this phase, so "the page loads" is only evidence once
    something is shown NOT to load.
    """
    shell = _shell_assets()
    return {
        "root": http_get("/"),
        "control_404": http_get("/console/"),
        "shell_paths": shell,
        "shell_results": {path: http_get(path) for path in shell},
    }


#: The `verify()` checks that look for a directory anchored on PROJECT_ROOT, by the
#: names install.py renders them under (install.py:1642, :1357, :1482). All three
#: resolve `PROJECT_ROOT / "src" / "thalamus" / "harness" / "hooks" / <harness>` and
#: report a `missing: [...]` list, so all three read the anchor and nothing else.
SCRIPT_PRESENCE_CHECKS = ("hook scripts present", "cursor hook scripts present",
                          "codex hook scripts present")

#: What the package thinks its project root is, and whether a checkout is there. Run
#: under both interpreters, so the two answers are comparable rather than merely both
#: recorded.
_PATHS_DUMP = (
    "import json;"
    "from thalamus.contract.paths import PROJECT_ROOT as r;"
    "print(json.dumps({'project_root': str(r),"
    "'pyproject': (r / 'pyproject.toml').is_file(),"
    "'config_experts': (r / 'config' / 'experts').is_dir(),"
    "'hook_dir': (r / 'src' / 'thalamus' / 'harness' / 'hooks' / 'claude-code')"
    ".is_dir()}))"
)


def _probe_home(name: str) -> Path:
    """A home directory of this probe's own.

    The cell's own HOME has been installed to and uninstalled from by the time the
    wheel phase runs, and a probe reading that state would be reading the checkout's
    install rather than the packaged layout. One per CLI, so neither probe reads the
    other's leftovers either.
    """
    home = ARTIFACTS / f"{name}-probe-home"
    home.mkdir(parents=True, exist_ok=True)
    return home


def _init_check_from(cli: Path, home: Path) -> dict:
    """`thalamus init --check` from one CLI, with a home of its own.

    The documented pre-install command (getting-started:127), which is also what the
    reproduction of #35 ran. `wheel-probe` rather than `thalamus-init` for the budget:
    `verify()` calls `probe_entry_point`, which allows itself 180 s for a `uv run`
    resolution, and a probe killed inside a wait the product considers normal reports
    as missing evidence rather than as a finding.
    """
    if not cli.exists():
        return {"cli": str(cli), "present": False}
    rc, out = run([str(cli), "init", "--check"], timeout=spec.TIMEOUTS["wheel-probe"],
                  cwd=home, env={"HOME": str(home)})
    lines = parse_check_lines(out)
    return {
        "cli": str(cli),
        "present": True,
        "rc": rc,
        "lines": len(lines),
        "scripts": {name: [mark, detail] for mark, name, detail in lines
                    if name in SCRIPT_PRESENCE_CHECKS},
    }


def _wheel_probe() -> dict:
    """What the installed wheel resolves, and what the checkout resolves beside it.

    Both halves are taken here, in one function, on the same box and minutes apart.
    The checkout half is the control: "the wheel cannot find its hook scripts" and
    "this box renders no such line" are the same reading otherwise, and the second one
    would report the defect on a tree where it had been fixed.
    """
    venv = HOME / spec.WHEEL_VENV_DIRNAME
    wheel_python = venv / "bin" / "python"
    wheel_home = _probe_home("wheel")
    return {
        "venv": str(venv),
        "installed": wheel_python.exists(),
        "wheel_paths": _dump_from(wheel_python, _PATHS_DUMP, cwd=wheel_home),
        "checkout_paths": _dump_from(_venv_python(), _PATHS_DUMP),
        "wheel_cli": _init_check_from(venv / "bin" / "thalamus", wheel_home),
        "checkout_cli": _init_check_from(REPO / ".venv" / "bin" / "thalamus",
                                         _probe_home("checkout")),
    }


def load_snapshot(label: str) -> dict | None:
    return _read_json(ARTIFACTS / f"snap-{label}.json")


def step_log(phase: str) -> str:
    try:
        return (ARTIFACTS / f"step-{phase}.log").read_text(errors="replace")
    except OSError:
        return ""


def step_rc(phase: str) -> int | None:
    try:
        return int((ARTIFACTS / f"step-{phase}.rc").read_text().strip())
    except (OSError, ValueError):
        return None


def parse_check_lines(text: str) -> list[tuple[str, str, str]]:
    """(marker, name, detail) for every rendered check line."""
    out = []
    for line in text.splitlines():
        match = CHECK_LINE.match(line.rstrip())
        if match:
            out.append((match.group(1), match.group(2), match.group(3)))
    return out


# ---------------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------------

def check_never_seen_before_the_run() -> Result:
    before, after = load_snapshot("preflight"), load_snapshot("installed")
    if before is None:
        return skip("no preflight snapshot, so nothing is known about the box before "
                    "the sequence ran")
    if after is None:
        return skip("no post-install snapshot, so the probe was never shown capable of "
                    "reporting an artifact PRESENT and a clean preflight means nothing")
    present_before = [n for n, seen in before["artifacts_present"].items() if seen]
    present_after = [n for n, seen in after["artifacts_present"].items() if seen]
    if not present_after:
        return bad("the same probe reports nothing present even after the install, so "
                   "it is not looking at paths this install writes",
                   "post-install probe found 0 artifacts")
    control = (f"the same probe found {len(present_after)} artifact(s) after the "
               f"install: {', '.join(present_after)}")
    if present_before:
        return bad(f"the box already carried {', '.join(present_before)} before the "
                   "sequence ran, so no first-run property is under test", control)
    return ok("no project artifact was present before the sequence", control)


def check_host_graph_is_unreachable() -> Result:
    """PREFLIGHT: the host's graph must be unreachable; the cell's own must not be.

    The isolation probe establishes the denial at G3. What this adds is the control the
    probe cannot give itself: that a graph on this port IS reachable when it is the
    cell's own, so "denied" means denied rather than "nothing runs on 8182 anywhere".
    """
    own = tcp_open("127.0.0.1", GRAPH_PORT)
    probe = _read_json(Path("/tmp/qe-probe.json")) or {}
    entries = [p for p in probe.get("probes", []) if p.get("name") == "host-graph-port"]
    if not entries:
        return skip("the isolation probe recorded no host-graph-port result")
    verdict = entries[0].get("verdict")
    if not own:
        return skip("the cell's own graph is not listening on "
                    f"127.0.0.1:{GRAPH_PORT}, so a refused host graph cannot be "
                    "distinguished from a port nothing serves anywhere")
    control = (f"the cell's OWN graph answered on 127.0.0.1:{GRAPH_PORT}, so the port "
               "is reachable when it should be")
    if verdict != "pass":
        return bad(f"the host's graph port was {entries[0].get('got')} from inside the "
                   "cell", control)
    return ok("the host's graph is unreachable from the cell", control)


def check_cli_exists_after_sync() -> Result:
    rc = step_rc("synced")
    if rc is None:
        return skip("the synced step recorded no exit code")
    cli = REPO / ".venv" / "bin" / "thalamus"
    if not cli.exists():
        return bad(f"{cli} does not exist after `uv sync`, which getting-started.md:46 "
                   "states is where the CLI lands", f"uv sync exited {rc}")
    # `--help`, not `--version`: measured 2026-08-21, this CLI has no version flag and
    # answers `--version` with `error: unrecognized arguments` and exit 2. Asserting a
    # flag that does not exist would report the CLI as broken on every green box.
    vrc, out = run([str(cli), "--help"], timeout=120)
    if vrc != 0:
        return bad(f"{cli} exists but `--help` exited {vrc}: {out.strip()[:200]}",
                   "the file exists, so the failure is the CLI and not the path")
    if "usage:" not in out.lower():
        return bad(f"{cli} exited 0 but printed no usage, so it is not the CLI",
                   f"{len(out.strip())} bytes of output were captured")
    return ok(f"{cli} exists and answers `--help`",
              f"`--help` exited 0 with {len(out.strip())} bytes carrying a usage line, "
              "so the probe distinguishes a working CLI from a missing one")


def check_check_exits_zero_before_install() -> Result:
    """CHECKED: getting-started:127 promises --check is safe before installing.

    Exit 1 comes only from a check that is `ok=False` and none of advisory, pending or
    blocked (install.py:2177-2185), so a non-zero here names something in place and
    wrong on a box where nothing is in place at all.

    The blocked count rides in the control because exit 0 alone is too weak a
    reading of the no-jq cell. A run where the `jq` line and everything downstream of
    it simply stopped being rendered would also exit 0, and would be the same output
    as a box that has jq. `?` is what a prerequisite's absence must produce, so
    counting it is what tells the two apart.
    """
    rc = step_rc("checked")
    if rc is None:
        return skip("the checked step recorded no exit code")
    lines = parse_check_lines(step_log("checked"))
    if not lines:
        return skip("the --check output carried no rendered check lines, so its exit "
                    "code cannot be attributed to anything")
    failing = [f"{n}: {d}" for m, n, d in lines if m == MARK_FAIL]
    blocked = [n for m, n, _ in lines if m == MARK_BLOCKED]
    control = (f"{len(lines)} check line(s) were parsed out of the run, "
               f"{len(failing)} of them failures and {len(blocked)} could-not-run"
               + (f" ({', '.join(blocked[:4])})" if blocked else ""))
    if rc != 0:
        return bad(f"`init --check` exited {rc} before any install, naming: "
                   f"{'; '.join(failing[:4]) or '(no failure line was rendered)'}",
                   control)
    return ok("`init --check` exited 0 before the install", control)


def check_no_failure_marker_beside_skipped() -> Result:
    """CHECKED: a check that could not run must not borrow the failure marker.

    The legend (getting-started.md:108-122) defines `✗` as something *in place and
    wrong*. A check that could not run for want of a prerequisite is a different claim
    and carries `?`: install.py:1427-1428 and :1589-1590 set `blocked` from a detail
    beginning "could not run", which renders `?` and leaves the exit code alone.

    The pairing this forbids is therefore absent by construction today, which is
    exactly when a detector is worth keeping and worth reading with suspicion — see
    the control, which requires the marker vocabulary to have been observed at all.
    """
    text = step_log("checked")
    lines = parse_check_lines(text)
    if not lines:
        return skip("no rendered check lines were captured, so no marker vocabulary "
                    "was observed and 'no offending pairing' would mean nothing")
    markers = {m for m, _, _ in lines}
    control = (f"{len(lines)} line(s) carrying marker(s) {''.join(sorted(markers))} "
               "were parsed, so the output format was understood")
    offending = [f"{n}: {d}" for m, n, d in lines
                 if m == MARK_FAIL and "skipped" in d.lower()]
    if offending:
        return bad(f"{len(offending)} check(s) print the failure marker beside the word "
                   f"'skipped': {'; '.join(offending[:3])}", control)
    return ok("no check pairs the failure marker with the word 'skipped'", control)


def check_graph_down_diagnosis() -> Result:
    """CHECKED: a down graph must produce the readable diagnosis, and a live one must not.

    writer.py:90-91 builds it. Which way this reads depends on the config: under
    `graph-not-started` the text must be present, and under every other config it must
    be absent — that second direction is the control, since a box that always prints it
    would satisfy the first for the wrong reason.
    """
    text = step_log("checked")
    if not text:
        return skip("no --check output was captured")
    diagnosis = "docker compose up -d" in text and "start it with" in text
    graph_down_config = CONFIG_NAME == "graph-not-started"

    # install.py:1206-1208 applies graph_down_detail only when the probe says nothing is
    # listening, so the diagnosis appearing under a graph-up config does not by itself
    # indict this check's subject — it may mean the graph had not finished starting
    # when --check
    # ran, which is issue #55's readiness window and a different finding entirely.
    # Without knowing the graph was answering, the two are indistinguishable and this
    # must not pick one.
    ready = load_snapshot("graph-ready") or {}
    if not graph_down_config and not ready.get("query_ok"):
        return skip(
            "the cell's graph was not confirmed to be answering queries when --check "
            f"ran (port_open={ready.get('port_open')}, query_ok={ready.get('query_ok')}"
            "), so a printed diagnosis cannot be told apart from the readiness window "
            "of issue #55")

    if graph_down_config:
        control = "this cell ran the graph-not-started config, so the diagnosis is due"
        if not diagnosis:
            return bad("with no graph running, the readable diagnosis naming the "
                       "compose command did not reach the user", control)
        return ok("the graph-down diagnosis reached the user", control)

    control = (f"this cell ran the {CONFIG_NAME!r} config with the graph up, which is "
               "the direction that catches a box printing the diagnosis unconditionally")
    if diagnosis:
        return bad("the graph-down diagnosis was printed on a cell whose graph is "
                   "running, so its presence proves nothing about a down graph", control)
    return ok("no graph-down diagnosis is printed when the graph is up", control)


def check_starting_graph_is_not_reported_as_absent() -> Result:
    """GRAPH_STARTING: in the readiness window, do not say the container is not running.

    The window is the gap between the port accepting a connection and the server
    answering a query. `_probe_graph` reports unreachable across the whole of it, and
    `graph_down_detail` then tells the user to `docker compose up -d` a container that
    is already up and starting.

    The control is the spec's own and it is a SKIP, not a pass: if the graph already
    answered when it was first sampled, this cell never entered the window and proves
    nothing. Reporting that as a pass is exactly how an absence-assertion starts passing
    forever.
    """
    ready = load_snapshot("graph-ready")
    if ready is None:
        return skip("no graph-ready snapshot was taken, so the window was never sampled")

    port_open = ready.get("port_open")
    query_ok = ready.get("query_ok")
    started_rc = step_rc("graph-starting")

    if started_rc not in (0, None) or not port_open:
        return skip(f"the graph's port was not open after `docker compose up -d` "
                    f"(rc={started_rc}, port_open={port_open}), so this cell is about a "
                    "container that did not start rather than one still starting")
    if query_ok:
        return skip("the graph already answered queries when first sampled, so this "
                    "cell never entered the readiness window and proves nothing about "
                    "what is reported inside it")

    text = step_log("checked")
    if not text:
        return skip("no --check output was captured during the window")

    control = ("the window was observed: the port accepted a connection while the "
               "server did not yet answer a query, and `docker compose up -d` had "
               "already returned 0 — so the container was up and starting")
    tells_user_to_start = "docker compose up -d" in text and "start it with" in text
    if tells_user_to_start:
        return bad("inside the readiness window the diagnosis tells the user to start "
                   "a container that is already running and starting up", control)
    return ok("the readiness window produced no start-the-container diagnosis", control)


#: Binaries getting-started.md names as required. Removing one is not a box the
#: documented install claims to work on: docs/getting-started.md:13 lists `jq` in the
#: prerequisites table and :17 says "jq is not optional".
DOCUMENTED_PREREQUISITES = ("jq", "uv")


def check_init_exits_zero_on_a_fresh_box() -> Result:
    # A config that takes a documented prerequisite off PATH is testing an unsupported
    # box, and "the documented install completes" is a claim about a supported one.
    # Without this the no-jq variant reports a red carrying no issue number, which by
    # this suite's own rule means a NEW defect — and it is not one, it is the variant
    # working as designed.
    removed = [r for r in _config_removes() if r in DOCUMENTED_PREREQUISITES]
    if removed:
        return skip(f"this cell removed {', '.join(removed)}, which "
                    "docs/getting-started.md lists as required, so a failing install "
                    "is the variant doing its job rather than a defect")
    rc = step_rc("installed")
    if rc is None:
        return skip("the installed step recorded no exit code")
    after = load_snapshot("installed")
    if after is None:
        return skip("no post-install snapshot, so a zero exit cannot be corroborated "
                    "against anything the install was supposed to write")
    wrote = [n for n, seen in after["artifacts_present"].items() if seen]
    if rc != 0:
        return bad(f"`thalamus init` exited {rc} on a box that has never seen the "
                   "project", f"the box carries {len(wrote)} artifact(s) after it")
    if not wrote:
        return bad("`thalamus init` exited 0 but wrote none of the artifacts it reports "
                   "writing, so the zero is not evidence of an install",
                   "post-install probe found no artifact at all")
    return ok("`thalamus init` exited 0",
              f"and left {len(wrote)} artifact(s): {', '.join(wrote)}, so the zero is "
              "not a no-op")


def check_claude_mcp_registration_is_verified() -> Result:
    """INSTALLED: verify() must report on whether the Claude Code MCP server registered.

    The control is that verify() DOES report on the other two harnesses. Without it,
    "no claude MCP check" is indistinguishable from "verify() reports no MCP checks at
    all", which would be a different defect with a different fix.
    """
    after = load_snapshot("installed")
    if after is None or after.get("verify") is None:
        return skip("verify() could not be read structurally, so which checks it "
                    "reports is unknown")
    names = [c["name"] for c in after["verify"]]
    mcp = [n for n in names if "MCP server registered" in n]
    others = [n for n in mcp if n.startswith(("cursor", "codex"))]
    claude = [n for n in mcp if not n.startswith(("cursor", "codex"))]

    if not others:
        return skip(f"verify() reports no MCP registration check for any harness "
                    f"({len(names)} checks seen), so the absence of a Claude one is "
                    "not specific to Claude")
    control = (f"verify() does report MCP registration for other harnesses: "
               f"{', '.join(others)}")
    if not claude:
        return bad("verify() has no check for whether the Claude Code MCP server "
                   "registered, so a box without the CLI installs 'successfully' with "
                   "no memory tools and no failure reported", control)
    return ok(f"verify() reports on Claude MCP registration: {', '.join(claude)}",
              control)


def check_hooks_are_armed_and_resolvable() -> Result:
    after = load_snapshot("installed")
    if after is None:
        return skip("no post-install snapshot, so no hook commands were captured")
    commands = after["our_hooks"]
    if not commands:
        return bad("the install wrote no hook commands carrying "
                   f"{OUR_HOOK_MARKER!r}", "0 of our commands found in the settings file")
    broken = []
    for command in commands:
        path = Path(command)
        if not path.exists():
            broken.append(f"{command}: does not exist")
        elif not os.access(command, os.X_OK):
            broken.append(f"{command}: not executable")
    control = (f"{len(commands)} hook command(s) were captured, so this is not "
               "reporting on an empty list")
    if broken:
        return bad(f"{len(broken)} hook command(s) do not resolve to an executable "
                   f"file: {'; '.join(broken[:4])}", control)
    return ok(f"all {len(commands)} hook command(s) resolve to executable files", control)


def check_skills_are_linked() -> Result:
    """INSTALLED: every shipped skill resolves through its user-scope link."""
    after = load_snapshot("installed")
    if after is None:
        return skip("no post-install snapshot")
    shipped = after["shipped_skills"]
    links = after["skill_links"]
    if not shipped:
        return skip("the checkout ships no skills by the SKILL.md rule, so there is "
                    "nothing for the link check to be about")
    missing = [name for name in shipped if name not in links]
    control = (f"the checkout ships {len(shipped)} skill(s) and {len(links)} link(s) "
               "exist at user scope, so both sides of the comparison are populated")
    if missing:
        return bad(f"{len(missing)} shipped skill(s) are not linked at user scope: "
                   f"{', '.join(missing[:6])}", control)
    return ok(f"all {len(shipped)} shipped skill(s) are linked", control)


def check_pending_items_are_clearable() -> Result:
    """INSTALLED: a pending item must name a command that can actually clear it.

    The control is that re-running init cleared at least one OTHER pending item, which
    is what separates "this item is stuck" from "init clears nothing".
    """
    after = load_snapshot("installed")
    if after is None or after.get("verify") is None:
        return skip("verify() could not be read after the install")

    # The comparison is the PRE-install --check against the post-install verify. Two
    # post-install reads was the first version of this and it could clear nothing by
    # construction: both sides were taken after the install, so "cleared 0" said
    # something about the snapshots, not about init.
    before = {name for mark, name, _ in parse_check_lines(step_log("checked"))
              if mark == MARK_PENDING}
    still = {c["name"] for c in after["verify"] if c["pending"] and not c["ok"]}
    if not before:
        return skip("the pre-install --check rendered no pending items, so nothing here "
                    "can be shown either cleared or stuck")

    cleared = before - still
    stuck = sorted(still & before)
    control = (f"the install cleared {len(cleared)} of {len(before)} pending item(s), "
               "which is what makes a survivor evidence of being stuck rather than of "
               "an init that installs nothing")
    if not cleared:
        return skip(f"the install cleared none of the {len(before)} pending item(s), so "
                    "a survivor cannot be told apart from an init that clears nothing")
    if stuck:
        return bad(f"{len(stuck)} pending item(s) survive an install that cleared "
                   f"{len(cleared)} others, so the command they name cannot clear "
                   f"them: {', '.join(stuck[:4])}", control)
    return ok(f"all {len(before)} pending item(s) cleared on install", control)


def check_clean_clone_manifest_count() -> Result:
    """INSTALLED: the scopes the CLI resolves are the manifests a clean clone tracks."""
    snap = load_snapshot("scopes")
    if snap is None:
        return skip("no scopes snapshot was taken")
    default = snap.get("scopes_default")
    override = snap.get("scopes_override")
    tracked = snap.get("tracked_manifests")
    if default is None:
        return skip("available_scopes() could not be read")
    if tracked is None:
        return skip("the tracked manifest count could not be read from git")
    if override is None or override == default:
        return skip("setting THALAMUS_CONFIG_DIR did not change the resolved scopes, "
                    "so the probe is not reading the override and would report the "
                    "same number whatever the box holds")
    control = (f"an explicit THALAMUS_CONFIG_DIR resolved {len(override)} scope(s) "
               f"against {len(default)} by default, so the override is being read")
    if len(default) != tracked:
        return bad(f"the CLI resolves {len(default)} scope(s) ({', '.join(default)}) "
                   f"but the clone tracks {tracked} manifest(s)", control)
    return ok(f"the CLI resolves the {tracked} manifest(s) a clean clone tracks",
              control)


def check_second_init_does_not_duplicate_wiring() -> Result:
    first, second = load_snapshot("installed"), load_snapshot("reinstalled")
    if first is None or second is None:
        return skip("a snapshot is missing either side of the second init")
    before, after = first["our_hooks"], second["our_hooks"]
    if not before:
        return bad("the first init wrote no hook commands, so 'the second added none' "
                   "would be true of a box where init does nothing",
                   "first-init hook count was 0")
    control = (f"the first init wrote {len(before)} hook command(s), so a duplicate "
               "would have something to show against")
    if len(after) > len(before):
        return bad(f"the second init added {len(after) - len(before)} hook command(s) "
                   f"— {len(before)} became {len(after)}, so re-running appends", control)
    if len(after) != EXPECTED_HOOK_ENTRIES:
        return bad(f"{len(after)} of our hook entries are wired, but HOOK_WIRING "
                   f"declares {EXPECTED_HOOK_ENTRIES}", control)
    return ok(f"our hook entries stayed at {len(after)} across a second init", control)


def check_moved_checkout_is_named() -> Result:
    """MOVED: after the checkout moves, --check must name the stale registration."""
    text = step_log("moved")
    if not text:
        return skip("the moved-checkout phase produced no output")
    lines = parse_check_lines(text)
    if not lines:
        return skip("the moved-checkout --check produced no rendered check lines")
    failing = [(n, d) for m, n, d in lines if m == MARK_FAIL]
    # Restricted to the MCP registration lines on purpose. Moving a checkout also breaks
    # the skill symlinks, and that check reports the breakage correctly — folding it in
    # made the first version of this fire on a line that was doing its job.
    mcp = [(n, d) for n, d in failing if "MCP server registered" in n]
    control = (f"{len(lines)} check line(s) were parsed after the move, "
               f"{len(failing)} of them failures, {len(mcp)} about MCP registration")
    if not failing:
        return bad("after the checkout moved, --check reported no failure at all",
                   control)
    if not mcp:
        return skip("no MCP registration check failed after the move, so the branch "
                    "that chooses the stale wording was never reached")
    # Pin the HEALTHY shape, not the diagnosis wording. The healthy branch renders a
    # bare location and stops: "`thalamus` in /path/to/mcp.json". Every unhealthy
    # branch appends a clause saying what is wrong and what to do. Enumerating those
    # clauses instead is what this check used to do, and it made an improvement to the
    # message read as the defect: the fix for #52 reworded "but not with the entry this
    # checkout builds" to "does not match the entry this checkout builds — differing:
    # args", which no pinned phrase matched, so a repaired install reported as broken
    # and the cell stayed green because the failure still named a filed issue.
    healthy = [f"{n}: {d}" for n, d in mcp if _HEALTHY_MCP_DETAIL.match(d.strip())]
    if healthy:
        return bad("an MCP registration check failed after the move while printing the "
                   f"text for a healthy install: {'; '.join(healthy[:2])}", control)
    return ok("every MCP failure after the move names the stale registration", control)


def check_console_serves_its_shell() -> Result:
    """CONSOLE: the page a user opens returns 200, and an unserved path does not."""
    snap = load_snapshot("console")
    if snap is None or not snap.get("console"):
        return skip("the console phase recorded nothing")
    probe = snap["console"]
    root_status, root_len = probe["root"]
    control_status, _ = probe["control_404"]
    if root_status == 0 and control_status == 0:
        return skip("no request to the console completed, so the server was not "
                    "reachable and nothing about what it serves was observed")
    if control_status == 200:
        return skip("a path the server does not serve returned 200, so every asset "
                    "assertion in this phase would pass on a server answering 200 to "
                    "everything")
    control = (f"an unserved path returned {control_status}, so a 200 means the server "
               "actually routed the request")
    if root_status != 200:
        return bad(f"the page a user opens returned {root_status}", control)
    if root_len <= 0:
        return bad("the page returned 200 with an empty body", control)
    return ok(f"the console's page returned 200 with {root_len} bytes", control)


def check_precached_assets_are_present() -> Result:
    """CONSOLE: every service-worker shell entry resolves, or install fails wholesale."""
    snap = load_snapshot("console")
    if snap is None or not snap.get("console"):
        return skip("the console phase recorded nothing")
    probe = snap["console"]
    results = probe.get("shell_results") or {}
    if not results:
        return skip("the service worker's SHELL list could not be read, so no asset "
                    "was checked")
    control_status, _ = probe["control_404"]
    if control_status == 200:
        return skip("a path the server does not serve returned 200, so 'every asset "
                    "resolves' would be true of any list at all")
    missing = [f"{path} -> {status}" for path, (status, _) in results.items()
               if status != 200]
    control = (f"{len(results)} shell entr(y/ies) were fetched and an unserved path "
               f"returned {control_status}")
    if missing:
        return bad(f"{len(missing)} precached asset(s) do not resolve, and the worker "
                   f"fails installation as a whole if any one does: "
                   f"{'; '.join(missing[:5])}", control)
    return ok(f"all {len(results)} precached asset(s) resolve", control)


def check_uninstall_leaves_no_dangling_link() -> Result:
    installed, after = load_snapshot("installed"), load_snapshot("uninstalled")
    if installed is None or after is None:
        return skip("a snapshot is missing either side of the uninstall")
    before_links, after_links = installed["skill_links"], after["skill_links"]
    removed = len(before_links) - len(after_links)
    dangling = after["dangling_skill_links"]
    if not before_links:
        return skip("the install linked no skills, so an uninstall removing none proves "
                    "nothing about whether it can")
    control = (f"the install left {len(before_links)} skill link(s) and the uninstall "
               f"removed {removed}, so this is not a vacuous clean")
    if removed <= 0:
        return bad("uninstall removed no skill links at all, so 'no dangling link' "
                   "describes a run that did nothing", control)
    if dangling:
        return bad(f"{len(dangling)} link(s) survive with a missing target: "
                   f"{', '.join(dangling[:5])}", control)
    return ok("no dangling skill link survives the uninstall", control)


def check_installed_wheel_finds_the_scripts_it_ships() -> Result:
    """Does a wheel installed outside a checkout resolve the files it shipped with?

    Read off `init --check`'s own rendering rather than off `PROJECT_ROOT` directly,
    because the anchor being wrong is the cause and the missing scripts are the
    impact: a fix that re-anchors on the package makes these lines pass, and a fix
    that only moves the constant somewhere else does not. The resolved root is
    recorded in the detail either way, so the witness names the cause.
    """
    snapshot_state = load_snapshot("wheel")
    if snapshot_state is None:
        return skip("this cell built no wheel — only the config that sets "
                    "`builds_a_wheel` runs that phase, and nothing here is evidence "
                    "about the packaged layout")
    probe = snapshot_state.get("wheel") or {}
    if not probe.get("installed"):
        return skip(f"the wheel was not installed (phase rc={step_rc('wheel')}), so "
                    "there is no packaged layout to read; see step-wheel.log")

    wheel_cli = probe.get("wheel_cli") or {}
    control_cli = probe.get("checkout_cli") or {}
    control_scripts = control_cli.get("scripts") or {}
    wheel_scripts = wheel_cli.get("scripts") or {}

    # The control is read first and in full, because every branch below is a statement
    # about the difference between the two CLIs and none of them means anything until
    # the checkout's own answer is known to be the healthy one.
    if not control_cli.get("present"):
        return skip(f"the control CLI {control_cli.get('cli')} is not on this box, so "
                    "the wheel's answer has nothing to be compared against")
    if not control_scripts:
        return skip("the checkout's own `init --check` rendered no script-presence "
                    f"line at all ({control_cli.get('lines')} check lines parsed, "
                    f"rc={control_cli.get('rc')}), so this run can say nothing about "
                    "where a packaged install looks for them")
    control_missing = [n for n, (mark, _d) in control_scripts.items()
                       if mark == MARK_FAIL]
    if control_missing:
        return skip(
            "the checkout's own CLI reports " + ", ".join(sorted(control_missing))
            + " missing too, so the probe is reading a path that does not populate on "
            "this box and a missing script under the wheel could not be attributed to "
            "packaging")

    checkout_root = (probe.get("checkout_paths") or {}).get("project_root")
    control = (f"the same probe from {control_cli['cli']} found all "
               f"{len(control_scripts)} script sets present, anchored on "
               f"{checkout_root} (rc={control_cli.get('rc')})")

    paths = probe.get("wheel_paths") or {}
    root = paths.get("project_root", "unresolved")
    where = (f"the installed package resolves PROJECT_ROOT to {root} "
             f"(pyproject.toml: {paths.get('pyproject')}, "
             f"config/experts: {paths.get('config_experts')}, "
             f"hooks dir: {paths.get('hook_dir')})")

    # Ordered ahead of the intersection deliberately: a wheel with no console script
    # renders no lines to intersect with, and reading that as "nothing comparable" would
    # turn the sharper failure — the documented command cannot be run at all — into
    # silence.
    if not wheel_cli.get("present"):
        return bad(f"the wheel installed no `thalamus` console script at "
                   f"{wheel_cli.get('cli')}, so the documented pre-install command "
                   f"cannot be run at all. {where}", control=control)
    both = sorted(set(control_scripts) & set(wheel_scripts))
    if not both:
        return skip(
            "the wheel's CLI rendered none of the script-presence lines the "
            f"checkout's did (checkout: {sorted(control_scripts)}, wheel: "
            f"{sorted(wheel_scripts)}, rc={wheel_cli.get('rc')}), so the two runs "
            "cannot be compared line for line")
    missing = [n for n in both if wheel_scripts[n][0] == MARK_FAIL]
    if missing:
        detail = "; ".join(f"{n}: {wheel_scripts[n][1]}" for n in missing)
        return bad(f"{len(missing)} of {len(both)} script sets are missing under the "
                   f"wheel — {detail}. {where}. `init --check` exited "
                   f"{wheel_cli.get('rc')}", control=control)
    return ok(f"the wheel-installed CLI found all {len(both)} script sets; {where}",
              control)


# ---------------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------------

EVALUATORS = {
    "golden-image-has-no-thalamus-artifact": check_never_seen_before_the_run,
    "host-graph-is-unreachable": check_host_graph_is_unreachable,
    "starting-graph-is-not-reported-as-absent":
        check_starting_graph_is_not_reported_as_absent,
    "cli-exists-after-sync": check_cli_exists_after_sync,
    "graph-down-diagnosis-reaches-the-user": check_graph_down_diagnosis,
    "check-exits-zero-before-install": check_check_exits_zero_before_install,
    "no-failure-marker-beside-the-word-skipped": check_no_failure_marker_beside_skipped,
    "init-exits-zero-on-a-fresh-box": check_init_exits_zero_on_a_fresh_box,
    "claude-mcp-registration-is-verified": check_claude_mcp_registration_is_verified,
    "hooks-are-armed-and-resolvable": check_hooks_are_armed_and_resolvable,
    "skills-are-linked": check_skills_are_linked,
    "pending-items-name-a-command-that-can-clear-them": check_pending_items_are_clearable,
    "clean-clone-manifest-count-is-what-the-cli-sees": check_clean_clone_manifest_count,
    "second-init-does-not-duplicate-wiring": check_second_init_does_not_duplicate_wiring,
    "moved-checkout-is-named-not-denied": check_moved_checkout_is_named,
    "console-serves-its-shell": check_console_serves_its_shell,
    "precached-assets-are-all-present": check_precached_assets_are_present,
    "uninstall-leaves-no-dangling-link": check_uninstall_leaves_no_dangling_link,
    "installed-wheel-finds-the-scripts-it-ships":
        check_installed_wheel_finds_the_scripts_it_ships,
}

#: Checks with no implementation, each with the reason. Reported in `not_evaluated` with
#: the reason attached, which is the difference between a gap that is known and one that
#: is invisible. `lint.py` requires every spec check to be in exactly one of these two.
DEFERRED: dict[str, str] = {}


def evaluate() -> dict:
    findings = []
    for check in spec.CHECKS:
        evaluator = EVALUATORS.get(check.name)
        if evaluator is None:
            result = skip(DEFERRED.get(
                check.name, "no implementation and no recorded reason"))
        else:
            try:
                result = evaluator()
            except Exception as exc:  # a broken check must not sink the cell
                result = skip(f"the check raised {type(exc).__name__}: {exc}")
        findings.append({
            "name": check.name,
            "phase": check.phase.value,
            "severity": check.severity.value,
            "issue": check.issue,
            "state": result.state,
            "detail": result.detail,
            "control": result.control,
        })
    return {
        "checks": findings,
        "passed": [f["name"] for f in findings if f["state"] == PASS],
        "failed": [f["name"] for f in findings if f["state"] == FAIL],
        "not_evaluated": [f["name"] for f in findings if f["state"] == NOT_EVALUATED],
    }


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "snapshot":
        snapshot(argv[2] if len(argv) > 2 else "unlabelled")
        return 0
    if len(argv) >= 2 and argv[1] == "evaluate":
        print(json.dumps(evaluate()))
        return 0
    print("usage: checks.py snapshot <label> | checks.py evaluate", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
