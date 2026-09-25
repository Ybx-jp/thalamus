---
id: A0203-claude-code-hook-stdin-is-a-socket
kind: claim
stated: 2026-09-25T01:23:52-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 4bcaabbbd27835631c302be638576c4387e9d6c47a09cc6c4f346387a746eb77
---

## Assertion

Claude Code hands a command hook its JSON input on stdin, and on Linux that descriptor is a socket: a hook that reopens it by path, through /dev/stdin, fails with ENXIO before reading anything, where a hook that reads the inherited descriptor, as cat does, receives the whole input.

## Scope

metric: whether a Claude Code command hook can read its input by reopening /dev/stdin
cohort: Claude Code's hooks reference as retrieved on 2026-09-25, and command hooks run by Claude Code 2.1.281 and 2.1.282 on Linux
condition: measured over the operator's transcripts on 2026-09-25: reflex-pointer-tap.sh, reading `$(</dev/stdin)`, recorded a hook error on all 2,448 of its PostToolUse and PostToolUseFailure runs, each reading `/dev/stdin: No such device or address`, while reflex.sh, reading `$(cat)`, ran on the same Bash calls; the reference names stdin and not the kind of descriptor, and does not cover macOS or Windows

## Grounds

- source: claude-code-hooks-stdin · §Hook input and output

## Warrant

The reference states that a command hook receives its JSON on stdin. Opening /proc/self/fd/0 fails with ENXIO when the descriptor is a socket and succeeds on a pipe or a file, and the measurement in the condition is the same payload read two ways on the same calls, one of which failed every time with that error; so the descriptor is a socket, and only a read of the descriptor itself receives the input.

## Backing

- source: claude-code-hooks-stdin · §Hook input and output
  speaker: Anthropic
  quote: "Command hooks receive JSON data via stdin and communicate results through exit codes, stdout, and stderr." […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
