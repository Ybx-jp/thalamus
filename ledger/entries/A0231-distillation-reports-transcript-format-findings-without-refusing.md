---
id: A0231-distillation-reports-transcript-format-findings-without-refusing
kind: claim
stated: 2026-10-18T12:55:51-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 5d23a7798bc99684e698ff116e2ab0867a6cd0ea7bd026299bad67a9638fe94a
---

## Assertion

Each Claude Code session thalamus extract distils has its transcript checked against the transcript-format rules, and any finding is written as a dated row to ~/.thalamus/logs/transcript-format.log and printed to stderr, while the distillation goes on as if there were none.

## Scope

metric: what a transcript-format finding produces on the distillation path
cohort: Claude Code sessions distilled by thalamus extract, including the one SessionEnd launches
condition: covers the report; the console does not read the log, so a detached run's finding is seen only in the log or the session-end log

## Grounds

- code: src/thalamus/harness/transcript_format.py § "report_findings" =sha256:64cec6b1b2fc2aa8a68d3dcb1cff1ccebe234d5a0cd8d7fd497dca55b035564a

## Warrant

report_findings returns an empty string and writes nothing for a clean report, and otherwise appends one row per distinct finding to FORMAT_LOG and prints the summary and each row to stderr; it raises nothing and returns nothing a caller could refuse on. _cmd_extract calls it with check_transcript of the session's transcript right after the transcript is retained, for every session whose facts name the claude-code harness, and continues to the graph write whatever it returned.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/transcript_format.py · standing · cites-as-live
