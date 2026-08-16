---
name: verify-before-you-carry
description: How to keep a check that cannot fail from reading as a clean result, and a measured number from becoming the wrong claim — arming the control, naming the population, reporting the denominator, and re-deriving a figure before it travels. Use BEFORE quoting any number you did not derive yourself, BEFORE trusting a green run from a checker you just wrote or were just handed, BEFORE reporting "no failures" from a scan, sweep, or audit, and when a control, a defense-off arm, or a negative result is what a conclusion rests on.
---

# Verify Before You Carry

A check that inspects nothing reports exactly what a healthy system reports. So does a
sweep over an empty set, a control that could not have failed, and a scan whose pattern
matches nothing. **Green is not evidence; green plus a witnessed red is evidence.**

This is not a caution to hold in mind. It is a set of actions to perform, because
holding it in mind demonstrably does not work: every instance below was produced by
someone who knew the rule, had just applied it elsewhere, and was still wrong.

## The four moves

### 1. Arm the control, then prove it is armed

A control is only a control if it can fail. Before trusting a negative result, confirm
the mechanism you are controlling for is actually engaged.

- Passing `-p no:randomly` disables a plugin. If the plugin was never installed, the
  flag is a no-op and the green run corroborates nothing. Check the plugin is present.
- A mutation harness that patches the wrong binding leaves every poisoned mutant
  behaving like the original. Confirm one mutant is actually poisoned.
- A positive control built from input the guard would never have blocked demonstrates
  nothing about the guard. Confirm the input would be blocked when the guard works.

Where a case asserts an absence, the control belongs *in the case* and its failure
class should say the check collapsed — not that the code is broken. Those are different
findings and must not share a verdict.

### 2. Report the denominator with the verdict

`0 failures` is meaningless alone. `0 failures over 61 elements` is a result;
`0 failures over 0 elements` is a broken run wearing the same words.

Anything that walks a surface, a file set, or a result set states how much it walked,
and any claim quoted from it carries that number. Coverage is per-view: a clean sweep
of the views you visited says nothing about the view you did not render.

### 3. Name the population a figure describes

A number can be correctly measured and still be the wrong claim, because it answers a
question nobody asked.

A conservative contrast check's penalty reaches ~0.083 globally — but that maximum
occurs near 8:1, where no movement can cross a threshold. The figure that can change a
verdict is the maximum among pairs *already near the floor*, ~0.057. The global maximum
is true, correctly derived, and the number someone will quote in good faith to argue
the check is too strict.

Before a figure travels: which population does it describe, and is that the population
the decision is about?

Where a maximum is attained on a flat ridge, quote the number without the attaining
example. A named example invites the next reader to check that one case, find less than
the header claims, and conclude the header is wrong — when they have found a different
point on the same ridge. That reader is adversarial by construction, because the only
person who checks the number is someone arguing the check is too strict.

### 4. Re-derive before you carry

Do not forward a number you did not compute. Re-derive it independently — different
implementation, different language, different rounding if that is in play — and report
the delta even when it changes nothing.

Deltas that changed no conclusion but were worth surfacing: 2.72 vs 2.73 vs 2.751 for
one composited colour (banker's rounding vs float vs round-half-up), and two sweeps
agreeing to 0.0014 while attaining their maxima at different points — which is what
established the ridge was flat rather than asserting it.

Near a threshold, round *against* yourself. A legibility floor exists to protect a
reader, so a checker must never pass what the screen fails; the tie goes to the reader.
State the cost of that choice — the false-failure margin — alongside the benefit, or
the next person will discover it while arguing the check is broken.

## Inherited results

A handed-over tool or figure gets the same treatment as one you found. Verifying a
handoff is not distrust; it is the only thing that makes the handoff worth having.

Run its self-check first, then check the self-check can fail. A tool shipped *with* a
self-check attached still produced a clean report over a view it never measured.

When you kill your own hypothesis, report it. A refinement that turns out to be a no-op
for a good reason is worth more than the refinement, because it establishes the current
form is right rather than merely cautious — and it stops the next person making the
same proposal.

## What this costs, and what it does not buy

The moves are cheap: one extra derivation, one denominator, one deliberate break.

They do not make a single reader sufficient. Four errors in one session were each
caught by a *second party who re-derived a handed-over result* — not by anyone applying
a rule, since in every case the author had the rule and applied it. Where the stakes
justify it, arrange for the second derivation to come from someone else.
