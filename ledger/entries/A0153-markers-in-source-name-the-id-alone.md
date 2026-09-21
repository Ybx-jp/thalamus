---
id: A0153-markers-in-source-name-the-id-alone
kind: claim
stated: 2026-09-20T20:38:51-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: c2e22d6c6882d06fed094ebb20f32f3b43c0c07d414a2737232d2f2456dd5d60
---

## Assertion

A citation marker written in a Python or shell file in this repository names its entry by the id alone, and `claims-ledger references` fails the run when one carries the entry's slug; every other document may write either spelling.

## Scope

metric: which of the two marker spellings each document in this repository may use
cohort: every path the configured document globs reach
condition: the `citation-slug` rule as `claims-ledger.toml` sets it; how a marker is written in a rendered document, and where in a file it sits, are separate questions

## Grounds

- toml-key: claims-ledger.toml § "citation-slug" =sha256:2835be9d273a2b240a0dbe1fd0019643c9a8801a8c16b68234d79349be187e6d

## Warrant

`citation-slug` is a list of rules, and the first whose paths match a document decides it. The one rule here names `**/*.py` and `**/*.sh` with the policy `forbid`, which `references` reports as a failure against a marker carrying a slug; a document no rule matches is asked nothing, which leaves every other configured document free to write either spelling.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-20T21:05:23-07:00 · superseded · grade: argued · author: main
  evidence: entry: A0154-markers-name-the-id-alone-in-every-document · supersedes
  note: the rule no longer stops at Python and shell files — `citation-slug` is now a bare `forbid` governing every configured document, so the clause leaving every other document free to write either spelling is false. What the two entries say about a source file is the same.

## References
