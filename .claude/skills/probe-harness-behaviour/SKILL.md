---
name: probe-harness-behaviour
description: Turn a belief about how a harness this repo does not control behaves — which hook event fires, what a payload carries, where hook output is delivered, what a CLI does — into a measured fact pinned in the claims ledger, before code or docs rest on it. Use BEFORE writing or relying on a sentence about Claude Code, codex or Cursor behaviour (a hook comment, an install.py block, a design doc, a docstring), when harness-fact-reminder flags an edit, when observed behaviour contradicts what the code or docs say the harness does, and when a design step says "unmeasured" about a harness.
---

# Probe a harness behaviour, then pin it

Thalamus rides on harnesses it does not control. A sentence about what one of them does
is a claim about someone else's code: nothing in this repository keeps it true, and
nothing fails when it stops being true. Written as a fact and never measured, it shapes
design and measurement silently.

**Worked case.** `reflex.sh`, `harness/reflex.py` and `docs/cli.md` all stated that a
Bash result carries no exit status, so a failing command that printed nothing
recognisable could never fire the reflex. The truth was upstream of that: a Bash call that
exits non-zero never reaches `PostToolUse` at all, because Claude Code routes it to
`PostToolUseFailure`, which carries the exit status on the first line of its `error`
field. The reflex had been wired on the wrong event since it shipped, and every figure it
reported counted only failures whose status a pipe had swallowed. One run of the same
command with and without `; true` showed it (#262; A0160, A0161).

## When this applies

A harness fact is any statement of the form *harness H, given X, does Y*: an event fires
or does not, a payload carries or lacks a field, output reaches this agent or that one, a
CLI flag behaves a certain way, a limit sits at a certain size. The tell is a sentence
naming Claude Code, codex, Cursor or "the harness" beside a verb about behaviour, and the
sharpest version is an absence — "is not in the payload", "never fires", "cannot be
observed". An absence about someone else's system is the easiest thing to assert and the
hardest thing anyone will ever re-check.

## The procedure

### 1. State the belief as the claim it would be

One sentence, with the harness and its version: `claude --version`, `codex --version`.
Name what depends on it — which code path, which doc sentence, which number.

### 2. Read the vendor's reference first

Fetch the page as text (Claude Code serves Markdown at `code.claude.com/docs/en/<page>.md`)
and find the section that decides it. A reference is evidence of intended behaviour, not
of this installation's behaviour, so step 3 still runs whenever the answer changes code.

### 3. Measure it on the installed version

`probe-claude-hooks.sh` in this directory measures hook events without touching the
operator's settings. It wires a logging hook on each event named through a `--settings`
overlay in a scratch directory, runs one `claude -p` turn on haiku, and reports which
events fired, every payload they received, and whose transcript the hook's
`additionalContext` reached:

    bash .claude/skills/probe-harness-behaviour/probe-claude-hooks.sh \
      "python3 -c 'import sys; print(\"out\"); print(\"err\", file=sys.stderr); sys.exit(3)'" \
      PostToolUse PostToolUseFailure

`--subagent` runs the command inside one subagent, for delivery questions. A marker found
in the session's transcript can be the subagent's relayed reply rather than a delivery;
read the record's type (`hook_additional_context` with `isSidechain` is a delivery).

**The operator runs it.** An auto-mode session's classifier refuses a nested `claude`
that spawns agents, and a copied credential store is refused as leakage. Hand the command
over for `! bash …` and do not route around the refusal.

Design every probe with a control that differs in the one variable under test — the same
command with and without `; true`, the same hook sync and async. A probe with no contrast
shows what happened, not why.

### 4. Pin what was established

In this repository the ledger's grounds are spans of its own tracked source; a lab record
of a probe run belongs to the private bridging ledger. So a harness fact is pinned in two
entries:

- **The harness fact**, grounded in the vendor's reference. Register the deciding section
  as a source — the extracted section as a committed file, since the ledger's cache is
  not committed and CI resolves quotations against the bytes:

      claims-ledger source add --id <id> --type documentation \
        --citation "<page>, <section> (retrieved <date>)" --retrieved <date> \
        --url <the .md url> --extraction "<how the section was cut>" \
        --keep-path ledger/sources/<id>.md

  The entry is `argued`, grounded `source: <id> · §<section>`, with the deciding lines as
  Backing quotes. `ledger/sources/claude-code-hooks-posttoolusefailure.md` and A0160 are
  the worked example.
- **This repository's dependence on it**, `measured`, grounded in the code span that
  relies on it and citing the harness entry `cites-as-live`: A0161 grounds on
  `install.py § "HOOK_WIRING"`. When the wiring changes, freshness flags every sentence
  that cites it.

An absence needs a `search:` ground; `claims-ledger validate` refuses one without it.

### 5. Rewrite the prose that stated the belief

Every sentence that asserted it — comments, docstrings, docs — states what is true now,
names the issue when the code is still wrong, and cites the dependence entry.
`tagging-prose-with-claims` covers where a marker sits.

### 6. File the defect when the code rested on the wrong belief

A GitHub issue with the probe's contrast as its evidence, the harness version, and what
the correct wiring needs (`track-open-work`). The code change that follows edits the span
the dependence entry pins, and that is where the entry is re-read.
