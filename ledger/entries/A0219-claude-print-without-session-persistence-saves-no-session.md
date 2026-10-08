---
id: A0219-claude-print-without-session-persistence-saves-no-session
kind: claim
stated: 2026-10-08T00:20:29-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 355275f922d408d93680011783fd395fb0002b2c0bfdbedf2bca84a67e925808
---

## Assertion

In Claude Code, a print-mode run given --no-session-persistence does not save its session to disk, so it leaves no transcript under the projects directory for a later reader to find.

## Scope

metric: whether a claude -p run leaves a session transcript on disk
cohort: Claude Code's CLI reference as retrieved on 2026-10-08
condition: measured on Claude Code 2.1.294 in print mode on haiku, the same one-turn prompt with and without the flag: without it the run's session id named one transcript file under ~/.claude/projects, with it none. Not covered: interactive sessions, where the flag does not apply.

## Grounds

- source: claude-code-cli-no-session-persistence · §CLI flags

## Warrant

The CLI reference's row for the flag says it disables session persistence so that sessions are not saved to disk, in print mode only. The session transcript is what Claude Code saves to disk for a session, so a run under the flag leaves none; the measurement shows the transcript present without the flag and absent with it on the installed version.

## Backing

- source: claude-code-cli-no-session-persistence · §CLI flags
  speaker: Anthropic
  quote: […] "Disable session persistence so sessions are not saved to disk and cannot be resumed. Print mode only." […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/reflex_channel.py · standing · cites-as-live
