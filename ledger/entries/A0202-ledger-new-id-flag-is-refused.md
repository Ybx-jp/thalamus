---
id: A0202-ledger-new-id-flag-is-refused
kind: claim
stated: 2026-09-25T01:14:27-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: c5da771a469992a6e44e8d4002ee6cd4b06597cf6995541baea6d2368ce1e5b5
---

## Assertion

In a Claude Code session in this checkout, a Bash command that runs claims-ledger new with --id is refused, so an entry id is always the one new allocates; source add --id, which names a source rather than an entry, is not refused.

## Scope

metric: which claims-ledger invocations the project's ledger-id-guard hook refuses
cohort: Bash commands in Claude Code sessions that load this checkout's .claude/settings.json
condition: covers claims-ledger run directly, by path, through uv run, and as python -m claims_ledger, at a command position; a script that runs the command is not seen, and nothing refuses the flag outside an agent session

## Grounds

- code: .claude/hooks/ledger-id-guard.py § "refuses" =sha256:615159fff04cf0a0d80365a9955d95700a8fd5482e799fdd9f53b00a31eb8d70

## Warrant

refuses parses the command into shell words, finds claims-ledger at a command position, skips its global options to the subcommand, and returns true only when that subcommand is new and --id or --id= appears before the next shell operator; main turns a true into a PreToolUse deny, and a source add invocation never reaches the --id test because its subcommand is not new.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- .claude/hooks/ledger-id-guard.py · standing · cites-as-live
- CLAUDE.md · standing · cites-as-live
- CONTRIBUTING.md · standing · cites-as-live
