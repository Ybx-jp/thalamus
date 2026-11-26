---
id: A0270-a-session-messaged-only-by-peers-distills-with-peer-lines
kind: claim
stated: 2026-11-25T16:09:25-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 024f2641306c88ff8610cfc14f42376b47435b47c6c91a9f7c86f8f9dd4f5ec2
---

## Assertion

Claude Code records a message delivered by SendMessage as a user record marked isMeta whose origin has kind peer and carries the sender's session name, verified pid, verified process start and the message body; an operator's typed prompt carries origin kind human and no isMeta. transcripts.parse counts a peer record as a user turn but not a prompt turn, so a session whose only input was peer messages passes has_substance on its tool calls, and render_digest renders it as a PEER line naming the sender and its scope rather than as a USER line.

## Scope

metric: how a SendMessage delivery is recorded in a Claude Code transcript, and how parse and render_digest read it
cohort: interactive Claude Code sessions on this box receiving cross-session messages
condition: measured on Claude Code 2.1.332, 2026-11-25, over four transcripts withheld as insubstantial (228080c2, 1bd22369, ceddb844, 26b01310): every request each received was a user record with isMeta true and origin.kind peer, with verifiedPeerPid matching the sender's ~/.claude/sessions/<pid>.json and verifiedPeerProcStart its procStart. The control was the same harness version's typed prompts in session 98636dda, which carried origin.kind human and no isMeta. Each of the four parsed to user_turns 0 before the change.

## Grounds

- code: src/thalamus/harness/transcripts.py § "peer_origin" =sha256:2fa956e4c43b5b2e3595a0102de86c76afd054dcba72b4d38eeec2644638f755
- code: src/thalamus/harness/transcripts.py § "parse" =sha256:9c4b678f325d90e328bfe40eeaaf32042f87eb483cf2cddb1bf9c0b82b512b09
- code: src/thalamus/harness/extraction.py § "render_digest" =sha256:5b4ca140b4abd929de6f97b97de4b0aaaa475e69c64ccbade33370a0874dc197

## Warrant

peer_origin is true exactly for a user record whose origin kind is peer; parse tests it before the isMeta skip and increments user_turns without prompt_turns, and render_digest tests it before the same skip and appends a PEER line with the resolved scope. has_substance needs a user turn and then a prompt or a tool call, so a peer-only session with tool use passes and a peer-only session without it does not.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/extraction.py · standing · cites-as-live
- src/thalamus/harness/transcripts.py · standing · cites-as-live
