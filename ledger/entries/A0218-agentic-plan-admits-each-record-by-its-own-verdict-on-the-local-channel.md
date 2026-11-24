---
id: A0218-agentic-plan-admits-each-record-by-its-own-verdict-on-the-local-channel
kind: claim
stated: 2026-10-08T00:17:51-07:00
author: main
grade: argued
supersedes: A0208-agentic-plan-admits-each-record-by-its-own-verdict
verbatim_change: pointwise admission holds on the local channel only and ends a claude-channel job as an error before any model call, and the cohort names both channels
verbatim_sha: e09e5d5ebfaaac2b58458e51b569371eb376e809a9aee2f9029ab1b62e36ab00
---

## Assertion

When the worker's environment sets THALAMUS_REFLEX_ADMISSION to pointwise and the job runs on the local channel, the agentic plan serves only records a per-record verdict kept: after a loop that ends on the stop tool or on the turn cap, each row the model was shown is judged by its own model call over the failure, the excerpt and that row alone, the rows the stop named first in its order and the rest in the order shown, until five are kept or every row is judged, and the served records are the kept ones in the order they were judged; a job the worker's clock ends serves what admission had kept by then, or, when admission had not begun, the first five records its calls returned. On the claude channel that value ends the job as an error before any model call. Without that value the plan serves the handles the stop named, in its order, at most five, and runs no verdict.

## Scope

metric: which of a job's returned records the agentic plan serves, and in what order
cohort: agentic plan jobs run by the reflex worker, on either channel
condition: a loop that ends with no tool call runs no admission and serves nothing; one that ends on its own socket deadline serves what its calls returned; a verdict whose answer does not parse keeps nothing

## Grounds

- code: src/thalamus/harness/agentic.py § "run" =sha256:27e6f22ff409346af7187a2b6e3da861a0c4ad31d6b1af4034fb006e77bb73d8
- code: src/thalamus/harness/agentic.py § "pointwise_admission" =sha256:49fda38f1353a5e7fb39ed55579e1e3ff97b65bf4ff1cc3f1e0731d9f1481320
- code: src/thalamus/harness/agentic.py § "admit" =sha256:a858e8e862d43545c0577652f81c97d99ae5ce91bce4b671f658c48eb2c9af41
- code: src/thalamus/harness/agentic.py § "admitted" =sha256:56f43e4acdb4f805e09660bf344a07cbb341518139040e943ef874690deeda7f
- code: src/thalamus/harness/agentic.py § "salvage" =sha256:10aac63ad33798f223f4240d2f9a63fbf8018be6aef973877f7d5b7a8c630c16
- search: corpus=src/thalamus; query="result.kept"; date=2026-10-08

## Warrant

A search of src/thalamus for result.kept finds four assignments — three in run and the worker's JobTimeout handler — and one reader, run_job's loop over the served nodes, so nothing else decides what a job serves. pointwise_admission is true only when ADMISSION_ENV, THALAMUS_REFLEX_ADMISSION, reads pointwise after stripping. run raises ExtractionError before building any prompt when the cli is reached by subprocess — the claude channel — and pointwise_admission is true, and the worker records an ExtractionError as the error outcome. Otherwise, when it is true, run calls admit for a loop stopped by the stop tool or by max_turns and sets kept to admitted, which lists the vertex ids of the verdicts whose keep is true, in verdict order, capped at MAX_KEEP; admit orders the stop's named handles that job.shown holds, then every other handle in job.shown, and for each sends one structured chat whose messages are ADMIT_SYSTEM and admit_prompt over the anchors, the excerpt and that handle's row, returning once MAX_KEEP verdicts are keep. When it is false, a stop sets kept to the vertex ids of the named handles select returned, capped at MAX_KEEP, and admit is never called. salvage returns admitted when admission had begun and returned_in_order otherwise, and it is what the worker's JobTimeout handler assigns to kept.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/agentic.py § "run" =sha256:27e6f22ff409346af7187a2b6e3da861a0c4ad31d6b1af4034fb006e77bb73d8
  artifact: absent
  note: propagated from a withdrawn ground

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/agentic.py § "pointwise_admission" =sha256:49fda38f1353a5e7fb39ed55579e1e3ff97b65bf4ff1cc3f1e0731d9f1481320
  artifact: absent
  note: propagated from a withdrawn ground

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/agentic.py § "admit" =sha256:a858e8e862d43545c0577652f81c97d99ae5ce91bce4b671f658c48eb2c9af41
  artifact: absent
  note: propagated from a withdrawn ground

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/agentic.py § "admitted" =sha256:56f43e4acdb4f805e09660bf344a07cbb341518139040e943ef874690deeda7f
  artifact: absent
  note: propagated from a withdrawn ground

- 2026-10-18T16:14:12-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/agentic.py § "salvage" =sha256:10aac63ad33798f223f4240d2f9a63fbf8018be6aef973877f7d5b7a8c630c16
  artifact: absent
  note: propagated from a withdrawn ground
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/agentic.py § "run" =sha256:27e6f22ff409346af7187a2b6e3da861a0c4ad31d6b1af4034fb006e77bb73d8
  note: src/thalamus/harness/agentic.py moved into the thalamus-reflex plugin package as agentic.py with run unchanged, so the assertion is unaffected
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/agentic.py § "pointwise_admission" =sha256:49fda38f1353a5e7fb39ed55579e1e3ff97b65bf4ff1cc3f1e0731d9f1481320
  note: src/thalamus/harness/agentic.py moved into the thalamus-reflex plugin package as agentic.py with pointwise_admission unchanged, so the assertion is unaffected
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/agentic.py § "admit" =sha256:a858e8e862d43545c0577652f81c97d99ae5ce91bce4b671f658c48eb2c9af41
  note: src/thalamus/harness/agentic.py moved into the thalamus-reflex plugin package as agentic.py with admit unchanged, so the assertion is unaffected
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/agentic.py § "admitted" =sha256:56f43e4acdb4f805e09660bf344a07cbb341518139040e943ef874690deeda7f
  note: src/thalamus/harness/agentic.py moved into the thalamus-reflex plugin package as agentic.py with admitted unchanged, so the assertion is unaffected
- 2026-10-18T16:25:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-reflex/src/thalamus_reflex/agentic.py § "salvage" =sha256:10aac63ad33798f223f4240d2f9a63fbf8018be6aef973877f7d5b7a8c630c16
  note: src/thalamus/harness/agentic.py moved into the thalamus-reflex plugin package as agentic.py with salvage unchanged, so the assertion is unaffected

## References

- docs/cli.md · standing · cites-as-live
- packages/thalamus-reflex/src/thalamus_reflex/agentic.py · standing · cites-as-live
