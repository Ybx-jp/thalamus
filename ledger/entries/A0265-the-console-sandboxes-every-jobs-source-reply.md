---
id: A0265-the-console-sandboxes-every-jobs-source-reply
kind: claim
stated: 2026-11-23T23:31:57-08:00
author: frontend
grade: argued
supersedes: none
verbatim_sha: 6ed5d30e62a3408192f6a3b98036231b5296199108fbf613192913a0be1d4fc6
---

## Assertion

Every reply the console relays under /api/jobs/ carries the console's own Content-Security-Policy of sandbox allow-scripts and X-Content-Type-Options nosniff whatever the source sent, with the source's own policy sent as a further header line, so a document a source serves runs in an opaque origin even when opened at top level and cannot use the console's API.

## Scope

metric: the header lines on a reply relayed from the jobs source
cohort: every response the console's /api/jobs/ forward answers, including the forwarder's own 400 and 502
condition: a browser enforces every Content-Security-Policy header it receives, so the source's policy can narrow and not widen; whether a given page still works under the sandbox is the page's concern

## Grounds

- code: packages/thalamus-console/src/thalamus_console/jobs_source.py § "FORCED_HEADERS" =sha256:e1096bcd8e8befd5c85d181ebabd9edaa6015607d70b651670a699eac72a1742
- code: packages/thalamus-console/src/thalamus_console/jobs_source.py § "relay_headers" =sha256:cb594449300cdf6842453f4078d91a7cd112166ce0529861f273c4adb2f27600
- code: tests/test_console_jobs_source.py § "test_every_jobs_reply_carries_the_consoles_own_sandbox_policy" =sha256:d0b41e8b6c342ff0944ddf31acbddb109f5eed2c2822e0b42e21f86601805956

## Warrant

FORCED_HEADERS holds the sandbox policy and nosniff; relay_headers always starts from it and appends the source's policy and CORS header as separate lines; Handler._jobs sends relay_headers on every forward reply, and the test checks the lines over real HTTP on a file reply, a JSON reply, a source 404 and a forwarder 400.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
- docs/console-jobs-source.md · standing · cites-as-live
