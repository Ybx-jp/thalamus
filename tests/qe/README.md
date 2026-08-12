# `qe` — the adversarial suite

Run it:

```bash
uv sync --extra dev                           # substrate, not convenience — see below
uv run python tests/qe/run.py --tier fast     # hermetic; what CI runs
uv run python tests/qe/run.py --all-tiers     # everything the box can support
```

The `dev` extra is a prerequisite of the fast tier. Three cases borrow probe helpers out
of dev's suite (`test_extraction._floor_graph`, `test_dispatch._descriptor`) rather than
reimplementing a SessionGraph or a dispatch descriptor that would drift from the real
one, and those modules import pytest at module scope. Without the extra the cases die on
import and report MALFORMED. `uv sync` alone does not supply it: pytest is declared in
the `dev` *extra*, and a bare sync installs only the `dev` dependency-group.

Not pytest, and not shipped in the wheel. Both on purpose.

**Not pytest**, because this suite carries
entries that are *supposed* to be red. `pyproject.toml` sets `testpaths = ["tests"]`,
so containment rests on filenames: **nothing in this tree may be named `test_*.py` or
`*_test.py`**, or dev's in-loop suite inherits an intentionally red corpus. Verify with
`uv run pytest --collect-only -q | grep -c tests/qe` — the answer must be 0.

**Not shipped**, because a released package carrying known-red entries would hand every
installer a working oracle for the defects in the release they just installed.

## Known-red, and why it is not a mute button

`expectations.json` triages defects that are real and unfixed. A triaged case exits 0,
so the suite is usable as a gate for the *next* defect. Each entry pins the defect's
**current behavior positively** via `witness_contains` — an entry that merely said "this
fails" would absorb any future failure at the same site, which is the laundering channel
a plain quarantine opens. Change the defect and the entry drifts, and drift is red.

Delete an entry in the same change that fixes its defect. A stale entry exits 2.

## Adding a case

A case returns `None` to pass or a `Finding` to fail, and must not raise — a raised
exception is MALFORMED, which says the check is broken, not the code. Declare the
`FailureClass` values the case may emit; emitting one outside that set is MALFORMED,
because an expectation could not have anticipated it.

**Every case that asserts an absence needs a positive control.** "Nothing was archived"
and "nothing ran" are the same output otherwise, and the second one passes forever.
Every case carries one, and building the guard control took four attempts — three
earlier versions demonstrated a fail-open using input the guard would never have blocked
anyway. That history is in `cases/guard_failopen.py`'s docstring because the next person
will reach for the same wrong controls.

**A green case must be shown capable of going red.** A case that guards a defect already
fixed proves nothing until its detector has been run against the defect as it shipped —
mutate the code or feed the detector a poisoned fixture, and watch it fail. Where the
mutation cannot live in the case, it belongs in the docstring so the next reader can
repeat it; where it can, it runs as the control (`cases/doc_mcp_snippet.py`).

## Where the cases come from

`findings/qe-corpus-draft.md` mines 152 defects that actually shipped and marks which
dev's suite already covers. Most cases here are drawn from its escaped and partial rows,
and those name their record in the docstring so a case and the defect it descends from
can be read together. The rest were found live, against the running system, and cite
what they were found by instead.
