"""codex's `thalamus` MCP server does not receive `THALAMUS_SCOPE` (#289).

codex starts a stdio MCP server with a fixed set of parent env vars plus the server's
own `env` table plus any name the server's `mcp_servers.<id>.env_vars` whitelists.
`register_codex_mcp` (`harness/install.py`) registers the `thalamus` server through
`codex mcp add --env THALAMUS_GRAPH_URL=<url>` and sets no `env_vars`, so
`THALAMUS_SCOPE` — set on the parent `codex` process by a pin — is never on the
whitelist and never reaches the server. `mcp_server.SCOPE = resolve_pin()` then finds
no `CLAUDE_CODE_AGENT` and no `THALAMUS_SCOPE` in its own environment and resolves
`main`. A codex session pinned to an expert distills into that scope (the pin's own
`session-start.sh` hook does see the launch environment) while its memory tools serve
and record recall as `main`.

**No credentials, no model spend.** codex starts the MCP server before it makes any
model request, so the server's environment is observable from a `CODEX_HOME` with no
`auth.json` at all. This case never authenticates and never completes a turn: it
overrides `mcp_servers.thalamus.command`/`.args` to point at a two-line script that
dumps its own environment to a file and exits, then kills the `codex exec` process the
moment that file appears (measured: ~0.3-0.5s after launch, well before the first
model request is attempted) rather than waiting out `codex exec`'s own exit, which — on
a `CODEX_HOME` with no credentials — is a multi-round 401/reconnect loop that outlives
any timeout worth blocking a suite on.

**Registered the way thalamus does, not hand-built.** The scratch `CODEX_HOME` is
populated by calling `install.register_codex_mcp()` itself, in a subprocess with
`CODEX_HOME` set before import — `install.py` reads `CODEX_HOME` from the environment
at import time (`install.py:106`), so an in-process call after this module's own import
would still see whatever `CODEX_HOME` this session started under. Only the server's
`command`/`args` are overridden afterwards, via `-c` dotted overrides on `codex exec`'s
own argv; the registered `env` table (`THALAMUS_GRAPH_URL`) is left standing, and
its survival into the dump is the check that the override merged into the registered
table rather than replacing it outright.

**Positive control.** The identical launch, with one addition —
`-c 'mcp_servers.thalamus.env_vars=["THALAMUS_SCOPE"]'` — must deliver
`THALAMUS_SCOPE=qe` into the same dump. Without this, "THALAMUS_SCOPE absent" cannot be
told apart from "this probe cannot see any parent env var at all"; the control shows the
probe can see the variable the moment codex is told to whitelist it, which is exactly
the fix this issue's "Open decision" is choosing between (a profile layer or a `-c`
override adding `env_vars` to the registration `register_codex_mcp` builds).

**Shown capable of going red, because it already is one.** This is a first-appearance
case for an open, unfixed issue (#289) — it is not driven against a synthetic mutation
because the shipped defect is standing right here. `witness_contains` in
`expectations.json` pins the dumped variable set as it reads today; the entry is
deleted in the same change that adds `env_vars` to `register_codex_mcp`'s registration,
and this case becomes that fix's regression guard.
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

_REGISTER_CHILD = """
from thalamus.harness import install
print(install.register_codex_mcp())
"""

_SITE = "src/thalamus/harness/install.py::register_codex_mcp"


def _register(codex_home: Path) -> str | None:
    """Register the `thalamus` server the way `thalamus init` does.

    A subprocess, not an in-process call: `install.CODEX_HOME` is resolved from
    `os.environ` at import time, and this module's own import (however this process
    got here) may have already happened under a different one. Returns None on
    success, or a string describing why registration could not be trusted — a probe
    failure, not a finding about codex.
    """
    env = dict(os.environ)
    env["CODEX_HOME"] = str(codex_home)
    env.pop("THALAMUS_GRAPH_URL", None)  # deterministic: exercise register's own default
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _REGISTER_CHILD],
            capture_output=True, text=True, env=env, timeout=60, check=False,
        )
    except subprocess.TimeoutExpired:
        return "register_codex_mcp() did not return within 60s"
    out = f"{proc.stdout}{proc.stderr}"
    if proc.returncode != 0 or "registered `thalamus`" not in out:
        return f"register_codex_mcp() did not report success: rc={proc.returncode} out={out.strip()[:300]}"
    return None


def _dump_env(
    codex_home: Path, cwd: Path, script: Path, outfile: Path, extra_config: tuple[str, ...],
    wait_s: float = 20.0,
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
    env = dict(os.environ)
    env["CODEX_HOME"] = str(codex_home)
    env["THALAMUS_SCOPE"] = "qe"
    env["THALAMUS_SANDBOX"] = "1"
    argv = [
        "codex", "exec", "--skip-git-repo-check",
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
        script = tmp / "dump.sh"
        script.write_text(_DUMP_SCRIPT)
        script.chmod(0o755)

        reg_error = _register(codex_home)
        if reg_error is not None:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="register_codex_mcp() could not be trusted to have registered "
                        "the server in the scratch CODEX_HOME, so a clean or a failing "
                        "dump below would mean nothing",
                witness=reg_error,
                site=_SITE,
            )

        # CONTROL, run first: the identical launch, with `env_vars` naming
        # THALAMUS_SCOPE, must deliver it. If it does not, this probe cannot see any
        # parent env var at all and a clean primary run proves nothing.
        control = _dump_env(
            codex_home, cwd, script, tmp / "control.env",
            extra_config=("-c", 'mcp_servers.thalamus.env_vars=["THALAMUS_SCOPE"]'),
        )
        if isinstance(control, str):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the positive control (env_vars=[\"THALAMUS_SCOPE\"]) never "
                        "produced an env dump, so the probe's ability to see a parent "
                        "env var at all is unverified",
                witness=control,
                site="tests/qe/cases/codex_scope_not_forwarded.py::_dump_env",
            )
        if control.get("THALAMUS_SCOPE") != "qe":
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the positive control did not deliver THALAMUS_SCOPE=qe even "
                        "with env_vars naming it explicitly, so a primary run that "
                        "lacks it proves nothing about codex's default whitelist",
                witness=f"control dump keys: {sorted(control)}",
                site="tests/qe/cases/codex_scope_not_forwarded.py::_dump_env",
            )

        primary = _dump_env(
            codex_home, cwd, script, tmp / "primary.env", extra_config=(),
        )
        if isinstance(primary, str):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the primary run (registered exactly as `thalamus init` "
                        "leaves it, no env_vars) never produced an env dump",
                witness=primary,
                site="tests/qe/cases/codex_scope_not_forwarded.py::_dump_env",
            )
        if "THALAMUS_GRAPH_URL" not in primary:
            # The registered `env` table must have survived the `-c` override that
            # replaced only `command`/`args` — otherwise this run says nothing about
            # env_vars at all, because the server never saw the registration built by
            # register_codex_mcp() in the first place.
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the primary run's dump carries no THALAMUS_GRAPH_URL, so the "
                        "`-c` override did not merge into the registered "
                        "`[mcp_servers.thalamus]` table the way #289's recipe measured "
                        "— this run is not exercising the shipped registration",
                witness=f"primary dump keys: {sorted(primary)}",
                site="tests/qe/cases/codex_scope_not_forwarded.py::_dump_env",
            )

        if primary.get("THALAMUS_SCOPE") == "qe":
            return None

        return Finding(
            failure_class=FailureClass.UNENFORCED_SIGNAL,
            summary="THALAMUS_SCOPE=qe was set on the parent `codex exec` process but "
                    "never reached the `thalamus` MCP server's environment — "
                    "register_codex_mcp() registers no `env_vars` whitelist entry for "
                    "it, so mcp_server.SCOPE resolves to `main` for a codex session "
                    "pinned to any expert (#289)",
            witness=f"primary dump keys: {sorted(primary)} "
                    f"(THALAMUS_SCOPE={primary.get('THALAMUS_SCOPE')!r}); "
                    f"control (env_vars whitelisted) delivered "
                    f"THALAMUS_SCOPE={control.get('THALAMUS_SCOPE')!r}",
            site=_SITE,
        )


CASE = Case(
    name="codex-mcp-server-does-not-receive-thalamus-scope",
    tier=Tier.DEEP,
    substrate=(Substrate.NEEDS_CODEX,),
    classes=(FailureClass.UNENFORCED_SIGNAL, FailureClass.COLLAPSED_SENTINEL),
    summary="a THALAMUS_SCOPE pin on the parent codex process must reach the thalamus "
            "MCP server's own environment",
    run=run,
    issue=289,
)
