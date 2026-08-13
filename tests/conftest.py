"""Suite-wide isolation from operator state.

A test that reads `~/.thalamus` is a test whose verdict depends on what the operator
did in the console this morning, and the failure it produces accuses the wrong code.
Anything under here exists because that already happened.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_launch_policy(tmp_path_factory, monkeypatch):
    """Point the launch-posture store at a tmp path for every test.

    `launch_argv` defaults its `selections` to the *stored* posture, read through the
    module-level `STORE`, so a test that calls it without passing selections is reading
    the operator's real choice. Measured 2026-08-13: with `cursor` set to `auto-review`
    in the console, three tests asserting Cursor launches with no permission flag failed
    on this box and passed on a clean one — the tests were right and their environment
    was not.

    Autouse rather than opt-in, because the tests that need it are exactly the ones
    whose authors did not know they were reading anything.
    """
    directory = tmp_path_factory.mktemp("launch-policy")
    monkeypatch.setattr("thalamus.harness.launch_policy.STORE",
                        directory / "policy.json")
    monkeypatch.setattr("thalamus.harness.launch_policy.LEDGER",
                        directory / "policy.jsonl")
