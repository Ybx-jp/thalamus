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

One cell's expected set may legitimately be empty. A config claims the defect its own
perturbation triggers, and a config whose tag is marked fixed claims nothing, so a
cell can have nothing of its own to reproduce while another cell still does. Those
cells make the weaker claim — no new failure, no regression at a repaired site — say
so on the way out, and exit 0.

The **matrix** having nothing to reproduce is a different condition, and `lint.py`
fails on it at exit 1. An empty `known_defect_issues()` means no cell anywhere is
built to reproduce anything, so no red result in the matrix can be read as a
reproduction and the harness has no positive control at all. It is not evidence that
the product is repaired; it means a defect was filed without its reproduction, or the
last tag was marked fixed without the next one being written.

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

Marking the last open tag fixed empties `known_defect_issues()`, and `lint.py` fails.
The way out is never a number in a field: a tag invented to satisfy a lint is a
fabricated positive control, which is the exact move this suite exists to catch. It
is the reproduction below.

## A filed defect arrives with its reproduction

Standing practice, and what keeps that gate satisfiable: **a defect this matrix can
trigger and observe is filed together with the cell that reproduces it, in the same
change.** The tracker then carries confirmed defects rather than asserted ones — an
issue with a red cell behind it has been shown happening on a box, not read off the
source — and the harness's positive control stays armed as a side effect rather than
as a chore. What is out of reach here goes to the tracker without a tag; what is
reachable and untagged is a reproduction someone has yet to write.

Four decisions, qe-side. The filing procedure itself is elsewhere — `CLAUDE.md`,
`CONTRIBUTING.md` and the `track-open-work` skill.

**Which phase.** A defect reachable from a command in `STEPS` pins its check to that
step's phase and runs in every cell. One that needs work the docs do not teach gets a
*synthesized* phase instead: `drive.py` runs it, `STEPS` does not carry it, and the
`doc` field is the reason — every step there is quoted to the file:line a user would
have read, and a command no documentation teaches has no such line to offer. `moved`,
`console` and `wheel` are all that shape. A check whose phase did not run in this cell
returns `skip()` with the reason, never a pass.

**Which cell.** `expected_reproductions()` reads a `Config`'s own tag to decide what
THIS cell must reproduce, so a defect that needs a perturbation — or a different
artifact, as `installed-wheel` does — gets a `Config` naming the same issue. A check
tagged with an issue no config claims is taken as reachable from the baseline sequence
and is expected everywhere. Either way the new config must land in exactly one of the
partitions the workflows fan out over — see *What runs where* — or nothing runs it.

**The control.** Mandatory wherever the check asserts something is missing, and it
must be an observation this run actually made — `ok()` refuses to build a pass out of
an empty control string. For #35 it is the checkout's own CLI answering the same
question, in the same phase, minutes apart on the same box: "the wheel cannot find its
hook scripts" and "this box renders no such line" are one reading otherwise, and the
second would go on reporting the defect after it was fixed.

**What `fixed` means later.** Nothing yet — leave it off. It is the flag the change
that *closes* the issue sets, on the check and the config together, and from then on
the site is expected to pass. See the section above for why that matters more than it
sounds.

Do not tag a defect you have not watched reproduce. A red cell is what makes the
number mean anything; without one the tag absolves a failure nobody has seen, which is
worse than an untagged gap.

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

`installed-wheel` is the only config that is not a perturbation of the box. It runs
the documented sequence like any other cell and then builds the wheel, installs it
into a venv of its own outside the checkout, and asks the packaged CLI the documented
pre-install question (`thalamus init --check`, getting-started:127) — which is the
whole sequence a user who did not clone has, milestone 0.1.1 being where the rest of
it is owed. It needs nothing from the workflow beyond what `uv sync` already needs: it
removes no binary, skips no phase, and builds with the `uv` the cell already has. The
venv it installs into goes in the cell's home (`spec.WHEEL_VENV_DIRNAME`) rather than
under `$QE_ARTIFACTS`, which is uploaded whole — the wheel is evidence, a hundred
megabytes of resolved dependency is not.

`no-config-dir` is weaker on a hosted runner than on the operator's box: it unsets
`THALAMUS_CONFIG_DIR`, which CI never set. The cell still confirms a clean clone
resolves its five tracked manifests, and the `scopes` snapshot's own control covers
whether an explicit override is read back.

The libvirt matrix in the operator's notes repo boots the same configs on real VMs from
golden images, which is the stronger claim — a hosted runner is a shared box with a
populated image, not a machine that has never seen a project.
