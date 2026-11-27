"""`--uninstall` must take back the subagent model `init` writes into the user settings.

`install()` writes two things into `~/.claude/settings.json`: the hook block and
`env.CLAUDE_CODE_SUBAGENT_MODEL = "sonnet"`, which routes every model-less subagent of
every Claude Code session on the box to that model. `uninstall()` strips the hooks and
leaves the env key, so after a full round trip the operator's settings still carry it.
`uninstall-takes-back-what-install-wrote` cannot see this: its marker is the string
`thalamus`, which neither the key nor its value contains.

Hermetic: a child with `HOME` moved to a temp dir, the vendor CLIs shimmed to fail on
`PATH`, the four registration seams stubbed and `verify()` replaced, since the subject
is the settings file and not the checks.

**Control.** The key must be present after install; otherwise its absence after
uninstall says nothing. Driven red on the commit that shipped it; the fix (strip the
key when it names `VANILLA_SUBAGENT_MODEL`) turns it green.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_CHILD = r"""
import json, os
from pathlib import Path
from thalamus.harness import install

tmp = Path(os.environ["QE_PROJECT_TMP"])
for _name in ("PROJECT_SETTINGS", "PROJECT_MCP", "PROJECT_CURSOR_HOOKS", "PROJECT_CURSOR_MCP"):
    setattr(install, _name, tmp / "project" / getattr(install, _name).name)
install.register_mcp = lambda dry_run=False: "mcp: stubbed"
install.deregister_mcp = lambda dry_run=False: "mcp: stubbed"
install.register_codex_mcp = lambda dry_run=False: "codex mcp: stubbed"
install.deregister_codex_mcp = lambda dry_run=False: "codex mcp: stubbed"
install.verify = lambda harnesses=install.HARNESSES: []

settings = install.USER_SETTINGS
settings.parent.mkdir(parents=True, exist_ok=True)
settings.write_text(json.dumps({"env": {"KEEP_ME": "yes"}}))
before = json.loads(settings.read_text())
install.install(harnesses=("claude",))
after = json.loads(settings.read_text())
install.uninstall()
end = json.loads(settings.read_text())
print(json.dumps({"home": str(Path.home()), "before": before, "after": after, "end": end}))
"""

_KEY = "CLAUDE_CODE_SUBAGENT_MODEL"


def _observe() -> dict | str:
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as proj:
        shims = Path(proj) / "bin"
        shims.mkdir()
        for name in ("claude", "codex"):
            (shims / name).write_text("#!/bin/sh\nexit 1\n")
            (shims / name).chmod(0o755)
        env = dict(os.environ)
        env.update(HOME=home, QE_PROJECT_TMP=proj,
                   PATH=f"{shims}{os.pathsep}{env.get('PATH', '')}")
        env.pop("CODEX_HOME", None)
        env.pop("THALAMUS_ARCHIVE_DIR", None)
        try:
            proc = subprocess.run([sys.executable, "-c", _CHILD], capture_output=True,
                                  text=True, env=env, timeout=300, check=False)
        except subprocess.TimeoutExpired:
            return "the round trip did not finish within 300s"
        if proc.returncode != 0 or not proc.stdout.strip():
            return f"rc={proc.returncode} stderr={proc.stderr.strip()[-400:]}"
        try:
            data = json.loads(proc.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError as exc:
            return f"no JSON from the child ({exc})"
        if Path(data["home"]).resolve() != Path(home).resolve():
            return f"child did not adopt the redirected HOME ({data['home']})"
        return data


def run() -> Finding | None:
    data = _observe()
    if isinstance(data, str):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the install/uninstall round trip did not run",
            witness=data,
            site="tests/qe/cases/uninstall_subagent_model_residue.py:_observe",
        )
    if data["after"].get("env", {}).get(_KEY) is None or "hooks" not in data["after"]:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=f"install wrote no {_KEY} or no hooks, so its absence after "
                    "uninstall would mean nothing",
            witness=f"after install: {json.dumps(data['after'])[:300]}",
            site="src/thalamus/harness/install.py:install",
        )
    if data["end"] == data["before"]:
        return None
    residue = {k: v for k, v in data["end"].get("env", {}).items()
               if k not in data["before"].get("env", {})}
    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary="`init --uninstall` leaves the subagent model `init` wrote into the "
                "user's Claude Code settings, so every session on the box keeps it",
        witness=f"settings.json env after install+uninstall carries {residue}; "
                f"before install it was {data['before'].get('env')}",
        site="src/thalamus/harness/install.py:uninstall",
    )


CASE = Case(
    name="uninstall-removes-the-subagent-model-install-set",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="after `init` then `init --uninstall`, ~/.claude/settings.json is what it was",
    run=run,
    issue=441,
)
