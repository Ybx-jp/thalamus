---
id: A0261-a-managers-rules-bind-every-scope-under-it-in-every-charter
kind: claim
stated: 2026-11-23T20:52:41-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: fe67d5bdc954cd84ebffe05d62ec9bff6143f8780f0e07f59e48e1629152cd0e
---

## Assertion

A scope's charter is its own domain followed by every rules text binding it: the rules of each scope on its reports_to chain up to main, ordered from the top of the chain down, and then its own. The pinned agent file, the codex profile, the delegated prompt and the consultation brief all render the charter from that text. A subordinate's rules are appended to what it inherits, and a manifest has no field that withdraws an inherited rule.

## Scope

metric: whether each charter carrier renders the rules of every scope above the pinned or consulted scope
cohort: every manifest under the config root's experts/, read through inherited_rules and charter_domain
condition: a scope reporting to main reads its own rules alone; any other scope's chain is read from the checked reporting tree

## Grounds

- code: src/thalamus/contract/reporting.py § "inherited_rules" =sha256:337bad8ed77ff20208dd4a61f223c785ad28f77df02b9a77bfca4428cadb0e89
- code: src/thalamus/contract/reporting.py § "charter_domain" =sha256:e65635d7ffa2186cb4cfc326bef5b15e01b47573c63ae31d9dc5eb363f7a3609
- code: src/thalamus/harness/pin.py § "_charter" =sha256:519925fb6ffad44ec0c87ee21ff6c5a5bd27d9cc35c5f68f5a9e8ed379dfd19a
- code: src/thalamus/harness/delegate.py § "build_prompt" =sha256:3d25939e711d156194baaffc4f9b991acc64fdfa2089bf8425f7f48f782eeb12
- code: src/thalamus/harness/consultation.py § "consult_request" =sha256:d7396430f918811d3a2fc4077b7e2b5a719aab18da9ec26e0cd59242ce62b011

## Warrant

inherited_rules walks reporting_graph's superiors from the scope's superior to main, reverses the chain so the top-most scope comes ahead, and keeps each non-empty rules text with its scope, the scope's own last. charter_domain joins the domain with one headed paragraph per entry. _charter (both the agent file and the codex profile), build_prompt and consult_request's brief interpolate charter_domain(manifest) where the domain goes. ExpertManifest's rules is a plain string, so a subordinate can add text and has no way to address an ancestor's.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/contract/reporting.py · standing · cites-as-live
