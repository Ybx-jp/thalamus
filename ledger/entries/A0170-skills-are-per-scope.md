---
id: A0170-skills-are-per-scope
kind: claim
stated: 2026-09-24T01:46:19-07:00
author: architect
grade: measured
supersedes: none
verbatim_sha: 4d237b6f0afc59b2569d7032f097371d7f0a77d80ab6c16e42aa2033eb78adcc
---

## Assertion

A scope can hold skills of its own in `config/skills/<scope>/<name>/SKILL.md`, and a Claude Code session pinned to that scope is told each one's name, description and path at startup, while a session pinned to any other scope is told nothing about them.

## Scope

metric: which sessions' SessionStart context lists a skill under config/skills/<scope>/
cohort: Claude Code sessions starting fresh or after /clear, under any resolved scope
condition: the Claude Code hook only; codex and Cursor sessions do not list scope skills

## Grounds

- code: src/thalamus/harness/hooks/claude-code/session-start.sh § "scope_skills" =sha256:c9689ef02ae15b880e1f7e4c6b12beab718d79b002e443246503f5b2ee45b1fe
- code: tests/test_claude_code_hooks.py § "TestScopeSkills" =sha256:0fd9a2fd313c32c5d2320390e77771fa24a877c635fd126ad764918f24c02b88

## Warrant

The SessionStart hook appends the output of thalamus_scope_skills, called with the session's resolved scope, which reads only that scope's own directory under the config root; the tests run the hook under the owning scope and under two others against the same config and assert the listing appears for the first alone.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-16T16:49:16-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/hooks/claude-code/session-start.sh § "scope_skills" =sha256:c9689ef02ae15b880e1f7e4c6b12beab718d79b002e443246503f5b2ee45b1fe
  artifact: sha256:a7ef4b629d6aa895ff251922979df2c94d2e5d90e55e6a05d21accb911d5ba43
  note: propagated from a moved ground
- 2026-10-16T16:51:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/harness/hooks/claude-code/session-start.sh § "scope_skills" =sha256:a7ef4b629d6aa895ff251922979df2c94d2e5d90e55e6a05d21accb911d5ba43
  note: The section's span ended at the next top-level assignment, the CI triage brief's `triage=""`, which was deleted with CI triage. The scope_skills lines themselves are unchanged, and the hook still appends only the session's own scope's skills, so the assertion is unaffected.

## References

- docs/concepts.md · standing · cites-as-live
