---
id: A0005-write-boundary-globs-match-absolute-paths
kind: claim
stated: 2026-09-13T20:03:21-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: b5ff06dbad6d348d1b948f4b64bc97fcb603e6471342cedc5d8906dfaf5766c9
---

## Assertion

A scope's write boundary is enforced by matching `deny_globs` against the absolute POSIX path of the file being written, with `allow_globs` evaluated ahead of the denies, so an allow entry can carve out an exception a deny would otherwise catch.

## Scope

metric: the matching semantics and evaluation order of a write boundary
cohort: every scope that declares deny_globs or allow_globs
condition: the glob-matching mechanism only; the PreToolUse hook that calls it is a separate carrier and not part of this ground

## Grounds

- code: src/thalamus/contract/manifest.py § "WriteBoundary" =sha256:937332e7ec6a0921e6618ecbaa05ed1f8d346efc86aa92728af2409981b30f85

## Warrant

WriteBoundary.denies loops over allow_globs before deny_globs and returns None on an allow match, which is exactly the absolute-path fnmatch semantics and allow-first order the assertion states.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-29T00:31:25-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "WriteBoundary" =sha256:937332e7ec6a0921e6618ecbaa05ed1f8d346efc86aa92728af2409981b30f85
  artifact: sha256:b82f6077939586cab6ba7c16b16fda29a37cdb5f0d7f0f710e92c7ec7a562728
  note: propagated from a moved ground

- 2026-09-29T00:31:35-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/contract/manifest.py § "WriteBoundary" =sha256:b82f6077939586cab6ba7c16b16fda29a37cdb5f0d7f0f710e92c7ec7a562728
  note: WriteBoundary gained model_config forbidding undeclared fields; the glob matching and allow-before-deny order are unchanged, so the assertion is unaffected

## References

- docs/concepts.md · standing · cites-as-live
