---
id: A0248-an-autonomous-run-cannot-move-an-attended-threads-status
kind: claim
stated: 2026-11-23T01:56:23-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 2c3a3187105407d801bccda1fc2bd10d5ee83f4dd3b31b583fb3ee402e4a71af
---

## Assertion

An autonomous session's reference to a thread it did not open as autonomous is written as a CONTINUES edge and leaves the thread's status as it was, whatever status the reference carries.

## Scope

metric: what an autonomous session's thread reference writes on the referenced thread
cohort: thread_refs of sessions written with session type autonomous
condition: threads held as attended, held without a type, or whose type cannot be read; a reference to an autonomous thread moves its status as an attended reference does

## Grounds

- code: src/thalamus/substrate/writer.py § "_write_thread_refs" =sha256:a8a19474c98557c6cac1e66c2c219483c05db6b0a20b1c43120f15891c3767d5

## Warrant

_write_thread_refs checks, before writing a status, whether the writing session is autonomous and the thread's held type is anything but autonomous; in that case it writes the CONTINUES edge and moves to the next reference without writing the status property or a RESOLVES edge.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/substrate/writer.py · standing · cites-as-live
