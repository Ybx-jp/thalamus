---
id: A0177-reflex-propagation-serves-the-hits-and-three-reached-records
kind: claim
stated: 2026-09-24T18:02:48-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 2a211342e687a407dd49b5c6a77177466bc1198665dc44ee72b4c3974f4b8803
---

## Assertion

A memory reflex firing on the propagation plan serves what word match would have served, then at most three of the records a two-hop spread from those hits reached, in descending order of activation, each on a line naming the relation and the handle it was reached from; a reached record whose line does not fit the digest cap is not served, and the pointer file holds exactly the records the digest lists beyond any word-match hits it held.

## Scope

metric: which records one propagation firing puts in the digest and the pointer file
cohort: served firings of thalamus reflex assigned the propagation plan
condition: a word-match hit that does not fit the digest is held in the pointer file as on the word-match plan, and then no reached record is served

## Grounds

- code: src/thalamus/harness/reflex.py § "fire" =sha256:67e341a6f38d701f26d8a7433c8abd9e34f331bb934860473aaff010acd8a64a
- code: src/thalamus/harness/propagation.py § "propagate" =sha256:8f3987f4e1e1a2ccb131923b38c554a94d6c6f2f6097b10ddf7e1ffdbcd370b7
- code: src/thalamus/harness/propagation.py § "linked_line" =sha256:e5895454d11c18faa44b5b0eb2c29ac6954170f09eea961e6bde678cb9488547

## Warrant

fire runs the word-match job first and keeps its results, blocks and lines exactly as the word-match plan does, then on the propagation plan calls propagate with those hits as seeds. propagate expands every seed and then the strongest frontier over every relation for DEPTH hops and returns the reached nodes other than the seeds ranked by accumulated activation, with the relation and source of each one's largest contribution. fire takes the first MAX_CANDIDATES of them, renders each with linked_line, packs them into the room the hits' lines leave under DIGEST_CHAR_CAP only when no hit was held, drops the closing held-count line, and resolves and appends to the pointer's handles and blocks only the records whose lines were kept.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-24T20:35:18-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/reflex.py § "fire" =sha256:67e341a6f38d701f26d8a7433c8abd9e34f331bb934860473aaff010acd8a64a
  artifact: sha256:031232e668301a6cd9d47a992888bbbe633a568074e272b3920d5a212d60daa8
  note: propagated from a moved ground
- 2026-09-24T20:37:18-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/reflex.py § "fire" =sha256:031232e668301a6cd9d47a992888bbbe633a568074e272b3920d5a212d60daa8
  note: fire gained an agentic branch that returns before any retrieval, and keys is computed before it; the propagation path — word match's lines, at most three reached records by activation, the unfitted record neither served nor written to the pointer file — is unchanged, so the assertion is unaffected


## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/reflex.py · standing · cites-as-live
