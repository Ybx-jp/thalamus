---
id: A0139-shipped-skills-symlink-into-user-scope
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: ad2b3eb641aa233602d66be85d3d26d44303df3aea63dfb8d6c0cb966a4bae43
---

## Assertion

Installing skills symlinks each package-shipped skill directory into the user's skills directory, which is what makes a shipped skill arm outside the checkout it lives in.

## Scope

metric: how a package-shipped skill reaches user scope
cohort: the function that installs skills into the user's skills directory
condition: not the project-scope real directories under `.claude/skills/`, which this function does not touch

## Grounds

- code: src/thalamus/harness/install.py § "link_skills" =sha256:9738239460891532bfcf9b152aa771315bee052eed5bfaf7e1efd7e04465725e

## Warrant

`link_skills` reads the shipped-skill set and symlinks each one into the user's skills directory, and its own docstring gives the reason: a session opened outside the checkout gets the hooks and the MCP server but, without this symlink, none of the shipped skills.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
