---
id: A0014-roster-command-spawns-on-demand
kind: claim
stated: 2026-09-13T20:12:24-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 6f049431f94050c14375fb208b5f6154a8f4195eb36a1f252b54a86fb05ea38b
---

## Assertion

`thalamus roster` brings up the `main` anchor and spawns experts on demand, with `--all` opening one window per expert instead.

## Scope

metric: what the roster command starts immediately, and when each expert window opens
cohort: every window the roster command can open
condition: the spawn behavior only

## Grounds

- code: src/thalamus/harness/pin.py § "roster" =sha256:2a9a62296abcfb9ffdc99f597301ebbc876da5b1767c48d64b585ec179306a2a

## Warrant

roster is the function thalamus roster calls, and its own handling of the full-versus-on-demand case is what fixes whether an expert window opens immediately or later.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-16T17:35:24-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/pin.py § "roster" =sha256:2a9a62296abcfb9ffdc99f597301ebbc876da5b1767c48d64b585ec179306a2a
  artifact: absent
  note: propagated from a withdrawn ground
- 2026-10-16T17:45:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/console/windows.py § "roster" =sha256:4693b1c04a1b8071fc8e95fa2bfc382afd05c7e017a0c286b42bdf3e490c6c43
  note: `roster` moved from harness/pin.py to console/windows.py unchanged. Moved by #342, which takes tmux and room handling out of core into console/; the assertion is unaffected.

## References

- docs/console.md · standing · cites-as-live
