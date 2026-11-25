"""A capability boundary must bind the capability under every name a session can call it by.

`EXPERT_CAPABILITY_DEFAULT` denies every pinned expert except `designer` the design
skills and artifact publishing: `deny_skills` `artifact-*`, `frontend-design*`,
`dataviz`, `author-repo-diagram`; `deny_tools` `Artifact`, `mcp__penpot__*`. Both are
`fnmatch` over the name in the payload, and the tool half is reached only through
`role-guard.sh`'s matcher in `harness/install.HOOK_WIRING`
(`Edit|Write|NotebookEdit|Skill|Artifact|mcp__penpot__.*`). Two names reach the same
capability and miss both:

- **A plugin-namespaced skill.** A skill a plugin ships is invoked as `<plugin>:<skill>`,
  so `anthropic-skills:artifact-emulator` is the skill `artifact-*` denies, and
  `fnmatch` anchors at the start of the string. `frontend-design*` happens to survive
  this, because that plugin and its skill share a name; `artifact-*` does not.
- **Artifact publishing through an MCP server.** A session armed with the
  claude-artifacts connector publishes a page with `mcp__claude-artifacts__publish_version`
  (also `publish_files`, `edit_version`). That name matches neither the hook matcher —
  so Claude Code never runs role-guard for it — nor `deny_tools`, so the guard would
  permit it if it did run. A qe-pinned session holding exactly these tools is what
  this case was written from.

The property: each capability the default denies is denied under each name listed
here, at both layers — the matcher routes the call to role-guard, and role-guard
blocks it.

**Matcher semantics.** Claude Code reads a matcher as a regex (measured 2026-08-17,
`install._build_matcher_block`). Whether it anchors is not measured here, so a name
counts as routed if the matcher matches it either way; that is the reading under which
a miss is least likely to be reported, and these names miss under both.

**Controls.** Under scope `qe`, with the repository's config root and a temporary HOME:
the bare skill `artifact-emulator` and the tool `Artifact` are blocked, and the skill
`recall-strategy` is permitted. A boundary that blocked nothing, or everything, fails
the controls before any variant is read.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]
_GUARD = _REPO / "src/thalamus/harness/hooks/claude-code/role-guard.sh"
_CONFIG_ROOT = _REPO / "config"
_SITE = "src/thalamus/contract/manifest.py::EXPERT_CAPABILITY_DEFAULT, src/thalamus/harness/install.py::HOOK_WIRING"

# Each denied capability, under the names a session can call it by.
_SKILLS = ("anthropic-skills:artifact-emulator",)
_TOOLS = ("mcp__claude-artifacts__publish_version", "mcp__claude-artifacts__publish_files",
          "mcp__claude-artifacts__edit_version")


def _guard(tool: str, tool_input: dict) -> int:
    with tempfile.TemporaryDirectory(prefix="qe-roleguard-") as home:
        env = dict(os.environ, HOME=home, THALAMUS_SCOPE="qe", THALAMUS_CONFIG_DIR=str(_CONFIG_ROOT))
        for var in ("CLAUDE_CODE_AGENT", "THALAMUS_ROOM", "THALAMUS_SANDBOX"):
            env.pop(var, None)
        payload = {"tool_name": tool, "session_id": "qe-probe", "cwd": str(_REPO), "tool_input": tool_input}
        return subprocess.run(["bash", str(_GUARD)], input=json.dumps(payload), capture_output=True,
                              text=True, env=env, timeout=60, check=False).returncode


def _role_guard_matcher() -> str:
    from thalamus.harness.install import HOOK_WIRING

    matchers = [m for event, m, script in HOOK_WIRING if event == "PreToolUse" and script == "role-guard.sh"]
    assert len(matchers) == 1 and matchers[0], matchers
    return matchers[0]


def _routed(matcher: str, tool: str) -> bool:
    return bool(re.fullmatch(matcher, tool) or re.search(matcher, tool))


def run() -> Finding | None:
    matcher = _role_guard_matcher()
    for label, got, want in (("Skill artifact-emulator", _guard("Skill", {"skill": "artifact-emulator"}), 2),
                             ("tool Artifact", _guard("Artifact", {"action": "publish"}), 2),
                             ("Skill recall-strategy", _guard("Skill", {"skill": "recall-strategy"}), 0)):
        if got != want:
            return Finding(FailureClass.FAILED_OPEN if want == 2 else FailureClass.INVARIANT_FALSIFIED,
                           f"control: scope qe {label} gave exit {got}, not {want}",
                           witness=f"{label} -> exit {got}", site=_SITE)
    if not _routed(matcher, "Artifact") or not _routed(matcher, "Skill"):
        return Finding(FailureClass.COLLAPSED_SENTINEL, "control: the matcher does not route its own named tools",
                       witness=matcher, site=_SITE)

    leaks = []
    for skill in _SKILLS:
        code = _guard("Skill", {"skill": skill})
        if code != 2:
            leaks.append(f"Skill {skill} -> exit {code}")
    for tool in _TOOLS:
        routed = _routed(matcher, tool)
        code = _guard(tool, {"content": "qe probe"})
        if not routed or code != 2:
            leaks.append(f"{tool}: matcher {'routes' if routed else 'does not route'} it, guard exit {code}")
    if leaks:
        return Finding(FailureClass.BOUNDARY_LEAK,
                       "the expert capability default denies a capability by one name and permits it by another",
                       witness="; ".join(leaks), site=_SITE)
    return None


CASE = Case(
    name="role-guard-binds-the-capability-not-the-name",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_JQ,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.FAILED_OPEN, FailureClass.INVARIANT_FALSIFIED,
             FailureClass.COLLAPSED_SENTINEL),
    summary="a denied skill or tool stays denied under its plugin-namespaced or MCP-server name",
    run=run,
    issue=425,
)
