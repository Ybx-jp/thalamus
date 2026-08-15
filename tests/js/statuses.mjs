// The harness session-status vocabulary, as the JS guards see it.
//
// This is `DELIVERABLE_STATUSES + (WAITING_STATUS,)` from
// src/thalamus/harness/dispatch.py. node cannot import Python, so the list is
// hardcoded here and the equality is asserted from the Python side:
// tests/test_console_js.py::test_status_vocabulary_is_pinned reads this array and
// fails if the two drift. Without that assertion a status added in Python would
// quietly widen the hole in the one-owner guard (tests/js/dialogue.test.mjs) —
// the guard would keep passing while no longer covering the new value.
//
// Not a `*.test.mjs`, so the pytest bridge does not try to run it as a suite.

export const HARNESS_STATUSES = ["idle", "busy", "waiting"];
