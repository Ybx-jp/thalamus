# Contributing

Thalamus is in active development. Issues and pull requests are welcome.

The agent-facing companion to this file is [CLAUDE.md](CLAUDE.md) — the same
conventions, written for a coding agent working in this repo. If you change a
convention, change both.

## Setup

```bash
git clone https://github.com/Ybx-jp/thalamus && cd thalamus
docker compose up -d          # the graph
uv sync --extra dev
uv run thalamus init          # only if you want the harness armed in your own editor
```

You do not need `thalamus init` to develop or run the tests. It wires hooks into your
editor at user scope; skip it if you only want to build and test.

`.python-version` pins CPython 3.12 for the checkout, and uv reads it, so every
worktree resolves the same interpreter without being told. The pin is load-bearing for
the `voice` extra: its `spacy` dependency publishes no wheel above 3.13, so
`uv sync --all-extras` fails outright on a newer one. It also keeps a measurement taken
in one worktree comparable to the same measurement in another.

The package itself supports Python >=3.11 (`requires-python`); the pin is this
checkout's development interpreter, not the range Thalamus installs into.

## Verification

```bash
uv run pytest                      # the suite must stay green
uv run ruff check src tests
uv run ty check src                # no diagnostics
uv run thalamus arch rules --gate  # dependencies against the declared layers
uv run thalamus arch scan --check  # the committed structural model must be current
uv run thalamus arch dead --gate   # definitions nothing outside tests/ refers to
uv run thalamus contract check     # after any change to a live write path
```

Every one of these runs in CI on each push (`.github/workflows/verify.yml`). Run them
before you push rather than after CI tells you.

The federation contract is enforced, not aspirational — `contract check` audits the
live graph, and a change to a write path that has not been checked against it is not
finished.

### Type checking is pinned

`ty` is pinned to an exact patch version in `pyproject.toml`, unlike every other
dependency here. It is pre-1.0 and its inference changes between releases, so a
floating spec turns a green tree red on someone else's schedule. Raise the pin
deliberately, in a change that also fixes whatever the new release reports.

### The structural gates, and the exception list

`arch rules --gate` checks measured dependencies against the layer rules declared in
`arch/model.yaml`, and `arch dead` looks for definitions under `src/` that nothing
outside `tests/` refers to. Both read their exceptions from the same place: an
`accepted` list in `arch/model.yaml` where every entry carries a required `reason`.

The exit codes are load-bearing and match `tests/qe/run.py`:

- **0** — clean, or exactly what `accepted` declares.
- **1** — a finding the model does not accept. Fix it, or add an entry saying why it
  stands.
- **2** — an `accepted` entry that no longer happens. Delete it.

Exit 2 is the half that keeps the list honest. An exception that stopped firing is not
a pass; left alone it goes on describing a design that has moved, and a list whose
entries nobody can justify removing is a list that only grows.

`arch scan --check` compares a fresh scan against the committed `arch/model.yaml`. When
it fails, run `thalamus arch scan --write` and commit the regenerated file with your
change — the model is a measurement of a specific tree, and one that lags the code
reports numbers for a tree that no longer exists.

### The console's JavaScript is tested

`tests/js/*.test.mjs` run under node, driven by `tests/test_console_js.py` as part of
the same pytest run. They lift functions out of `src/thalamus/console/static/app.js`
**by name**, so renaming one breaks extraction loudly. That is the intended failure,
not a flake — update the test alongside the rename.

node is optional; a checkout without it skips those tests rather than failing.

## Layout

```
src/thalamus/
  substrate/   storage kernel — schema, Gremlin writer, Gremlin reader, query span tap.
               Below the contract: knows nodes and edges, not experts or tiers
  contract/    the federation boundary — ontology, expert manifests, conformance
  console/     the browser control plane over the tmux roster
  archive/     immutable content-addressed store for retained evidence
  harness/     MCP server, hooks, skills, transcript bootstrap
  eval/        trace tap, attribution, cost — the live-serving half of the eval loop.
               The counterfactual harness (task battery, arms, oracle) is research
               instrumentation; it lives in the private thalamus-eval companion repo
  pulse/       live telemetry dashboard
config/        expert manifests
tests/         pytest suite, plus tests/js and tests/qe
```

The layering rule that matters: **`substrate/` sits below the contract.** It knows
nodes and edges. It does not know what an expert is, what a trust tier means, or which
scope may write what. If you find yourself importing `contract/` into `substrate/`,
the change belongs somewhere else.

