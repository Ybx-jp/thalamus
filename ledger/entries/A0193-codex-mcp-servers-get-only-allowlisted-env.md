---
id: A0193-codex-mcp-servers-get-only-allowlisted-env
kind: claim
stated: 2026-09-25T00:39:55-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 8a5793fffa27d9d4b29803b76c504f1b53453071ecc0f0b2a88f07773533415e
---

## Assertion

In codex, a stdio MCP server does not inherit codex's environment: it is started with a fixed allowlist of variables plus its own env table and the variables its env_vars list forwards, so a variable set by an env prefix on the codex command line reaches the server only when env_vars names it.

## Scope

metric: which variables a codex stdio MCP server process starts with
cohort: codex's MCP documentation as retrieved on 2026-09-25, for codex-cli 0.154.0
condition: measured on codex-cli 0.154.0 with codex exec, a logging server armed by -c overrides: with `env PROBE_TEMPLATE=<arm>` in front the server saw eight variables (HOME LANG LOGNAME PATH SHELL TERM USER and PROBE_CONTROL from its env table) and not PROBE_TEMPLATE, the same set as the control without the prefix; adding `env_vars=["PROBE_TEMPLATE","THALAMUS_SCOPE"]` delivered both. The operator's installed thalamus server entry, under `env THALAMUS_SCOPE=qe codex exec --profile thalamus-qe`, started without THALAMUS_SCOPE (#289). A subagent's own server process got the same filtered set.

## Grounds

- source: codex-mcp-stdio-env · §STDIO servers

## Warrant

The STDIO servers section gives a server two environment fields, env for variables to set and env_vars for variables to allow and forward; a variable has to be allowed to be forwarded, which is the allowlist the measurement observed, and the measurement shows an unlisted prefix variable is dropped.

## Backing

- source: codex-mcp-stdio-env · §STDIO servers
  speaker: OpenAI
  quote: […] "`env_vars` (optional): Environment variables to allow and forward." […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
