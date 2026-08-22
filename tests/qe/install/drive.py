"""Run the documented install sequence on the box this is executing on, and judge it.

    python3 tests/qe/install/drive.py --config graph-not-started

`spec.py` says what the sequence is, `checks.py` says how to find out whether it
held, and this says who runs them and in what order. Until now that ordering lived
only inside the bash `seed.py` generates for a libvirt guest, which meant the only
box that could be measured was one this repo cannot describe — the sequence was
knowledge, and it was written in a private repo's string literals.

**The box under test is the box this runs on.** That is the whole portability
claim: `checks.py` reads nothing but `$QE_ARTIFACTS`, `$QE_GUEST_HOME` and
`$QE_REPO`, so "the guest" and "the runner" are the same idea wearing different
hardware. A libvirt cell sets those to `/home/ubuntu`; a GitHub macOS runner sets
them to `/Users/runner`; neither file has to know which one it got.

## What this refuses to do

**It will not run a step whose command is missing.** A box without `docker` asked
to run the baseline config gets `boundary-abort`, never a result: a sequence that
silently drops `docker compose up -d` and carries on measures a box nobody has,
and every graph-phase check downstream would report SKIPPED as though the evidence
merely went missing. `Outcome.BOUNDARY_ABORT` exists to say "a gate refused" in a
way that is not a statement about the product.

**It will not run a config whose perturbation did not apply.** `removes` renames a
binary off PATH; if the rename fails, or if a second copy is still resolvable, the
cell aborts rather than running an unperturbed box under a perturbed name. A
`no-jq` cell that still has `jq` passes every check and proves nothing.

## Exit codes, and why green is not the goal

The tree carries filed install defects, so **a run in which nothing fails means the
harness did not observe** — the same rule `spec.known_defect_issues()` states and
that nothing, until now, enforced. The codes follow `tests/qe/run.py`'s vocabulary
rather than inventing a second one:

    0  the cell ran; every failing check named a known issue, and at least one did
    1  a check failed naming NO issue, or a step that may not fail did — a NEW defect
    2  no known defect reproduced: they were fixed, or this cell cannot see them
    3  MALFORMED — the oracle could not run, a gate refused, the perturbation failed

Code 2 is not a pass. It is the harness reporting on itself.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import spec  # noqa: E402
import verdict as verdict_mod  # noqa: E402

#: Mirrors `checks.py`, and is threaded to it through `QE_CONSOLE_PORT` so
#: the driver and the probe can never disagree about which port was under
#: test. Overridable so a cell on a box already running a console does not
#: measure that one.
CONSOLE_PORT = int(os.environ.get("QE_CONSOLE_PORT", "8378"))

#: Where a snapshot is taken, keyed by the step it follows. `None` is "before any
#: step". The order mirrors `seed.py`'s generated cell script exactly, because most
#: checks are differential and a snapshot in the wrong place is not a weaker
#: observation — it is a different one wearing the same label.
SNAPSHOTS_AFTER: dict[spec.Phase | None, tuple[str, ...]] = {
    None: ("preflight",),
    spec.Phase.GRAPH_STARTING: ("graph-ready",),
    spec.Phase.INSTALLED: ("installed", "scopes"),
    spec.Phase.REINSTALLED: ("reinstalled",),
    spec.Phase.UNINSTALLED: ("uninstalled",),
}

#: The phase each snapshot belongs to, so a config that skips the phase skips the
#: snapshot with it rather than recording an empty one under a name a check trusts.
SNAPSHOT_PHASE: dict[str, spec.Phase] = {
    "preflight": spec.Phase.PREFLIGHT,
    "graph-ready": spec.Phase.GRAPH_READY,
    "installed": spec.Phase.INSTALLED,
    "scopes": spec.Phase.INSTALLED,
    "reinstalled": spec.Phase.REINSTALLED,
    "console": spec.Phase.CONSOLE,
    "uninstalled": spec.Phase.UNINSTALLED,
}


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


class GateRefused(Exception):
    """A precondition failed. Never a statement about the product under test."""


@dataclass
class Recorder:
    """The cell's running account of itself: what ran, what failed, what was said."""

    artifacts: Path
    steps: list[dict] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    last_phase: str = ""

    def note(self, line: str) -> None:
        stamped = f"[{int(time.time())}] {line}"
        self.log.append(stamped)
        print(stamped, flush=True)

    def mark(self, phase: str) -> None:
        self.last_phase = phase

    def record(self, phase: str, rc: int, start: float, end: float,
               argv: list[str]) -> None:
        self.steps.append({"phase": phase, "rc": rc, "start": int(start),
                           "end": int(end), "argv": list(argv)})

    def fail(self, name: str) -> None:
        if name not in self.failed:
            self.failed.append(name)

    def log_tail(self, limit: int = 2000) -> str:
        text = "\n".join(self.log)[-limit:]
        return base64.b64encode(text.encode("utf-8", "replace")).decode("ascii")


