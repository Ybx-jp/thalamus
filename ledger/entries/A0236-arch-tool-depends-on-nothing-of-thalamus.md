---
id: A0236-arch-tool-depends-on-nothing-of-thalamus
kind: claim
stated: 2026-10-25T23:46:33-07:00
author: architect
grade: argued
supersedes: none
verbatim_sha: d4d785567fbe16a256de148af0cf4a1d6113d5a048208755c028e99f07b575d3
---

## Assertion

The thalamus-arch distribution declares PyYAML and pluggy as its only dependencies, and its package imports only its own modules among this repository's, so it installs and runs alone.

## Scope

metric: which distributions thalamus-arch declares and which first-party modules its package imports
cohort: the thalamus-arch package under packages/thalamus-arch
condition: the arch rules gate run over this repository with every package's source root scanned

## Grounds

- toml-key: packages/thalamus-arch/pyproject.toml § "dependencies" =sha256:cbc169e64b4f74490ac34af825bd5902c45db70e75b9d093dfac14325baa32ae
- yaml: arch/model.yaml § "rules" =sha256:a424b4258c5c09b16055017277be1170fdd7a60e08efc5337ef21be88fdf29c5

## Warrant

The dependencies list names only PyYAML and pluggy, so an installer brings in nothing of thalamus; and the rule for the plugin-arch layer, which holds every module under packages/thalamus-arch/src, may depend on no layer, so an import from it into a core or plugin module is a violation that arch rules --gate fails on unless an accepted entry names it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
- CONTRIBUTING.md · standing · cites-as-live
