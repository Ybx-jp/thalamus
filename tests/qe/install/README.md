# The install matrix — the sequence, the oracle, and a driver

Boots nothing. What is here is the part of the install matrix that is true of
**Thalamus** rather than of one machine: the documented first-run sequence, the
assertions over it, and a driver that runs both on whatever box it is executing on.

| File | Purpose |
|---|---|
| `spec.py` | The matrix as data: phases, steps, configs, checks, prerequisites, timeouts. Stdlib only, imports nothing from `thalamus`. |
| `checks.py` | The executable half of the oracle: how to find out whether each check held. Stdlib only; reaches the product by shelling `REPO/.venv/bin/python`. |
| `verdict.py` | Framing and the five outcomes a cell can come to. |
| `drive.py` | Runs the sequence on this box, snapshots at the phase boundaries, and judges the result. |
| `lint.py` | Guards on the spec. No box needed. |

The libvirt provisioner that boots Ubuntu cells — golden images, cloud-init seeds,
the `qe-cell` network, the isolation probe and its host addresses — is a property of
one machine and lives in the operator's notes repo. It reads `spec.py` and
`checks.py` from here and copies them into each guest verbatim.

## Why the split is here and not one file further left

`spec.py` was already written to be copied into a machine that has never seen the
project, so it could not import anything. That constraint is what makes the same
three files run on a GitHub macOS runner: `checks.py` reads nothing but
`$QE_ARTIFACTS`, `$QE_GUEST_HOME` and `$QE_REPO`, so "the guest" and "the runner"
are one idea on different hardware.

## Running a cell

```bash
python3 tests/qe/install/drive.py --config graph-not-started
python3 tests/qe/install/lint.py
```

`drive.py` runs against the checkout it is invoked from and the invoking user's home
by default, which on a developer box means **it will install into your home
directory and then uninstall from it**. Point it somewhere else to try it:

```bash
git clone . /tmp/cell/thalamus
python3 tests/qe/install/drive.py --config graph-not-started \
    --repo /tmp/cell/thalamus --home /tmp/cell/home --artifacts /tmp/cell/art
```

## Green is not the goal

Every check names the issue whose defect it reproduces, so **while a cell has
something to reproduce, a run that fails nothing has not found a clean install — it
has failed to observe.** `spec.expected_reproductions(config)` says what THIS cell is
built to reproduce, and `drive.py` exits 2 when none of them do. That is the harness
reporting on itself, and it is not a pass.

A cell whose expected set is empty makes the weaker claim instead — no new failure,
no regression — and says so on the way out at exit 0. It is not a fault, and neither
`drive.py` nor `lint.py` treats it as one; it is the state a repaired tree is in, and
the thing to do about it is tag the next filed defect, not keep one open.

```
0  every failing check named an unfixed filed issue, and at least one did
1  a check failed naming NO issue or a FIXED one, or a step that may not fail did
2  no known defect reproduced: they were fixed, or this cell cannot see them
3  MALFORMED — the oracle could not run, or a gate refused
```

### An issue tag expires

An issue number **absolves** a red result: it is the whole of what turns exit 1
into exit 0. So a tag left in place after the fix landed absolves forever, and the
site it names becomes the one place in the matrix where a regression cannot be
seen. **Set `fixed=True` on the `Check` and the `Config` in the same change that
closes the issue** — the same rule that deletes a known-red entry from
`expectations.json` when its defect is fixed. From then on the check is expected to
pass and a red one is reported as `REGRESSED` at exit 1.

Two ways in, and the second is why this is not paranoia. The defect comes back — or
the *oracle* drifts off the repaired behaviour and reports a working install as
broken. `moved-checkout-is-named-not-denied` did the second: it enumerated the
diagnosis wording #52 shipped with, the fix reworded that message, the check went
red on the fix, and its own tag kept the cell green. A check that reads a rendering
pins the shape of the **healthy** branch, which is stable, never the prose of the
unhealthy ones, which improves.

