---
id: A0168-claude-code-hook-stop-and-prompt-id
kind: claim
stated: 2026-09-24T02:17:04-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 79945f82ab5095d0548623ff59bff13bb4ed8db924f37b66e675092f04d59cd9
---

## Assertion

In Claude Code, a hook's input carries a prompt_id naming the user prompt being processed, and a PostToolBatch hook that returns continue false stops the agentic loop before the next model call, showing its stopReason to the user and leaving it in the conversation. The transcript a hook is pointed at is written asynchronously and may lag the current turn.

## Scope

metric: what a Claude Code hook can key a per-prompt count on, how it stops a prompt, and how current the transcript it reads is
cohort: Claude Code's hooks reference as retrieved on 2026-09-24
condition: prompt_id requires Claude Code 2.1.196 or later; says nothing about other harnesses

## Grounds

- source: claude-code-hooks-budget · §Common input fields
- source: claude-code-hooks-budget · §JSON output
- source: claude-code-hooks-budget · §PostToolBatch decision control

## Warrant

The common input fields define prompt_id as the id of the prompt being processed and warn that the transcript may lag; the JSON output table defines continue false and stopReason for every event; the PostToolBatch section says continue false stops the loop before the next model call.

## Backing

- source: claude-code-hooks-budget · §Common input fields
  speaker: Anthropic
  quote: […] "UUID identifying the user prompt currently being processed." […]
- source: claude-code-hooks-budget · §Common input fields
  speaker: Anthropic
  quote: […] "The transcript file is written asynchronously and may lag the in-memory conversation" […]
- source: claude-code-hooks-budget · §PostToolBatch decision control
  speaker: Anthropic
  quote: […] "stops the agentic loop before the next model call."

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
