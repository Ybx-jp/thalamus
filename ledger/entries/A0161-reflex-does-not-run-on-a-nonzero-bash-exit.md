---
id: A0161-reflex-does-not-run-on-a-nonzero-bash-exit
kind: claim
stated: 2026-09-23T23:39:20-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 557104d7f8421b6925b2579f5bf6f6002a2ca8ca1f9aadac0859660e1e7067bb
---

## Assertion

The memory reflex is wired only on Claude Code's PostToolUse event, so it does not run for a Bash call whose command exits non-zero; it sees a failure only when the failing output arrives with exit status 0.

## Scope

metric: which Bash calls reach reflex.sh in a Claude Code session installed by thalamus init
cohort: every Bash call in such a session
condition: covers the wiring as installed, not a hand-edited settings file

## Grounds

- code: src/thalamus/harness/install.py § "HOOK_WIRING" =sha256:52d652c2f2408f58cdbbcd5ce92113cb7741821a7b9b8509c041fd22d8af2ed7
- entry: A0160-claude-code-routes-a-nonzero-bash-exit-to-posttoolusefailure · cites-as-live
- search: corpus=src/thalamus/harness/install.py; query="reflex.sh"; date=2026-09-23

## Warrant

HOOK_WIRING, the table thalamus init writes the Claude Code hook block from, names reflex.sh under PostToolUse with the Bash matcher and under no other event; a search of install.py for the script's name finds that row and the prose that explains its absence from the other harnesses, and no second Claude Code row. A Bash call that exits non-zero reaches PostToolUseFailure instead (A0160), so no row of the table runs reflex.sh for it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
- CONTRIBUTING.md · standing · cites-as-live
- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/hooks/claude-code/reflex.sh · standing · cites-as-live
- src/thalamus/harness/reflex.py · standing · cites-as-live
