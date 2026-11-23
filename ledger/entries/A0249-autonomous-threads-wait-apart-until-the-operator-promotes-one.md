---
id: A0249-autonomous-threads-wait-apart-until-the-operator-promotes-one
kind: claim
stated: 2026-11-23T01:56:24-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 17074c4ba65fd1eab7adc10ead4c31a1106b733fb1b620ba2971232eb40292bd
---

## Assertion

The default open-threads read leaves out every thread an autonomous session opened that carries no promotion, and the autonomous read returns exactly those. Promoting a thread sets its promotion properties and nothing else, and is refused for a thread that is absent or was not opened by an autonomous session.

## Scope

metric: which open threads each of the two reads returns, and what a promotion writes
cohort: open and in-progress Thread vertices in one scope
condition: the reader's two queues and the promotion write; the ledger row a promotion appends first is outside this claim

## Grounds

- code: src/thalamus/substrate/reader.py § "_awaiting_promotion" =sha256:bd730a0deb2fd3df063cb9e94e719e36077b446cd740d0b491db923853db76c0
- code: src/thalamus/substrate/reader.py § "recall_open_threads" =sha256:5c5ae21e7e3c3ca704513965196c24fde51de60b8442ac3d3c40134b81d641d1
- code: src/thalamus/substrate/writer.py § "write_thread_promotion" =sha256:371874b3951a79975dd59dbaaa228a802661f8df2993f8d3fbba0f6867f03c47
- code: src/thalamus/substrate/writer.py § "check_promotable" =sha256:16a49f7826c46e571fefbae1cd667cf8e461f0c7a688092c5297bf8228b9ce24

## Warrant

_awaiting_promotion selects a thread whose session_type is autonomous and that has no promoted_at. recall_open_threads keeps only threads matching it when autonomous is set and excludes exactly those otherwise, so the two reads are complements over the open threads. write_thread_promotion calls check_promotable, which raises unless the vertex is a Thread held as autonomous, and then sets promoted_at, promotion_ref and promotion_surface and no other property, so tier and session_type stay as written.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- CLAUDE.md · standing · cites-as-live
- src/thalamus/substrate/reader.py · standing · cites-as-live
