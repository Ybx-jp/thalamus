---
id: A0257-claude-code-applies-hook-edits-to-the-running-session
kind: claim
stated: 2026-11-23T16:03:24-08:00
author: main
grade: argued
supersedes: none
verbatim_sha: 988cc4aaf21a807b858085ef19b9b1c1d9cbfcfac2bc9800e52386ad477dd5e1
---

## Assertion

Claude Code watches its settings files and reloads them on change, so an edit to the hooks in user, project or local settings reaches a session that is already running, with no relaunch and no /clear.

## Scope

metric: whether a hook added, removed or repointed in a settings file runs on the next matching event of a session started before the edit
cohort: Claude Code's settings files as its reference documented them on 2026-11-23
condition: does not cover MCP servers, which are not settings, keys the reference lists as read once at session start, managed settings delivered by MDM or the console, or other harnesses

## Grounds

- source: claude-code-settings-when-edits-take-effect · §When edits take effect

## Warrant

The reference states that Claude Code watches the settings files and applies most edits to the running session without a restart, names hooks among the keys that reload, extends the reload to user, project and local settings, and lists the keys that wait for a restart without naming hooks among them. A hook edit in any of those files therefore reaches the open session.

## Backing

- source: claude-code-settings-when-edits-take-effect · §When edits take effect
  speaker: Anthropic
  quote: "Claude Code watches your settings files and reloads them when they change, so it applies most edits to the running session without a restart, including edits to `permissions`, `hooks`, and credential helpers such as `apiKeyHelper`."
- source: claude-code-settings-when-edits-take-effect · §When edits take effect
  speaker: Anthropic
  quote: "The reload covers user, project, local, and managed settings."
- source: claude-code-settings-when-edits-take-effect · §When edits take effect
  speaker: Anthropic
  quote: "Claude Code reads some keys only once, at session start, so an edit to one of them doesn't reach the running session."

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
- README.md · standing · cites-as-live
- docs/console.md · standing · cites-as-live
- docs/getting-started.md · standing · cites-as-live
- packages/thalamus-console/src/thalamus_console/server.py · standing · cites-as-live
- src/thalamus/harness/install.py · standing · cites-as-live
- src/thalamus/harness/preflight.py · standing · cites-as-live
