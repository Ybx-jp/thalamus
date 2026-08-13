"""Drive `thalamus init` and `--uninstall` against a HOME that is not the operator's.

Not a case. Two cases need the same expensive observation — what the installer writes
into a home directory, and what survives its own removal — and running it twice would
double a subprocess that imports the whole package.

**Why a subprocess with `HOME` set, rather than monkeypatching the constants.**
`install.py` derives `USER_SETTINGS`, `USER_SKILLS_DIR`, `USER_AGENTS_DIR`,
`USER_CURSOR_HOOKS` and `USER_CURSOR_MCP` from `Path.home()` at *import* time. Patching
each one in-process is the shape `tests/test_install.py` uses, and it is sound there
because that suite asserts on the specific files it patched. It is the wrong instrument
here: both cases assert over *everything the installer touched*, so a target nobody
thought to patch is exactly the thing they are looking for, and an in-process fixture
would silently send it to the operator's real `~/.claude`. Setting `HOME` for a child
moves all of them at once and needs no list — the property
`home-redirection-moves-every-path` exists to keep that premise true.

Three things `HOME` does not contain. The first is stubbed on `PATH`, the other two in
the child:

- **The vendor CLI.** `install()` finishes by verifying, and `_mcp_env_from_cli` runs
  `claude mcp get thalamus` to read back the registered environment. Claude Code answers
  by creating `~/.claude.json` **and** `~/.claude/backups/.claude.json.backup.<ts>` in
  whatever home it is pointed at, so an unshimmed probe reports the vendor's own files as
  part of the installer's footprint — and reports them only on a box that has the CLI,
  which CI does not. A case whose result depends on whether `claude` is installed is
  reporting on the box. A shim earlier on `PATH` that exits non-zero keeps the same code
  path (`shutil.which` still resolves, the caller takes its documented
  "nothing is running the old config" branch) and writes nothing. Shadowing a binary on
  `PATH` rather than patching around it is the idiom `tests/test_spawn_settle.py` already
  uses to keep a real tmux off the operator's server.

- `register_mcp` / `deregister_mcp` shell out to `claude mcp add|remove`, and
  `~/.claude.json` is **not** reliably contained by overriding `HOME` for that child —
  measured while `--uninstall` was being written (`9bcd7c7`): a removal run against a
  throwaway home wrote its backup into the fake home and edited the real file anyway,
  deregistering the box's actual server. Stubbing the two named seams is what makes this
  probe safe to run on a developer's machine.
- The four `PROJECT_*` constants anchor on the checkout, and `install()` *strips* the
  project-scope hook block and MCP entry it finds there. Unredirected, this probe would
  edit tracked files in the operator's working tree. They are pointed at the temp dir.

The child reports three snapshots of the home tree — before install, after install,
after uninstall — plus the text `_confirm()` prints. `_confirm()` is called with a
non-tty stdin, which declines: the probe wants the blast-radius text, not the consent,
and `install()` is invoked directly afterwards rather than through the prompt.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_CHILD = r"""
import io, json, os, sys
from pathlib import Path
from contextlib import redirect_stdout

home = Path.home()
tmp = Path(os.environ["QE_PROJECT_TMP"])
from thalamus.harness import install

for _name in ("PROJECT_SETTINGS", "PROJECT_MCP", "PROJECT_CURSOR_HOOKS", "PROJECT_CURSOR_MCP"):
    setattr(install, _name, tmp / "project" / getattr(install, _name).name)
install.register_mcp = lambda dry_run=False: "mcp: stubbed"
install.deregister_mcp = lambda dry_run=False: "mcp: stubbed"


def tree():
    out = {}
    for p in sorted(home.rglob("*")):
        rel = str(p.relative_to(home))
        if p.is_symlink():
            out[rel] = "symlink:" + str(p.readlink())
        elif p.is_dir():
            out[rel] = "\x00dir"
        else:
            try:
                out[rel] = p.read_text(errors="replace")
            except OSError as exc:
                out[rel] = "\x00unreadable:%s" % type(exc).__name__
    return out


class _NotATty(io.StringIO):
    def isatty(self):
        return False


buf = io.StringIO()
_stdin = sys.stdin
sys.stdin = _NotATty()
try:
    with redirect_stdout(buf):
        install._confirm()
finally:
    sys.stdin = _stdin

