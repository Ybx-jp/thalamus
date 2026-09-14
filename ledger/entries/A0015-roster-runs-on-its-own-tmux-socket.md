---
id: A0015-roster-runs-on-its-own-tmux-socket
kind: claim
stated: 2026-09-13T20:13:31-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: a94609477242a6acb40ef46a31c518e85d9e2b4704053fcc3ced6d17a9259eed
---

## Assertion

The roster runs on a tmux server of its own, `tmux -L thalamus`, named by `THALAMUS_TMUX_SOCKET`.

## Scope

metric: which environment variable names the tmux socket, and what its default is
cohort: every tmux invocation the roster makes
condition: the socket name only

## Grounds

- code: src/thalamus/harness/tmux.py § "SOCKET_ENV" =sha256:fee4ab61b591612a236711bc86876d9a71e4e486650a99142c4e146ddb7462b5

## Warrant

SOCKET_ENV and DEFAULT_SOCKET are what every tmux call the roster makes reads to pick its -L argument, so together they are the whole of what names the socket.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
