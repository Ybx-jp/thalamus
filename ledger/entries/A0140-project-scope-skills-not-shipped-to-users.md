---
id: A0140-project-scope-skills-not-shipped-to-users
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 69dbc3b78592eac26075298213c19162751759e0df8e679ef78410ef5bfe6d95
---

## Assertion

Only the skill directories reachable from the package's own skills directory are ever treated as shipped and eligible for symlinking into user scope; a directory anywhere else is never part of that set no matter its contents.

## Scope

metric: which skill directories are eligible to be installed into user scope
cohort: the function that enumerates shipped skills
condition: not whether a directory is well-formed as a skill (that is a separate frontmatter check within the same function); only which directory tree is even considered

## Grounds

- code: src/thalamus/harness/install.py § "shipped_skills" =sha256:3ac962f19e2de5f16d25ce93cc8ab29c50ebb2d635fef714e3ff8aadeb7446d0

## Warrant

`shipped_skills` only ever iterates the package's fixed skills directory; a project's own `.claude/skills/` real directories sit outside that path entirely, so nothing in this function's scan can ever surface them as installable, independent of their content.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
