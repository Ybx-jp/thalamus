---
id: A0232-transcript-format-rules-find-nothing-on-the-measured-corpus
kind: claim
stated: 2026-10-18T12:55:51-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 54faf58370fb8f8fa0e6588cc5da90f5085064bd54dea31a4c7eacc3cec0ddbf
---

## Assertion

With the measured sets the transcript-format rules hold, they find nothing on the Claude Code transcripts they were measured on, and with the readers' skip of the compaction summary removed they find every compaction summary in that corpus.

## Scope

metric: findings from check_transcript over a corpus of Claude Code transcripts
cohort: the 398 transcript files under ~/.claude/projects on the development box on 2026-10-18, subagent files included, and the 649 retained transcripts in its archive, written by Claude Code 2.1.181 to 2.1.302
condition: covers that corpus, one operator's sessions; a release after 2.1.302, or a feature this operator never used, can write a record the sets do not cover, which is the case the rules exist to report

## Grounds

- code: src/thalamus/harness/transcript_format.py § "KNOWN_BLOCK_TYPES" =sha256:632e96eda2b8bebc65df3aaaa658dbfb984105b1fdee451b433748d3243b71a8
- code: src/thalamus/harness/transcript_format.py § "VOICE_ORIGIN_KINDS" =sha256:ec1cc2e7786df081b4beb8684c214317a4e869496e182c298fc86b2bbd5f3c85
- code: src/thalamus/harness/transcript_format.py § "VOICE_TURN_ORIGINS" =sha256:08917cac8062adb3bafe8201ed8b2ed79dbf865d1bb666dd4c1b7f88546169af
- code: src/thalamus/harness/transcript_format.py § "VOICE_PROMPT_SOURCES" =sha256:7f7a09d202408d612f6ed44a8328afc834ea3c11e274d9cd1f27e73063cff7a9
- code: src/thalamus/harness/transcript_format.py § "VOICE_NEUTRAL_FLAGS" =sha256:d5e778af8696281d59134bb8a944c60f8d295e7a33ed2bd57171ada0bf1e97ab

## Warrant

The sets were read off the corpus before the rules were run on it: block types per role, the origin.kind, turnOrigin and promptSource values on user records whose text the readers take for the operator, and the true boolean flags on those records. The first run over the archive found two values outside them, a fallback block in 2.1.211 that carries only a model switch and a stackedExpansion flag in 2.1.204 on a slash command the operator typed with arguments; each was read, judged not to change what the readers should do, and added. The run after that found nothing in either corpus. With is_compaction_summary replaced by a function returning false, the readers as they were before the summary skip, the operator-voice rule reported all 32 records flagged isCompactSummary in the two corpora, a session's live and archived copies counted apart, by their isCompactSummary and isVisibleInTranscriptOnly flags, the earliest written by 2.1.181.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/transcript_format.py · standing · cites-as-live
