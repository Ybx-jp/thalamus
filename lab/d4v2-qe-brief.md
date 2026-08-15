# qe brief — the session row, and the seams around it

**Two authors.** Part A and B are the designer's: encodings, thresholds, and what a
pixel is allowed to mean. Part C is homelab's: deployment, the box, and the places a
test can be green while the thing is broken. Take each invariant back to its author —
the designer for what a rule *should* be, homelab for how it reaches the operator's
machine.

**One rule over all of it, and it is the reason this brief exists:** the branch shipped
an `AttributeError` on every readable poll while the suite was green, because the test
handed the code a fake session and *a fake grows whatever attribute the code asks it
for*. The general form: **a test that constructs its own copy of the thing under test
cannot see that thing drift.** Everything below is a variation on it.

Standing companions to that rule:

- A guard nobody has watched fail is decoration. Every invariant here should have a
  known-bad input that flips it red, and the red should be *witnessed*, not reasoned.
- Assert the meaning, not the spelling. §8's whole history is a word list standing in
  for a rule.
- Bind vocabularies across the language boundary rather than copying them. A copy is a
  second owner, and two owners drift.

---

## Part A (designer) — contrast, and why it is harder than a palette check

§2 carries a floor: 4.5:1 for text against its **own composited background**, 3:1 for
non-text carriers. Four pairs were measured failing on the built roster 2026-08-15:

| pair | ratio | need | carries |
|---|---|---|---|
| `#4d5661` on `#0e1116` | **2.54:1** | 4.5 | *not in reach*, the line-2 qualifier lane, group header + count + sub, the `⋯` affordance, sheet section labels |
| `#4d5661` on `#161b22` | **2.32:1** | 4.5 | header brand `console`, the `thalamus` subs |
| `#7d8794` on `#1c232c` | **4.35:1** | 4.5 | chips — `full`, `esc`, `mode`, `✕` |
| `#7d8794` on `#222025` | **4.44:1** | 4.5 | `dismiss`, the error detail line inside the band |

**The failure is a *pairing*, not a colour.** `#4d5661` is fine on some grounds and
fails on two others; `#7d8794` passes at 5.18:1 on the page and fails at 4.35:1 on a
chip. So a test iterating palette tokens alone under-reports, and one crossing tokens ×
all grounds over-reports on pairs the CSS never produces. Two honest designs — qe picks:

1. **Declare the pairs.** One place lists every (foreground, ground) the stylesheet may
   produce; one test asserts each meets its threshold, a second asserts the CSS produces
   no undeclared pair. Cheap, reviewable, but binds only what the declaration covers.
2. **Assert over a rendered DOM.** Walk the real client, composite each element's actual
   background, compute per element. Catches what (1) misses; costs a browser in CI.

**Two traps, both worth encoding as tests-of-the-test:**

- **Alpha.** A first pass read `backgroundColor` and treated `rgba(224,104,92,0.12)` as
  opaque, yielding **1.0:1** for the band — a fake pass-through of the same colour. Any
  implementation must composite alpha down the ancestor chain to an opaque base, and
  foreground alpha too. *A test reporting 1.0:1 for legible red-on-dark-red is measuring
  nothing.*
- **Thresholds are size- and weight-dependent.** 3:1 applies only at ≥24 px, or ≥18.66 px
  bold. Everything on this row is 9–13 px so effectively everything needs 4.5:1 — but
  hardcoding 4.5 hides the rule and misjudges the day a heading arrives.

**Fixture:** point the assertion at `#4d5661` on `#0e1116`, watch it fail at 2.54; lift
and watch it pass. *A contrast test nobody has seen fail is decoration.*

