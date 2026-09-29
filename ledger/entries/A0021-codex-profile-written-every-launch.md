---
id: A0021-codex-profile-written-every-launch
kind: claim
stated: 2026-09-13T20:19:13-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 7a8962f938a73ab5b2c63c3b9fbb633837a8115142b92d9e5f4cea2b5d1a9293
---

## Assertion

The codex profile file is written fresh on every launch rather than assumed to already be there, because a `--profile` naming a missing file starts an ordinary, unarmed session with no error.

## Scope

metric: when the profile file is written relative to a launch, and what happens if it is absent
cohort: every codex session launched pinned
condition: the write-on-launch behavior only

## Grounds

- code: src/thalamus/harness/pin.py § "write_codex_profile" =sha256:2222b676632551b8b96930ea441e6ec63ebbecf1c37e321fc91ed35843acb0b8

## Warrant

write_codex_profile is called from the launch and roster spawn paths each time rather than only once, so the profile a --profile flag names is written unconditionally before codex starts.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-29T00:31:25-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/pin.py § "write_codex_profile" =sha256:2222b676632551b8b96930ea441e6ec63ebbecf1c37e321fc91ed35843acb0b8
  artifact: sha256:43d8f153d00540f970ad02725c0c3dae057d10ac395a300a87f4eed74dd8ef1a
  note: propagated from a moved ground

- 2026-09-29T00:31:35-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/pin.py § "write_codex_profile" =sha256:43d8f153d00540f970ad02725c0c3dae057d10ac395a300a87f4eed74dd8ef1a
  note: write_codex_profile now passes codex_registers_thalamus to the renderer so the profile can forward the pin to the MCP server; it still writes the file on every call, so the assertion is unaffected

## References

- docs/concepts.md · standing · cites-as-live
