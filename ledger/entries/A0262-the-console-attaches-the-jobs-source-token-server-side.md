---
id: A0262-the-console-attaches-the-jobs-source-token-server-side
kind: claim
stated: 2026-11-23T23:08:31-08:00
author: frontend
grade: argued
supersedes: none
verbatim_sha: 35eb9a41aad612903620e2812896ec0fded2f492bf4d415b10d1fed0087b960b
---

## Assertion

The console forwards a request under /api/jobs/ to the jobs source's /v1/console/ tree with the source's bearer token read from the token file and attached by the console process, and relays only the source's status, body and a fixed list of reply headers, so the token never reaches the browser.

## Scope

metric: where the jobs source's token is attached and what of the source's reply reaches the browser
cohort: every request the console forwards to a configured jobs source
condition: the token file named by --jobs-token-file; the path checks that keep a forward inside /v1/console/ are part of the same function

## Grounds

- code: packages/thalamus-console/src/thalamus_console/jobs_source.py § "forward" =sha256:9f43e31d48bf477af81fcc8f9cd4d160c287f97b98e95e7b959c45d4ca611519

## Warrant

forward builds the Authorization header from the token file inside the server process and returns a Reply holding the source's status, body and only the headers named in PASSED_HEADERS, none of which carries the request's own Authorization header, so the token has no path into the response the console sends.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
- docs/console.md · standing · cites-as-live