# ---------------------------------------------------------------------------------
# The box, as this cell wants it
# ---------------------------------------------------------------------------------

def config_by_name(name: str) -> spec.Config:
    for config in spec.CONFIGS:
        if config.name == name:
            return config
    known = ", ".join(c.name for c in spec.CONFIGS)
    raise GateRefused(f"unknown config {name!r}; the spec carries: {known}")


def cell_env(config: spec.Config, repo: Path, home: Path, artifacts: Path) -> dict:
    """The environment every documented command and every probe runs under.

    `PYTHONUTF8` is not decoration. `checks.py` reads the rendered `✓ ○ ! ✗` markers
    with a regex, and a runner whose locale lands on ASCII turns every marker line
    into mojibake that matches nothing — which reports as "no rendered check lines
    were captured", i.e. as missing evidence rather than as a broken locale.
    """
    env = dict(os.environ)
    for key in config.unset:
        env.pop(key, None)
    env.update(config.env)
    env.update({
        "QE_ARTIFACTS": str(artifacts),
        "QE_GUEST_HOME": str(home),
        "QE_REPO": str(repo),
        "QE_CONFIG": config.name,
        "HOME": str(home),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "QE_CONSOLE_PORT": str(CONSOLE_PORT),
    })
    return env


class Perturbation:
    """Apply a config's `removes` to the real PATH, and put it back afterwards.

    Renaming in a loop rather than once: `command -v` finds the first copy, and a
    box with `jq` in both `/usr/bin` and a package manager's prefix keeps answering
    after the first rename. `seed.py`'s guest script has the single-copy version of
    this, and on the golden image there is only ever one copy — which is exactly the
    kind of assumption that holds until the harness runs somewhere else.
    """

    #: A bound, not a target. If PATH still resolves the name after this many
    #: renames something is regenerating it and the cell must not proceed.
    MAX_COPIES = 8

    def __init__(self, config: spec.Config, env: dict, recorder: Recorder) -> None:
        self.config = config
        self.env = env
        self.recorder = recorder
        self.renamed: list[tuple[Path, Path]] = []

    def __enter__(self) -> "Perturbation":
        for name in self.config.removes:
            for _ in range(self.MAX_COPIES):
                found = shutil.which(name, path=self.env.get("PATH"))
                if not found:
                    break
                src = Path(found)
                dst = src.with_name(src.name + ".qe-removed")
                try:
                    src.rename(dst)
                except OSError as exc:
                    self.__exit__(None, None, None)
                    raise GateRefused(
                        f"config {self.config.name!r} must take {name!r} off PATH and "
                        f"could not: renaming {src} failed with {exc}. A cell that "
                        "runs unperturbed under a perturbed name reports on a box "
                        "nobody asked about."
                    ) from exc
                self.renamed.append((src, dst))
                self.recorder.note(f"perturbation: moved {src} aside")
            else:
                self.__exit__(None, None, None)
                raise GateRefused(
                    f"{name!r} is still resolvable after {self.MAX_COPIES} renames; "
                    "something is putting it back and the perturbation cannot be "
                    "trusted to have applied."
                )
            if shutil.which(name, path=self.env.get("PATH")):
                self.__exit__(None, None, None)
                raise GateRefused(f"{name!r} is still on PATH after removal")
        return self

    def __exit__(self, *_exc) -> None:
        while self.renamed:
            src, dst = self.renamed.pop()
            try:
                dst.rename(src)
            except OSError:
                pass


def gate_commands_present(steps: tuple[spec.Step, ...], config: spec.Config,
                          env: dict) -> None:
    """Every step this cell will run must have its command, or nothing runs.

    Deliberately separate from the perturbation: a binary this config took away is
    absent *by design* and is not a missing precondition. Anything else missing
    means the box cannot run the documented sequence, and the honest report is that
    the gate refused rather than a matrix of SKIPPED checks that reads like the
    evidence merely went astray.
    """
    intentional = set(config.removes)
    missing = sorted({
        s.argv[0] for s in steps
        if s.argv[0] not in intentional
        and not shutil.which(s.argv[0], path=env.get("PATH"))
    })
    if missing:
        raise GateRefused(
            f"this box has no {', '.join(missing)}, which the documented sequence "
            f"runs. Config {config.name!r} does not skip those steps, so the cell "
            "would measure a sequence nobody documents."
        )


