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

## Verification

```bash
uv run pytest                 # the suite must stay green
uv run ruff check src tests
uv run thalamus contract check   # after any change to a live write path
```

The federation contract is enforced, not aspirational — `contract check` audits the
live graph, and a change to a write path that has not been checked against it is not
finished.

### The console's JavaScript is tested

`tests/js/*.test.mjs` run under node, driven by `tests/test_console_js.py` as part of
the same pytest run. They lift functions out of `src/thalamus/console/static/app.js`
**by name**, so renaming one breaks extraction loudly. That is the intended failure,
not a flake — update the test alongside the rename.

node is optional; a checkout without it skips those tests rather than failing.

## Layout

```
src/thalamus/
  substrate/   storage kernel — schema, Gremlin writer, Gremlin reader.
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
