---
id: A0192-claude-code-launch-env-reaches-hooks-and-mcp-servers
kind: claim
stated: 2026-09-25T00:39:55-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: c2c705ad38b9d6624e7afbb4f96010f54e5da0cc88df40bb214c2861e4bcb5cd
---

## Assertion

In Claude Code, a variable set by an env prefix on the claude command line reaches every hook process, including hooks fired inside a subagent, and every stdio MCP server process, including servers declared in the frontmatter of the main-thread agent or of a subagent.

## Scope

metric: which child processes of a Claude Code session see a variable the launch put in front of the binary
cohort: Claude Code's hooks and environment-variable references as retrieved on 2026-09-25
condition: measured on Claude Code 2.1.282 in print mode on haiku, `env PROBE_TEMPLATE=<arm> claude -p` against the same command without the prefix: with the prefix the variable was present in PreToolUse and SessionStart hooks of the session and in the PreToolUse hook fired inside a general-purpose subagent (whose payload carried agent_id and agent_type, absent from the session's own), in a stdio server from --mcp-config, and in stdio servers declared in agent frontmatter both under --agent and when that agent ran as a subagent; without it the variable was absent everywhere. Frontmatter servers were skipped outright in a folder whose trust dialog had not been accepted. Not covered: CLAUDE_CODE_SUBPROCESS_ENV_SCRUB set, which strips credential variables from the same processes.

## Grounds

- source: claude-code-subprocess-environment · §Common input fields
- source: claude-code-subprocess-environment · §Environment variables

## Warrant

The hooks reference says a hook process inherits the parent environment apart from the OTEL exporter variables and, under the scrub setting, credential variables. The scrub setting's own row names MCP stdio servers among the subprocess environments it strips credentials from, which places those servers' environments under the same inheritance the hooks get. The measurement shows the rule holds for an arbitrary variable in both kinds of process, inside subagents too.

## Backing

- source: claude-code-subprocess-environment · §Common input fields
  speaker: Anthropic
  quote: "A hook process inherits the parent environment, apart from the `OTEL_*` exporter variables" […]
- source: claude-code-subprocess-environment · §Environment variables
  speaker: Anthropic
  quote: […] "strip credentials from subprocess environments (Bash tool, hooks, MCP stdio servers)" […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