# ---------------------------------------------------------------------------------
# Running the sequence
# ---------------------------------------------------------------------------------

def gate_prerequisites(config: spec.Config, env: dict) -> None:
    """The documented prerequisites must be here, or absent exactly on purpose.

    `gate_commands_present` only sees a step's own command, so `jq`, `tmux` and the
    agent CLI — none of which the sequence invokes directly — can be missing on a
    hosted runner without a single step noticing. The install then succeeds, does
    less than it says, and the cell reports on a box the docs do not describe.

    A config that removes an agent CLI is asserting their absence, so the rule
    inverts for it: every one of them must be gone, not merely the named one. A
    `no-agent-cli` box that still answers `codex` is not the box the config means.
    """
    path = env.get("PATH")
    removed = set(config.removes)
    missing = [p for p in spec.PREREQUISITES
               if p not in removed and not shutil.which(p, path=path)]
    if missing:
        raise GateRefused(
            f"the documented prerequisites {', '.join(missing)} are not on PATH and "
            f"config {config.name!r} does not remove them "
            "(docs/getting-started.md:9-15)."
        )
    if removed & set(spec.AGENT_CLIS):
        still = [c for c in spec.AGENT_CLIS
                 if c not in removed and shutil.which(c, path=path)]
        if still:
            raise GateRefused(
                f"config {config.name!r} means a box with no agent CLI, and this one "
                f"still answers {', '.join(still)}."
            )
        return
    if not any(shutil.which(c, path=path) for c in spec.AGENT_CLIS):
        raise GateRefused(
            "no agent CLI is on PATH (" + ", ".join(spec.AGENT_CLIS) + "), which "
            "distillation shells out to. No config asked for that, so it is a box "
            "the sequence was not written for rather than a variant."
        )


def gate_config_premise(config: spec.Config, recorder: Recorder,
                        port: int | None = None) -> None:
    """The config's premise must actually hold on this box before anything runs.

    `graph-not-started` does not mean "we did not run `docker compose up -d`". It
    means the sequence meets a box with no graph, and its checks are written to that
    premise: issue #17's asserts the readable diagnosis reaches the user, which a box
    with a graph already up will never print. Measured 2026-08-21 on a developer box
    running the operator's own graph — the cell reported #17 reproduced, from a step
    that had nothing to diagnose. A premise nobody checks turns into a finding.
    """
    # `port` is a parameter so the gate can be shown refusing without a graph and
    # shown permitting without one absent — on a developer box neither control can be
    # arranged against a fixed 8182, and a gate nobody can exercise is a gate nobody
    # knows the state of. Production calls pass nothing.
    port = spec_graph_port() if port is None else port
    if spec.Phase.GRAPH_STARTING in config.skip_steps and _port_open(port):
        raise GateRefused(
            f"config {config.name!r} is premised on a box with no graph, and "
            f"127.0.0.1:{port} is already answering. Checks written to that premise "
            "would report on a box this is not."
        )
    recorder.note(f"premise of {config.name!r} holds on this box")


def spec_graph_port() -> int:
    """The graph port, read from the oracle so there is one definition of it."""
    import checks
    return checks.GRAPH_PORT


def run_step(step: spec.Step, repo: Path, env: dict, artifacts: Path,
             recorder: Recorder) -> int:
    """One documented command, with its log and exit code left where the oracle looks.

    The two artifacts are the entire interface to `checks.py`: `step-<phase>.log`
    holds the combined output and `step-<phase>.rc` the exit code, and an evaluator
    that finds neither reports "the step recorded no exit code" rather than passing.
    """
    phase = step.phase.value
    timeout = spec.TIMEOUTS[spec.timeout_key(step)]
    log_path = artifacts / f"step-{phase}.log"
    recorder.mark(f"{phase} START")
    recorder.note(f"step {phase}: {' '.join(step.argv)} (timeout {timeout}s)")
    start = time.time()
    try:
        proc = subprocess.run(step.argv, cwd=repo, env=env, timeout=timeout,
                              capture_output=True, text=True, errors="replace")
        out, rc = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        out = (exc.output or "") + f"\n[drive] timed out after {timeout}s"
        rc = 124
    except FileNotFoundError:
        out, rc = f"[drive] {step.argv[0]} not found on PATH", 127
    end = time.time()
    log_path.write_text(out)
    (artifacts / f"step-{phase}.rc").write_text(f"{rc}\n")
    recorder.log.append(out)
    recorder.record(phase, rc, start, end, step.argv)
    recorder.mark(f"{phase} END rc={rc}")
    recorder.note(f"step {phase}: exited {rc} in {end - start:.1f}s")
    if rc != 0 and not step.may_fail:
        recorder.fail(phase)
    return rc


