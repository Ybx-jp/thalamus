---
id: A0208-agentic-plan-admits-each-record-by-its-own-verdict
kind: claim
stated: 2026-09-28T17:10:50-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 6113482ddf3102b899e7b867febfd151fbe0e234cb42b5fd8e20945d05297b33
---

## Assertion

When the worker's environment sets THALAMUS_REFLEX_ADMISSION to pointwise, the agentic plan serves only records a per-record verdict kept: after a loop that ends on the stop tool or on the turn cap, each row the model was shown is judged by its own model call over the failure, the excerpt and that row alone, the rows the stop named first in its order and the rest in the order shown, until five are kept or every row is judged, and the served records are the kept ones in the order they were judged; a job the worker's clock ends serves what admission had kept by then, or, when admission had not begun, the first five records its calls returned. Without that value the plan serves the handles the stop named, in its order, at most five, and runs no verdict.

## Scope

metric: which of a job's returned records the agentic plan serves, and in what order
cohort: agentic plan jobs run by the reflex worker
condition: a loop that ends with no tool call runs no admission and serves nothing; one that ends on its own socket deadline serves what its calls returned; a verdict whose answer does not parse keeps nothing

## Grounds

- code: src/thalamus/harness/agentic.py § "run" =sha256:89f4ac0eb02a12277dcc0ee3ec6b2142835c4e25eace9e18527b00d9b1f59c94
- code: src/thalamus/harness/agentic.py § "pointwise_admission" =sha256:49fda38f1353a5e7fb39ed55579e1e3ff97b65bf4ff1cc3f1e0731d9f1481320
- code: src/thalamus/harness/agentic.py § "admit" =sha256:ad009fbd5d8c6c8297050be822b94f423718aeeb3ed37684816afefa998afa52
- code: src/thalamus/harness/agentic.py § "admitted" =sha256:56f43e4acdb4f805e09660bf344a07cbb341518139040e943ef874690deeda7f
- code: src/thalamus/harness/agentic.py § "salvage" =sha256:10aac63ad33798f223f4240d2f9a63fbf8018be6aef973877f7d5b7a8c630c16
- search: corpus=src/thalamus; query="result.kept"; date=2026-09-28

## Warrant

A search of src/thalamus for result.kept finds four assignments — three in run and the worker's JobTimeout handler — and one reader, run_job's loop over the served nodes, so nothing else decides what a job serves. pointwise_admission is true only when ADMISSION_ENV, THALAMUS_REFLEX_ADMISSION, reads pointwise after stripping. When it is true, run calls admit for a loop stopped by the stop tool or by max_turns and sets kept to admitted, which lists the vertex ids of the verdicts whose keep is true, in verdict order, capped at MAX_KEEP; admit orders the stop's named handles that job.shown holds, then every other handle in job.shown, and for each sends one structured chat whose messages are ADMIT_SYSTEM and admit_prompt over the anchors, the excerpt and that handle's row, returning once MAX_KEEP verdicts are keep. When it is false, a stop sets kept to the vertex ids of the named handles select returned, capped at MAX_KEEP, and admit is never called. salvage returns admitted when admission had begun and returned_in_order otherwise, and it is what the worker's JobTimeout handler assigns to kept.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/agentic.py · standing · cites-as-live
