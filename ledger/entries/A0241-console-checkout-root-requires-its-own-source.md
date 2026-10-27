---
id: A0241-console-checkout-root-requires-its-own-source
kind: claim
stated: 2026-10-27T10:24:25-07:00
author: architect
grade: argued
supersedes: none
verbatim_sha: 6f596de69f71b65d7c5e816db187046ae6faf837d3cca1320ac73f01fa1bfcda
---

## Assertion

The console counts a checkout as the one it is served from only when that checkout's toplevel holds the console's server module at its path in the thalamus repository and that path resolves to the module actually running; for a console installed into a virtual environment that sits inside another repository's work tree, checkout_root returns None, so deploy returns its refusal for a console outside a checkout before it acts on that repository.

## Scope

metric: the root checkout_root returns, and so the tree deploy, build_info and the background fetch act on
cohort: a running console process, whether installed from a wheel or run from a checkout
condition: any install location, including a virtualenv inside an unrelated repository's work tree

## Grounds

- code: packages/thalamus-console/src/thalamus_console/server.py § "checkout_root" =sha256:cbf95911a2843da6801c5bd0b6c7d6b79a2f08a80c4b41d084ffd5d1ae9ea2e9

## Warrant

checkout_root asks for the toplevel above the module's own resolved path and returns it only when the toplevel joined with SOURCE_PATH resolves to that same path, returning None otherwise; deploy refuses with an error before running any command when checkout_root is None, and the fetch loop returns.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- packages/thalamus-console/src/thalamus_console/server.py · standing · cites-as-live
