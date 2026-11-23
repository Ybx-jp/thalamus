---
id: A0251-an-autonomous-preflight-stops-the-run-an-attended-one-reports
kind: claim
stated: 2026-11-23T02:30:01-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 62fcc99a298a52461bdb44dadcfa95f2c1d32fcfb46bd12c0830e4af8ac89039
---

## Assertion

The preflight runs five checks: tool surface, hooks runnable, guards armed, budget and write path, of which hooks runnable is advisory. For an autonomous session any other check that did not pass, including one that could not be decided, fails the preflight, and the hook output denies the call and stops the run. For an attended session only a check that failed fails it, and the hook output gives the failures and any failed advisory check to the session as additional context and lets the call proceed. An advisory check never fails the preflight.

## Scope

metric: which check outcomes fail the preflight, and what the hook output does on a failure
cohort: preflight reports built by harness/preflight.run, by session type
condition: the report and the hook output; repeating the result on later calls is the hook script's and is outside this claim

## Grounds

- code: src/thalamus/harness/preflight.py § "run" =sha256:1551801a96534245a37c1c5c7ede41027430f2f543ac0fc17004f12351fdf70f
- code: src/thalamus/harness/preflight.py § "Report" =sha256:a203362346cf6afa1b4c3e686f669ac3eaf48e8bc9878614532c4d0a9111607d
- code: src/thalamus/harness/preflight.py § "hook_output" =sha256:1ea533bf964f5949c7b2ba7cf46eb7cc063b5ecaa56726d55ef53ae341af3014

## Warrant

run builds the report from the five checks, and check_hooks_runnable marks its check advisory. Report.aborts is true for an autonomous session, and Report.failures then takes every non-advisory check whose ok is not True, so an undecided None counts; for an attended session it takes only non-advisory ok False. hook_output returns continue false with a deny permission decision when an aborting report has failures; otherwise, for an attended report, an additionalContext with no continue key naming its failures and failed advisories, and nothing when there are none.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-11-23T10:58:00-08:00 · superseded · grade: measured · author: main
  evidence: entry: A0253-an-attended-preflight-tells-the-operator-at-session-start · supersedes
  note: An attended session is now also preflighted at session start, on every check but the tool surface, and an attended report reaches the operator as a system message as well as the session as context, with the initial tool call leaving out what the session-start run reported. The checks, which outcomes fail, and the autonomous abort are unchanged.

## References
