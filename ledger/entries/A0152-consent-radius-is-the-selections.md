---
id: A0152-consent-radius-is-the-selections
kind: claim
stated: 2026-09-14T21:27:45-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: b536ea6c9729c035a96cbed0b109ed6d3896473cee4ff5474ec3e1e51c45b2da
---

## Assertion

The blast radius `thalamus init` names before asking is the one its `--harness` selection will write: a harness's targets appear in the consent prompt only when that harness is in the selection, and the targets outside the selection gate appear for every selection.

## Scope

metric: which write targets the consent prompt names, as a function of the harness selection
cohort: every interactive `thalamus init` run that reaches the prompt
condition: what the prompt names, not whether the operator is asked at all and not whether `install()` writes anything a prompt line omits — the second is A-less and held by `tests/qe/cases/install_consent.py`

## Grounds

- code: src/thalamus/harness/install.py § "_consent_lines" =sha256:83b4a9cd6c2d11f1e992515ba4d5719f2c7e7d7b7e5f9078fdf587c8e379449a

## Warrant

`_consent_lines` builds its list under `if "claude" in harnesses`, `if "cursor" in harnesses` and `if "codex" in harnesses`, the same three memberships `install()` gates its legs on, and appends the skills, agents and profile lines outside every branch, which is where `link_skills()` and `write_all_agents()` sit in `install()`. So a line is printed exactly when the leg that writes it will run.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-20T20:37:07-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/harness/install.py § "_consent_lines" =sha256:83b4a9cd6c2d11f1e992515ba4d5719f2c7e7d7b7e5f9078fdf587c8e379449a
  artifact: sha256:d3826e654bfd232338d3f54777aacf0090c959b8b5b68fa1cc261ed97ab3133b
  note: propagated from a moved ground

- 2026-09-20T20:37:29-07:00 · corroborated · grade: argued · author: main
  evidence: code: src/thalamus/harness/install.py § "_consent_lines" =sha256:d3826e654bfd232338d3f54777aacf0090c959b8b5b68fa1cc261ed97ab3133b
  note: the citation marker inside this section now names the entry by id alone, under the `citation-slug` rule `claims-ledger.toml` sets for source files, and the docstring line holding it was rejoined. The assertion is unaffected.

## References

- src/thalamus/harness/install.py · standing · cites-as-live
