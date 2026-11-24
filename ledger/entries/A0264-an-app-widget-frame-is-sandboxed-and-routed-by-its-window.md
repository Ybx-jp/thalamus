---
id: A0264-an-app-widget-frame-is-sandboxed-and-routed-by-its-window
kind: claim
stated: 2026-11-23T23:25:31-08:00
author: frontend
grade: argued
supersedes: none
verbatim_sha: d5199dabd49fce18a3d475946b7ce4d536ba36ea93eaaa16f6dc23c6cdafa823
---

## Assertion

The board embeds an app widget in an iframe whose sandbox allows scripts and nothing else, so the app runs in an opaque origin, and the board acts on a message only when it comes from one of its own registered app frames, finding the app by the sending window and never by anything the message says.

## Scope

metric: what an app frame is allowed by its sandbox, and how the board decides which app a message speaks for
cohort: every app widget the board page renders, as a tile or full screen
condition: the frame-src policy that keeps a registered frame from navigating to another origin lives in board.html and is measured there; the server-side grant is the jobs source's

## Grounds

- js: packages/thalamus-console/src/thalamus_console/static/board.js § "appFrame" =sha256:3e1c2e05e245150ed63f4420cb601c95a368417cb18180fea43d6d788b3b1526
- js: packages/thalamus-console/src/thalamus_console/static/board.js § "routeAppMessage" =sha256:647744831c5c564153ba355eeeebf727e40c1986f961abe4c48d5447ec6161dc

## Warrant

appFrame sets sandbox to allow-scripts alone, which leaves out allow-same-origin and so gives the frame an opaque origin; routeAppMessage looks the sender up in the registry keyed by contentWindow and returns null for any window it does not hold, and the app it acts for is the registry entry's, not a field of the message.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
- docs/console.md · standing · cites-as-live
