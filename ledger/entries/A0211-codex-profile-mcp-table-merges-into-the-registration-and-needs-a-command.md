---
id: A0211-codex-profile-mcp-table-merges-into-the-registration-and-needs-a-command
kind: claim
stated: 2026-09-29T00:30:21-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 7049fc3c60ab3936940c7f131c5f32c28a3e8c548099c1caf54145335e968e25
---

## Assertion

In codex, an mcp_servers table in a profile file merges into the table of the same name in config.toml key by key, so a profile can add env_vars to a registered server and leave its command, args and env standing; a stdio server table that ends up with no command stops codex at startup.

## Scope

metric: how a profile's mcp_servers table combines with config.toml's, and what a table with no command does
cohort: codex's configuration documentation as retrieved on 2026-09-25, for codex-cli 0.154.0
condition: measured 2026-09-29 on codex-cli 0.154.0 with codex exec and no credentials: a profile carrying only `[mcp_servers.thalamus] env_vars=[…]` over a config.toml registered by `codex mcp add` started the server with the registered command and env plus the listed variables; the same profile in a CODEX_HOME with no registration exited 1 with `Error loading config.toml: invalid transport in mcp_servers.thalamus`, while the same launch without the profile started normally.

## Grounds

- source: codex-mcp-stdio-env · §STDIO servers
- source: codex-config-precedence · §Configuration precedence

## Warrant

The configuration precedence section layers profile files between the command line and the user config.toml, which the measurement shows combine per key within one server table; the STDIO servers section marks command as required, which is the field a profile table with nothing beneath it lacks.

## Backing

- source: codex-mcp-stdio-env · §STDIO servers
  speaker: OpenAI
  quote: […] "`command` (required): The command that starts the server." […]
- source: codex-config-precedence · §Configuration precedence
  speaker: OpenAI
  quote: […] "[Profile](https://learn.chatgpt.com/docs/config-file/config-advanced#profiles) files selected with `--profile profile-name` (`~/.codex/profile-name.config.toml`)" […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/pin.py · standing · cites-as-live
