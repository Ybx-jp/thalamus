"""A manifest key the loader does not know must refuse the load, not vanish.

`ExpertManifest` declares no `model_config`, so pydantic's default applies and an
unknown top-level key is dropped without a word. The keys that matter most are the
boundaries, and every one of them has a safe-looking default: a missing
`write_boundary` is an empty one, a missing `budget` is `inherit`. So an operator who
writes `write_boundry:` — one letter off — gets a manifest that loads, generates its
persona, installs, and runs the scope with **no write boundary at all**, while the file
he reads says there is one. The live tier's `misspelled-boundary` config drives the same
manifest through a real session; this is the hermetic half.

The property: loading a manifest carrying an unknown top-level key raises. Checked on the
real loader (`contract.manifest.load_manifest`) against a config root written to a
temporary directory, never the operator's.

**Control.** The same manifest with the key spelled correctly must load with the deny
glob in place — otherwise a loader that could not read the temporary root at all (a
wrong `THALAMUS_CONFIG_DIR` seam, a changed filename rule) would raise for the wrong
reason and this case would pass on it.

**Shown capable of going red.** It is red on the tree as it stands. Add
`model_config = ConfigDict(extra="forbid")` to `ExpertManifest` and it goes green; the
control keeps passing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Tier

_BASE = ("contract: v0\nscope: {scope}\nname: probe\ndomain: probe\ntier: 2\n"
         "{key}:\n  deny_globs:\n    - \"*/src/*\"\n  reason: probe\n")


def _load(root: Path, scope: str, key: str):
    from thalamus.contract.manifest import load_manifest

    experts = root / "experts"
    experts.mkdir(parents=True, exist_ok=True)
    (experts / f"{scope}.yaml").write_text(_BASE.format(scope=scope, key=key))
    return load_manifest(scope, root)


def run() -> Finding | None:
    with tempfile.TemporaryDirectory(prefix="qe-manifest-") as tmp:
        root = Path(tmp)
        control = _load(root, "probe-good", "write_boundary")
        if control.write_boundary.deny_globs != ["*/src/*"]:
            return Finding(
                FailureClass.COLLAPSED_SENTINEL,
                "the correctly spelled control did not load its deny glob, so a refusal "
                "of the misspelled one would prove nothing",
                witness=repr(control.write_boundary),
                site="tests/qe/cases/manifest_unknown_key.py")
        try:
            loaded = _load(root, "probe-typo", "write_boundry")
        except Exception:  # noqa: BLE001 — any refusal is the property holding
            return None
    return Finding(
        FailureClass.FAILED_OPEN,
        "a manifest whose `write_boundary` key is misspelled loads without error and "
        "runs the scope with an empty write boundary",
        witness=f"write_boundry: deny */src/* -> write_boundary={loaded.write_boundary!r}",
        site="src/thalamus/contract/manifest.py (ExpertManifest has no extra='forbid')")


CASE = Case(
    name="manifest-unknown-key-refuses-the-load",
    tier=Tier.FAST,
    substrate=(),
    classes=(FailureClass.FAILED_OPEN, FailureClass.COLLAPSED_SENTINEL),
    summary="an unknown top-level manifest key must refuse the load, not drop silently",
    run=run,
    issue=294,
)
