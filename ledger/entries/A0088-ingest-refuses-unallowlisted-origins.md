---
id: A0088-ingest-refuses-unallowlisted-origins
kind: claim
stated: 2026-09-13T20:13:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: b10c9d5fd41e026f0bf9de5af053149931b2f5bc12181c74a7db9289291685ef
---

## Assertion

Ingesting a URL is refused when the host that actually answered the request is not on the target scope's manifest allowlist, and the check runs against the origin that answered rather than against the address that was requested.

## Scope

metric: whether the serving origin, not the requested address, is what gets checked against the allowlist
cohort: every URL ingest, which goes through check_origin; a local file path is exempt and needs no manifest
condition: does not cover retaining the bytes or co-indexing the text, which happen only once this check passes

## Grounds

- code: src/thalamus/harness/ingest.py § "check_origin" =sha256:2ae48709312770f26b2e554db9cbb17191cc4577e7a282d5f4bef035f66f24ae

## Warrant

check_origin takes the origin that answered rather than the requested location, raises IngestError when the scope's manifest does not allow it, and is positioned in preflight to run before anything downstream is spent, so the section shows the gate checking the actual answering host rather than the address on the command line.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- README.md · standing · cites-as-live
