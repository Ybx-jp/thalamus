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

- 2026-10-16T21:58:02-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "config_root" =sha256:c95eeb87ed26a9a80eefc691546dff4e8e5c22af096b5de1a19ae6b67d1cb3b9
  artifact: sha256:dd5b8d978f037debbc4c3ea0afe757765d6e8125aa63e6fefc789f69fbde63d1
  note: propagated from a moved ground
- 2026-10-16T22:10:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/contract/manifest.py § "config_root" =sha256:dd5b8d978f037debbc4c3ea0afe757765d6e8125aa63e6fefc789f69fbde63d1
  note: config_root's fallback became default_config (checkout `config/`, else ~/.thalamus/config); THALAMUS_CONFIG_DIR still overrides it. #35 makes an installed wheel resolve its own files and run itself (contract/paths.py). The assertion is unaffected.
- 2026-10-16T22:41:07-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "config_root" =sha256:dd5b8d978f037debbc4c3ea0afe757765d6e8125aa63e6fefc789f69fbde63d1
  artifact: sha256:215abf6b8b3c0094f351fcb3e30c1404ab79f610c5062beb84024aebb815cbcb
  note: propagated from a moved ground
- 2026-10-16T22:43:58-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/contract/manifest.py § "config_root" =sha256:215abf6b8b3c0094f351fcb3e30c1404ab79f610c5062beb84024aebb815cbcb
  note: config_root delegates to paths.config_root, which reads THALAMUS_CONFIG_DIR first. #343 moves the ownership table out of the package into the config root's ownership.json. The assertion is unaffected.

## References

- docs/concepts.md · standing · cites-as-live
