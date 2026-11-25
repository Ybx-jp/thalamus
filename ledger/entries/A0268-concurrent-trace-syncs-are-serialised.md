---
id: A0268-concurrent-trace-syncs-are-serialised
kind: claim
stated: 2026-11-24T23:09:12-08:00
author: main
grade: argued
supersedes: none
verbatim_sha: 7c66c08c40b410279029c537e23e256a8198d9ceb87add7cf7509ca09fb66ac7
---

## Assertion

Two writing trace syncs never write to the graph at the same time: a writing sync holds an exclusive lock beside the trace tap for its whole run, and one that finds the lock held waits for it instead of skipping.

## Scope

metric: whether two `thalamus eval sync --write` runs over the same tap can write to the graph concurrently
cohort: every writing sync started through `eval.sync.sync`, which includes the one each session-end hook chains after extract
condition: the runs share a tap directory and a filesystem with working `flock`; a dry run writes nothing and takes no lock, so it is outside the claim

## Grounds

- code: src/thalamus/eval/sync.py § "sync" =sha256:ae97c508cccdabc623b0f57aae5d4a07401b7fce4939385f3b59c62a0b2bd2a0
- code: src/thalamus/eval/sync.py § "_sync_lock" =sha256:efc6e2e829d0ad0bf48e38770cf22f9d7992fab60ce57f7a0b6c3e6a6cd099e8

## Warrant

`sync` enters `_sync_lock` around the whole of `_sync` whenever `write` is true, and `_sync_lock` takes `LOCK_EX` on `sync.lock` in the tap directory, retrying the request as a blocking call when the non-blocking attempt is refused, so the second run proceeds only after the first has released the lock and then runs its full sweep.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/eval/sync.py · standing · cites-as-live
- docs/cli.md · standing · cites-as-live
