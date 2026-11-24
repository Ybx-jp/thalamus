---
id: A0263-a-jobs-source-write-passes-the-consoles-origin-gate-first
kind: claim
stated: 2026-11-23T23:08:40-08:00
author: frontend
grade: argued
supersedes: none
verbatim_sha: 24deb944aba7d3b607f68792b247c2d48bb899a2406056df66e826d8d9c50609
---

## Assertion

A POST under /api/jobs/ is forwarded to the jobs source only after the console's Origin check has accepted it, so a write sent from a page on another origin, or from a sandboxed frame whose origin is null, is refused with 403 before anything reaches the source.

## Scope

metric: whether a cross-origin or opaque-origin write can reach the jobs source through the console
cohort: every POST the console receives under /api/jobs/
condition: a request carrying no Origin or Referer is let through, as for every other write here; the check is the console's CSRF defence, not authentication

## Grounds

- code: packages/thalamus-console/src/thalamus_console/server.py § "same_origin" =sha256:b3ac4c7e43e4c58dd5c62951f3b499b1ac8e9323be5c19ed2c7b70268011823a
- code: tests/test_console_jobs_source.py § "test_a_write_from_another_page_never_reaches_the_source" =sha256:6a3e97f36de8c983380d5aba7ca7a1e0260187ddf4860d9e72f6af9de5f401a4
- code: tests/test_console_jobs_source.py § "test_a_write_from_a_sandboxed_frame_is_refused" =sha256:7f5ef1ac91343fbb0dfc9fe4dad4cbb1ccec524b58bee4ff0e417485b800d77a

## Warrant

Handler.do_POST answers 403 from its Origin check before reading the body and before any route, and the /api/jobs/ forward is one of the routes after it; a section ground cannot pin a method, so the two tests pin the behaviour over real HTTP: a write from another origin and one from an opaque origin both answer 403 and the fake source records no POST. same_origin returns False for the origin string null, which is what a sandboxed frame sends.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
- docs/console.md · standing · cites-as-live
