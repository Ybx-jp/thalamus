"""A pinned codex session's `thalamus` MCP server receives the pin (#289).

codex starts a stdio MCP server with a fixed set of parent env vars plus the server's
own `env` table plus any name the server's `mcp_servers.<id>.env_vars` whitelists.
`register_codex_mcp` (`harness/install.py`) registers the `thalamus` server through
`codex mcp add --env THALAMUS_GRAPH_URL=<url>` and sets no `env_vars` (`codex mcp add`
has no flag for it, and `config.toml` is codex's file). The scope's generated profile
carries the whitelist instead: `pin.write_codex_profile` adds `[mcp_servers.thalamus]
env_vars = [...]` (`pin.CODEX_MCP_FORWARDED_ENV`) when `config.toml` registers
`thalamus`, and codex merges a profile's table into the registered one key by key. A
pinned session is launched `THALAMUS_SCOPE=<scope> codex --profile thalamus-<scope>`,
so the server then finds the pin in its own environment. Without it
`mcp_server.SCOPE = resolve_pin()` resolves `main` and a codex session pinned to an
expert serves and records recall as `main` while distilling into the expert's scope.

**The launch shape is the property.** The scratch `CODEX_HOME` is populated by
`install.register_codex_mcp()` itself, the scope's profile is written by
`pin.write_codex_profile(load_manifest(...))` into the same home, and the probe launches
`codex exec --profile thalamus-<scope>` with the pin in the parent environment. Both
run in a subprocess with `CODEX_HOME` set before import — `install.py` reads it from the
environment at import time, so an in-process call would still see whatever `CODEX_HOME`
this session started under.

**No credentials, no model spend.** codex starts the MCP server before it makes any
model request, so the server's environment is observable from a `CODEX_HOME` with no
`auth.json`. The probe overrides `mcp_servers.thalamus.command`/`.args` (via `-c`, which
merges into the registered and profile tables) to point at a two-line script that dumps
its own environment to a file and exits, then kills `codex exec` the moment that file
appears rather than waiting out its 401/reconnect loop.

**Controls.** Three arms, each differing from the primary in one variable:

- `env_vars=["THALAMUS_SCOPE"]` passed by `-c`, no profile: the probe can see a parent
  variable the moment codex is told to whitelist it. Without it "absent" cannot be told
  from "this probe sees no parent variable at all".
- no `--profile` (the registration alone, the shape before the profile carried the
  list): must still show no `THALAMUS_SCOPE`. If it shows one, something other than the
  profile forwards it and the primary arm proves nothing about the profile.
- the primary arm must also carry the registered `THALAMUS_GRAPH_URL`: the profile
  layer merged into the registration rather than replacing it, and the server this arm
  measured is the one `register_codex_mcp` built.

The five forwarded names are set to distinct values in the parent environment, and the
primary arm must deliver each of them unchanged.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_DUMP_SCRIPT = '#!/bin/sh\nenv | sort > "$1"\nexit 1\n'

_SCOPE = "qe-probe"
_MANIFEST = ("contract: v0\nscope: qe-probe\nname: probe\ndomain: probe\ntier: 2\n")

#: The parent-environment values a pinned launch carries, one per name in
#: `pin.CODEX_MCP_FORWARDED_ENV`. Distinct, so a delivered value is attributable.
_PIN_ENV = {
    "THALAMUS_SCOPE": _SCOPE,
    "THALAMUS_ROOM": "qe-probe-room",
    "THALAMUS_FORKED_FROM": "qe-probe-parent",
}

_REGISTER_CHILD = """
from thalamus.harness import install
print(install.register_codex_mcp())
"""

_PROFILE_CHILD = """
import sys
from pathlib import Path
from thalamus.contract.manifest import load_manifest
from thalamus.harness import pin
scope, root, home = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
print(pin.write_codex_profile(load_manifest(scope, root), home=home, base=root))
"""

_SITE = "src/thalamus/harness/pin.py::write_codex_profile"
_SELF = "tests/qe/cases/codex_scope_not_forwarded.py"


def _child_env(codex_home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("THALAMUS_")}
    env["CODEX_HOME"] = str(codex_home)
    return env


def _run_child(code: str, codex_home: Path, *args: str) -> str | None:
    """Run a snippet under `CODEX_HOME=<scratch>`; None on success, else why not.

    A subprocess, not an in-process call: `install.CODEX_HOME` is resolved from
    `os.environ` at import time, and this module's own import (however this process
    got here) may have already happened under a different one. A failure is a probe
    failure, not a finding about codex.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code, *args],
            capture_output=True, text=True, env=_child_env(codex_home), timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "child did not return within 60s"
    if proc.returncode != 0:
        return f"rc={proc.returncode} out={(proc.stdout + proc.stderr).strip()[-300:]}"
    return None


