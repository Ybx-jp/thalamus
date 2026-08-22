"""An install cell must refuse a box it cannot measure, rather than report on it.

`tests/qe/install/drive.py` runs the documented first-run sequence and judges it. Every
check it evaluates is written to a premise — a box with the documented prerequisites, a
box with no graph, a box where the config's perturbation actually applied — and none of
those premises is visible in the result. A cell that runs anyway does not produce a
weaker finding; it produces a confident wrong one.

That is not hypothetical. Measured 2026-08-21: the `graph-not-started` cell run on a
developer box whose graph was already up reported issue #17 reproduced — "the graph-down
diagnosis did not reach the user" — from a step that had no graph-down condition to
diagnose. The reproduction count went up, the harness looked like it was working, and
the observation was of nothing.

So the driver has three gates, and this case is what keeps them gates. Each is asserted
twice: once that it refuses when its premise is false, and once that it *permits* when
the premise holds. The second half is the load-bearing one. A gate that refuses
everything satisfies every refusal assertion in this file and would turn the whole
install matrix into a permanent `boundary-abort` — which reads, in a ledger, exactly
like a box that was never available.

**Hermetic by construction.** Every probe runs against a synthetic PATH of shell stubs
in a temp directory and a socket this case binds itself. It never touches the real PATH,
never renames a real binary, and never connects to the operator's graph — a case that
had to move `jq` aside to check the `no-jq` gate would be a case that leaves a box
broken when it crashes.
"""

from __future__ import annotations

import contextlib
import os
import socket
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_INSTALL = Path(__file__).resolve().parents[1] / "install"
if str(_INSTALL) not in sys.path:
    sys.path.insert(0, str(_INSTALL))

import drive  # noqa: E402
import spec  # noqa: E402


def _stub_dir(root: Path, names) -> Path:
    """A PATH directory of executables that do nothing, for `shutil.which` to find."""
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        stub = root / name
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    return root


def _refused(fn) -> str | None:
    """The refusal message, or None if the gate permitted."""
    try:
        fn()
    except drive.GateRefused as exc:
        return str(exc)
    return None


def _recorder(tmp: Path) -> drive.Recorder:
    rec = drive.Recorder(artifacts=tmp)
    rec.note = lambda _line: None  # type: ignore[method-assign]
    return rec


def _check_commands(tmp: Path) -> Finding | None:
    baseline = drive.config_by_name("baseline")
    full = _stub_dir(tmp / "full", ("uv", "docker", "jq", "tmux", "claude"))
    partial = _stub_dir(tmp / "partial", ("uv", "jq", "tmux", "claude"))

    permitted = _refused(
        lambda: drive.gate_commands_present(spec.STEPS, baseline,
                                            {"PATH": str(full)}))
    if permitted is not None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the command gate refuses a box that HAS every command the "
                    "sequence runs, so its refusals carry no information",
            witness=permitted,
            site="tests/qe/install/drive.py gate_commands_present",
        )

    refusal = _refused(
        lambda: drive.gate_commands_present(spec.STEPS, baseline,
                                            {"PATH": str(partial)}))
    if refusal is None:
        return Finding(
            failure_class=FailureClass.FAILED_OPEN,
            summary="a box with no `docker` was permitted to run the baseline "
                    "sequence, so `docker compose up -d` would be dropped and every "
                    "graph-phase check would report SKIPPED as though its evidence "
                    "had gone astray",
            witness=f"PATH={partial} holds uv, jq, tmux, claude and no docker",
            site="tests/qe/install/drive.py gate_commands_present",
        )

    # A command the config takes away is absent BY DESIGN and is not a missing
    # precondition. Without this, every `removes` config would abort on itself.
    removes_docker = replace(baseline, name="synthetic-no-docker",
                             removes=("docker",))
    intentional = _refused(
        lambda: drive.gate_commands_present(spec.STEPS, removes_docker,
                                            {"PATH": str(partial)}))
    if intentional is not None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the command gate treats a config's own `removes` as a missing "
                    "precondition, so no perturbing config could ever run",
            witness=intentional,
            site="tests/qe/install/drive.py gate_commands_present",
        )
    return None


def _check_prerequisites(tmp: Path) -> Finding | None:
    baseline = drive.config_by_name("baseline")
    full = _stub_dir(tmp / "prereq-full", ("uv", "docker", "jq", "tmux", "claude"))
    # `jq` appears in no step's argv, so nothing in the sequence would notice it gone.
    no_jq = _stub_dir(tmp / "prereq-nojq", ("uv", "docker", "tmux", "claude"))
    no_cli = _stub_dir(tmp / "prereq-nocli", ("uv", "docker", "jq", "tmux"))

    permitted = _refused(
        lambda: drive.gate_prerequisites(baseline, {"PATH": str(full)}))
    if permitted is not None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the prerequisite gate refuses a box that has every documented "
                    "prerequisite, so its refusals carry no information",
            witness=permitted,
            site="tests/qe/install/drive.py gate_prerequisites",
        )

    for label, path, why in (
        ("jq", no_jq, "the hook layer parses its stdin with jq and exits silently "
                      "without it, so the install reports success and then does less "
                      "than it says"),
        ("an agent CLI", no_cli, "distillation shells out to one of them"),
    ):
        if _refused(lambda p=path: drive.gate_prerequisites(baseline,
                                                            {"PATH": str(p)})) is None:
            return Finding(
                failure_class=FailureClass.FAILED_OPEN,
                summary=f"a box with no {label} was permitted to run the documented "
                        f"sequence, and {why}",
                witness=f"PATH={path}",
                site="tests/qe/install/drive.py gate_prerequisites",
            )

    # The inverse rule: a config asserting their absence must find ALL of them gone,
    # not merely the one it named. A `no-agent-cli` box still answering `codex` is not
    # the box that config means.
    no_agent = drive.config_by_name("no-agent-cli")
    leftover = _stub_dir(tmp / "prereq-leftover", ("uv", "docker", "jq", "tmux",
                                                   "claude", "codex"))
    if _refused(lambda: drive.gate_prerequisites(
            no_agent, {"PATH": str(leftover)})) is None:
        return Finding(
            failure_class=FailureClass.FAILED_OPEN,
            summary="the `no-agent-cli` config was permitted on a box that still "
                    "answers `codex`, so the cell would run unperturbed under a "
                    "perturbed name and pass every check it exists to fail",
            witness=f"PATH={leftover} holds claude and codex",
            site="tests/qe/install/drive.py gate_prerequisites",
        )
    return None