def snap(label: str, env: dict, recorder: Recorder) -> None:
    """Record the box's state under a label the differential checks read by name."""
    recorder.note(f"snapshot {label}")
    proc = subprocess.run([sys.executable, str(_HERE / "checks.py"), "snapshot", label],
                          env=env, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        recorder.note(f"snapshot {label} failed: "
                      f"{(proc.stdout + proc.stderr).strip()[:400]}")


def moved_phase(repo: Path, env: dict, artifacts: Path, recorder: Recorder) -> None:
    """Rename the checkout and re-run `--check`, which is what an upgrade looks like.

    A phase rather than a config, for the reason `seed.py` gives: the perturbation
    has to sit between a completed install and the uninstall that needs the checkout
    back where it was, so it cannot be applied to the box before the sequence starts.
    """
    moved = repo.with_name(repo.name + "-moved")
    timeout = spec.TIMEOUTS["thalamus-init"]
    recorder.mark("moved START")
    recorder.note(f"phase moved: {repo} -> {moved}")
    argv = ["uv", "run", "thalamus", "init", "--check"]
    start = time.time()
    try:
        repo.rename(moved)
    except OSError as exc:
        recorder.note(f"phase moved: could not rename the checkout ({exc}); skipped")
        return
    try:
        moved_env = dict(env, QE_REPO=str(moved))
        proc = subprocess.run(argv, cwd=moved, env=moved_env, timeout=timeout,
                              capture_output=True, text=True, errors="replace")
        out, rc = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        out, rc = (exc.output or "") + f"\n[drive] timed out after {timeout}s", 124
    finally:
        moved.rename(repo)
    (artifacts / "step-moved.log").write_text(out)
    (artifacts / "step-moved.rc").write_text(f"{rc}\n")
    recorder.log.append(out)
    recorder.record("moved", rc, start, time.time(), argv)
    recorder.mark(f"moved END rc={rc}")


def console_phase(repo: Path, env: dict, artifacts: Path, recorder: Recorder) -> None:
    """Start the console, fetch its shell, stop it.

    Polled on the port rather than slept on: a fixed sleep either wastes the cell's
    budget or reports a server that had not finished binding as one that does not
    serve. The probe itself lives in `checks.py`, so the asset list and the 404
    control have exactly one definition.
    """
    argv = ["uv", "run", "thalamus", "console", "--port", str(CONSOLE_PORT)]
    recorder.mark("console START")
    recorder.note("phase console: starting")
    start = time.time()
    server_log = (artifacts / "console-server.log").open("w")
    try:
        proc = subprocess.Popen(argv, cwd=repo, env=env, stdout=server_log,
                                stderr=subprocess.STDOUT, start_new_session=True)
    except FileNotFoundError:
        server_log.close()
        recorder.note("phase console: no `uv` to start it with; skipped")
        return
    up = False
    try:
        for _ in range(spec.TIMEOUTS["graph-ready"]):
            if proc.poll() is not None:
                break
            if _port_open(CONSOLE_PORT):
                up = True
                break
            time.sleep(1)
        recorder.note(f"phase console: listening={up}")
        snap("console", env, recorder)
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            pass
        server_log.close()
    # Recorded as an exit code, so "up" must be 0. Storing the boolean here is a bug
    # this harness has already had once: a working phase printed `console rc=1`.
    recorder.record("console", 0 if up else 1, start, time.time(), argv)
    recorder.mark(f"console END up={up}")


# ---------------------------------------------------------------------------------
# The oracle, and what its output means
# ---------------------------------------------------------------------------------

def evaluate(env: dict, recorder: Recorder) -> dict:
    """Run `checks.py evaluate`, or say loudly that the oracle did not run.

    The fallback matters more than the happy path. An oracle that crashed and an
    oracle that found nothing wrong produce the same empty `failed` list, and
    collapsing those two is how a harness reports a clean sweep over a box it never
    looked at.
    """
    proc = subprocess.run([sys.executable, str(_HERE / "checks.py"), "evaluate"],
                          env=env, capture_output=True, text=True, errors="replace")
    try:
        parsed = json.loads(proc.stdout)
        if not isinstance(parsed, dict) or "checks" not in parsed:
            raise ValueError("evaluate returned JSON that is not a findings object")
        return parsed
    except (json.JSONDecodeError, ValueError) as exc:
        recorder.note(f"the oracle did not run: {exc}; "
                      f"stderr: {proc.stderr.strip()[:400]}")
        recorder.fail("check-evaluation-did-not-run")
        return {"checks": [], "passed": [], "failed": [],
                "not_evaluated": [c.name for c in spec.CHECKS]}


def triage(findings: dict) -> tuple[set[int], list[str], list[str]]:
    """Split failing checks into reproduced defects, regressions, and novel failures.

    A check that goes red naming an OPEN issue has reproduced something already
    filed. A check that goes red naming nothing has found something that is not.

    A check that goes red naming a `fixed` issue is neither, and it is the reason
    this returns three buckets instead of two. An issue number absolves a red — it
    is what turns exit 1 into exit 0 — so a tag left in place after the fix landed
    absolves forever, and the site it names becomes the one place in the matrix
    where a regression cannot be seen. Two ways in, both observed: the defect comes
    back, or the oracle drifts off the repaired behaviour and reports a working
    install as broken. The second is not hypothetical — `moved-checkout-is-named-not
    -denied` pinned the pre-fix wording of the #52 message, went red on the fix that
    reworded it, and stayed absolved by its own tag.
    """
    fixed = spec.fixed_issues()
    by_name = {c["name"]: c for c in findings.get("checks", [])}
    reproduced: set[int] = set()
    regressed: list[str] = []
    novel: list[str] = []
    for name in findings.get("failed", []):
        issue = by_name.get(name, {}).get("issue", 0)
        if issue and issue in fixed:
            regressed.append(f"{name} (#{issue})")
        elif issue:
            reproduced.add(issue)
        else:
            novel.append(name)
    return reproduced, regressed, novel


def build_payload(cell: str, config: spec.Config, recorder: Recorder,
                  findings: dict) -> dict:
    for name in findings.get("failed", []):
        recorder.fail(name)
    return {
        "cell": cell,
        "config": config.name,
        "repo_source": "checkout",
        "result": "fail" if recorder.failed else "pass",
        "failed": list(recorder.failed),
        "steps": recorder.steps,
        # The libvirt cell carries its isolation probe here. A hosted runner has no
        # operator graph to be isolated FROM, so there is nothing to probe and the
        # honest value is null — `checks.py` reports that check as not evaluated,
        # which is what "we could not look" is supposed to look like.
        "probe": None,
        "checks": findings,
        "not_evaluated": findings.get("not_evaluated", []),
        "log_tail": recorder.log_tail(),
    }


# ---------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="baseline",
                        help="a config name from spec.CONFIGS")
    parser.add_argument("--cell", default="",
                        help="a label for this run; defaults to <platform>-<config>")
    parser.add_argument("--repo", type=Path, default=Path.cwd(),
                        help="the checkout under test (default: cwd)")
    parser.add_argument("--home", type=Path, default=Path.home(),
                        help="the home directory the install writes into")
    parser.add_argument("--artifacts", type=Path, default=Path("/tmp/qe-artifacts"),
                        help="where snapshots, step logs and the verdict are written")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    repo = args.repo.resolve()
    recorder = Recorder(artifacts=artifacts)
    verdict_path = artifacts / "verdict.json"

    try:
        config = config_by_name(args.config)
        cell = args.cell or f"{sys.platform}-{config.name}"
        env = cell_env(config, repo, args.home.resolve(), artifacts)
        steps = tuple(s for s in spec.STEPS if s.phase not in config.skip_steps)
        gate_commands_present(steps, config, env)
        gate_prerequisites(config, env)
        gate_config_premise(config, recorder)
    except GateRefused as exc:
        print(f"boundary-abort: {exc}", file=sys.stderr)
        verdict_path.write_text(json.dumps(
            {"outcome": verdict_mod.Outcome.BOUNDARY_ABORT.value,
             "detail": str(exc)}, indent=2))
        return 3

    recorder.note(f"cell {cell}: config {config.name!r}, repo {repo}, "
                  f"{len(steps)} of {len(spec.STEPS)} documented steps")
    if config.skip_steps:
        recorder.note("skipped by config: "
                      + ", ".join(p.value for p in config.skip_steps))

    def snapshots_after(phase: spec.Phase | None) -> None:
        for label in SNAPSHOTS_AFTER.get(phase, ()):
            if SNAPSHOT_PHASE[label] in config.skip_steps:
                recorder.note(f"snapshot {label} skipped: its phase is not in this cell")
                continue
            snap(label, env, recorder)

    try:
        with Perturbation(config, env, recorder):
            snapshots_after(None)
            for step in steps:
                run_step(step, repo, env, artifacts, recorder)
                snapshots_after(step.phase)
                if step.phase is spec.Phase.REINSTALLED:
                    if spec.Phase.MOVED not in config.skip_steps:
                        moved_phase(repo, env, artifacts, recorder)
                    if spec.Phase.CONSOLE not in config.skip_steps:
                        console_phase(repo, env, artifacts, recorder)
            findings = evaluate(env, recorder)
    except GateRefused as exc:
        print(f"boundary-abort: {exc}", file=sys.stderr)
        verdict_path.write_text(json.dumps(
            {"outcome": verdict_mod.Outcome.BOUNDARY_ABORT.value,
             "detail": str(exc)}, indent=2))
        return 3

    payload = build_payload(cell, config, recorder, findings)
    verdict_path.write_text(json.dumps(payload, indent=2))
    frame_path = artifacts / "verdict.frame"
    verdict_mod.write_frame(frame_path, json.dumps(payload).encode("utf-8"))
    result = verdict_mod.classify(frame_path, domstate="shut off",
                                  deadline_expired=False,
                                  last_phase=recorder.last_phase)

    reproduced, regressed, novel = triage(findings)
    return report(result, findings, reproduced, regressed, novel, recorder,
                  verdict_path)


