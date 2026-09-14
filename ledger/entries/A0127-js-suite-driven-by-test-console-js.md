---
id: A0127-js-suite-driven-by-test-console-js
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: f91e9153f959548be320e77132a78bf91e7b06c414ffd643219fcb4d8fcbb332
---

## Assertion

The console's `*.test.mjs` files are discovered and run as pytest cases from within `tests/test_console_js.py`, which shells out to node against each one.

## Scope

metric: what discovers and executes the console's JavaScript test files
cohort: the bridge between the JS test files and the pytest run
condition: not the JS test files' own assertions, only the mechanism that finds and runs them

## Grounds

- code: tests/test_console_js.py § "SCRIPTS" =sha256:e281deca9a3fbc8caf4e3ed0fcfcc206d7eac9c2147cba719a12e6cd1c2a448a
- code: tests/test_console_js.py § "test_console_js" =sha256:4a939460fb8f401fbcc134c9ee7a788707ab7fbc1d63abb5ee5470f442ba56a0

## Warrant

`SCRIPTS` globs every `*.test.mjs` file under the JS test directory, and `test_console_js` runs the node binary against a script and fails the pytest case on a non-zero return code; together they are the whole of what turns a `.test.mjs` file into a pytest result.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
