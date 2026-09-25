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

- 2026-09-23T23:48:59-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/pin.py § "codex_profile_name" =sha256:1767368ca35b7eda3b37c60232106fb1fafa0b26f814dd3638a9f4808e4c81a0
  artifact: sha256:c5a2218c0a5168efbd1b52f70a1525a471512bafc609fab66664899c7a370c32
  note: propagated from a moved ground

- 2026-09-24T00:05:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/pin.py § "codex_profile_name" =sha256:c5a2218c0a5168efbd1b52f70a1525a471512bafc609fab66664899c7a370c32
  note: the comment block introducing CODEX_MODELS now follows codex_profile_name and is read into its section; the function and the profile path are unchanged, so the assertion is unaffected
- 2026-09-24T00:17:03-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/pin.py § "codex_profile_name" =sha256:c5a2218c0a5168efbd1b52f70a1525a471512bafc609fab66664899c7a370c32
  artifact: sha256:7a3602b8211b25645dfe36c22d9042701c39a2c0f0ecd6532b1d32fdfa7a24d8
  note: propagated from a moved ground

- 2026-09-24T00:40:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/pin.py § "codex_profile_name" =sha256:7a3602b8211b25645dfe36c22d9042701c39a2c0f0ecd6532b1d32fdfa7a24d8
  note: the CODEX_MODELS comment block read into this section was reworded; the function and the profile path are unchanged

## References

- docs/concepts.md · standing · cites-as-live
