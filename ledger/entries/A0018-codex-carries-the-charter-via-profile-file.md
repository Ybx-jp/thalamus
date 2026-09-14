---
id: A0018-codex-carries-the-charter-via-profile-file
kind: claim
stated: 2026-09-13T20:16:52-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 9f84cce1222497ccfe96530e9b1d05ddc1e10750732d9e264b5eec668bac1fc7
---

## Assertion

codex carries a pin's charter and MCP arming through `--profile thalamus-<scope>`, a generated `$CODEX_HOME/thalamus-<scope>.config.toml`.

## Scope

metric: how codex receives the charter and its scope's MCP arming
cohort: every codex session launched pinned
condition: the profile-name and file mechanism only

## Grounds

- code: src/thalamus/harness/pin.py § "codex_profile_name" =sha256:1767368ca35b7eda3b37c60232106fb1fafa0b26f814dd3638a9f4808e4c81a0

## Warrant

codex_profile_name is what names the generated TOML profile the --profile flag points at, which is the carrier codex has in place of an agent file.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
