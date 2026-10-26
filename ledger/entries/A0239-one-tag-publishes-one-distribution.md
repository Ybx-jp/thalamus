---
id: A0239-one-tag-publishes-one-distribution
kind: claim
stated: 2026-10-26T00:09:58-07:00
author: architect
grade: argued
supersedes: none
verbatim_sha: 01800ad6233d0930fd93bb11faf551d97017fb5517d9ebaafb076bf4788c40f5
---

## Assertion

The release workflow publishes only from a tag ref, and a tag publishes exactly one distribution: a bare v tag the core, thalamus-memory, and a tag of the form package-vX.Y.Z the package of that name under packages/, built on its own at the version the tag names.

## Scope

metric: which distributions a run of the release workflow uploads to PyPI
cohort: runs of .github/workflows/release.yml, by tag push or by dispatch
condition: the workflow file as committed; PyPI's own publisher configuration is outside it

## Grounds

- yaml: .github/workflows/release.yml § "jobs" =sha256:630efc05b104206bc819e63cde39dcb996892f782f92ac9a1e8fdf9f02297d13

## Warrant

The build job's target step maps the tag name to one distribution and refuses a tag that names none or a directory declaring another name, uv build builds only that package into dist, the version step refuses a wheel whose metadata version differs from the tag, and the publish job, gated on a tag ref, uploads that dist directory and nothing else.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- .github/workflows/release.yml · standing · cites-as-live
- CONTRIBUTING.md · standing · cites-as-live
