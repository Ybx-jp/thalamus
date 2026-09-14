---
id: A0091-write-boundary-enforced-by-role-guard
kind: claim
stated: 2026-09-13T20:16:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: f46e8382a0b32897d03d944a39b4b097ef8ffe91448167e7c6106eb2ac16e22a
---

## Assertion

A scope manifest may declare a write_boundary of deny and allow path globs, and this field is enforced by the role-guard PreToolUse hook as a defense-in-depth layer over the manifest's own domain description.

## Scope

metric: what a write_boundary field is and what is stated to enforce it
cohort: every expert manifest that declares one
condition: does not cover the specific denial any one manifest states, only the field's shape and its stated enforcement mechanism

## Grounds

- code: src/thalamus/contract/manifest.py § "WriteBoundary" =sha256:937332e7ec6a0921e6618ecbaa05ed1f8d346efc86aa92728af2409981b30f85

## Warrant

WriteBoundary's docstring states the field is declared tier-0 and enforced by the role-guard PreToolUse hook as defence in depth, and the class itself defines the deny_globs, allow_globs and denies() matching logic that hook consults, so the section both names the enforcer and implements the matching it enforces.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- README.md · standing · cites-as-live
