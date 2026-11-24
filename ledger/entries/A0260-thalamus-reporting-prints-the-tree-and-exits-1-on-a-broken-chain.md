---
id: A0260-thalamus-reporting-prints-the-tree-and-exits-1-on-a-broken-chain
kind: claim
stated: 2026-11-23T17:36:11-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 5f2a020348f607997c13d97a24e24844b111304b1109d1eb5b01dbc6d62a2f11
---

## Assertion

thalamus reporting prints the reporting tree as indented text, main on the top line and each scope indented under its superior; with --json it prints each scope's superior and each scope's direct reports. A broken chain exits 1 with the refusal on stderr.

## Scope

metric: what thalamus reporting prints and how it exits
cohort: the config root the CLI resolves, THALAMUS_CONFIG_DIR first
condition: every invocation

## Grounds

- code: src/thalamus/cli.py § "_cmd_reporting" =sha256:3886d15675de46f0be19cfce1cc3529b9add71ed8467144f5502bd25ec0bbe2b
- code: src/thalamus/contract/reporting.py § "ReportingGraph" =sha256:71b98e75a3ea7e4fb78b838640c1600ac4b89ae7605963f63dfbaf3ea28267dd

## Warrant

_cmd_reporting builds the graph with reporting_graph, turns a ValueError or FileNotFoundError into sys.exit with the message, which writes it to stderr and exits 1, and prints either as_dict as JSON or lines. ReportingGraph.lines walks from main depth-first, two spaces per level, children sorted; as_dict holds reports_to as scope to superior and reports as each scope with direct reports to their sorted list.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