def _register(codex_home: Path) -> str | None:
    """Register the `thalamus` server the way `thalamus init` does."""
    return _run_child(_REGISTER_CHILD, codex_home)


def _write_profile(codex_home: Path, root: Path) -> str | None:
    """Write the scope's derived profile into the scratch home, as `thalamus pin` does."""
    experts = root / "experts"
    experts.mkdir(parents=True, exist_ok=True)
    (experts / f"{_SCOPE}.yaml").write_text(_MANIFEST)
    return _run_child(_PROFILE_CHILD, codex_home, _SCOPE, str(root), str(codex_home))


def _dump_env(
    codex_home: Path, cwd: Path, script: Path, outfile: Path, extra_config: tuple[str, ...],
    pin_env: dict[str, str], profile: bool, wait_s: float = 20.0,
) -> dict[str, str] | str:
    """Launch `codex exec` against the scratch home, kill it the instant the server's
    env dump appears, and return the parsed dump — or a string naming why none arrived.

    Polled rather than waited out: `codex exec` on a `CODEX_HOME` with no credentials
    keeps running through a 401/reconnect loop long after the MCP server (and its env
    dump) is long since written, and waiting for the process's own exit would make
    every run of this case pay for that loop.
    """
    if outfile.exists():
        outfile.unlink()
    env = _child_env(codex_home)
    env.update(pin_env)
    env["THALAMUS_SANDBOX"] = "1"
    argv = ["codex", "exec", "--skip-git-repo-check"]
    if profile:
        argv += ["--profile", f"thalamus-{_SCOPE}"]
    argv += [
        "-c", f'mcp_servers.thalamus.command="{script}"',
        "-c", f'mcp_servers.thalamus.args=["{outfile}"]',
        *extra_config,
        "say ok",
    ]
    log = cwd / "codex.log"
    with open(log, "wb") as logf:
        proc = subprocess.Popen(
            argv, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
            env=env,
        )
    try:
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline and not outfile.exists():
            time.sleep(0.1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    if not outfile.exists():
        detail = log.read_text(errors="replace")[-500:] if log.exists() else ""
        return f"no env dump appeared within {wait_s:g}s; last codex output: {detail}"

    dumped: dict[str, str] = {}
    for line in outfile.read_text(errors="replace").splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            dumped[k] = v
    return dumped


def run() -> Finding | None:
    with tempfile.TemporaryDirectory(prefix="qe-codex-scope-") as raw:
        tmp = Path(raw)
        codex_home = tmp / "codex_home"
        codex_home.mkdir()
        cwd = tmp / "cwd"
        cwd.mkdir()
        root = tmp / "config"
        script = tmp / "dump.sh"
        script.write_text(_DUMP_SCRIPT)
        script.chmod(0o755)
        pin_env = {
            **_PIN_ENV,
            "THALAMUS_CONFIG_DIR": str(root),
            "THALAMUS_ARCHIVE_DIR": str(tmp / "archive"),
        }

        reg_error = _register(codex_home)
        if reg_error is not None:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="register_codex_mcp() could not be trusted to have registered the server "
                "in the scratch CODEX_HOME, so a clean or a failing dump below would "
                "mean nothing",
                witness=reg_error,
                site=_SELF,
            )
        profile_error = _write_profile(codex_home, root)
        if profile_error is not None:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="pin.write_codex_profile() could not be trusted to have written the "
                "scope's profile into the scratch CODEX_HOME, so a dump from "
                "`--profile` would mean nothing",
                witness=profile_error,
                site=_SELF,
            )

        # CONTROL 1, run first: no profile, `env_vars` naming THALAMUS_SCOPE by `-c`,
        # must deliver it. If it does not, this probe cannot see any parent env var
        # at all and a clean primary run proves nothing.
        control = _dump_env(
            codex_home, cwd, script, tmp / "control.env",
            extra_config=("-c", 'mcp_servers.thalamus.env_vars=["THALAMUS_SCOPE"]'),
            pin_env=pin_env, profile=False,
        )
        if isinstance(control, str):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the positive control (env_vars=[\"THALAMUS_SCOPE\"], no profile) never "
                "produced an env dump, so the probe's ability to see a parent env var "
                "at all is unverified",
                witness=control,
                site=_SELF,
            )
        if control.get("THALAMUS_SCOPE") != _SCOPE:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the positive control did not deliver THALAMUS_SCOPE even with env_vars "
                "naming it explicitly, so a primary run that lacks it proves nothing "
                "about codex's default whitelist",
                witness=f"control dump keys: {sorted(control)}",
                site=_SELF,
            )

        # CONTROL 2: the registration alone, no `--profile`. The variable that differs
        # from the primary is the profile, so this must still not carry the pin.
        bare = _dump_env(
            codex_home, cwd, script, tmp / "bare.env", extra_config=(),
            pin_env=pin_env, profile=False,
        )
        if isinstance(bare, str):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the no-profile arm (the registration as `thalamus init` leaves it) "
                "never produced an env dump",
                witness=bare,
                site=_SELF,
            )
        if "THALAMUS_GRAPH_URL" not in bare:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the no-profile arm's dump carries no THALAMUS_GRAPH_URL, so the `-c` "
                "override did not merge into the registered `[mcp_servers.thalamus]` "
                "table — this run is not exercising the shipped registration",
                witness=f"no-profile dump keys: {sorted(bare)}",
                site=_SELF,
            )
        if "THALAMUS_SCOPE" in bare:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the no-profile arm delivered THALAMUS_SCOPE with no env_vars anywhere, "
                "so something other than the profile forwards it and a profile arm "
                "carrying it proves nothing about the profile",
                witness=f"no-profile THALAMUS_SCOPE={bare.get('THALAMUS_SCOPE')!r}",
                site=_SELF,
            )

        primary = _dump_env(
            codex_home, cwd, script, tmp / "primary.env", extra_config=(),
            pin_env=pin_env, profile=True,
        )
        if isinstance(primary, str):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the primary run (`--profile thalamus-<scope>`, registered as "
                "`thalamus init` leaves it) never produced an env dump",
                witness=primary,
                site=_SELF,
            )
        if "THALAMUS_GRAPH_URL" not in primary:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the primary run's dump carries no THALAMUS_GRAPH_URL, so the profile "
                "layer replaced the registered `[mcp_servers.thalamus]` table instead "
                "of merging into it — this is not the shipped registration's server",
                witness=f"primary dump keys: {sorted(primary)}",
                site=_SELF,
            )

        wrong = {
            name: primary.get(name) for name, want in pin_env.items()
            if primary.get(name) != want
        }
        if not wrong:
            return None

        return Finding(
            failure_class=FailureClass.UNENFORCED_SIGNAL,
            summary="a pin set on the parent `codex exec --profile thalamus-<scope>` "
                    "process did not reach the `thalamus` MCP server's environment, so "
                    "mcp_server.SCOPE resolves to `main` for a codex session pinned to "
                    "any expert (#289)",
            witness=f"primary dump did not deliver {wrong} (wanted {pin_env}); "
                    f"dump keys: {sorted(primary)}; no-profile arm "
                    f"THALAMUS_SCOPE={bare.get('THALAMUS_SCOPE')!r}; control "
                    f"(env_vars whitelisted) delivered "
                    f"THALAMUS_SCOPE={control.get('THALAMUS_SCOPE')!r}",
            site=_SITE,
        )


CASE = Case(
    name="codex-mcp-server-does-not-receive-thalamus-scope",
    tier=Tier.DEEP,
    substrate=(Substrate.NEEDS_CODEX,),
    classes=(FailureClass.UNENFORCED_SIGNAL, FailureClass.COLLAPSED_SENTINEL),
    summary="a THALAMUS_SCOPE pin on the parent codex process must reach the thalamus "
            "MCP server's own environment through the scope's profile",
    run=run,
    issue=289,
    fixed=True,
)
