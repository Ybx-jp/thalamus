---
id: A0223-reflex-claude-channel-runs-claude-print-with-four-fixed-settings
kind: claim
stated: 2026-10-08T00:20:30-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: adfcb883daa5bc02132c36d57f5a5717cebe1d12dc9a9ffb8b9e5f1d1a1cbd49
---

## Assertion

A claude-channel reflex job runs as one claude -p in the triggering agent's working directory, or in its own temporary directory when that one is gone, with THALAMUS_SANDBOX in its environment, --no-session-persistence, the vocabulary allowed as mcp__reflex__*, Bash, Edit, Write, NotebookEdit, WebFetch and WebSearch denied, and the plan's prompt appended to Claude Code's own system prompt; it passes no flag that replaces the operator's settings, MCP servers, tool set or permission mode. So every Thalamus hook it fires declines, it leaves no transcript, it may call the vocabulary without a prompt, and it can neither change files nor fetch pages in any permission mode.

## Scope

metric: the argv, environment and working directory of a claude-channel job's claude -p, and what follows from them
cohort: agentic reflex jobs the worker runs on the claude channel
condition: rests on Claude Code's documented behaviour for each flag (A0219, A0220, A0221) and on the launch environment reaching hooks (A0192); measured on Claude Code 2.1.294 with haiku, a live job left no transcript and no hook record under its session id, and called the vocabulary through the relay to its stop

## Grounds

- code: src/thalamus/harness/reflex_channel.py § "command" =sha256:2bbf94c55931ae8672536742ac621e70994de8564c01c8c18bac7cec3a151697
- code: src/thalamus/harness/reflex_channel.py § "DENIED_TOOLS" =sha256:e55e63cb86b24576b2c3ba95b789b549f178aa5c24d89030457800d22a5bbf6b
- code: src/thalamus/harness/reflex_channel.py § "run_loop" =sha256:1e3004636982992503cdc3aecb4dd3175358458a85886da6c7a1201656127f99
- entry: A0219-claude-print-without-session-persistence-saves-no-session · cites-as-live
- entry: A0220-claude-print-loads-the-operators-configuration · cites-as-live
- entry: A0221-claude-print-runs-allowed-mcp-tools-and-denies-the-rest · cites-as-live
- entry: A0192-claude-code-launch-env-reaches-hooks-and-mcp-servers · cites-as-live
- search: corpus=src/thalamus/harness/reflex_channel.py; query="--permission-mode"; date=2026-10-08

## Warrant

command returns the CLI row's print argv followed by --no-session-persistence, --max-turns, an --mcp-config naming one stdio server, reflex, that runs thalamus reflex --job-tools on the job's directory, --allowedTools mcp__reflex__*, --disallowedTools with DENIED_TOOLS joined, and --append-system-prompt; it passes none of --bare, --strict-mcp-config, --setting-sources, --tools, --system-prompt or --permission-mode, and a search of the module for --permission-mode finds nothing, as do searches for the others but --bare, which appears only in command's docstring. run_loop starts it with sandbox_env, which adds THALAMUS_SANDBOX to the worker's environment, in the job's cwd when that is a directory and its own temporary directory otherwise. The launch environment reaches every hook (A0192), every Thalamus hook exits at its sandbox guard, and a -p run without --bare runs the operator's hooks (A0220); the flag saves no session (A0219); the allow glob approves the server's tools and a bare deny holds in every mode (A0221).

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/reflex_channel.py · standing · cites-as-live
