"""
Which roster the suite itself runs against.

Interfaces: tests/conftest.py's environment scrub, read back through
contract.manifest.
Infrastructure: none — this is a statement about the process running pytest.
Scope: one property, and it is about the suite rather than the product. Several
tests are parametrized over `available_scopes()`, so the *number of tests collected*
depends on which manifest directory `THALAMUS_CONFIG_DIR` names. Exported to a
private roster it was 1369; unexported, 1365 — and both runs printed a passing suite
with nothing saying the covered set differed. A contributor's green and the
operator's green have to be the same claim.
"""

import os
from pathlib import Path

from thalamus.contract import manifest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_the_suite_runs_against_the_manifests_this_repository_tracks():
    """Whatever the launching shell exported, collection reads `config/` here.

    The scrub is in conftest at import time rather than in an autouse fixture,
    because parametrization is evaluated during collection and no fixture has run
    yet. A test that wants a different roster still sets the variable in its own
    body — this fixes the floor, not the ceiling.
    """
    assert "THALAMUS_CONFIG_DIR" not in os.environ
    assert manifest.config_root() == REPO_ROOT / "config"


def test_the_tracked_manifests_are_the_ones_on_disk():
    """And the set is non-empty, so anything parametrized over it is not vacuous."""
    tracked = sorted(p.stem for p in (REPO_ROOT / "config" / "experts").glob("*.yaml"))

    assert tracked, "no expert manifests tracked — scope-parametrized tests collect nothing"
    assert manifest.available_scopes() == tracked
