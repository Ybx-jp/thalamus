"""HOME redirection must actually redirect every path this package derives from home.

Unlike its neighbours, this case is expected to PASS, and it is here because the deep
tier's entire safety story rests on the property it asserts. Thirty-three module-level
constants across `pin.py`, `ceremonies.py`, `eval/rooms.py`, `archive/store.py` and
others are built from `Path.home()` at *import* time. A deep-tier case that spawns real
sessions is safe only if setting `HOME` in a child process moves all of them; a single
constant that escapes would write into the operator's live state during a test run,
which is the one failure this suite must never itself cause.

So it is a guard on the premise rather than a hunt for a defect: green today, and red
the moment someone introduces a path that bypasses `HOME` — a literal `/home/...`, an
XDG variable read at import, a `pwd.getpwuid` lookup.

**Why it sets HOME rather than clearing it.** `env -u HOME` does not unset the home
directory: with `HOME` absent from the environment, `Path.home()` still resolves through
the passwd database and returns the operator's real home. A runner that builds a
deliberately minimal `env={...}` therefore writes to real state *while looking isolated*.
That is a hazard in POSIX rather than a defect in this repo — nothing here can fix it —
so it is recorded here, next to the mechanism it would defeat, instead of being asserted
as a failure that could never go green.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

# Modules whose import-time constants must follow HOME. Named explicitly rather than
# discovered, because a discovery pass that silently found zero modules would report
# perfect isolation.
_PROBE = r"""
import json, pathlib, importlib
mods = ["thalamus.harness.pin", "thalamus.harness.ceremonies", "thalamus.harness.rescope",
        "thalamus.harness.quick", "thalamus.eval.rooms", "thalamus.eval.conditioning",
        "thalamus.eval.traces", "thalamus.archive.store"]
found = {}
for name in mods:
    try:
        mod = importlib.import_module(name)
    except Exception as exc:
        found[name] = f"IMPORT-FAILED: {type(exc).__name__}"
        continue
    for attr in dir(mod):
        if attr.startswith("__"):
            continue
        value = getattr(mod, attr, None)
        if isinstance(value, pathlib.Path):
            found[f"{name}.{attr}"] = str(value)
print(json.dumps({"home": str(pathlib.Path.home()), "paths": found}))
"""


def run() -> Finding | None:
    with tempfile.TemporaryDirectory() as fake_home:
        env = dict(os.environ)
        env["HOME"] = fake_home
        env.pop("THALAMUS_ARCHIVE_DIR", None)  # would mask the archive constant
        proc = subprocess.run(
            [sys.executable, "-c", _PROBE],
            capture_output=True, text=True, env=env, timeout=120, check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the probe subprocess failed, so 'nothing escaped' and 'nothing "
                        "was checked' are the same result",
                witness=f"rc={proc.returncode} stderr={proc.stderr.strip()[:300]}",
                site="tests/qe/cases/home_isolation.py",
            )

        data = json.loads(proc.stdout.strip().splitlines()[-1])
        reported_home = data["home"]
        paths = data["paths"]

        # CONTROL: the child must have believed the fake home. Without this, every path
        # would sit under the real home for a reason unrelated to any escape.
        if Path(reported_home).resolve() != Path(fake_home).resolve():
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="control failed: the probe did not adopt the redirected HOME, so "
                        "no conclusion about escaping constants is available",
                witness=f"probe Path.home()={reported_home} expected={fake_home}",
                site="tests/qe/cases/home_isolation.py",
            )

        import_failures = {k: v for k, v in paths.items() if str(v).startswith("IMPORT-FAILED")}
        if import_failures:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="a probed module failed to import, so its constants were never "
                        "examined and coverage here is smaller than it appears",
                witness="; ".join(f"{k}={v}" for k, v in import_failures.items()),
                site="tests/qe/cases/home_isolation.py::_PROBE",
            )

        # A path escapes only if it sits under the real home AND is not the checkout.
        #
        # The naive filter — "starts with the real home" — is wrong, and the first
        # version of this case used it and reported `pin.PROJECT_ROOT` as an escape.
        # PROJECT_ROOT is derived from `__file__`, so it names the repository, which on
        # this box merely happens to live under /home/ybx. It is *supposed* to point at
        # the checkout and following HOME would be the bug.
        #
        # PROJECT_ROOT is still an isolation concern for a different reason — `install()`
        # strips PROJECT_SETTINGS from it (`install.py:967`), so arming hooks dirties the
        # operator's checkout — but that is a write-target problem, not a HOME-redirection
        # failure, and asserting it here would make this case red for a reason its own
        # summary does not describe.
        real_home = Path.home().resolve()
        repo = Path(__file__).resolve().parents[3]
        escaped = sorted(
            f"{name}={value}" for name, value in paths.items()
            if Path(value).resolve().is_relative_to(real_home)
            and not Path(value).resolve().is_relative_to(repo)
        )

    if not escaped:
        return None

    return Finding(
        failure_class=FailureClass.BOUNDARY_LEAK,
        summary=(
            "a module-level path constant did not follow a redirected HOME, so a "
            "deep-tier case would write into the operator's live state while appearing "
            "isolated"
        ),
        witness="; ".join(escaped),
        site="src/thalamus/** (import-time Path.home() constants)",
    )


CASE = Case(
    name="home-redirection-moves-every-path",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="HOME redirection must move every import-time path constant (deep tier rests on it)",
    run=run,
)
