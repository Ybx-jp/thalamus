# 017 — The mutant gate, and the test suite that rewarded imitation

**Date:** 2026-07-26 · **Component:** eval loop layer 2 (`thalamus eval oracle`) ·
**Status:** gate built and **passed 7/7 on first run**, no resolutions needed;
one design defect found and fixed on the way; the all-green result carries a
selection caveat named below.

## What was attempted

docs/04 has named the mutant set as the graded oracle's discrimination bar since
the ladder landed, and nothing implemented it. `source.fix_ref` sat in the schema
with no runner that could read it, so last session's anchor validation was done by
hand and the ladder's resolution in the interior — where every observed arm sits —
was unmeasured.

Build `thalamus eval oracle <task>`: grade the negative anchor, the positive
anchor, and a 4–6 mutant set against pre-registered rungs, with no model in the
loop. Every candidate's quality is known by construction, so the whole instrument
validates at zero inference cost.

## The defect the build found: L1 was grading against the wrong suite

Mutants are degradations *of the known-good fix*, so they start from `fix_ref`.
That tree carries the tests the fix shipped with itself, and grading against those
is wrong in two separate ways:

1. **Every degradation collapses to rung 0.** The fix's own unit test fails on any
   mutant that weakens case-insensitivity, so L1 falls before the ladder can say
   *how* degraded the candidate is. The discrimination the mutant set exists to
   measure is destroyed two rungs below where it happens.
2. **It rewards imitation.** `test_keyword_matching_is_case_insensitive_and_regex_safe`
   imports `_keyword_predicate` **by name** and asserts on its `.value`. A
   *correct* fix that structures the predicate differently fails L1 on an
   ImportError.

The second is the serious one. docs/04 requires the relations be behavioral
precisely so they "cannot reward imitating the historical fix's names" — and here
that exact reward was about to enter through the gate instead, one layer below
where anyone was watching for it. L1 means *the pre-existing suite stays green*,
and pre-existing means the suite a candidate arm inherits, so `tests/` is now
pinned to `source.ref` for every graded candidate. Source stays at the candidate's
ref; that is the thing under grading.

Generalized: **an instrument assembled from parts built for another purpose
inherits their assumptions silently.** Same shape as the circularity guard found
when the ladder was layered over probes built to measure delivery — invisible
under a binary verdict, visible the moment resolution is demanded.

## Why these mutants are not classical operators

The classical licence for mutants-as-fault-proxies is the competent programmer
hypothesis plus the coupling effect — mutants are coupled to real high-priority
faults, measured across ~15M of them (arXiv 2103.07189), and coupling is a
quantity that can be measured rather than assumed (arXiv 2512.16741). Both
hypotheses describe **human** programmers making small syntactic deviations from
nearly-correct code.

These candidates are LLM agents, and they fail differently: plausible wholesale
rewrites, over-fixes touching behavior the report never mentioned, fixes correct
at one call site and absent at four. A set built from classical operators would be
coupled to the wrong fault distribution. So each mutant declares `mimics` — the
observed arm behavior it stands in for — and the schema enforces it rather than
trusting the author to have thought about it.

## Result

| candidate | mimics | expect | got |
|---|---|---|---|
| negative-anchor | bug present by construction | L1 | L1 |
| positive-anchor | the real fix (8b70330) | L5 | L5 |
| m1-partial-session-site | fixed where the repro pointed, nowhere else | L3 | L3 |
| m2-overfix-verbatim-sites | over-fix: case-blinds artifact/project too | L4 | L4 |
| m3-floor-lowered | collateral loosening the prompt forbade | L4 | L4 |
| m4-stopword-fallback-dropped | rewrite that quietly drops the recency fallback | L4 | L4 |
| m5-equivalent-renamed-helper | **not a defect** — correct fix, helper renamed | L5 | L5 |

Rungs were committed in `7d9cd10`'s successor **before** the gate ran; the commit
is the pre-registration timestamp. Nothing needed resolving.

The two ends carry the most weight. `m1` at L3 is the ladder separating "fixed the
symptom" from "diagnosed the path" — a distinction the binary oracle could not
make and the anchor pair cannot reach, since both endpoints are outside it. `m5`
at L5 is the anti-imitation check: a correct fix under a different name scores full
marks, which is the property the pinned-suite fix above was needed to preserve.
The equivalent mutant is a deliberate instrument here rather than the nuisance the
literature treats it as — undecidability does not bite when equivalence is authored
rather than inferred.

## The caveat on an all-green first run

7/7 first try is a result to be suspicious of, and the reason is selection, not
luck: **m2, m3, and m4 were authored after reading R3's guard list**, so they
target guards known to exist. That is not circular in the fatal sense — the ladder
was not tuned to the mutants, and the relations were authored held-out from the fix
weeks before these patches existed — but the mutants were chosen to be catchable,
and a set chosen that way cannot discover a blind spot.

What it does establish: the ladder's rungs fire *where they claim to*, each guard
does work no lower rung does (m3 in particular is invisible to L2, whose noise
probe matches nothing at any floor), and the interior is ordered rather than
saturated. What it does not establish: that the ladder catches degradations nobody
thought to write a guard for. The next mutant set should include at least one
authored *without* reading the relations — the same held-out protocol the relations
themselves were authored under, inverted.

A second, smaller gap: whether these mutants are genuinely coupled to observed arm
failures is asserted from the campaign record, not measured. arXiv 2512.16741's
statistical framework for coupling strength is the cited method for closing that,
and it is unrun here.

## What this unblocks

The instrument has now cleared its own stated discrimination bar, so a graded
campaign can be read as saying something about candidates rather than about the
grader. That is the next step: re-run the counterfactual arms under the ladder and
see whether graded rungs de-saturate the 18/18 binary verdict.

## Grounding

- arXiv 2212.06118 — oracle-based test adequacy; coverage is a poor adequacy
  metric and should not indicate fault-detection effectiveness. Why the verdict is
  a gate and not a kill-rate.
- arXiv 2412.20692 — metamorphic test adequacy from necessary properties; the
  warrant for nested relations at L3–L5.
- arXiv 2103.07189 — mutants coupled to real high-priority faults at ~15M scale.
- arXiv 2512.16741 — competent programmer hypothesis and coupling effect named;
  coupling made measurable.
- arXiv 2601.03525 — the cardinality bias a weighted sum (or a kill-rate) imports.

Both mutation papers were ingested into the `eval-methodology` scope this session
(feed `thalamus`); the oracle-adequacy pair was already held but cited nowhere in
docs/11 until now (§2d).
