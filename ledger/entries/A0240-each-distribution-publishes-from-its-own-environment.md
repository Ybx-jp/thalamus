---
id: A0240-each-distribution-publishes-from-its-own-environment
kind: claim
stated: 2026-10-26T00:33:49-07:00
author: architect
grade: argued
supersedes: none
verbatim_sha: 1633868e30f1ef97c16c06045be86f3b2dd01f27bb466d381d096f78ade88fec
---

## Assertion

The release workflow's publish job runs in a deployment environment chosen by the distribution being released, pypi for the core and pypi- followed by the package name for a package under packages/, so a PyPI publisher that names its project's environment accepts uploads only from that distribution's release runs.

## Scope

metric: which deployment environment a release run's publish job runs in
cohort: runs of .github/workflows/release.yml from a tag ref
condition: each PyPI project's trusted publisher names the environment this workflow assigns it, which is configured on PyPI and not in this repository

## Grounds

- yaml: .github/workflows/release.yml § "jobs" =sha256:895840c1bc18b62507fc669c993cc958e0b6051bee7a2dfb6b23d84ad368a7a9

## Warrant

The build job's target step sets environment to pypi when the package is thalamus-memory and to pypi-<package> otherwise, exports it as a job output, and the publish job's environment is that output; PyPI's trusted publishing checks the environment claim of the job's identity token against the publisher, so a token minted in one package's environment does not match another project's publisher.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- .github/workflows/release.yml · standing · cites-as-live
- CONTRIBUTING.md · standing · cites-as-live
