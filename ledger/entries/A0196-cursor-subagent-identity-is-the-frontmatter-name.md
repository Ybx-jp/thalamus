---
id: A0196-cursor-subagent-identity-is-the-frontmatter-name
kind: claim
stated: 2026-09-25T00:39:55-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: b65f1559e179f8dff17d74c1bf2b719b140345568bcb799055ec693bf9ef0982
---

## Assertion

Cursor reads subagent files from a project's .claude/agents as well as its .cursor/agents and .codex/agents, and identifies each by its frontmatter name, falling back to the filename only when name is absent; two files carrying one name surface as a single subagent.

## Scope

metric: whether a second agent file beside an existing one is visible to a Cursor session, and under what identity
cohort: Cursor's subagents documentation as retrieved on 2026-09-25
condition: measured on cursor-agent 2026.08.11-e8db854 in print mode with model auto, in a scratch workspace's .claude/agents: a listing returned each file's frontmatter name, a nameless file under its filename stem, a name containing -- accepted as given, and a single entry for two files sharing one name; invoked by that name, the file whose filename was longer answered in 10 of 10 pairs, with mtime, directory order and filename sort each varied against it. Which of two same-name files wins is not documented, and the 10 pairs do not establish the mechanism. The operator's ~/.claude/agents files did not appear in the listing, although the documentation names that folder.

## Grounds

- source: cursor-subagents · §File locations
- source: cursor-subagents · §Configuration fields

## Warrant

The file locations table lists .claude/agents among the project subagent folders, for Claude compatibility; the configuration fields table makes name the identifier and derives it from the filename only as a default, so a file is known by its name field and two files with one name are one subagent to Cursor.

## Backing

- source: cursor-subagents · §File locations
  speaker: Cursor
  quote: […] "| | .claude/agents/ | Current project only (Claude compatibility) |" […]
- source: cursor-subagents · §Configuration fields
  speaker: Cursor
  quote: […] "| name | string | No | Derived from filename | Display name and identifier." […]

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