before = tree()
actions, _checks = install.install()
after = tree()
uninstall_actions = install.uninstall()
end = tree()

print(json.dumps({
    "home": str(home),
    "consent": buf.getvalue(),
    "named": {
        "USER_SETTINGS": str(install.USER_SETTINGS),
        "USER_SKILLS_DIR": str(install.USER_SKILLS_DIR),
        "USER_AGENTS_DIR": str(install.USER_AGENTS_DIR),
        "USER_CURSOR_HOOKS": str(install.USER_CURSOR_HOOKS),
        "USER_CURSOR_MCP": str(install.USER_CURSOR_MCP),
    },
    "package_skills": [str(p.resolve()) for p in install.shipped_skills()],
    "install_actions": actions,
    "uninstall_actions": uninstall_actions,
    "before": before,
    "after": after,
    "end": end,
}))
"""


@dataclass(frozen=True)
class Probe:
    """One install/uninstall round trip against a throwaway home.

    `created` is the installer's own footprint — paths present after `install()` and
    absent before it. Every assertion in both cases is scoped to that set rather than to
    the whole tree, because the tree also holds whatever the interpreter, `uv` and the
    OS put there, and a residue check over those is a report about the box.
    """

    home: str
    consent: str
    named: dict[str, str]
    package_skills: tuple[str, ...]
    install_actions: tuple[str, ...]
    uninstall_actions: tuple[str, ...]
    before: dict[str, str]
    after: dict[str, str]
    end: dict[str, str]

    @property
    def created(self) -> dict[str, str]:
        return {k: v for k, v in self.after.items() if k not in self.before}


_CACHE: list[Probe | str] = []


def observe(timeout: float = 300.0) -> Probe | str:
    """Run the round trip, or return a string describing why it could not be run.

    A string return is a broken probe, never a finding: the caller turns it into a
    COLLAPSED_SENTINEL finding naming this file, because "the installer wrote nothing
    objectionable" and "the installer never ran" are the same silence otherwise.

    Memoized for the process, which is what makes this module shared rather than merely
    common. The observation is a pure read of one deterministic round trip, `Probe` is
    frozen, and both callers only read it — so the second case gets the first case's
    snapshots instead of a second install. A failure is cached too: two cases reporting
    the same broken probe should report the same reason, not race to produce two.
    """
    if _CACHE:
        return _CACHE[0]
    result = _run(timeout)
    _CACHE.append(result)
    return result


def _run(timeout: float) -> Probe | str:
    with tempfile.TemporaryDirectory() as fake_home, tempfile.TemporaryDirectory() as proj:
        shim_dir = Path(proj) / "bin"
        shim_dir.mkdir()
        shim = shim_dir / "claude"
        shim.write_text("#!/bin/sh\n# qe: the vendor CLI writes to a home it resolves "
                        "itself. Answer 'not registered' and touch nothing.\nexit 1\n")
        shim.chmod(0o755)

        env = dict(os.environ)
        env["HOME"] = fake_home
        env["QE_PROJECT_TMP"] = proj
        env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"
        # An archive redirect pointing at the operator's real store would survive the
        # HOME move and is not part of what this probe is about.
        env.pop("THALAMUS_ARCHIVE_DIR", None)
        try:
            proc = subprocess.run(
                [sys.executable, "-c", _CHILD],
                capture_output=True, text=True, env=env, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            return f"the install probe did not finish within {timeout:g}s"
        if proc.returncode != 0 or not proc.stdout.strip():
            return (f"the install probe failed: rc={proc.returncode} "
                    f"stderr={proc.stderr.strip()[:400]}")
        try:
            data = json.loads(proc.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError as exc:
            return f"the install probe emitted no JSON object ({exc})"

        # CONTROL on the probe itself: the child must have believed the redirected HOME.
        # Without this, a child that fell back to the passwd database would report on the
        # operator's real home — which is both a false result and a live hazard.
        if Path(data["home"]).resolve() != Path(fake_home).resolve():
            return (f"the probe did not adopt the redirected HOME "
                    f"(child reported {data['home']}, expected {fake_home})")

        return Probe(
            home=data["home"], consent=data["consent"], named=data["named"],
            package_skills=tuple(data["package_skills"]),
            install_actions=tuple(data["install_actions"]),
            uninstall_actions=tuple(data["uninstall_actions"]),
            before=data["before"], after=data["after"], end=data["end"],
        )
