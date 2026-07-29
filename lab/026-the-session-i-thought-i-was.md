# 026 — The session I thought I was

**Date:** 2026-07-28 · **Component:** pin ledger, trace tap, `thalamus rescope` ·
**Status:** an **incident report** with one instrument finding and one design gap.
The headline the session first claimed for itself is **retracted** in §3.

---

## §1 — What was claimed in the moment

While building `thalamus rescope`, a `memory_recall("append-only audit log
immutable correction provenance")` returned, among literature claims, a tier-1
first-party result: `scope:eval-methodology:session:7f815861…`, a Session vertex
distilled at 02:58Z.

The session believed `7f815861` was **its own id**. On that belief it concluded:
this session has already distilled, vertex IDs include scope
(`contract.ontology.vid`), therefore the rescope-to-`main` row it had appended
twenty minutes earlier would not *move* the Session vertex — it would mint a
second one under `main` and strand the first with a stale half-transcript. It
reverted the row and reported to the operator that **memory had caught a bug the
operator had requested**.

That reading was celebrated. It is wrong.

## §2 — What actually happened

The session's id was **`e05114ff`**, not `7f815861`. `7f815861` is a *different*
eval-methodology session from the previous day — the one whose open threads this
session was primed with at SessionStart. It really was distilled; it simply was
not us.

Consequences of the misidentification:

1. **There was never a fork risk.** `e05114ff` had **0 Session vertices** at the
   time. The rescope-to-`main` the operator asked for was safe all along, and the
   "catch" reverted a correct action for a wrong reason.
2. **Two rows were appended to the wrong session's ledger.** `7f815861` now
   carries a `rescope → main` and a `rescope → eval-methodology` it never earned.
   Net resolution is unchanged (the revert restored its original scope), so
   nothing downstream misroutes — but a tier-0 audit record now contains two
   operator-attributed events that no operator performed. Recorded here rather
   than papered over; the ledger is append-only by design, and rows are not
   deleted to make a story tidier.
3. **The operator's actual request went unexecuted for ~40 minutes**, while the
   session reported it as thoughtfully declined.

## §3 — What actually caught it, and the retraction

Not memory. **The trace tap.**

The error surfaced only because the operator asked for a lab write-up, which
prompted a check of whether the eval loop's used-vs-ignored attribution had
detected the supposed "use" event. That check read `~/.thalamus/traces/` and
found the session's own tool calls were absent under `7f815861` — its last trace
there was `2026-07-28T01:15:59Z`, hours stale — while `bash_gremlin` at
`05:52:14Z` and `memory_recall` at `05:51:47Z`, which matched this session's
actions exactly, were recorded under **`e05114ff`**. The pin ledger then
confirmed it: `e05114ff` engaged at `2026-07-29T04:12:25Z`, the minute this
conversation began.

So the honest causal chain is: **instrumentation caught an agent's false belief
about its own identity**, and it did so incidentally, during an unrelated
verification, roughly forty minutes after the false belief began driving actions.

**The retraction matters for the project's headline claim.** lab/015 and lab/016
measured `fix-name-convergence` at **0/18** — memory *use* unevidenced. This
session briefly looked like the first first-party instance of recalled content
changing an action. It is not: the recalled content was real and correctly
returned, but the *inference drawn from it* was false, and the action it produced
(the revert) was wrong. A retrieval that changes behaviour by being
**misattributed to the wrong subject** is not evidence of memory utility. The
0/18 stands.

## §4 — The design gap: an agent cannot know its own session id

This is the transferable finding.

Nothing in a session's context reliably tells it its own `session_id`. This
session inferred one from a subagent task-directory path, which named a
*different* session. The value is available to every **hook** (Claude Code puts
`session_id` on hook stdin) and is written into the pin ledger — but it is never
injected into the session's own context, so any self-referential operation the
agent performs must *guess the subject*.

Every self-referential operation inherits this: `rescope`, self-audit, "has my
work distilled yet", and any future "correct my own routing" affordance. It is
the same class as lab/012's `THALAMUS_PROJECT` bug — a session reasoning about
itself from a value that names something else — but sharper, because there the
wrong value was a plausible-looking directory basename and here it is a
well-formed UUID that resolves to a real, adjacent, same-scope session.

**The guardrail did not help, and could not have.** `thalamus rescope` was built
in this same session and refuses precisely this case:

```
$ thalamus rescope 7f815861 main
Refused: session 7f815861 has already distilled into `eval-methodology`…
```

It refused. It was still the wrong answer, because it validated the **wrong
subject**. A check applied to a misidentified subject is not a weak check; it is
no check at all, and it is worse than none because it returns a confident verdict.
This is the guardrail analogue of "green and ungrounded" (`ground-in-literature`):
the assertion passed, about the wrong thing.

## §5 — What changed

- `thalamus rescope e05114ff main` — the operator's original request, executed
  once the real subject was known, validated as undistilled.
- The two spurious rows on `7f815861` are left in place and disclosed here.
- **Open:** `rescope` should not take a session id by guesswork. A `--current`
  mode resolving from the ledger (most recent `engaged` row for this cwd) or, better,
  a `session_id` injected into context by SessionStart would remove the guess.
  Not built; recorded so it is not re-derived by the next session to hit this.
- **Open:** nothing detects a session reasoning about a session id that is not its
  own. The trace tap holds the evidence — the tap keys every record by the id the
  *harness* reports, which is authoritative — but nothing compares that against ids
  the session mentions.

## §6 — Discipline note

The first draft of this entry was going to be titled after the operator's
reaction: memory proving its value by preventing a user-requested bug. It read
well and it was false. The check that falsified it — "did attribution actually
detect this use?" — took four minutes and was only run because the write-up
demanded a number. **The write-up is the instrument.** An anecdote that is never
asked for its trace record survives indefinitely; lab/024's §1 makes the same
point about interim results, and lab/025 about self-answered consultations. Same
failure family: a plausible narrative, unverified, arriving with confidence.
