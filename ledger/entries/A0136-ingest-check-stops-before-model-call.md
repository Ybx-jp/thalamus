---
id: A0136-ingest-check-stops-before-model-call
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 587b325878dfdac27ddbf2cd703860bd54e4965714f04f6cd15d7dda61d0d97e
---

## Assertion

Running the ingest path in check mode performs the fetch, the origin gate and the archive retention, and returns before any model call, carrying the served origin, content type and the document's own extracted title.

## Scope

metric: what work `--check` performs and what it stops short of
cohort: the shared preflight step both `--check` and a full ingest run through
condition: not the model-extraction step itself, which this preflight step precedes and does not perform

## Grounds

- code: src/thalamus/harness/ingest.py § "preflight" =sha256:844f1bc61b4b2ba00cfe6b7f76f8babbc8e51a1b1514e1442a609b8e1872c1d1

## Warrant

`preflight`'s own docstring states it is everything `ingest()` establishes before it bills a model, and its body runs the address check, the fetch, the origin gate, archiving and text extraction, returning a `Preflight` carrying origin, content type and title — with no call into the extraction module anywhere in it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
