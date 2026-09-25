---
id: A0207-word-search-splits-an-unmatched-identifier
kind: claim
stated: 2026-09-25T02:17:42-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 93f2fd15823f8e937510bcb76342ebc5e1d5d0cda25d095b5822f81be9767924
---

## Assertion

A word search over one kind of node, as the agentic plan's lexical_by_kind and the memory_search_kind MCP tool run it, searches a compound identifier as written first, and only when that finds no node of the kind does it search the identifier's parts, split on underscores, dots, slashes, colons, hyphens and lower-to-upper case boundaries, each part then counting as a term of its own toward the two-term match floor.

## Scope

metric: which terms a word search over one kind scans for, and which count toward its match floor
cohort: queries passed to lexical_by_kind
condition: a part of two characters or fewer, a stopword, or `test`/`tests` is dropped; a query grows to at most MAX_TERMS terms by splitting; an all-lowercase compound with no separator is searched whole only

## Grounds

- code: src/thalamus/substrate/vocabulary.py § "lexical_by_kind" =sha256:7ed569bed86a93b1771f596ce9a5ec3e4f3b9f9d9a253f5a4b524fa6af0ceaa9
- code: src/thalamus/substrate/vocabulary.py § "identifier_parts" =sha256:8c269f15809453492019bdefa8205eaae9018b6550677700285dcb801491ed20
- search: corpus=src/thalamus; query="identifier_parts"; date=2026-09-25

## Warrant

lexical_by_kind appends a keyword to its terms when its scan finds a node, and otherwise replaces it with the parts identifier_parts returns, scanning each and stopping once the terms reach MAX_TERMS; the floor is the smaller of two and the number of terms. identifier_parts returns nothing for a token with no separator or case boundary, so such a token is a term that matched nothing. A search of src/thalamus for identifier_parts finds its definition and one caller, lexical_by_kind, which reads the parts only in the branch taken after a keyword's scan found nothing, so no other path splits a query.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
