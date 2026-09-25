---
id: A0160-claude-code-routes-a-nonzero-bash-exit-to-posttoolusefailure
kind: claim
stated: 2026-09-23T23:39:18-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 1d64350c29790cc519750888189640ec440e3ba4510565899949b8d5be8f61de
---

## Assertion

In Claude Code, a Bash tool call whose command exits with a failing status is a failed tool call: it runs PostToolUseFailure hooks, whose input carries an error string that opens with the exit status and then holds the command's output, and a hook there can return additionalContext to the agent.

## Scope

metric: which hook event a Bash call that ran and exited non-zero reaches, and what that event's input and output carry
cohort: Claude Code's hooks as its reference documented them on 2026-09-23
condition: does not cover calls rejected before execution, which reach neither event, or other harnesses

## Grounds

- source: claude-code-hooks-posttoolusefailure · §PostToolUseFailure

## Warrant

The reference defines PostToolUseFailure as the event for a tool that started executing and failed, states that for Bash a command that ran and exited produces an error whose first line is the exit code followed by its output, and lists additionalContext among the fields a hook on it may return. A Bash call that exits non-zero is therefore delivered to PostToolUseFailure, and a hook wired only on PostToolUse does not see it.

## Backing

- source: claude-code-hooks-posttoolusefailure · §PostToolUseFailure
  speaker: Anthropic
  quote: "Runs when a tool that started executing fails: the tool threw an error, or an MCP tool returned an error result."
- source: claude-code-hooks-posttoolusefailure · §PostToolUseFailure input
  speaker: Anthropic
  quote: […] "For Bash and PowerShell, a command that ran and exited produces a first line `Exit code N`, then any output the command produced as one block with stdout and stderr interleaved" […]
- source: claude-code-hooks-posttoolusefailure · §PostToolUseFailure decision control
  speaker: Anthropic
  quote: […] "`PostToolUseFailure` hooks can provide context to Claude after a tool failure."

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/hooks/claude-code/reflex.sh · standing · cites-as-live
