---
id: A0087-archive-is-immutable-content-addressed
kind: claim
stated: 2026-09-13T20:12:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 3528621da44e0adf8a6ec6221017b086aaa6c2d02557c99c5319c91921b1d649
---

## Assertion

Retained bytes are archived under the sha256 of their own content, and archiving the same bytes again is a no-op rather than a second write.

## Scope

metric: how a piece of retained evidence is named and whether re-archiving the same bytes duplicates it
cohort: every payload passed to archive_bytes, including session transcripts and ingested documents
condition: does not cover secret-scanning or reporting on the bytes, only their storage and content addressing

## Grounds

- code: src/thalamus/archive/store.py § "archive_bytes" =sha256:d3d71bd0f872a3e5779f7db7c758cca40989c0ea49087259408e4671c2aeb645

## Warrant

archive_bytes computes the sha256 of the payload, names the destination from that hash, and returns immediately with already_present set when that destination already exists, so the section shows both the content addressing and the idempotence directly.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- README.md · standing · cites-as-live
