---
id: A0209-an-unknown-manifest-key-refuses-the-load
kind: claim
stated: 2026-09-29T00:30:20-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 90c6a2375d67ab67e2717397b1a6584d8b3204784324c5f072c55789cf5f7c66
---

## Assertion

Loading an expert manifest that carries a key the model does not declare, at the top level or inside write_boundary or capability_boundary, raises a ValueError naming the manifest's file; leaving a key out keeps its documented default.

## Scope

metric: whether an undeclared manifest key is refused or dropped
cohort: manifests read through load_manifest
condition: every launch path loads every manifest (write_all_agents, write_all_codex_profiles), so one refused manifest stops pin, spawn and init until it is corrected. role-guard.sh still fails open on a manifest it cannot load, so a manifest misspelled after a session started is not enforced by the guard for that session.

## Grounds

- code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:3ef12bb520ff34e1f9f3f1449c2c3f6ab73c2f003500091bd43e3b8521cccf98
- code: src/thalamus/contract/manifest.py § "WriteBoundary" =sha256:b82f6077939586cab6ba7c16b16fda29a37cdb5f0d7f0f710e92c7ec7a562728
- code: src/thalamus/contract/manifest.py § "CapabilityBoundary" =sha256:bb4f0c07d5db9a796aaf8c6303812c28536e0a5b9f0ead2793620ed084d153d6
- code: src/thalamus/contract/manifest.py § "load_manifest" =sha256:841f3a4e9bde3b515b489a6d4165d2dd3335f91be21f542e92aec8aa6cd2f2d7

## Warrant

The three models set extra to forbid, so pydantic raises a ValidationError for an undeclared field instead of discarding it, and load_manifest re-raises that as a ValueError prefixed with the manifest's path. Fields that are absent still take their declared defaults.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-16T17:45:40-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:3ef12bb520ff34e1f9f3f1449c2c3f6ab73c2f003500091bd43e3b8521cccf98
  artifact: sha256:b65fad6b3e06f0440ee1686f649afff4af1258e0dfdb69d93764b818f0e4baeb
  note: propagated from a moved ground

- 2026-10-16T17:45:40-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "CapabilityBoundary" =sha256:bb4f0c07d5db9a796aaf8c6303812c28536e0a5b9f0ead2793620ed084d153d6
  artifact: sha256:71d23739bb329a5e26b87e97209f6b94a754070020547c72f81191e1beea44e9
  note: propagated from a moved ground
- 2026-10-16T17:55:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:b65fad6b3e06f0440ee1686f649afff4af1258e0dfdb69d93764b818f0e4baeb
  note: Only wording in the section changed: #342 retires "roster" where it meant the set of experts or the console's tmux windows. The assertion is unaffected.
- 2026-10-16T17:55:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: src/thalamus/contract/manifest.py § "CapabilityBoundary" =sha256:71d23739bb329a5e26b87e97209f6b94a754070020547c72f81191e1beea44e9
  note: Only wording in the section changed: #342 retires "roster" where it meant the set of experts or the console's tmux windows. The assertion is unaffected.
- 2026-11-23T17:37:45-08:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:b65fad6b3e06f0440ee1686f649afff4af1258e0dfdb69d93764b818f0e4baeb
  artifact: sha256:50a10758e207f8d803bc1f78b3aeb0bbf8eb5c4baeaedb9aaa21e78261cdcbf4
  note: propagated from a moved ground

- 2026-11-23T17:37:46-08:00 · corroborated · grade: argued · author: main
  evidence: code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:50a10758e207f8d803bc1f78b3aeb0bbf8eb5c4baeaedb9aaa21e78261cdcbf4
  note: The class gains a reports_to field defaulting to main. The assertion is unaffected.
- 2026-11-23T20:53:28-08:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:50a10758e207f8d803bc1f78b3aeb0bbf8eb5c4baeaedb9aaa21e78261cdcbf4
  artifact: sha256:95646f6236406d8384815d944e2a8707a0ca9050065318a227a737548d91f0ed
  note: propagated from a moved ground

- 2026-11-23T20:53:28-08:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "load_manifest" =sha256:841f3a4e9bde3b515b489a6d4165d2dd3335f91be21f542e92aec8aa6cd2f2d7
  artifact: sha256:4085508c61e2be255a086a93f47e86abb7d41d6e731b267c22be25a32709b2f5
  note: propagated from a moved ground

- 2026-11-23T20:56:00-08:00 · corroborated · grade: argued · author: main
  evidence: code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:95646f6236406d8384815d944e2a8707a0ca9050065318a227a737548d91f0ed
  note: The class gains a rules field defaulting to the empty string and a private record of the config root it was loaded from. The assertion is unaffected.

- 2026-11-23T20:56:00-08:00 · corroborated · grade: argued · author: main
  evidence: code: src/thalamus/contract/manifest.py § "load_manifest" =sha256:4085508c61e2be255a086a93f47e86abb7d41d6e731b267c22be25a32709b2f5
  note: The function now records the config root on the loaded manifest. The assertion is unaffected.
- 2026-11-24T21:21:13-08:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "WriteBoundary" =sha256:b82f6077939586cab6ba7c16b16fda29a37cdb5f0d7f0f710e92c7ec7a562728
  artifact: sha256:ab9abc46ee3ae1c2d589ed83b9d32c592c9869853caad6f20d7aa9acac2b1d5b
  note: propagated from a moved ground

- 2026-11-24T21:21:13-08:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "CapabilityBoundary" =sha256:71d23739bb329a5e26b87e97209f6b94a754070020547c72f81191e1beea44e9
  artifact: sha256:9f9476c55d6fb6c9866beed5e0b8836b050d90e06a36ae322c0695709ae5e5e1
  note: propagated from a moved ground
- 2026-11-24T21:21:34-08:00 · corroborated · grade: argued · author: main
  evidence: code: src/thalamus/contract/manifest.py § "WriteBoundary" =sha256:ab9abc46ee3ae1c2d589ed83b9d32c592c9869853caad6f20d7aa9acac2b1d5b
  note: denies now matches the resolved file as well as the path as given; model_config still forbids undeclared keys, so the assertion is unaffected
- 2026-11-24T21:21:34-08:00 · corroborated · grade: argued · author: main
  evidence: code: src/thalamus/contract/manifest.py § "CapabilityBoundary" =sha256:9f9476c55d6fb6c9866beed5e0b8836b050d90e06a36ae322c0695709ae5e5e1
  note: denies_skill also matches the name after a plugin prefix; model_config still forbids undeclared keys, so the assertion is unaffected

## References

- src/thalamus/contract/manifest.py · standing · cites-as-live
