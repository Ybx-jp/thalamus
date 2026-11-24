---
id: A0253-an-attended-preflight-tells-the-operator-at-session-start
kind: claim
stated: 2026-11-23T10:51:57-08:00
author: main
grade: measured
supersedes: A0251-an-autonomous-preflight-stops-the-run-an-attended-one-reports
verbatim_change: the preflight gained a session-start phase run for attended sessions without the tool surface, and an attended report now reaches the operator as a system message as well as the session as context, with the initial tool call leaving out what the session-start run reported
verbatim_sha: 88a31ed3f6c42f435721d6dce0f78f8e55ea1fbce40af232edef08a9bf6fc9c1
---

## Assertion

The preflight runs in two phases. At the initial tool call it runs five checks: tool surface, hooks runnable, guards armed, budget and write path; at session start it runs the same checks less the tool surface, and session-start.sh runs that phase for an attended session only. Hooks runnable is advisory and never fails the preflight. For an autonomous session any other check that did not pass, including one that could not be decided, fails it, and at the initial tool call the hook output denies the call and stops the run. For an attended session only a check that failed fails it, and the hook output gives the failures and any failed advisory check to the session as additional context and to the operator as a system message, at the initial tool call leaving out any finding the session-start run already reported, and lets the session proceed.

## Scope

metric: which checks each phase runs, which outcomes fail the preflight, and what the hook output does on a failure
cohort: preflight reports built by harness/preflight.run, by session type and phase
condition: the report, the hook output and the session-start wiring; repeating the result on later tool calls is preflight.sh's and is outside this claim

## Grounds

- code: src/thalamus/harness/preflight.py § "run" =sha256:a15ebe3fda5583d1e6b866221ed2d8d996db9cd047e8d463e050da826973e12b
- code: src/thalamus/harness/preflight.py § "Report" =sha256:8b1d4cca4be4250fbd925cde4ecd295a3e012b2524bfc148d52f88a0837b432c
- code: src/thalamus/harness/preflight.py § "hook_output" =sha256:869a66d845a89ed5ae7dfecbbafa4376f13cdabdd6bb198d540c91d53553e8e7
- code: src/thalamus/harness/preflight.py § "told_at_start" =sha256:f89ae5f544d5890c8f1fcfc3bb7e5b5cd6e5366b1a8cf6c542648d8ee6de0d24
- code: src/thalamus/harness/hooks/claude-code/session-start.sh § "operator_notice" =sha256:0e54ed6d1356f160978a514c77c023911caea14a46cfcb06cc43c0ade857b598

## Warrant

run builds the report from the five checks at the first-tool-call phase and drops the tool surface at the session-start phase, and check_hooks_runnable marks its check advisory. Report.aborts is true for an autonomous session, and Report.failures then takes every non-advisory check whose ok is not True, so an undecided None counts; for an attended session it takes only non-advisory ok False. hook_output returns continue false with a deny permission decision for an aborting report with failures at the initial tool call, nothing for an autonomous report at session start, and otherwise, for an attended report, a systemMessage and an additionalContext under the phase's hook event naming each failure and failed advisory whose name and detail are not in the told set; told_at_start reads that set from the session-start record, as the CLI passes it at the initial tool call. session-start.sh calls the session-start phase only when the session type is attended.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-11-23T13:18:00-08:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/preflight.py § "told_at_start" =sha256:f89ae5f544d5890c8f1fcfc3bb7e5b5cd6e5366b1a8cf6c542648d8ee6de0d24
  artifact: sha256:ff9f8d25412a8d2dd66daff07f4d5d56e05ca3a7cd7a2cf2b472466bed5ab418
  note: propagated from a moved ground
- 2026-11-23T13:20:00-08:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/preflight.py § "told_at_start" =sha256:ff9f8d25412a8d2dd66daff07f4d5d56e05ca3a7cd7a2cf2b472466bed5ab418
  note: told_at_start now reads a start record of the wrong shape as no record (#404) instead of raising; a well-formed record still yields the name and detail of each failed check, so the assertion is unaffected
- 2026-11-23T16:06:02-08:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/preflight.py § "hook_output" =sha256:869a66d845a89ed5ae7dfecbbafa4376f13cdabdd6bb198d540c91d53553e8e7
  artifact: sha256:60e19dbaec94fd437a8bae726d614ab935a9a9564d7a219d514d0f468c434cb9
  note: propagated from a moved ground
- 2026-11-23T16:10:00-08:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/preflight.py § "hook_output" =sha256:60e19dbaec94fd437a8bae726d614ab935a9a9564d7a219d514d0f468c434cb9
  note: hook_output's closing repair sentence moved into the module constant _REPAIR and now says a hook fixed in its settings file reaches the session on save; the outputs it chooses and the fields each carries are unchanged, so the assertion is unaffected

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/harness/preflight.py · standing · cites-as-live
- src/thalamus/harness/hooks/claude-code/session-start.sh · standing · cites-as-live
