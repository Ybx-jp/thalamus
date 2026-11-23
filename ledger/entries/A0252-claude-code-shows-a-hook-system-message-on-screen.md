---
id: A0252-claude-code-shows-a-hook-system-message-on-screen
kind: claim
stated: 2026-11-23T10:51:51-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 3b6c10b5e098b38588397563c015fa9cabaafb2e1cdb80bf67b8b58c80ed9b10
---

## Assertion

In an interactive Claude Code session a hook output's systemMessage is drawn in the terminal for the user to read: a SessionStart hook's appears under the session banner before the user has typed a prompt, and a PreToolUse hook's appears under the tool call it fired on. The same hooks returning additionalContext and no systemMessage drew nothing on screen. The attended preflight reaches the operator through systemMessage, from session-start.sh at session start and from the PreToolUse hook at the initial tool call.

## Scope

metric: what a SessionStart and a PreToolUse hook's output puts on the interactive terminal screen, and when
cohort: interactive Claude Code sessions in a terminal, hooks loaded from project settings
condition: measured on Claude Code 2.1.330, 2026-11-23, claude --setting-sources project --model haiku launched in a detached 120-column tmux pane from a scratch directory, the pane read with tmux capture-pane. With both hooks returning a systemMessage codeword plus an additionalContext codeword, the screen showed SessionStart:startup says: and the codeword above the empty prompt before any input, and PreToolUse:Bash says: and its codeword under the Bash call. A control launched the same way with the hooks returning only the additionalContext codewords showed neither codeword at either point. The preflight itself was then run the same way with this repository's session-start.sh and preflight.sh wired: its session-start notice was on screen before the prompt, and the initial tool call drew only the tool-surface finding.

## Grounds

- code: src/thalamus/harness/preflight.py § "hook_output" =sha256:869a66d845a89ed5ae7dfecbbafa4376f13cdabdd6bb198d540c91d53553e8e7
- code: src/thalamus/harness/hooks/claude-code/session-start.sh § "operator_notice" =sha256:0e54ed6d1356f160978a514c77c023911caea14a46cfcb06cc43c0ade857b598

## Warrant

hook_output puts an attended report's findings in a systemMessage beside the additionalContext, because the probes showed the systemMessage drawn on screen and the additionalContext alone drawn nowhere, so the operator would otherwise never see them. session-start.sh passes the session-start report's systemMessage through as its own output's systemMessage, which the probe showed on screen before the prompt.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/preflight.py · standing · cites-as-live
- src/thalamus/harness/hooks/claude-code/session-start.sh · standing · cites-as-live
