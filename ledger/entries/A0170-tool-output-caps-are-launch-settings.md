---
id: A0170-tool-output-caps-are-launch-settings
kind: claim
stated: 2026-09-24T02:17:05-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 8164d03b21af79f80778f8439741ed8092dce1c4dc3209ef1b5fc4532e7cf58d
---

## Assertion

Claude Code caps a tool result's size from three environment variables — BASH_MAX_OUTPUT_LENGTH in characters for Bash, MAX_MCP_OUTPUT_TOKENS for MCP tools and CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS for file reads — and codex from its tool_output_token_limit configuration key.

## Scope

metric: where each harness reads its tool-result size cap from
cohort: Claude Code's environment variables reference and codex's config reference, retrieved 2026-09-24
condition: Claude Code ignores BASH_MAX_OUTPUT_LENGTH when the bashOutputMaxChars setting is set

## Grounds

- source: tool-output-caps · §Environment variables
- source: tool-output-caps · §codex config reference

## Warrant

The environment variables table defines each of the three variables as the limit for its tool family, with Bash's counted in characters and capped at 150000; the codex config reference lists tool_output_token_limit as the token budget for an individual tool output.

## Backing

- source: tool-output-caps · §Environment variables
  speaker: Anthropic
  quote: […] "Maximum number of characters of bash output that Claude Code reads back into a command's result (default: 30000; maximum: 150000)." […]
- source: tool-output-caps · §Environment variables
  speaker: Anthropic
  quote: […] "Maximum number of tokens allowed in MCP tool responses." […]
- source: tool-output-caps · §codex config reference
  speaker: OpenAI
  quote: […] "Token budget for storing individual tool/function outputs in history." […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
