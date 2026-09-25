---
id: A0173-retired-sources-take-only-what-rests-on-them
kind: claim
stated: 2026-09-24T02:42:23-07:00
author: architect
grade: measured
supersedes: none
verbatim_sha: 7843fd7c4e9a818e13af621886b3905e5298cd6d598905b2359624aeffd3e249
---

## Assertion

`thalamus retire-sources` removes a Claim or Chunk only when every `DERIVED_FROM` edge it has lands on a retiring Source, and an Entity only when every vertex adjacent to it is also being removed; the dry run counts, by edge label, the edges surviving vertices lose.

## Scope

metric: which Claims, Chunks and Entities a source retirement plan removes, and which lost edges it reports
cohort: every plan decide builds from rows read for the named Sources
condition: the decision over rows already read; the traversals that read them are not covered

## Grounds

- code: src/thalamus/substrate/source_retirement.py § "decide" =sha256:1e9b5ceb25520710f608a5da5dd18714b9899b98193acce90db3e82b6105d18c
- code: tests/test_source_retirement.py § "test_a_claim_another_document_also_supports_is_kept" =sha256:245201fa601d02c1de45fe164e1eca7ac06914761a1d95ba835835a255911acf
- code: tests/test_source_retirement.py § "test_an_entity_another_claim_mentions_is_kept" =sha256:8cfdb254b4c514a9b4d14ca4a0b6151e010acc0275b3102d0f36a6c1fd433369
- code: tests/test_source_retirement.py § "test_edges_from_surviving_vertices_are_counted_as_history_lost" =sha256:d8acb6eab195611588a135aa244ec4081d7a8101baa5c00f82a3c2f3b3e6c314

## Warrant

decide is the only place the plan chooses what goes: it keeps a derived vertex with any DERIVED_FROM target outside the retiring set, keeps an Entity with any surviving neighbour, and counts edges from retiring Claims and Chunks to vertices outside the plan; the three tests exercise each of those rules.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
