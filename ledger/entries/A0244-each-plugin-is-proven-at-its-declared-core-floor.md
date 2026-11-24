---
id: A0244-each-plugin-is-proven-at-its-declared-core-floor
kind: claim
stated: 2026-11-04T17:27:44-08:00
author: main
grade: argued
supersedes: none
verbatim_sha: 01135e1075611e2657997f883f2fc7f267fa5fc27eb9b1ed73d16f0bf1bf79bd
---

## Assertion

Every plugin that depends on the core is installed, as a wheel and as an sdist, beside the core at exactly the version its `thalamus-memory` floor names, taken from PyPI, and must import every module it ships and load in `thalamus --help` with nothing on stderr. CI's plugin-floors job does this on every push and pull request, and reports rather than fails a floor that names a pre-release; the release workflow does it for the plugin being released, and fails a pre-release floor.

## Scope

metric: whether a plugin whose floor is lower than the core it imports from reaches master or PyPI without a red check
cohort: every distribution under packages/ that declares a thalamus-memory requirement; thalamus-arch declares none and is skipped
condition: the floor is the lower bound of a >= specifier and names a version PyPI holds; a pre-release floor is not proven against anything until it names a release

## Grounds

- yaml: .github/workflows/verify.yml § "jobs" =sha256:36d593c62c1fb09da44d8ec692ccd669a1551188bf6215665b5cb530bcfbf6b8
- entry: A0120-verify-commands-gated-in-ci · distinguishes
- entry: A0239-one-tag-publishes-one-distribution · distinguishes
- entry: A0240-each-distribution-publishes-from-its-own-environment · distinguishes
- yaml: .github/workflows/release.yml § "jobs" =sha256:ccb009b24d9eef4548a1d50f13860e798d9988e2a4081cbc18bbfa85bf97b3ef

## Warrant

verify.yml's plugin-floors job builds every distribution and runs tools/check-plugin-floors.sh over every wheel and sdist; release.yml runs the same script with --release for any package other than the core and thalamus-arch. The script reads each artifact's Requires-Dist for thalamus-memory, takes the >= bound, installs the artifact with thalamus-memory==<bound> into a fresh environment, imports every module from outside the checkout in isolated mode and runs thalamus --help; a pre-release bound is reported and passes, or fails under --release. Run over the tree of ccb601b, where thalamus-measure imported sourced and LANGUAGE while flooring the core at 0.1.1, it failed thalamus-measure on the ImportError; over baaa321, before that import, every plugin passed at 0.1.1.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- .github/workflows/release.yml · standing · cites-as-live
- .github/workflows/verify.yml · standing · cites-as-live
- CLAUDE.md · standing · cites-as-live
- CONTRIBUTING.md · standing · cites-as-live
