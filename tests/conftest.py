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
