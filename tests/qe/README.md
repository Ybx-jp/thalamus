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
`*_test.py`**, or dev's in-loop suite inherits an intentionally red corpus. The case
`in-loop-suite-collects-nothing-from-this-tree` runs the collector and asserts it reaches
no node here, so the rule is checked on every push rather than by a reader who would have
to already know it exists.

**Not shipped**, because a released package carrying known-red entries would hand every
installer a working oracle for the defects in the release they just installed.

## `install/` — the whole-box tier

`tests/qe/install/` is a different shape of case and does not run under `run.py`. It
holds the documented first-run sequence as data, the oracle over it, and `drive.py`,
which runs both against a real box: clone, `uv sync`, `docker compose up -d`,
`thalamus init`, reinstall, move the checkout, serve the console, uninstall. Its own
README covers the gates and the exit codes.

Three things run it. `.github/workflows/qe-macos.yml` drives the `graph-not-started`
cell on a hosted macOS runner every push — real Darwin, never-seen-the-project, no
Docker and therefore no graph. `.github/workflows/qe-linux.yml` runs the other five
configs on `ubuntu-latest`, which ships Docker, so it is the only automated cell that
reaches the graph phases at all. The libvirt matrix in the operator's notes repo boots
Ubuntu cells on real VMs and reads the same `spec.py` and `checks.py` out of this tree.

The filename containment rule binds there too, and the `dev` extra does not: `spec.py`,
`checks.py` and `verdict.py` are stdlib-only on purpose, because they are copied into
boxes that have never seen this project.

## Known-red, and why it is not a mute button

`expectations.json` triages defects that are real and unfixed. A triaged case exits 0,
so the suite is usable as a gate for the *next* defect. Each entry pins the defect's
**current behavior positively** via `witness_contains` — an entry that merely said "this
fails" would absorb any future failure at the same site, which is the laundering channel
a plain quarantine opens. Change the defect and the entry drifts, and drift is red.

Delete an entry in the same change that fixes its defect. A stale entry exits 2.

**The list may shrink freely and may not grow unheard.** Adding an entry is what turns a
`NEW_FAILURE` into a `KNOWN_RED` and exit 1 into exit 0, so addition — not widening — is
the mute primitive, and widening a pin is a smaller helping of the same act. The case
`expectation-additions-are-never-silent` diffs this file against a base revision and goes
red on either, naming the entry. It verifies no approval and has no field that could
declare one: nothing this repo holds could attest an operator's approval to a hermetic
check, and a field an agent fills in for itself is a rubber stamp. What it buys is that an
addition costs a red run on the commit that introduces it. See docs/13, *The oracle's own
protection*, for what that does and does not cover.

## Adding a case

A case returns `None` to pass or a `Finding` to fail, and must not raise — a raised
exception is MALFORMED, which says the check is broken, not the code. Declare the
`FailureClass` values the case may emit; emitting one outside that set is MALFORMED,
because an expectation could not have anticipated it.

**A case that reproduces a filed defect names its issue**, with `issue=` and `fixed=` on
the `Case` — the same two fields, with the same meanings, as `install/spec.py::Check`. An
issue number tells a reader of a red run that the defect was already filed; `fixed=True`
withdraws that, and says the case is now the regression guard for a closed issue and is
expected to pass. `run.py` prints the tag beside the verdict and refuses two states: a
case `fixed` with no issue to withdraw, and a case `fixed` while an entry in
`expectations.json` still acknowledges its failure. Both are MALFORMED — a triaged red on
a closed defect is a regression nobody reads.

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

A case may also guard a surface that has not failed yet, and the install/uninstall pair
is why the distinction is worth stating: `9bcd7c7` gave the release a way back out of an
installer that writes to six places in `$HOME`, which is the sharpest edge a first-time
cloner meets and had no end-to-end check. Those cases descend from no record. They are
green, they were driven red against poisoned fixtures before being trusted, and their
docstrings say which mutation to repeat.
