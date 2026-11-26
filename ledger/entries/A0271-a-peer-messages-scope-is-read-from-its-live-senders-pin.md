---
id: A0271-a-peer-messages-scope-is-read-from-its-live-senders-pin
kind: claim
stated: 2026-11-25T16:09:25-08:00
author: main
grade: argued
supersedes: none
verbatim_sha: 776a1b32868f65499f27aa732160e541152780068767e6530bae2243bd02769c
---

## Assertion

quick.peer_scope resolves the scope of a SendMessage sender by finding the live session descriptor whose pid and process start match the message origin's verified pair and reading that session's pin-ledger scope, falling back to the descriptor's agent; when no live descriptor matches it returns the empty string, which the digest renders as scope unknown.

## Scope

metric: the scope a PEER line in the extraction digest names
cohort: peer records whose sender is a Claude Code session in the same config dir
condition: resolution happens when the digest is rendered, so it is only as durable as the sender's process: a re-extraction after the sender exits names no scope.

## Grounds

- code: src/thalamus/harness/quick.py § "peer_scope" =sha256:eb20b4a58191fa9edd3b6e69de2e138dcae7d05eab5b65a95ee25963f173a59a
- code: src/thalamus/harness/pin.py § "ledger_scope" =sha256:1a278a802935db5390165d122b19f1dbdcc93c43ba810f5d12b7bb8ab4e064fc

## Warrant

peer_scope matches live_sessions on both pid and proc_start, which live_sessions has already checked against /proc, then asks pin.ledger_scope for the scope of the matched session id; a pin is held by the process, so the current session's row carries the scope the earlier one wrote under.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/quick.py · standing · cites-as-live
