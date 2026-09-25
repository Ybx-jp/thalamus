---
id: A0188-claude-code-posttoolbatch-context-reaches-the-next-request
kind: claim
stated: 2026-09-24T19:11:58-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 171574f43e3b62a9b8540a1221642ef153493b4d8af549fa24127b0f85f41ab0
---

## Assertion

In Claude Code, a PostToolBatch hook may return additionalContext, which is injected once before the next model call.

## Scope

metric: what a Claude Code PostToolBatch hook can put in front of the model without stopping the loop
cohort: Claude Code's hooks reference as retrieved on 2026-09-24
condition: measured on Claude Code 2.1.282 in print mode on haiku: with a one-turn cap, the budget hook's additionalContext at the first batch was followed by a text answer and no further tool call, where the uncapped control ran all three requested calls

## Grounds

- source: claude-code-hooks-posttoolbatch-context · §PostToolBatch decision control

## Warrant

The PostToolBatch decision control section lists additionalContext among the fields a PostToolBatch hook can return and defines it as a context string injected once before the next model call.

## Backing

- source: claude-code-hooks-posttoolbatch-context · §PostToolBatch decision control
  speaker: Anthropic
  quote: […] "Context string injected once before the next model call." […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/budget.py · standing · cites-as-live
