---
id: A0182-reflex-agentic-jobs-end-in-a-recorded-outcome
kind: claim
stated: 2026-09-24T20:35:42-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 2fea977f50178a63a59400866f28e12d230768a325db35707e5604412c38b810
---

## Assertion

An agentic reflex job the worker claims is either left ready for the carrier or recorded in the queue's job ledger with how it ended: session_end, with no model call, when its session is not registered live at the claim or before any model turn; timeout, never empty, when the job's wall clock of 120 seconds from its claim runs out before the plan kept anything; empty when the plan kept nothing; error when the model server or the graph could not be reached. The sweep records died for a claimed job whose worker process is gone, and undelivered or session_end for a ready result or pending job of a session that ended more than the grace period ago.

## Scope

metric: the outcome recorded for each agentic reflex job
cohort: jobs appended to ~/.thalamus/reflex/queue by thalamus reflex and claimed by thalamus reflex --work, or found by its sweep
condition: liveness is read from Claude Code's session registry; a box with no registry directory answers every session live

## Grounds

- code: src/thalamus/harness/reflex_worker.py § "run_job" =sha256:0878ccf71844ae76c24d5c9ca870dead33a4681b4563f3f025dabef1309758a0
- code: src/thalamus/harness/reflex_worker.py § "sweep" =sha256:0b778e68928ce23452f656c6c44ab82f036da6bbe7fe44382dd9e58472acc093
- code: src/thalamus/harness/reflex_worker.py § "DEADLINE_SECONDS" =sha256:e649b0e23db7428d2495066ea3b5f315619c026c813915ab8f4dc450913f9997
- code: src/thalamus/harness/reflex_worker.py § "session_alive" =sha256:765e5adbfa8b1f835e6dfa6b3ed6dd745c9ac699de1b07dce5d8a0f9db2a5172

## Warrant

run_job checks alive before building anything and finishes as session_end; it runs the plan inside _Clock(DEADLINE_SECONDS), whose timer raises JobTimeout, packs what the job returned, and finishes as timeout when nothing resolves, as session_end when the loop's per-turn liveness check ended it, as error on ExtractionError, OSError or RuntimeError, and as empty otherwise when nothing was kept; any other path writes the ready file. sweep writes died for a pending.<pid>.claimed file whose pid is neither this process nor running, and for a session alive answers false, undelivered for each ready file and session_end for a pending file older than the grace period. session_alive answers true when the registry directory is absent.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
