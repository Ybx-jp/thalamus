---
id: A0040-distillation-names-references-by-short-handles
kind: claim
stated: 2026-09-13T20:38:26-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: a33efac716fadbe0608633b6cbf05e4ba6c9db69de53ca610653a02245054929
---

## Assertion

Distillation writes the `USES` edge from the extractor's own references, which it names by 8-character handles.

## Scope

metric: what identifier a reference in the extractor's output is keyed by
cohort: every reference an extraction names
condition: the handle format only

## Grounds

- code: src/thalamus/harness/extraction.py § "reference_handle" =sha256:ea9341f6374419372f632de45563837b131cada7466144c141d71f452b0028fb

## Warrant

reference_handle is what produces the 8-character handle a reference is identified by, so it is the code fixing that format.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
