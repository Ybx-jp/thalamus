---
id: A0225-an-installed-wheel-reads-the-users-config
kind: claim
stated: 2026-10-16T22:05:00-07:00
author: architect
grade: measured
supersedes: none
verbatim_sha: b1c6a7eecbbe13cc968c1a4a558c24a582c33c59faa2bc6cabbb0d3f05a0f203
---

## Assertion

Without `THALAMUS_CONFIG_DIR`, a checkout reads its own `config/` and an installed wheel reads `~/.thalamus/config`.

## Scope

metric: which directory the config root falls back to when nothing names one
cohort: every manifest and preset lookup that goes through config_root with no base and no override
condition: the fallback only; the override's precedence is A0010's

## Grounds

- code: src/thalamus/contract/manifest.py § "default_config" =sha256:0f402b9802fe503a01963d46b8b4f532901869526db5fa079bf4522fdeb8b322
- code: src/thalamus/contract/paths.py § "_checkout" =sha256:4949395a1370c49ad1f4be3ded5de7b8009c29b9c1d24fb120079da266cdf1bd

## Warrant

default_config returns the checkout's `config/` when paths.CHECKOUT is set and `~/.thalamus/config` otherwise, and _checkout sets CHECKOUT only for a package loaded from a `src/` tree beside a `pyproject.toml`, which an installed wheel never is.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
