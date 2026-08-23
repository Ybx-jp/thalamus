"""Suite-wide isolation from operator state.

A test that reads `~/.thalamus` is a test whose verdict depends on what the operator
did in the console this morning, and the failure it produces accuses the wrong code.
Anything under here exists because that already happened.
"""

from __future__ import annotations

import os

import pytest

# Scrubbed at *import* rather than in the autouse fixture below, because the thing it
# changes is collection, not execution. `THALAMUS_CONFIG_DIR` moves `manifest.config_root`
# off `config/` in this checkout and onto whatever roster the operator's shell points
# at, and `test_role_guard.py` parametrizes its capability-boundary guard over
# `available_scopes()` — which is evaluated while the module is imported, before any
# fixture runs. Exported, the suite collected 1369 tests against 9 private manifests;
# unexported, 1365 against the 5 tracked here, and nothing said which run had happened.
#
# The tracked manifests win. A suite whose size depends on a private repository reports
# on the operator's box rather than on this one, and a contributor's green run and his
# are then not the same claim. A test that wants a different roster sets the variable in
# its own body, which still works — this clears the floor, it does not hold it down.
os.environ.pop("THALAMUS_CONFIG_DIR", None)


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


@pytest.fixture(autouse=True)
def _isolate_extractor_policy(tmp_path_factory, monkeypatch):
    """Point the extractor store at a tmp path for every test.

    Same defect as the posture store above, one command along: `_cmd_extract` and
    `_cmd_ingest` resolve which CLI runs the pass through the module-level `STORE`, so a
    test that builds an args namespace and calls either reads whichever extractor the
    operator picked in the console. It decides the harness, the model and a printed
    line, and none of the tests that go through those paths passed a store or knew they
    were reading one.
    """
    directory = tmp_path_factory.mktemp("extractor-policy")
    monkeypatch.setattr("thalamus.harness.extractor_policy.STORE",
                        directory / "policy.json")
    monkeypatch.setattr("thalamus.harness.extractor_policy.LEDGER",
                        directory / "policy.jsonl")


# The variables that describe *the session running pytest* rather than anything under
# test. `resolve_room` and `resolve_pin` are env-first by design — inside a session
# that is the right answer and there is no second channel to disagree with — so a test
# that does not pass them explicitly reads whichever shell the suite was launched from.
SESSION_ENV = ("THALAMUS_ROOM", "THALAMUS_SCOPE")


@pytest.fixture(autouse=True)
def _isolate_session_env(monkeypatch):
    """Unset the launching session's own room and scope for every test.

    Measured 2026-08-15: run from inside room `d4v2`, 15 dispatch tests fail and the
    same suite is green from a plain shell. `dispatch.authenticate` refuses a caller
    that is in a different room than the one it addresses, and reads the caller's room
    from `THALAMUS_ROOM` — so a suite run by a room member has that member's identity
    silently substituted for the caller each test meant to describe. The verdict
    tracked the operator's shell, and the failure accused the code.

    Autouse and suite-wide rather than per-test, for the same reason as the launch
    posture above: the tests affected are exactly the ones whose authors did not know
    they were reading anything. A test that wants a room sets it in its own body, which
    still wins — this clears the floor, it does not hold it down.

    This scrubs the *reader's* environment; it does not make an env-first read correct
    in production. A long-lived process that never says which room it is in adopts the
    one it was launched in and holds it for life, and no scrub here would show that —
    see `test_the_dispatch_endpoint_declares_its_roomlessness_to_the_real_signature`,
    which asserts against the real signature and so does not depend on this fixture.
    """
    for name in SESSION_ENV:
        monkeypatch.delenv(name, raising=False)
