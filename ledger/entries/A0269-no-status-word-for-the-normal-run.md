---
id: A0269-no-status-word-for-the-normal-run
kind: claim
stated: 2026-11-25T00:48:59-08:00
author: frontend
grade: argued
supersedes: none
verbatim_sha: 50a16cbf8b5a78e3dbd9d5c38a7d44ffb375ea3ab1da7aff9d58094e33e6b558
---

## Assertion

The jobs-source contract sends a run's or stage's status only when it is running, failed, found nothing or skipped, and a run's right-hand word otherwise says what it produced; a finding reaches the pages as a meta line, an optional title, an observation and a short source link, all printed verbatim by one renderer; and a board widget's result carries a view-mode source line in words beside the table names the board prints only in edit mode.

## Scope

metric: which words the jobs and board pages can receive for a run's status, a finding and a widget's footer
cohort: the RunStatus, RunRef, Finding, FindingSource and EvalSource shapes of jobs_source.openapi.json, and the pages that render them
condition: a source that sends a shape the contract does not name is outside what the pages promise to draw

## Grounds

- code: tests/test_console_jobs_spec.py § "test_the_tone_vocabulary_is_closed_and_runs_map_one_to_one" =sha256:d65e5f32476ffb0f2153f656f753bc62d5e26940488e3740a809a95e0c7824a1
- js: packages/thalamus-console/src/thalamus_console/static/surface.js § "findingCard" =sha256:a789b242f826152a1d095340fa7f37e37541a44ada212b4cb20fa0162a93f2bf
- js: packages/thalamus-console/src/thalamus_console/static/board.js § "cardFoot" =sha256:ec8c5e06805554941f0b34ecc310184420213ae1a72a334451e37d0a283e49ef

## Warrant

The spec test pins RunStatus's closed word set to failed, running, found nothing and skipped, and every example in the contract validates against its schema in the same file, so a source example that sends notable or silent as a status fails the suite; findingCard prints meta, title or observation and the source link's text without branching on any of their values; cardFoot prints the source line outside edit mode and the foot's table names inside it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
- docs/console-jobs-source.md · standing · cites-as-live
- docs/console.md · standing · cites-as-live
