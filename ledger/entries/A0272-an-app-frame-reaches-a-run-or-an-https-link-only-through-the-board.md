---
id: A0272-an-app-frame-reaches-a-run-or-an-https-link-only-through-the-board
kind: claim
stated: 2026-11-25T21:56:08-08:00
author: frontend
grade: argued
supersedes: none
verbatim_sha: 9ffebe81117dd121f2bf03ef105d89cdb393913797781926283679cc2e648ac7
---

## Assertion

An app frame can ask the board to go to a job run's page only by naming a run id the jobs source's runs route would take, and to open a link only when it is https; an open may name a view token, matched whole, that becomes the full page's hash; anything else in those messages is dropped.

## Scope

metric: what an app frame can make the board navigate to or open
cohort: every app widget the board renders, tile or full screen
condition: the frame's own sandbox, which allows no navigation of its own, is A0264's

## Grounds

- js: packages/thalamus-console/src/thalamus_console/static/board.js § "routeAppMessage" =sha256:4aa0647281bec88703ae7a54eb49398b7e5b720e72d83fbda606c9d04cdf8981
- js: packages/thalamus-console/src/thalamus_console/static/board.js § "httpsUrl" =sha256:c660e53f5c029165bb93932cc69a4c7a37c631938aa12511e78700133e6cf5db

## Warrant

routeAppMessage returns a run act only when the run matches the hex run-id pattern whole, an open's view only when it matches the token pattern whole, and a link act only for a URL httpsUrl accepts; httpsUrl parses the value and returns it only when its protocol is https:.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
- docs/console-jobs-source.md · standing · cites-as-live