def report(result, findings: dict, reproduced: set[int], regressed: list[str],
           novel: list[str], recorder: Recorder, verdict_path: Path) -> int:
    counts = (len(findings.get("passed", [])), len(findings.get("failed", [])),
              len(findings.get("not_evaluated", [])))
    print(f"\ncell {result.outcome.value}: {counts[0]} passed, {counts[1]} failed, "
          f"{counts[2]} not evaluated — {verdict_path}")
    for check in findings.get("checks", []):
        if check["state"] != "pass":
            issue = f"#{check['issue']}" if check["issue"] else "unfiled"
            print(f"  {check['state']:14} {check['name']:48} {issue}")

    if "check-evaluation-did-not-run" in recorder.failed:
        print("\nMALFORMED: the oracle did not run, so nothing here is evidence.")
        return 3

    step_failures = [f for f in recorder.failed
                     if f not in findings.get("failed", [])
                     and f != "check-evaluation-did-not-run"]
    if novel or regressed or step_failures:
        for name in novel:
            print(f"\nNEW: {name} failed and names no filed issue.")
        for name in regressed:
            print(f"\nREGRESSED: {name} names an issue marked fixed in spec.py, so "
                  "this check was expected to pass. Either the defect is back, or "
                  "the check has drifted off the repaired behaviour and is now "
                  "reporting a working install as broken. Read the witness before "
                  "reopening anything.")
        for name in step_failures:
            print(f"\nNEW: step {name} failed and may not fail.")
        return 1

    known = sorted(spec.known_defect_issues())
    if not known:
        # Every tagged defect is marked fixed, so there is nothing left for a run to
        # reproduce and "nothing reproduced" has stopped being evidence of a blind
        # harness. The positive control this exit code provided is gone with it: from
        # here a cell can only report the absence of NEW failures, which is a weaker
        # claim than this matrix was built to make. Re-arm it by tagging the next
        # filed defect, and read a green cell as "nothing new" until then.
        print("\nNo unfixed defect is tagged in spec.py, so this cell had nothing "
              "known to reproduce. Green here means no NEW failure — it is no longer "
              "evidence that the harness can see.")
        return 0
    if not reproduced:
        print(f"\nNothing reproduced. The tree carries filed install defects "
              f"({', '.join('#%d' % i for i in known)}), so a cell that reproduces "
              "none of them either ran against a tree where they are fixed or could "
              "not see them. This is not a pass.")
        return 2

    got = ", ".join(f"#{i}" for i in sorted(reproduced))
    print(f"\nReproduced {got} — the harness observed, and every failure is filed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
