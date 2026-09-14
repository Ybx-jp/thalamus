---
id: A0142-node-is-optional-and-its-absence-skips
kind: claim
stated: 2026-09-13T21:40:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 339fba525271b70b5d850d333191dc8803ae0dfad2ea0a0225d1ec5c2bd0da6b
---

## Assertion

A checkout with node missing skips the JavaScript suite rather than failing it: the test that drives those scripts is marked to skip when node cannot be found on the path.

## Scope

metric: what a checkout without node produces for the JavaScript suite — a skip or a failure
cohort: the parametrized test that runs each tests/js script under node
condition: the skip condition on that test only; it does not cover the other tests in the same module, which read the source rather than run it

## Grounds

- code: tests/test_console_js.py § "test_console_js" =sha256:4a939460fb8f401fbcc134c9ee7a788707ab7fbc1d63abb5ee5470f442ba56a0

## Warrant

The skip marker is part of the definition it sits on, and its condition is that the resolved node executable is absent, so the whole parametrized test is skipped rather than run when node is not on the path. A test that is skipped cannot fail, which is the difference the claim rests on.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
