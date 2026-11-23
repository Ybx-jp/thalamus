---
id: A0247-a-node-keeps-the-session-type-it-was-first-written-under
kind: claim
stated: 2026-11-23T01:56:22-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 73054bffea4b80085f10f9fc685088e5e7f2f821bf5f3160dd8548c50b43e45b
---

## Assertion

A node keeps the session type it was originally written under. When a session of one type re-writes a Claim or Thread held under the other type, or one whose type cannot be read, the re-write's on-match payload is empty; on such an Artifact the payload is the usual one minus tier, source, ingested_at and session_type. Re-writing a Session that holds a type as the other type raises SessionTypeConflict before anything is written.

## Scope

metric: the properties a session's write may change on a vertex that already exists
cohort: Session, Claim, Thread and Artifact vertices re-written by write_session
condition: a vertex with no session_type property predates the field and is held as attended, except a Session, which takes the type it is next written with

## Grounds

- code: src/thalamus/substrate/writer.py § "_on_match_for" =sha256:176fd43bb267ec0e5c5e8a383d4a51036ec24690afb359bc9443dd76676bbbfa
- code: src/thalamus/substrate/writer.py § "_upsert_session_vertex" =sha256:a9a759501a231e17b39efc14c422b7bca238dc1c92128b6fee7ab3c34757b6b2

## Warrant

_on_match_for reads the held session type and returns the full on-match payload only when the vertex is absent or held under the writing session's own type; otherwise it returns an empty payload for a Claim or Thread and the payload minus tier, source, ingested_at and session_type for an Artifact, and an unreadable type counts as other. _upsert_session_vertex reads the Session's held session_type and raises SessionTypeConflict when it is set and differs from the session being written.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/substrate/writer.py · standing · cites-as-live
