---
id: A0230-contract-check-transcripts-fails-on-any-format-finding
kind: claim
stated: 2026-10-18T12:55:50-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 8a52cc5ad2c2694a7305f81c54523355d25f4ff40e4000869bc1d445165e4253
---

## Assertion

thalamus contract check --transcripts checks every Claude Code transcript under ~/.claude/projects, and every pair of archived snapshots of one session, against the transcript-format rules, prints each finding with the transcript it is in, and exits 1 when there is any finding; it reads no graph and makes no model call.

## Scope

metric: the exit status and output of thalamus contract check --transcripts
cohort: the transcripts discover() offers, extraction sandboxes excluded, and the sessions archived_snapshots() finds more than one retained file for
condition: covers Claude Code transcripts only; codex and Cursor transcripts are not checked

## Grounds

- code: src/thalamus/cli.py § "_report_transcript_format" =sha256:34e97ea2cbc5a0940fa0b89c4808beee76013cbc04545bc9adfec89aa1f99388

## Warrant

_report_transcript_format runs check_transcript on every path discover() returns and check_snapshots over the archive, prints a line per transcript with findings and per broken snapshot pair, and calls sys.exit(1) when either list is non-empty; it never connects to the graph, which _cmd_contract reaches only after the --transcripts branch has returned.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/cli.py · standing · cites-as-live