def _check_premise(tmp: Path) -> Finding | None:
    config = drive.config_by_name("graph-not-started")
    if spec.Phase.GRAPH_STARTING not in config.skip_steps:
        return Finding(
            failure_class=FailureClass.DOC_CODE_DRIFT,
            summary="the `graph-not-started` config no longer skips the graph phases, "
                    "so this case is asserting the premise of a config that changed "
                    "underneath it",
            witness=f"skip_steps={[p.value for p in config.skip_steps]}",
            site="tests/qe/install/spec.py CONFIGS",
        )

    with contextlib.closing(socket.socket()) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        busy = listener.getsockname()[1]
        refusal = _refused(
            lambda: drive.gate_config_premise(config, _recorder(tmp), port=busy))
        if refusal is None:
            return Finding(
                failure_class=FailureClass.FAILED_OPEN,
                summary="a cell premised on a box with no graph was permitted where a "
                        "graph answers, which is how issue #17 was reported reproduced "
                        "from a step that had nothing to diagnose (measured "
                        "2026-08-21)",
                witness=f"127.0.0.1:{busy} was listening and the gate permitted",
                site="tests/qe/install/drive.py gate_config_premise",
            )

    # The control, taken after the socket closed: the same gate must permit when the
    # premise holds, or it is a gate that refuses everything.
    permitted = _refused(
        lambda: drive.gate_config_premise(config, _recorder(tmp), port=busy))
    if permitted is not None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the premise gate refuses even when nothing is listening, so "
                    "every cell would abort and a boundary-abort ledger would be "
                    "indistinguishable from a box that was never available",
            witness=permitted,
            site="tests/qe/install/drive.py gate_config_premise",
        )
    return None


def _check_perturbation(tmp: Path) -> Finding | None:
    """`removes` must clear every copy on PATH, and put them all back afterwards.

    The single-rename version of this is correct on a golden image, where there is
    exactly one copy of anything — and silently wrong anywhere else, which is the whole
    reason the driver runs on boxes the golden image does not describe.
    """
    first = _stub_dir(tmp / "pert-a", ("jq", "uv", "docker", "tmux", "claude"))
    second = _stub_dir(tmp / "pert-b", ("jq",))
    path = f"{first}{os.pathsep}{second}"
    config = drive.config_by_name("no-jq")
    env = {"PATH": path}

    import shutil
    try:
        with drive.Perturbation(config, env, _recorder(tmp)):
            if shutil.which("jq", path=path) is not None:
                return Finding(
                    failure_class=FailureClass.FAILED_OPEN,
                    summary="`jq` is still resolvable inside a `no-jq` cell, so the "
                            "cell measures an unperturbed box and passes the checks "
                            "it exists to fail",
                    witness=f"which(jq) = {shutil.which('jq', path=path)} with "
                            f"PATH={path}",
                    site="tests/qe/install/drive.py Perturbation",
                )
    except drive.GateRefused as exc:
        # Caught rather than allowed to propagate. A raised exception is MALFORMED —
        # "the check is broken" — and that is the wrong report for a perturbation that
        # gave up on a box it should have handled: two copies is well inside the bound
        # it declares, so refusing here would make every `no-jq` cell an abort while
        # the ledger showed nothing worse than an unavailable box.
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the perturbation refused a box it should have been able to "
                    "perturb, so every `no-jq` cell would boundary-abort instead of "
                    "running",
            witness=f"two copies of jq on PATH, bound is "
                    f"{drive.Perturbation.MAX_COPIES}: {exc}",
            site="tests/qe/install/drive.py Perturbation",
        )
    if shutil.which("jq", path=path) is None:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary="the perturbation did not restore every copy it moved aside, so a "
                    "cell leaves the box it ran on missing a binary",
            witness=f"PATH={path} still answers nothing for jq after the cell",
            site="tests/qe/install/drive.py Perturbation.__exit__",
        )
    return None


def run() -> Finding | None:
    with tempfile.TemporaryDirectory(prefix="qe-drive-gates-") as raw:
        tmp = Path(raw)
        for probe in (_check_commands, _check_prerequisites, _check_premise,
                      _check_perturbation):
            finding = probe(tmp)
            if finding is not None:
                return finding
    return None


CASE = Case(
    name="install-cell-gates-refuse-a-box-it-cannot-measure",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.FAILED_OPEN, FailureClass.COLLAPSED_SENTINEL,
             FailureClass.INVARIANT_FALSIFIED, FailureClass.DOC_CODE_DRIFT),
    summary="the install driver must boundary-abort on a box whose premises are false, "
            "and must still permit one whose premises hold",
    run=run,
)
