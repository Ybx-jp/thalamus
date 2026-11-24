---
id: A0229-distillation-skips-the-compaction-summary
kind: claim
stated: 2026-10-18T12:26:18-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 1266e8863a74d9fb01a1ab3d5e3d7e5787aa42f3efa231c5d91f26c8c9fd54f9
---

## Assertion

The summary Claude Code writes into a session's transcript when it compacts is not read as an operator turn: the transcript facts, the extraction digest and the retrieval excerpt all skip it, and nothing of the conversation is lost by that, because a compaction only appends and leaves the turns it summarises earlier in the same file.

## Scope

metric: whether a record flagged isCompactSummary reaches the turn counts, the digest the extractor reads, or the reflex excerpt
cohort: Claude Code transcripts read by thalamus.harness.transcripts and thalamus.harness.extraction
condition: covers Claude Code 2.1.302, the version the append-only layout was measured on; the transcript format is not in the vendor's reference, so no source pins it; does not cover codex or Cursor transcripts, which carry no such flag

## Grounds

- code: src/thalamus/harness/transcripts.py § "is_compaction_summary" =sha256:876d5fdc51cbb0fbe76af38aecb307d97b91c058d0c1c0a306b0843c8fcbe272

## Warrant

is_compaction_summary is the test parse, render_digest and excerpt_for_job apply to a record before treating it as a turn, and it is true exactly for a record carrying isCompactSummary. Skipping rather than relabelling loses nothing because of how 2.1.302 compacts, measured on 2026-10-18 on both triggers: after a manual /compact the 29-line transcript as a PreCompact hook saw it was a byte prefix of the file after compaction, and after an automatic compaction at 203,341 tokens the session's first prompt and the record the boundary names as its logical parent were both still in the file, ahead of the compact_boundary record, the summary and attachment records it appended, and none of the messages it preserved was written a second time.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/extraction.py · standing · cites-as-live
- src/thalamus/harness/transcripts.py · standing · cites-as-live
