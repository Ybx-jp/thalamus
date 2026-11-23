---
id: A0250-claude-code-records-the-tool-surface-before-the-first-tool-call
kind: claim
stated: 2026-11-23T02:30:00-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 85457f7b979bcbaecf6b36755232299ecd7736a585f6294b8e417d8a6a75ffc2
---

## Assertion

In Claude Code the session transcript does not yet exist when SessionStart and UserPromptSubmit hooks fire, and by the initial PreToolUse hook it holds the harness's record of the tool surface: a deferred_tools_delta attachment listing deferred tools, an api-request-shape record listing the tools sent with the request, or both. A PreToolUse hook output carrying continue false alone lets that call run before the session stops; adding a deny permission decision stops it without running the call; and an additionalContext from a PreToolUse hook reaches the model. The preflight reads the surface from those two records and chooses its outputs on those facts.

## Scope

metric: what a Claude Code hook can read of the tool surface at each event, and what a PreToolUse hook's output does to the call and the session
cohort: Claude Code headless sessions with project-scope hooks on SessionStart, UserPromptSubmit, PreToolUse and Stop
condition: measured on Claude Code 2.1.330, 2026-11-23, claude -p --setting-sources project --model haiku from a scratch directory whose hooks logged the transcript's state at each event. With all tools deferred-eligible (session 52a4c1c8) the transcript was absent at SessionStart and UserPromptSubmit and held one deferred_tools_delta at the first PreToolUse, with connectors arriving in a second delta after it. With --tools Bash and a thalamus --mcp-config (session 42098356) no delta was written and the api-request-shape record before the first PreToolUse listed Bash and 17 thalamus tools. A hook returning continue false alone: the Bash call wrote its file, terminal_reason hook_stopped. The same with permissionDecision deny: the file was not written, the tool result was the deny reason, terminal_reason hook_stopped, exit 0. A hook returning additionalContext with a codeword: the model repeated the codeword.

## Grounds

- code: src/thalamus/harness/preflight.py § "observed_surface" =sha256:1674b8ec4a672acd9a9e6e320e41f56d8f5a0adcff11d476e78284011e4c48cd
- code: src/thalamus/harness/preflight.py § "hook_output" =sha256:1ea533bf964f5949c7b2ba7cf46eb7cc063b5ecaa56726d55ef53ae341af3014

## Warrant

observed_surface reads exactly the two records the probes found before the first tool call, unions what a sequence of deltas adds, and answers None when neither is present, which the tool-surface check reports as undecided rather than empty. hook_output pairs continue false with a deny for an aborting failure, because the first probe showed continue false alone runs the call, and uses additionalContext for a reporting one, which the last probe showed reaching the model. The preflight hook runs on PreToolUse because the earlier events see no transcript.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-11-23T10:53:10-08:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/preflight.py § "hook_output" =sha256:1ea533bf964f5949c7b2ba7cf46eb7cc063b5ecaa56726d55ef53ae341af3014
  artifact: sha256:869a66d845a89ed5ae7dfecbbafa4376f13cdabdd6bb198d540c91d53553e8e7
  note: propagated from a moved ground
- 2026-11-23T10:59:00-08:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/preflight.py § "hook_output" =sha256:869a66d845a89ed5ae7dfecbbafa4376f13cdabdd6bb198d540c91d53553e8e7
  note: hook_output gained a session-start phase, a systemMessage beside the additionalContext, and a told set; an aborting report at the initial tool call still pairs continue false with a deny, and a reporting one still carries additionalContext, so the assertion is unaffected

## References

- src/thalamus/harness/preflight.py · standing · cites-as-live
