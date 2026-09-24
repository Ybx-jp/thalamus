---
id: A0157-reflex-digest-is-sized-in-characters
kind: claim
stated: 2026-09-23T21:47:03-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 7fbc81d9337ef72e90d26a024edce84b5b86a5a8d70ed631e87ec227ef06b340
---

## Assertion

The memory reflex puts at most 4,000 characters of digest into the agent's context per firing, however many records the recall returned, by keeping whole index lines in rank order until the next one would cross that cap and counting the rest as held in the pointer file.

## Scope

metric: the length of the digest one reflex firing hands the agent
cohort: every served firing of the word-match plan
condition: does not cover the pointer file's size, which is not in context, or the session-wide budget across firings

## Grounds

- code: src/thalamus/harness/reflex.py § "DIGEST_CHAR_CAP" =sha256:a246a5b49f584ed4029623079363f9dd50e3edd5428b6066fb9993325bde01b1
- code: src/thalamus/harness/reflex.py § "pack_digest" =sha256:72726eb9f21fe862e5f08e0568bb868a6b972b596c12d89b73e317b67b3b4c6a

## Warrant

DIGEST_CHAR_CAP sets the cap at 4,000 characters, and pack_digest keeps a line only while the frame plus the kept lines stays within the cap it is given, breaking at the first line that would cross it, so the digest's size is bounded by the constant rather than by the count of candidates.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