### `tests/qe/` is owned by the `qe` scope

If you run an agent in this repo with the harness installed, a PreToolUse guard will
refuse its edits under `tests/qe/` unless the session is pinned to `qe`
(`thalamus pin qe`, or a `thalamus-qe` subagent). That tree holds the adversarial
suite, and `qe`'s own manifest denies it `src/` in return — a scope that can repair
the implementation it asserts against is not independent of it, and one that can
soften the assertion is not either.

Editing it yourself, by hand, is not blocked; the guard binds agents' file-editing
tools. If you are working with an agent, pin it rather than working around the guard.

### Skills

`.claude/skills/` contains two kinds of entry, and the difference is load-bearing:

- **Symlinks** into `src/thalamus/harness/skills/` — these ship inside the package and
  are installed at user scope by `thalamus init`. Editing through the symlink works,
  but `git add` on that path fails; stage the real path under `src/`.
- **Real directories** — project-scope skills for working *on* this repo. They arm
  only in this checkout and are not installed for users.

A skill is procedure and knowledge, nothing else. It is read in order to *do*
something, so a paragraph about what the procedure used to be is pure cost at the
moment of use. When you correct a skill, change the instruction and delete what it
replaced.

## Documentation

`docs/` is user-facing: [getting-started](docs/getting-started.md),
[concepts](docs/concepts.md), [cli](docs/cli.md). Design records and research live
outside this repo.

Two rules:

**Whenever a change alters behaviour a doc describes, update that doc in the same
change.** Not as a follow-up.

**Docs describe the current state only.** No changelog narration, no apologising for a
past design. History lives in git.

**Delete ghosts; do not annotate them.** A reference to something that no longer exists
gets removed where it stands, not labelled as gone. "This was removed in 0.2" is still
the dead name — it costs a reader context on every pass and tells them nothing that
naming the current state wouldn't. Rewrite the reference to what exists now, or cut the
sentence. This binds as you pass through a file for any reason: a stale name noticed
while doing something else is deleted in that change.

The exception is narrow: a hazard that still bites is knowledge, not history. "A
bare-port target 404s because serve strips the mount path" earns its place because a
reader acts on it. The test is whether someone needs it to act correctly *now*.

## Issues and pull requests

**Describe the change and its impact.** A commit message and a PR body are technical
records with an audience that did not sit through the work: what changed, what it
affects, what a reader has to do differently, what is still unbuilt.

They are not a narrative of how the work went, which argument won, or what the
evidence "does not support". Verdict framing is the tell — *the case was unbeaten*,
*this cuts against the proposal*, *reads backwards*. Cut it. Titles are descriptive,
not literary.

```
good:  Attribution judge tokenizes node terms and the output window differently
bad:   The judge that could not tell defense from refusal
```

This does not license omission, which is the opposite failure. Constraints,
counter-evidence, refused alternatives and known gaps stay in, stated as facts with
their numbers. "The write-back is not built; the result is conditional on it" is
exactly the sentence that belongs in a PR.

Suggested labels: `type:bug`, `type:feature`, `type:docs`, `type:chore`, plus one
`area:` label — `substrate`, `harness`, `console`, `eval`, `contract`, or `ingestion`.

### Commits

Commit by path. `git add -A` in a checkout that may have concurrent work sweeps
somebody else's half-finished file into your commit — check `git status` and name the
files you changed.

## Grounding new design

Two standing rules for anything new — a feature, a component, a schema change, an eval
metric:

1. **Never design from scratch when established research can give you a boost.**
2. **Never claim novelty where prior work exists.** Cite sources along the way.

A design that cites nothing has not been grounded; it has been guessed. Phrase novelty
claims as "not found in the current scan", never as a bare "novel".

## Security

The evidence archive holds retained session transcripts verbatim, and transcripts
contain whatever was on screen — credentials included. `bootstrap` scans for secrets
and **reports**; it never redacts, because evidence that has been quietly rewritten is
not evidence.

Never commit a graph export, a transcript, or an archive path. Both the graph and the
archive live outside the tree by construction, and `.gitignore` guards the paths
against a stray write.

The console binds `127.0.0.1` and carries no authentication. If you add a surface that
can bind elsewhere, it needs a warning at minimum and authentication before it is a
default.
