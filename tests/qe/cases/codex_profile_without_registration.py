"""A codex profile written where `thalamus` is not registered carries no `thalamus` table.

The scope's generated profile adds `[mcp_servers.thalamus] env_vars = [...]` so the
registered server receives the pin (`codex_scope_not_forwarded`). A profile table with
no `command` of its own and nothing in `config.toml` to merge into is an MCP server with
no transport, and codex refuses to start on it ("invalid transport in
mcp_servers.thalamus") — for every launch that names the profile, with no session and no
charter. So `pin.write_codex_profile` writes the table only when `$CODEX_HOME/config.toml`
registers `thalamus` (`pin.codex_registers_thalamus`). This is the other half of that
change: a box that never ran `thalamus init`, or ran `init --uninstall`, must still get a
profile it can launch.

**Control.** The identical profile written into a `CODEX_HOME` whose `config.toml`
registers `thalamus` must carry the table. Without it a `write_codex_profile` that never
renders the table at all would pass this case, and the case would say nothing about the
condition it exists to pin.

**Hermetic.** A scratch `CODEX_HOME` and config root, `home=` passed explicitly, no
codex binary. The codex-side refusal is measured and pinned in the ledger (A0211); this
asserts only the file this repository controls.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Tier

_MANIFEST = "contract: v0\nscope: qe-probe\nname: probe\ndomain: probe\ntier: 2\n"
_TABLE = "[mcp_servers.thalamus]"
_REGISTERED = '[mcp_servers.thalamus]\ncommand = "/bin/true"\nargs = []\n'
_SITE = "src/thalamus/harness/pin.py::write_codex_profile"


def _profile(root: Path, home: Path, config_toml: str | None) -> str:
    from thalamus.contract.manifest import load_manifest
    from thalamus.harness import pin

    home.mkdir(parents=True, exist_ok=True)
    if config_toml is not None:
        (home / "config.toml").write_text(config_toml)
    path = pin.write_codex_profile(load_manifest("qe-probe", root), home=home, base=root)
    return path.read_text()


def run() -> Finding | None:
    with tempfile.TemporaryDirectory(prefix="qe-codex-profile-") as raw:
        tmp = Path(raw)
        root = tmp / "config"
        (root / "experts").mkdir(parents=True)
        (root / "experts" / "qe-probe.yaml").write_text(_MANIFEST)

        registered = _profile(root, tmp / "registered", _REGISTERED)
        if _TABLE not in registered:
            return Finding(
                FailureClass.COLLAPSED_SENTINEL,
                "the control profile, written where `thalamus` is registered, carries no "
                "`[mcp_servers.thalamus]` table, so a profile without one proves nothing "
                "about the registration condition",
                witness=registered[-400:],
                site="tests/qe/cases/codex_profile_without_registration.py")

        for label, config_toml in (("no config.toml", None),
                                   ("config.toml with no thalamus server",
                                    '[mcp_servers.other]\ncommand = "/bin/true"\n'),
                                   ("unparseable config.toml", "[mcp_servers\n")):
            bare = _profile(root, tmp / label.replace(" ", "-"), config_toml)
            if _TABLE in bare:
                return Finding(
                    FailureClass.FAILED_OPEN,
                    "a profile written where `thalamus` is not registered carries a "
                    "`[mcp_servers.thalamus]` table with no command to merge into, which "
                    "stops codex at startup for every launch naming the profile",
                    witness=f"{label}: profile contains {_TABLE!r}",
                    site=_SITE)
    return None


CASE = Case(
    name="codex-profile-without-registration-has-no-thalamus-table",
    tier=Tier.FAST,
    substrate=(),
    classes=(FailureClass.FAILED_OPEN, FailureClass.COLLAPSED_SENTINEL),
    summary="a codex profile written where thalamus is not registered must not carry an "
            "[mcp_servers.thalamus] table, which codex refuses to start on",
    run=run,
    issue=289,
    fixed=True,
)
