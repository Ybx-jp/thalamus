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

Every check names the issue whose defect it reproduces, so **a run that fails
nothing has not found a clean install — it has failed to observe.**
`spec.known_defect_issues()` says which issues are expected on the tree as it
stands, and `drive.py` exits 2 when none of them reproduce. That is the harness
reporting on itself, and it is not a pass.

```
0  every failing check named a filed issue, and at least one did
1  a check failed naming NO issue, or a step that may not fail did — a NEW defect
2  no known defect reproduced: they were fixed, or this cell cannot see them
3  MALFORMED — the oracle could not run, or a gate refused
```

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

`.github/workflows/qe-macos.yml` runs the `graph-not-started` cell on `macos-14`.
That is the only cell CI can host: Apple silicon runners have no nested
virtualization, so there is no Docker and no graph, and everything after
`docker compose up -d` lands as not evaluated with a reason. macOS cannot be a cell
in the libvirt matrix at all — it may only be virtualized on Apple hardware.

The Linux matrix covers the graph phases and the other five configs.