When every tagged defect is marked fixed, `known_defect_issues()` empties and
`lint.py` prints it as a `NOTE` at exit 0. It is not a lint failure: making it one
would leave two ways to a clean lint, closing the last defect or tagging one nobody
measured, and the second is a fabricated positive control. What `lint.py` does refuse
is a matrix where nothing is tagged at all, open or fixed — with no `fixed` tag either
there is no site at which a red result reads as a regression, and the run can only
report novel failures. Re-arm the control by tagging the next filed defect.

## The gates, and why a cell would rather abort than report

Three preconditions run before a single documented command, and each of them
refuses with `boundary-abort` rather than producing a result. A refusal is a
statement about the box; only a completed cell is a statement about the product.

- **Every command the sequence runs must exist.** A box without `docker`, asked for
  a config that does not skip the graph phases, would otherwise drop the step and
  report every graph check as SKIPPED — indistinguishable from evidence that went
  astray.
- **The documented prerequisites must be present**, or absent exactly because the
  config removes them. `jq` and `tmux` appear in no step's argv, so nothing in the
  sequence notices their absence; without `jq` the hook layer exits silently and the
  install does less than it says while reporting success.
- **The config's premise must hold.** `graph-not-started` does not mean "we skipped
  `docker compose up -d`", it means the sequence meets a box with no graph. Measured
  2026-08-21: run on a developer box with the operator's graph up, the cell reported
  issue #17 reproduced from a step that had nothing to diagnose.

`removes` is applied by renaming the binary and re-resolving until PATH stops
answering, because a `no-jq` cell that still finds `jq` in a second prefix passes
every check and proves nothing.

## What runs where

**Neither workflow names a config.** `configs_requiring_no_graph()` and
`configs_needing_a_graph()` partition `CONFIGS`, and the two workflows read their cells
out of them — `qe-linux.yml` builds its matrix from a `discover` job, `qe-macos.yml`
derives its single config and refuses if there is more than one. A hardcoded list would
be a second source of truth, and a config added to `spec.CONFIGS` would simply not run
with nothing to say so. `lint.py` refuses a config in neither partition or in both.

`.github/workflows/qe-macos.yml` runs the graphless config on `macos-14`. Apple silicon
runners have no nested virtualization, so there is no Docker and no graph, and
everything after `docker compose up -d` lands as not evaluated with a reason. That is
also the only hosted box a graphless config can run on, which is why that job is a
single cell and asserts it. macOS cannot be a cell in the libvirt matrix at all — it may
only be virtualized on Apple hardware.

`.github/workflows/qe-linux.yml` runs the graph-bearing configs on `ubuntu-latest`, one
job each, `fail-fast: false`. Hosted Linux runners ship Docker and Compose v2, so these
are the only automated cells that reach `GRAPH_STARTING` and `GRAPH_READY` — and
therefore the only ones that can evaluate `starting-graph-is-not-reported-as-absent`,
which samples the window between the port accepting a connection and the server
answering a query. On a box without Docker that snapshot is never taken and the check
reports `not_evaluated`.

`drive.py`'s `Perturbation` makes a binary absent by renaming it, which needs write
permission on the holding directory. A hosted runner does not have that on `/usr/bin`,
so `qe-linux.yml` relocates the binaries a config removes into `~/.local/bin` first,
reading the list from `spec.CONFIGS`. The end state is the one the config asks for — the
binary is off PATH once perturbed — but it is reached by moving the file rather than by
the box never having had it.

`no-config-dir` is weaker on a hosted runner than on the operator's box: it unsets
`THALAMUS_CONFIG_DIR`, which CI never set. The cell still confirms a clean clone
resolves its five tracked manifests, and the `scopes` snapshot's own control covers
whether an explicit override is read back.

The libvirt matrix in the operator's notes repo boots the same configs on real VMs from
golden images, which is the stronger claim — a hosted runner is a shared box with a
populated image, not a machine that has never seen a project.
