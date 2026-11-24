---
id: A0245-autonomous-session-nodes-are-marked-and-held-at-tier-two
kind: claim
stated: 2026-11-23T01:56:20-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 6e1ce97af81c18f36d667b2a49c2a6ffb86fa3d810fef5098e2cb649d32ae0be
---

## Assertion

Every node a session distils carries that session's type, attended or autonomous, as a property, and every node an autonomous session distils is written at tier 2 or below: an attended session's nodes default to tier 1, an autonomous session's to tier 2, and an item that carries its own more trusted provenance is lowered to tier 2 before it is written.

## Scope

metric: the tier and the session-type property written on each node of a distilled session
cohort: Session, Source, Artifact, Claim and Thread vertices written by write_session
condition: the write path of a distilled session; knowledge batches carry no session and no session type

## Grounds

- code: src/thalamus/substrate/schema.py § "session_type_tier" =sha256:d9ff526bd75a9027bd81a37e179377199841fbb9fcc0f88afce99475b194bc17
- code: src/thalamus/substrate/schema.py § "SessionGraph" =sha256:d26573c8afd09d77769e1bc25da28fe4e94db9af834f1fd4db3b9cae1dcaf6e1
- code: src/thalamus/substrate/writer.py § "_provenance_properties" =sha256:973e87ba93ea12dee2df8938996a16abe22cd4ca7a3f5cdf66947dc2f2b83389

## Warrant

session_type_tier maps attended to FIRST_PARTY and autonomous to CURATED. SessionGraph.default_provenance takes its tier from that map, and SessionGraph.provenance_for raises any provenance more trusted than the map's tier to it, leaving a less trusted one alone. Every node write_session makes takes its provenance from provenance_for and flattens it through _provenance_properties with the session's type, which writes the session_type property beside tier, source and ingested_at.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/substrate/schema.py · standing · cites-as-live
