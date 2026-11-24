---
id: A0221-claude-print-runs-allowed-mcp-tools-and-denies-the-rest
kind: claim
stated: 2026-10-08T00:20:30-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: f12a247ebde2333593e21560a17af223e3f969ad2b24dfb522903f615e8f6115
---

## Assertion

In a Claude Code print-mode run with no permission host, an allow rule of the form mcp__<server>__* approves every tool of that one server without a prompt, a deny rule naming a tool bare removes it in every permission mode including bypassPermissions, and any other call that would prompt is denied rather than waited on.

## Scope

metric: which tool calls a claude -p run makes without asking, refuses, or denies for want of an answer
cohort: Claude Code's permissions, permission-modes and headless references as retrieved on 2026-10-08
condition: the operator's own allow and ask rules and permission mode still decide the calls these rules do not; not covered: a run with a permission host or --permission-prompt-tool

## Grounds

- source: claude-code-permissions-mcp-allow-globs · §Tool name wildcards
- source: claude-code-permission-modes-deny-rules · §Available modes
- source: claude-code-headless-unattended-denials · §Turn off permission prompts in unattended runs

## Warrant

The permissions reference accepts a tool-name glob in an allow rule after a literal mcp__<server>__ prefix and gives mcp__puppeteer__* as matching every tool of that server. The permission-modes reference says deny rules block in every mode, bypassPermissions included. The headless reference says that in a -p run with no host, a request that would prompt is denied. Together these decide the three cases.

## Backing

- source: claude-code-permissions-mcp-allow-globs · §Tool name wildcards
  speaker: Anthropic
  quote: "Allow rules accept tool-name globs only after a literal `mcp__<server>__` prefix." […] "`mcp__puppeteer__*` matches every tool from the `puppeteer` server" […]
- source: claude-code-permission-modes-deny-rules · §Available modes
  speaker: Anthropic
  quote: […] "Deny rules block in every mode, including `bypassPermissions`." […]
- source: claude-code-headless-unattended-denials · §Turn off permission prompts in unattended runs
  speaker: Anthropic
  quote: […] "In a `-p` run with no host, these requests are denied either way, and the flag also tells Claude not to retry them." […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- packages/thalamus-reflex/src/thalamus_reflex/reflex_channel.py · standing · cites-as-live
