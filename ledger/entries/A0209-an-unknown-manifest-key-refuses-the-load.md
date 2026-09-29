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

## References

- src/thalamus/contract/manifest.py · standing · cites-as-live
