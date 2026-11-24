---
id: A0266-the-console-never-follows-a-source-redirect-or-relays-a-short-reply
kind: claim
stated: 2026-11-23T23:38:32-08:00
author: frontend
grade: argued
supersedes: none
verbatim_sha: e077d4e659da9d30ee09c73818f921fc0c4e5207de1cdfd035a32c8454027da2
---

## Assertion

The console never follows a redirect from the jobs source, so the source's token never reaches the host a Location header names, and it answers 502 instead of relaying a reply whose body is shorter than its declared Content-Length or longer than the console's cap.

## Scope

metric: what the console does with a 3xx, a truncated body and an oversized body from the jobs source
cohort: every request jobs_source.forward sends, on its success and its HTTPError paths
condition: the token is also attached as an unredirected header, so the redirect refusal is not the only thing keeping it from a second host

## Grounds

- code: packages/thalamus-console/src/thalamus_console/jobs_source.py § "_NoRedirects" =sha256:668b651dcc0322177a3accad65ead75c69b2e78e97b9ea43021d84fa7f9320a7
- code: packages/thalamus-console/src/thalamus_console/jobs_source.py § "_relay" =sha256:a265b735b41e52520d7a7ea219ad5716c1830e7ca57bdd6eb98d3840d9143379
- code: tests/test_console_jobs_source.py § "test_a_redirect_is_refused_and_the_token_goes_nowhere" =sha256:77157c06c17af998e7426f418c2d5b41c86686cc62b2bdefa2a570304fcad382
- code: tests/test_console_jobs_source.py § "test_a_truncated_reply_is_a_failure_not_a_short_answer" =sha256:c96ea59434ab543e3c668e67fab238d7c01f6d4654ea155be9bcc24d21f3ee1d

## Warrant

_NoRedirects.redirect_request returns None, so urllib raises the 3xx as an HTTPError, which forward turns into a 502 without opening the Location; _relay reads one byte past the cap and compares what arrived with Content-Length, answering 502 for either mismatch, and forward sends both its success and its HTTPError replies through it. The two tests show it over real HTTP: the redirect target records no request, and a source that declares 500 bytes and sends 7 gets a 502.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
- docs/console-jobs-source.md · standing · cites-as-live
