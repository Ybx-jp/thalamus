---
id: A0201-claude-code-subagent-hooks-run-with-the-sessions-persona-env
kind: claim
stated: 2026-09-25T00:50:10-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: ccc6ae8edade5737be3ddfbf3e8814164ba86fec4b14abc6187fde878e3585e2
---

## Assertion

In Claude Code a hook fired inside a subagent runs with the session's environment, so CLAUDE_CODE_AGENT there still names the persona the session was launched with; only the payload's agent_type and agent_id name the subagent. The Claude Code thalamus_resolve_scope reads the payload's agent_type before CLAUDE_CODE_AGENT, so a subagent whose type is an expert's agent resolves to that expert and any other subagent resolves to the session's own pin.

## Scope

metric: what a Claude Code hook fired inside a subagent can read about which agent it runs for, and the scope the hook library resolves from it
cohort: Claude Code hooks sourcing the claude-code resolve-scope.sh
condition: measured on Claude Code 2.1.282, 2026-09-25: `env PROBE_TPL=tpl-X claude -p --agent probe-scope--tpl-a` with a --settings overlay wiring a PreToolUse Bash hook that recorded its payload and environment, one Bash call on the main thread and one inside a general-purpose subagent. The main thread's payload carried agent_type probe-scope--tpl-a and no agent_id; the subagent's carried agent_id adddc3f725fd89669 and agent_type general-purpose; both hooks' environments held CLAUDE_CODE_AGENT=probe-scope--tpl-a and PROBE_TPL=tpl-X.

## Grounds

- code: src/thalamus/harness/hooks/claude-code/resolve-scope.sh § "thalamus_guard_command" =sha256:35b5128e1a17a6dfbb743179cd5b16e5b45e990b9f8d5c66427842d3a549df94
- entry: A0174-claude-code-subagent-hooks-name-the-launchers-transcript · cites-as-live

## Warrant

The ground is the section opened by the file's last top-level assignment, which runs to the end of the file and holds thalamus_resolve_scope; the code section pattern splits shell files only at assignments, not at functions. thalamus_resolve_scope tries its argument, which every tool hook passes from the payload's agent_type, and then CLAUDE_CODE_AGENT, taking the first that names a thalamus- agent with a manifest, and otherwise THALAMUS_SCOPE. The probe shows that inside a subagent CLAUDE_CODE_AGENT and every other variable are the session's, and that agent_type is the subagent's (A0174 has the reference for agent_type and agent_id), so the order of those two candidates is what decides between the subagent's scope and the session's.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/hooks/claude-code/resolve-scope.sh · standing · cites-as-live
- docs/design/launch-templates.md · standing · cites-as-live
