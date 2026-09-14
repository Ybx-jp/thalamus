---
id: A0034-claim-identity-converges-on-kind-and-normalized-description
kind: claim
stated: 2026-09-13T20:32:44-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 36388d18bebe2fcb5b1e8c68b48d254f4afe8e7b6c64ac5291d9546d70e981c9
---

## Assertion

A claim's identity is its `(kind, normalized description)`, so the same claim reached independently in two sessions converges on one graph node.

## Scope

metric: what two claims must share to be treated as the same node
cohort: every claim written into the graph
condition: the identity function only; the upsert-by-id behavior that makes this convergence actually happen at write time is a separate claim

## Grounds

- code: src/thalamus/substrate/schema.py § "_normalized" =sha256:3c2f6f66b98cf443c7e3e1a10669d9e92bdfcd105df8c0d7ef4a305545718c9d

## Warrant

content_id hashes (kind, _normalized(description)) and nothing else, so any two claims whose descriptions _normalized reduces to the same string are, by construction, the same vertex id.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
