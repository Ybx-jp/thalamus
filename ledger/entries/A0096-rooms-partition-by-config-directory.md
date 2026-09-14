---
id: A0096-rooms-partition-by-config-directory
kind: claim
stated: 2026-09-13T20:21:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 59842e3181603d6dab2c294849258014bafc41e534be71d77bf5f4e5e3317c81
---

## Assertion

A room's boundary is structural: each room gets its own config directory under a harness-specific subpath, which is what session discovery scans to find a member's peers.

## Scope

metric: what directory a room member's session state and discovery scan live under
cohort: every room member, across the harnesses a room supports
condition: does not cover the PreToolUse hook that additionally blocks an outbound message attempt, only the config-directory partition itself

## Grounds

- code: src/thalamus/harness/pin.py § "room_config_dir" =sha256:140b84ab81b360f4fea220eee9cf5dbdcb4e90ab732f9f88a583e6e5638f78e9

## Warrant

room_config_dir returns a path rooted at the room's own directory rather than the operator's shared config dir, and its docstring together with the neighbouring valid_room docstring explains that peer discovery enumerates exactly this directory, so the section is what makes a non-member invisible to discovery in the first place.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- README.md · standing · cites-as-live
