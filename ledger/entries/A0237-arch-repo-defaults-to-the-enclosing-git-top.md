---
id: A0237-arch-repo-defaults-to-the-enclosing-git-top
kind: claim
stated: 2026-10-25T23:46:33-07:00
author: architect
grade: argued
supersedes: none
verbatim_sha: 11098f6dec9df3d1122f9d7655c746e7b21bd46d300d9c5b86a218b3a898b371
---

## Assertion

With no --repo, the arch subcommands measure the top of the version-controlled repository that holds the working directory, and outside any repository the working directory itself.

## Scope

metric: which directory an arch subcommand reads arch/model.yaml from and scans
cohort: thalamus-arch and thalamus arch invoked without --repo
condition: the version-control executable on the PATH

## Grounds

- code: packages/thalamus-arch/src/thalamus_arch/model.py § "repo_root" =sha256:c87a7df7002dca64372766a71d1ece13817e8d72ce889e0743ec48cc278e142b

## Warrant

repo_root asks for the top level of the repository from the given start, defaulting to the current directory, returns that top when the command succeeds and the start itself when it fails, and run resolves the repository through repo_root whenever args.repo is unset.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
- packages/thalamus-arch/src/thalamus_arch/model.py · standing · cites-as-live
