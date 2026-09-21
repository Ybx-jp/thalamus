---
id: A0154-markers-name-the-id-alone-in-every-document
kind: claim
stated: 2026-09-20T21:05:03-07:00
author: main
grade: argued
supersedes: A0153-markers-in-source-name-the-id-alone
verbatim_change: the rule widened from Python and shell files to every configured document, so the Scope's cohort is now every document rather than the paths two globs reached
verbatim_sha: cb43abd275172b6dcecd78fbd30970457adfdab0622ff3bda6b7d9f7e64f1674
---

## Assertion

A citation marker written anywhere in this repository names its entry by the id alone, and `claims-ledger references` fails the run when one carries the entry's slug; the rule reaches every configured document, source and Markdown alike.

## Scope

metric: which of the two marker spellings a document in this repository may use
cohort: every document the configured globs reach
condition: the `citation-slug` rule as `claims-ledger.toml` sets it; where in a file a marker sits, and whether a Markdown one is hidden in a comment, are separate questions

## Grounds

- toml-key: claims-ledger.toml § "citation-slug" =sha256:d0da32e7884064ecc33f02bef94ef8a07cfbaaf212f0c5cfb3df6f75b4a1fbc3

## Warrant

`citation-slug` written as a bare string is one rule carrying no paths, and a rule with no paths governs every document rather than being matched against one. Its value here is `forbid`, which `references` reports as a failure against any marker carrying a slug, so no configured document is left asking either spelling.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- claims-ledger.toml · standing · cites-as-live
- CONTRIBUTING.md · standing · cites-as-live
