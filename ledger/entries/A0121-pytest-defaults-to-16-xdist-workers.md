---
id: A0121-pytest-defaults-to-16-xdist-workers
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: e9b56d6ff534bdbf4fef32d4f50d8556880f20fc1d2b8482f2e0fb457de51b19
---

## Assertion

The test suite's default pytest invocation parallelises across 16 xdist workers.

## Scope

metric: the worker count a bare `uv run pytest` uses
cohort: the project's pytest configuration
condition: not the measured runtimes or the reasoning for choosing 16 over another count, which are recorded as commentary rather than as a value this ground carries

## Grounds

- toml-key: pyproject.toml § "addopts" =sha256:23b2ea6f9ca808d86afde622553090b5de4394b0d5dad6abe567761f3f58ba87

## Warrant

`addopts` is the pytest option string applied to every invocation unless overridden, and its value names the worker count directly; reading the key is reading the default rather than inferring it from a comment that could drift from the value beside it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
