---
id: A0167-reflex-shadow-logs-calls-the-failure-test-passes-over
kind: claim
stated: 2026-09-24T00:57:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 148f21b41ed0d679c2078cff504b610d7cb3d6957441e780359e9e689696a2a7
---

## Assertion

A Bash call whose output the reflex's failure test passes over, on either hook event, is shadow-logged by a detached process the hook does not wait for: one row per call recording the event, the anchors the output would have given, how many of them this agent's live firings have not spent, and whether that clears the query gate a firing applies, with nothing retrieved, traced or injected; eval reflex counts those rows per event.

## Scope

metric: which Bash calls produce a shadow row, what the row holds, and whether the hook or the graph is touched in producing it
cohort: Bash calls in a Claude Code session that reach reflex.sh and do not qualify as failures
condition: a sandboxed session, a payload with no session id and a non-Bash tool exit before the failure test and produce no row

## Grounds

- code: src/thalamus/harness/hooks/claude-code/reflex.sh § "log_dir" =sha256:683fbe2423d6545cc5aae6bddbc48c770af8a3360a91bbb47577898caa11cb66
- code: src/thalamus/harness/reflex.py § "ShadowRow" =sha256:7e5ab97d76a766ae16512d580a94ca9149f4e4612d7d9e2b0d0f25c0482fed82
- code: src/thalamus/harness/reflex.py § "shadow" =sha256:9330b922beb6a5d6a1215e21c4258fd07b0259db99bb67d3d35c83e2aa7bb4c2
- code: src/thalamus/eval/reflex.py § "reflex_report" =sha256:627349e2564b752496c1e7584c8a5d52ed0e3352638604527d0037ed97702238

## Warrant

In reflex.sh the branch taken when neither the failure pattern matches nor the call was interrupted starts thalamus reflex with the shadow flag under nohup, with its standard streams closed and in the background, then exits the hook with no output. The shadow function extracts anchors with the same extractor fire uses, counts those whose key no live firing by the same agent has recorded, applies the same minimum of new anchors, and appends a ShadowRow to the shadow directory; it calls neither recall nor the trace writer. reflex_report reads every shadow row and counts calls, calls with anchors and calls that would have queried, keyed on the event.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-24T18:02:04-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/eval/reflex.py § "reflex_report" =sha256:627349e2564b752496c1e7584c8a5d52ed0e3352638604527d0037ed97702238
  artifact: sha256:6dacbee7c02af7c68613d11798cbb06a9a5a9a3f57763f537802b4ba58da358c
  note: propagated from a moved ground
- 2026-09-24T18:02:30-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/eval/reflex.py § "reflex_report" =sha256:6dacbee7c02af7c68613d11798cbb06a9a5a9a3f57763f537802b4ba58da358c
  note: reflex_report gained per-plan outcome counts and per-arm trace numbers; the shadow-row loop and its three per-event counts are unchanged, so the assertion is unaffected
- 2026-09-24T20:35:18-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/eval/reflex.py § "reflex_report" =sha256:6dacbee7c02af7c68613d11798cbb06a9a5a9a3f57763f537802b4ba58da358c
  artifact: sha256:261d36075e7a26a59affe64959ccd47ffd4313827d87e1f46950a373cb845688
  note: propagated from a moved ground
- 2026-09-24T20:37:18-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/eval/reflex.py § "reflex_report" =sha256:261d36075e7a26a59affe64959ccd47ffd4313827d87e1f46950a373cb845688
  note: reflex_report gained a loop over the queue's job ledger ahead of the shadow loop; the shadow loop and its per-event counts are unchanged, so the assertion is unaffected


## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/hooks/claude-code/reflex.sh · standing · cites-as-live
- src/thalamus/harness/reflex.py · standing · cites-as-live
