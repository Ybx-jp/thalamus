---
id: A0043-eval-sync-stamps-verified-served-not-used
kind: claim
stated: 2026-09-13T20:41:47-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 2df17c18e1cffcfac608c3431d6b3c34df644dec7eda90576b0499ee19b4ab40
---

## Assertion

`thalamus eval sync` stamps a `USES` edge `verified` from the session's own traces -- true when a retrieval actually served the target into a session containing the claim, false when sync looked and found none, absent when sync has not looked yet; served is not used, and the used verdict lives on the trace's `RETURNS` edge instead.

## Scope

metric: what the verified stamp on a USES edge records, and which edge instead records used
cohort: every USES edge eval sync inspects
condition: the stamping function only

## Grounds

- code: src/thalamus/eval/sync.py § "uses_stamp" =sha256:a7cdea1960ae6547fb21f71d415a8927832a91938d5b41affe2b7117349daaa0

## Warrant

uses_stamp's own docstring and return value distinguish verified-as-served from used, stating explicitly that the used verdict belongs to the attribution instrument on RETURNS, which is exactly this claim.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
