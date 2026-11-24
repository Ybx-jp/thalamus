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

- 2026-11-23T23:39:08-08:00 · contested · grade: argued · author: propagation
  evidence: code: packages/thalamus-console/src/thalamus_console/jobs_source.py § "forward" =sha256:9f43e31d48bf477af81fcc8f9cd4d160c287f97b98e95e7b959c45d4ca611519
  artifact: sha256:88b7034e31b48af1445912b0272092bfae471d20ee72e046688e482748ad01b0
  note: propagated from a moved ground
- 2026-11-24T01:58:33-08:00 · corroborated · grade: argued · author: main
  evidence: code: packages/thalamus-console/src/thalamus_console/jobs_source.py § "forward" =sha256:88b7034e31b48af1445912b0272092bfae471d20ee72e046688e482748ad01b0
  note: forward moved for the proxy fixes: the token is now added with add_unredirected_header, redirects are refused through _NoRedirects and answered 502, and the reply is built by _relay, which 502s a short or oversized body and otherwise keeps only PASSED_HEADERS. The token is still read and attached in the console process, no relayed header and no 502 message carries it, so it still never reaches the browser

## References
- docs/console.md · standing · cites-as-live
