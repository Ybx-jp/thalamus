---
id: A0017-claude-code-carries-the-charter-via-agent-file
kind: claim
stated: 2026-09-13T20:15:45-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: fa22786e6297e79d17c19b623b9b26b92bc784b22d1fbae5315c1e6aeaf7abdb
---

## Assertion

Claude Code carries a pin's charter and MCP arming through `--agent thalamus-<scope>`, an agent file generated under `.claude/agents/`.

## Scope

metric: how Claude Code receives the charter and its scope's MCP arming
cohort: every Claude Code session launched pinned
condition: the agent-file mechanism only

## Grounds

- code: src/thalamus/harness/pin.py § "write_agent" =sha256:0546100a9f15db84bef0d5150038e237b200448079e07cee192fdf012864c1f5

## Warrant

write_agent is what generates the .claude/agents/thalamus-<scope> file the --agent flag names, so it is the code making this the carrier for Claude Code specifically.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-16T17:35:24-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/pin.py § "write_agent" =sha256:0546100a9f15db84bef0d5150038e237b200448079e07cee192fdf012864c1f5
  artifact: sha256:2dd7ee24759cc35e2f6e45cfc02f67744e17bd20acbaa41e96ba7c85cf0759d0
  note: propagated from a moved ground
- 2026-10-16T17:45:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/harness/pin.py § "write_agent" =sha256:2dd7ee24759cc35e2f6e45cfc02f67744e17bd20acbaa41e96ba7c85cf0759d0
  note: Only the docstring changed, naming the console's spawn where it named `spawn`. Moved by #342, which takes tmux and room handling out of core into console/; the assertion is unaffected.

## References

- docs/concepts.md · standing · cites-as-live
