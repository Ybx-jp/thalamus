---
id: A0010-config-dir-env-var-swaps-the-roster
kind: claim
stated: 2026-09-13T20:08:56-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 32640ab24b66483fd6e6b3a315a9bb7668cdff77e44998dc702ec26e15d156c9
---

## Assertion

Pointing `THALAMUS_CONFIG_DIR` at a directory holding its own `experts/` subdirectory swaps in a different roster of manifests.

## Scope

metric: which environment variable selects the manifests directory, and what overrides the checkout default
cohort: every manifest lookup that goes through config_root
condition: the directory resolution only

## Grounds

- code: src/thalamus/contract/manifest.py § "config_root" =sha256:c95eeb87ed26a9a80eefc691546dff4e8e5c22af096b5de1a19ae6b67d1cb3b9

## Warrant

config_root reads THALAMUS_CONFIG_DIR as the override for where experts/ is read from, which is exactly the roster-swapping mechanism the assertion describes.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
