# 031 — The dial that had nothing to tune: the detail cap stays at 8

**Date:** 2026-07-29 · **Component:** retrieval (`_select_details`) · **Status:** measured, null result. One bug found and fixed.

## The question

[lab/030](030-the-miss-rate-was-the-consultation.md) found the detail cap is the
dial actually doing work in the recall path — 8% of fan-out, against the match
floor's nil — and that lab/007 had called it arbitrary and never tuned it. So:
tune it.

## Why this dial is uniquely tunable offline

Lowering a cap only ever *removes* nodes that were rendered, and every rendered
node already carries a used/ignored verdict. So a smaller cap can be evaluated
against real labels with no counterfactual estimation — the missing-label
problem that blocks offline evaluation of the *ranker* (lab/029) does not apply
downward. Raising it is not label-safe and is not attempted here.

Evidence base: **1,354 labelled detail renders** parsed from the verbatim tap
responses, joined to `RETURNS` verdicts. Render order is recoverable because the
reader prints vertex IDs inline and the tap stores the response verbatim.

## The answer is: leave it at 8

**Nothing predicts whether a detail gets used.**

Used-rate by render position within a session block:

| position | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| labelled | 226 | 206 | 171 | 141 | 111 | 95 | 75 | 64 |
| used | 58% | 62% | 65% | 61% | 59% | 58% | 60% | 72% |

Flat. Which is what the code predicts: `_select_details` returns
`matching[:cap]` — an **unranked** slice in graph order — so position was never
going to carry a relevance signal.

The obvious fix would be to rank before truncating. It buys nothing:

| cap | first-K by render order | top-K by keyword-hit score |
|---|---|---|
| 2 | 60.0% | 61.6% |
| 4 | 61.3% | 59.1% |
| 6 | 60.6% | 60.6% |
| 8 | 61.2% | 61.2% |

Nor does claim length (53–59% across four buckets, no trend). The only
discriminator found is **claim kind** — decision 62%, solution 56%, problem 53%
(n = 536/378/440). A 9pp spread on a 60% base: a candidate, not a mandate, and
untried.

So the cap is a **volume knob at a fixed ~60/40 exchange rate**, not a precision
knob. Going 8 → 5 would drop ~146 used claims to save ~88 ignored ones. That is
a bad trade at a 60% use rate, and there is no ordering signal that would let a
smaller cap keep the better claims instead of an arbitrary eighth of them.

**The dial is not idle** — it binds (truncates genuinely matching claims) in
**90 of 522 rendered blocks, 17.2%**, and 23.8% of blocks render exactly at the
cap. So this is a null result with the dial firing, not a null result from a
dial nobody touches.

## The caveat that bounds all of the above

Of 1,354 detail renders, **19 (1.4%) were attributed via the strong path** — the
agent citing the vertex ID. The other 98.6% rest on lexical echo:
`MIN_MATCHED_RATIO = 0.3` of the node's own distinctive terms appearing in later
output. Every rendered detail matched the query by construction, and the agent
routinely restates its query terms, so the instrument is measuring something
close to "did the conversation stay on topic."

Citation rate does decline with position (1.9% at positions 1–4, 1.4% at 5–8,
0.0% at 9+), which is the one hint that later details are worth less — but on
n=19 that is noise, and it is reported here only so the next pass knows where to
look. **The honest position is that the metric cannot support a finer
distinction than the one it is failing to show**, and no cap change should be
made on it.

## The bug: the elision stub hid the cap

`_select_details` computed one number, `len(details) - len(matching[:cap])`, and
reported all of it as *"N more claim(s) in this session did not match the
query."* When the cap binds, some of those N **did** match and were truncated.
Reproduced: 12 claims, 10 matching, cap 8 → *"4 more claim(s)… did not match"*
when only 2 did not.

Two costs, and the second is why it belongs in this entry:

1. It told the reader that capped-off matching claims were irrelevant, which is
   the opposite of true, and the stub is precisely the thing lab/007 introduced
   to keep elision *honest*.
2. **It made the cap invisible in the trace.** Nothing in a response
   distinguished "the cap bound here" from "these claims were off-topic", so the
   one number needed to tune the cap was the one number never recorded — which
   is why the 17.2% bind rate had to be reconstructed by replay rather than read
   off the corpus.

Now counted apart: *"4 more claim(s) in this session: 2 matched but exceeded the
8-claim render cap; 2 did not match the query."* The stub still renders no
vertex ID, so the eval loop still never prices a phantom return.

## What would change this conclusion

- A detail-level signal that actually predicts usage. Claim kind is the only
  candidate the data offers; recency, tier, and the claim's own convergence
  count are unmeasured.
- An attribution path for details that is not lexical echo. At 1.4% strong-path
  coverage, the ceiling on any future tuning of this dial is the instrument, not
  the analysis.
