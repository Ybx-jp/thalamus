"""A manifest's `deny_tools` must block Bash when it names Bash.

A job context unsuited to Bash is bounded by a manifest copy whose
`capability_boundary.deny_tools` names it. `CapabilityBoundary.deny_tools` is described
as "fnmatch patterns over the tool name; a match blocks the call", and nothing in that
description excludes Bash. Two layers stand between the field and the call:

- `role-guard.sh`'s matcher in `harness/install.HOOK_WIRING` must route Bash to the
  guard at all, and
- the guard's `case "$tool_name"` must send Bash to the tool check; a tool it has no
  branch for exits 0 before any manifest is read.

The property: under a manifest denying Bash, Bash is routed and refused, and under the
same manifest without that deny it is permitted (the guard must not start refusing
Bash for every scope).

**The copy has to restate the default.** A declared `capability_boundary` replaces
`EXPERT_CAPABILITY_DEFAULT` rather than adding to it, which is how `designer` opts out
(`Manifest.effective_capability_boundary`). So the manifest under test is the default
plus `Bash`, and the case also pins the replacement: a copy declaring only
`deny_tools: [Bash]` permits `Artifact`, which the default refuses. That row is not a
defect; it is there so a copy written the short way is seen to drop the design
boundary, and so a change to the replacement semantics fails here rather than silently.

**Controls**, under scope `qe` with a temporary HOME and a copy of the repository's
config root: the default refuses `Artifact` and permits Bash; the default-plus-Bash
copy refuses `Artifact`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]
_GUARD = _REPO / "src/thalamus/harness/hooks/claude-code/role-guard.sh"
_SITE = "src/thalamus/harness/hooks/claude-code/role-guard.sh (tool dispatch), src/thalamus/harness/install.py::HOOK_WIRING"
_BASH = {"command": "echo qe-probe > /dev/null", "description": "probe"}


def _config(boundary: dict | None) -> tempfile.TemporaryDirectory:
    root = tempfile.TemporaryDirectory(prefix="qe-capcfg-")
    shutil.copytree(_REPO / "config", root.name, dirs_exist_ok=True)
    if boundary is not None:
        with open(Path(root.name, "experts", "qe.yaml"), "a") as f:
            f.write("\ncapability_boundary: " + json.dumps(boundary) + "\n")
    return root


def _guard(config: str, tool: str, tool_input: dict) -> int:
    with tempfile.TemporaryDirectory(prefix="qe-roleguard-") as home:
        env = dict(os.environ, HOME=home, THALAMUS_SCOPE="qe", THALAMUS_CONFIG_DIR=config)
        for var in ("CLAUDE_CODE_AGENT", "THALAMUS_ROOM", "THALAMUS_SANDBOX"):
            env.pop(var, None)
        payload = {"tool_name": tool, "session_id": "qe-probe", "cwd": str(_REPO), "tool_input": tool_input}
        return subprocess.run(["bash", str(_GUARD)], input=json.dumps(payload), capture_output=True,
                              text=True, env=env, timeout=60, check=False).returncode


def _routed(tool: str) -> bool:
    from thalamus.harness.install import HOOK_WIRING

    matchers = [m for event, m, script in HOOK_WIRING if event == "PreToolUse" and script == "role-guard.sh"]
    assert len(matchers) == 1 and matchers[0], matchers
    return bool(re.fullmatch(matchers[0], tool) or re.search(matchers[0], tool))


def run() -> Finding | None:
    from thalamus.contract.manifest import EXPERT_CAPABILITY_DEFAULT

    default = EXPERT_CAPABILITY_DEFAULT.model_dump()
    with_bash = {**default, "deny_tools": [*default["deny_tools"], "Bash"],
                 "reason": "qe probe: this job context does not run shell commands"}
    with _config(None) as base, _config(with_bash) as full, _config(
            {"deny_tools": ["Bash"], "reason": "qe probe"}) as short:
        rows = [("default, Artifact", base, "Artifact", {"action": "publish"}, 2),
                ("default, Bash", base, "Bash", _BASH, 0),
                ("default plus Bash, Artifact", full, "Artifact", {"action": "publish"}, 2)]
        for label, config, tool, tool_input, want in rows:
            got = _guard(config, tool, tool_input)
            if got != want:
                return Finding(FailureClass.FAILED_OPEN if want == 2 else FailureClass.INVARIANT_FALSIFIED,
                               f"control: {label} gave exit {got}, not {want}",
                               witness=f"{label} -> exit {got}", site=_SITE)
        replaced = _guard(short, "Artifact", {"action": "publish"})
        if replaced != 0:
            return Finding(FailureClass.DOC_CODE_DRIFT,
                           "a declared capability_boundary no longer replaces the expert default; "
                           "effective_capability_boundary's docstring and this case describe replacement",
                           witness=f"deny_tools [Bash] only, Artifact -> exit {replaced}",
                           site="src/thalamus/contract/manifest.py::Manifest.effective_capability_boundary")
        routed = _routed("Bash")
        refused = _guard(full, "Bash", _BASH)
    if not routed or refused != 2:
        return Finding(FailureClass.UNENFORCED_SIGNAL,
                       "a manifest whose deny_tools names Bash does not stop Bash",
                       witness=f"matcher {'routes' if routed else 'does not route'} Bash; "
                               f"role-guard under deny_tools [..., Bash] -> exit {refused}",
                       site=_SITE)
    return None


CASE = Case(
    name="a-capability-boundary-that-denies-bash-stops-bash",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.UNENFORCED_SIGNAL, FailureClass.FAILED_OPEN, FailureClass.INVARIANT_FALSIFIED,
             FailureClass.DOC_CODE_DRIFT),
    summary="deny_tools naming Bash routes Bash to role-guard and refuses it; without the deny Bash passes",
    run=run,
    issue=428,
)
