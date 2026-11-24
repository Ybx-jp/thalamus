---
id: A0220-claude-print-loads-the-operators-configuration
kind: claim
stated: 2026-10-08T00:20:30-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 63a5411cc93bade3e64f7b52a0635caee369f07b85bbb31cb9a0faeafaadb264
---

## Assertion

In Claude Code, a print-mode run without --bare loads the same configuration an interactive session would, from the working directory and from ~/.claude, and runs the hooks it finds there, so the operator's user-scope hooks fire in it.

## Scope

metric: which configuration and hooks a claude -p run loads
cohort: Claude Code's headless reference as retrieved on 2026-10-08
condition: measured on Claude Code 2.1.294 in print mode on haiku with --no-session-persistence, the same one-turn prompt with and without THALAMUS_SANDBOX in its environment: without it the operator's user-scope SessionEnd hook wrote its log for that run's session id and the pin hook recorded it, with it neither did. Not covered: --bare runs, which skip hook discovery.

## Grounds

- source: claude-code-headless-print-loads-configuration · §Start faster with bare mode

## Warrant

The headless reference says that without --bare a -p run loads the same context an interactive session would, including what is configured in the working directory or ~/.claude, and that it runs a project's hooks without a trust prompt. Hooks configured in ~/.claude are therefore armed in such a run; the measurement shows the user-scope SessionEnd hook firing for a -p run and declining when the run carries the sandbox marker its guard reads.

## Backing

- source: claude-code-headless-print-loads-configuration · §Start faster with bare mode
  speaker: Anthropic
  quote: […] "Without it, `claude -p` loads the same [context](/docs/en/how-claude-code-works#the-context-window) an interactive session would, including anything configured in the working directory or `~/.claude`."
- source: claude-code-headless-print-loads-configuration · §Start faster with bare mode
  speaker: Anthropic
  quote: "Without `--bare`, a `-p` session runs the hooks in a project's `.claude/settings.json` and connects the servers in its `.mcp.json`, even in a folder you've never trusted." […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- packages/thalamus-reflex/src/thalamus_reflex/reflex_channel.py · standing · cites-as-live
