# 037 — The verdicts that could not be replayed

**Date:** 2026-07-30 · **Component:** eval layer 1 (`eval/sync.py`, `eval/attribution.py`, `eval/calibration.py`) · **Status:** audited; three fixed, four open with a thread.

## The rule the audit applied

`judged_terms` fixed one instance of a general disease: a stored verdict that is a
function of state the record does not carry. The test is replay. **A recorded
judgement that cannot be re-derived from what was recorded is a re-derivation wearing
a record's clothes** — it will be recomputed on read against whatever the inputs have
become, and agree with itself for the wrong reason.

The literature names the failure and its remedy in the same breath: TOKI calls the
class *audit erasure*, and its tightness theorem makes keyed write-time logging of the
adjudicating judge *necessary* for replay consistency (docs/11 §5). Not sufficient —
necessary. So the audit is not a style preference.

The pattern to copy was already one property away. `Trace.ranker_config` stamps the
ranking dials at retrieval time precisely so a dial change cannot be back-attributed
(lab/029). Every finding below is that argument applied somewhere it had not been.

## What was found, ranked

**1. The judging window's *selection* was unrecorded.** `judged_terms`' own docstring
claimed "the window comes from the immutable archive, so terms + window reproduce the
verdict exactly". The blob is immutable; the *choice* of blob is not. The window comes
from the transcript Source with no incoming `SUPERSEDES`, resolved at call time — and
re-distilling a still-open session mints a new head. A verdict recorded before that
and replayed after judges different bytes, silently. **Fixed:** `judged_against` on
the Trace, the content hash the window was actually cut from.

**2. The dials were unrecorded.** `judged_terms` stored the instrument's inputs and
nothing about its settings. The same term set under `MIN_MATCHED_TERMS = 3` is a
different verdict. **Fixed:** `judge_config` on the Trace
(`j1:shipped-t2-r0.3`), legible rather than hashed for the same reason
`ranker_config` is — a straddled window should say *which* dial moved.

**3. `restrict()` discarded the field auditability is measured from.** A real bug, not
a design gap. `calibration.restrict()` rebuilt each `Case` without `judged_terms`, and
`restrict` is what experiments/001 narrows the corpus with *before* calling
`auditable()`. So the auditability of a restricted corpus read as zero in the one
place it is actually reported. **Fixed,** with a regression test — the existing suite
passed throughout, which is the point.

**4. Verdicts are judged against today's graph text, not the text the agent saw.**
`_land_event` builds its comparison set from `_node_text(g, node_id)` — the live graph
— while the tap already retains the verbatim rendered response the agent received, and
already content-addresses it for the withholding join. Sync runs arbitrarily later, so
even a *fresh* verdict can be about text the agent never saw, with `judged_terms`
faithfully recording the wrong stimulus. **Open.** `written_at` (docs/09, same day)
makes the drift detectable for the first time; it does not make the judgement right.

**5. Campaign records omit `fix_ref` and the fix-touched path set.** `contaminated`
and `escapes` are computed from a git diff over the operator's *live* repo. The record
stores `ref` but not `fix_ref`, not the resolved path set, and no digest of the task
definition. A task YAML edited afterwards re-scopes every prior contamination verdict.
**Open.**

**6. Rake-audit human labels do not carry their stimulus.** Items render Claim
descriptions and `Session.summary` — both mutable — drawn live at worksheet time.
`sample_to_jsonl` persists `{item, rake, session, decoy}` and not the rendered text,
so the label and what was labelled are joined by item number alone. The worksheet on
disk holds the prose; nothing hashes or rejoins it. **Open.**

**7. Consultation citations are validated by existence, not by content.** An answer
records `role: citation` edges by ID, never copying. A cited node rewritten afterwards
leaves an "the answer rests on this" record whose referent has moved, and
`audit_exchanges` only checks that *some* citation edge exists. **Open** — and this
one is arguably correct as designed (by ID, never copied, is a deliberate rule), so
the open question is whether to stamp the cited text's digest rather than to copy it.

## The class, caught in the wild the same day

A design checkpoint on the next campaign (exchange `34166c3f423141aa`) went looking at
the 17 recorded injected arms and found the disease already present. Four of fifteen
`memo_echoed` verdicts — 10:30, 10:51, 11:00 and 11:46 UTC on 2026-07-30 — carry
`evidence: "cited by vertex ID"`. That is impossible under the current key,
`__injected_memo__`, which is named in a comment three lines above it *precisely* so it
cannot occur in prose. They are the output of the superseded `"memo"` key, which
self-matched every arm that said the word. `rescored_at` is null on all 17, so nothing
in the corpus says which instrument produced which verdict.

What it does and does not cost: the **ratios are computed the same way under both keys**
and are unaffected, and lab/036's reading — "all four ceiling arms with the field
recorded visibly acted on the memo (term ratios 0.41–0.54)" — rests on ratios. That
conclusion stands. What cannot be cited is the evidence string, and by extension the
`used` boolean on those four, which under the old key had a path to true that the new
key removed. Rescore before the next campaign uses them.

This is the argument for `judge_config` in its strongest form. Had the fingerprint
existed, these four would say `j0:memo-...` beside the others' `j1:shipped-...` and the
mismatch would have been a query rather than a discovery.

## Two counter-examples worth keeping

`gold.py` records `judge_verdict` at *draw* time "so scoring cannot be accused of
choosing the comparison after seeing the labels", and persists `node_text` and
`window_excerpt` into the sample. That is the shape. Its one gap is that the human
labels a truncated excerpt while `judge_verdict` was computed on the unbounded window,
so `agreement()` compares two stimuli and the record does not say so.

`sync.py` already stamps `answered_from` beside its raw input
`answered_by_agent_type` — a derived verdict kept next to the thing it was derived
from. Copy that, not the alternative.

## What it does not fix

Nothing here backfills. Verdicts written before 2026-07-30 carry no `judged_terms`,
no `judge_config` and no `judged_against`, and that absence *is* the measurement of
how much of the corpus is auditable — `calibration.auditable()` reports it as three
numbers rather than one, because a stored term set, an immutable node kind, and
neither are three different degrees of trustworthy and pooling them would hide the
worst one.

**Ends in:** three fixes, four open items, one live instance, one rescore owed.