> Homelab note: a first implementation now ships as `tests/test_console_contrast.py`
> (token-level, design 1's shape, grounds declared per token). It verifies its own
> arithmetic and asserts the tiers stay distinguishable. It does **not** composite alpha
> and does not know font size — both of Part A's traps are unhandled, deliberately, and
> are qe's to decide on. Treat it as a starting point to replace or extend, not as
> coverage.

## Part B (designer) — console seams, and the invariant each protects

Ordered by what breaks worst if it drifts. Each is a *design* invariant: the test should
fail on the meaning, not on a string.

1. **The reduction binds to the real descriptor type.** Generalise past the one field:
   any reduction from a descriptor or ledger row into the wire binds to the real
   dataclass, and the binding counts only if deleting the field breaks the test. Ask
   whether *other* reductions still take fakes.
2. **`observed` / `blocked` / `activity` cannot disagree.** One lookup, one branch.
   Unobserved ⇒ `blocked is None` **and** `activity == ""` **and** `activity_since is
   None`; blocked ⇒ no activity word; unrecognised status ⇒ `observed=True`,
   `blocked=False`, `activity=""`. A partially-null row renders as a false
   non-observation.
3. **The poll carries no screens.** The 80% finding regresses the moment a field is
   added back for convenience. Assert `/api/panes` carries no pane text, that payload
   size stays sub-linear in transcript volume, and that the mirror's text comes only
   from the focused-window request.
4. **`screen_rev` is opaque.** The client may compare consecutive values and nothing
   else. Assert the rail pulses on *any* change (swap hash for counter and the client
   must not care) and that no client code parses, orders or interprets it.
5. **The count reads `blocked`, never the pill.** A blocked row mid-restart shows
   `restarting` and is *still counted*. Precedence reallocates a slot; it never retracts
   a finding.
6. **Precedence is total and ordered,** including the two live collisions: viewed +
   unobserved (the anchor row), and `dead` outranking `observed === false` — drawing
   *not in reach* over a corpse is a false non-observation, the same error class as (2).
   The band sits outside the chain entirely.
7. **Grouping fails in one direction only.** `project`, else `repo_root`, else the
   trailing group. Property-shaped: two rows never share a group unless they share a
   non-empty key. Under-group is honest; over-group asserts a relation that does not
   hold and looks identical to a correct one. `dir` must never reach the grouping key.
8. **The distill enum is pinned to Python,** like the status vocabulary. Five states
   reach the wire, `done` never does, `op` rides only `unknown`. A state added in
   `distill.py` should fail the test that names it rather than widening a hole.
9. **`abandoned` is a threshold, not a literal** — 3× `STALL_AFTER_S`. Assert it tracks
   the constant, and that the boundary is inclusive-correct at 1× and 3×.
10. **Clock idioms are a pure function with a truth table.** `M:SS` under an hour,
    `6h47m` under a day, `6d 2h` beyond. `146h26m` was the defect.
11. **Record-only rows draw no `opened` clock.** `updated` is when distillation last
    moved; dressing it as a start asserts something nobody recorded.
12. **The §8 guard is itself guarded** — good and bad shapes are pinned as cases. Decide
    whether the knowingly-accepted residual holes (bare-identifier object keys,
    destructuring) deserve a recorded xfail, so the acceptance is visible rather than
    folkloric.

## Part C (homelab) — the plumbing

See `/tmp/qe-brief-homelab-half.md` for the long form; the substance is here.

1. **Where else the fake-descriptor bug lives.** Unaudited candidates:
   `console/transcript.py`'s `LedgerIndex` rows → `attach_ledger_facts`; `distill.py`'s
   `_kill_rows` → the `unknown` row's identity; `quick.LedgerRow`, `QuickResult`,
   `ForkRun`. Anything crossing into a wire payload or a console surface.
2. **What runs is not what is checked out.** The console the operator uses runs from the
   **installed package path** under a systemd `--user` unit, on whatever branch that
   checkout is on. A worktree can be fully green and wholly irrelevant to the running
   service. Two specific hazards: `thalamus init` **from a worktree repoints the global
   install at the worktree** (temporary directory, permanent breakage when removed); and
   hooks arm **per process**, so "committed" and "in effect" are different claims and
   only the first is testable today. Ask whether `init` should refuse from a
   non-primary checkout, and whether `init --check` can assert the wired paths resolve
   inside it.
3. **The clean-slate seed can swallow the state it was taught to report.** `distill.py`
   skips logs older than `seeded_at`. `abandoned` rows are *by definition* old
   (`ABANDON_AFTER_S` = 3600 s), so a freshly seeded console may never surface an
   abandonment that predates it. The same collision appears in the test fixture, which
   seeds at `now - 3600`. **Two constants chosen independently now bound each other and
   nothing says so.**
4. **The console's vantage is a deployment property.** Descriptor partitioning (lab/045)
   means what the console can observe depends on how it was launched: 2 of 9 windows
   from inside a room, the complementary 7 of 9 from the host dir, same roster, same
   instant. Pin the *relationship*, never a count — and any screenshot or manual check
   must state its vantage or it is not reproducible.
5. **tmux is the substrate and is not transactional.** Every call is an argv list, never
   a shell string, and captured pane text must never reach a command — worth an explicit
   test. Identity resolves by `pane_id` and falls back to a match that **refuses rather
   than guesses** when two windows share a scope and a directory; assert the refusal, not
   just the happy path. `recycling`/`closing` are stamps whose truth is "in flight", and
   `grace_s` is what makes a leaked flag self-report instead of reading `restarting`
   forever.
6. **The dismissal file is the console's only durable state.** `STATE_V` bumped 2 → 3 on
   this branch. Pin: an old version **migrates rather than resetting dismissals**, a
   corrupt file does not crash the poll, and dismissal stays per-occurrence. A silent
   reset re-shows failures the operator already handled, which is the fastest way to
   teach someone to ignore the channel.
7. **Concurrency is unexercised.** `ThreadingHTTPServer`, a module-global `_LEDGER`
   behind `READ_LOCK`, several clients at 1.2 s, and `thalamus roster` mutating tmux
   underneath. At minimum: concurrent polls during a recycle, and a roster sync racing a
   poll.
8. **A guard that cries wolf gets worked around, and one currently does.** The
   `room-command-guard` hook blocked, in one session: `git add …/roster.test.mjs`; a
   `sed` naming `dispatch.py`; a `grep` whose *pattern* contained `send-keys`; a
   `gh pr create` whose **body text** contained the word "room"; and `thalamus spawn
   --help`. All innocuous, each routed around with a glob or a file. **A high
   false-positive rate trains its subject to build bypasses, and the bypasses then work
   for the real case.** This is §4.3a's base-rate argument applied to a security control,
   and it is measurable: put a precision number on it and tighten the matcher to the
   invocation shape rather than to a token appearing anywhere in a command. The guard's
   purpose is sound; this is about its precision only.

## Part D — two chores that undermine every claim made after them

- **`THALAMUS_ROOM` leaks into pytest.** 16 failures from inside a room session, fully
  green under `env -u THALAMUS_ROOM`. Anyone verifying in-room reads a red suite and
  discounts the work.
- **`tests/test_ownership.py::test_the_partition_runs_both_ways` failed once and has
  not been reproduced.** Observed exactly once, in a full-suite run on 2026-08-15
  around 14:10 PDT; it passed in isolation immediately after and in every run since.
  **The mechanism is unknown.** An earlier version of this brief called it
  "order-dependent, fails on some random seeds" — that was homelab's inference and it
  was wrong: `pytest-randomly` is not installed, collection order is deterministic and
  was verified identical across runs, so `-p no:randomly` (which two of us passed for
  days) was a no-op against a plugin that was never there. The assertion output was
  never captured, so it is not even known which of the two assertions failed, or
  whether the guard returned 0 (allowed) or 1 (crashed under `set -euo pipefail`) —
  which have opposite diagnoses. Ruled out since: env leak into the subprocess (the
  helper builds a clean env), cross-test pollution of the manifest dir, pairing with
  the seven files sharing guard machinery, and mid-write manifests (every
  `config/experts/*.yaml` and `contract/ownership.py` is stamped at worktree creation
  and untouched since). `thalamus_repo_root` is pure path arithmetic with no `git`
  call, so index contention is not a channel either.

**Homelab's call on order: the env leak first.** It is mechanical, and it unblocks
trustworthy verification for everyone in the room. The ownership failure needs a second
observation before anything can be chased: the mechanism is unknown, and a guard against
a mechanism nobody has identified is decoration.
