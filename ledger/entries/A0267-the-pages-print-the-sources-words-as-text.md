---
id: A0267-the-pages-print-the-sources-words-as-text
kind: claim
stated: 2026-11-23T23:41:47-08:00
author: frontend
grade: argued
supersedes: none
verbatim_sha: 6f3969dfa9464b19ace082d10de75826533ca420a2dddf0317dcea1703d3e7d4
---

## Assertion

The jobs and board pages build every element from a source's data as text nodes and never parse a source string as markup, and they print a status's word in the colour of its tone, falling back to the muted colour for a tone they do not know.

## Scope

metric: how a string and a status from the jobs source reach the page
cohort: every element jobs.js and board.js build through surface.js's h(), and every status they print through statusWord
condition: the sandboxed app frame's own DOM is the app's, not the console's

## Grounds

- js: packages/thalamus-console/src/thalamus_console/static/surface.js § "h" =sha256:7bb24da4dd00dddf9b310f8965b9b2b05ae86eac036c194d9dce67ff16f4f068
- js: packages/thalamus-console/src/thalamus_console/static/surface.js § "appendKids" =sha256:ff3c96239b7319c1033bcc284fabcdfe55a1ea447e14f90e80c1afc78b8ac8f9
- js: packages/thalamus-console/src/thalamus_console/static/surface.js § "toneClass" =sha256:6b5d0bf8f644183d852702308651d7ed5c8713b45b2f06c9ed3a7c6ad0d10091

## Warrant

appendKids turns every child that is not already a node into document.createTextNode, h sets attributes and textContent and nothing else, and toneClass maps a tone outside TONES to the muted class; tests/js/jobs.test.mjs fails on any innerHTML, insertAdjacentHTML or outerHTML assignment in jobs.js or surface.js.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
- docs/console-jobs-source.md · standing · cites-as-live
