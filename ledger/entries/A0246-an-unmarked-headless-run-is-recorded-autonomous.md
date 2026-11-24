---
id: A0246-an-unmarked-headless-run-is-recorded-autonomous
kind: claim
stated: 2026-11-23T01:56:21-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 1f64132fdf26e95376725f8a5b194e4f188b4d6abd0f16e97ab8925ae7dfd2bc
---

## Assertion

A Claude Code session's type is resolved at launch and read back at distillation by one rule: a THALAMUS_SESSION_TYPE of attended or autonomous wins, and otherwise a session whose entrypoint starts with sdk, which a headless run reports, is autonomous and any other is attended. A pin-ledger row without a recorded type is read by the same rule from its entrypoint.

## Scope

metric: the session type recorded for a Claude Code session and the type distillation reads back for it
cohort: Claude Code sessions whose session-start hook sources the claude-code resolve-scope.sh, and pin-ledger rows read by thalamus extract
condition: the launch-time resolution and the ledger read; a --session-type flag on extract overrides the ledger and is outside this claim

## Grounds

- code: src/thalamus/harness/hooks/claude-code/resolve-scope.sh § "thalamus_guard_command" =sha256:0b257a1ccf8a93d182e8299fe680c73ffb7f10250d2a66cbc2af41b07a25e926
- code: src/thalamus/harness/pin.py § "ledger_session_type" =sha256:b7ed0f689e0f1f545986ea6d13468fca1d2a193281faea25d2111a8371e35a94

## Warrant

The ground in resolve-scope.sh is the section opened by the file's last top-level assignment, which runs to the end of the file and holds thalamus_resolve_session_type; the code section pattern splits shell files only at assignments. That function prints a declared attended or autonomous value as given, and otherwise autonomous for an entrypoint matching sdk* and attended for anything else, unset included; session-start.sh records its output as the row's session_type. ledger_session_type returns a recorded type as given, and for a row with none applies the same sdk prefix to the row's entrypoint.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-11-23T16:22:20-08:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/hooks/claude-code/resolve-scope.sh § "thalamus_guard_command" =sha256:0b257a1ccf8a93d182e8299fe680c73ffb7f10250d2a66cbc2af41b07a25e926
  artifact: sha256:022702641b55f65f2db447c7c6e13111dd5ba780e29cce00d685ad5a56e55d71
  note: propagated from a moved ground
- 2026-11-23T16:30:00-08:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/hooks/claude-code/resolve-scope.sh § "thalamus_guard_command" =sha256:022702641b55f65f2db447c7c6e13111dd5ba780e29cce00d685ad5a56e55d71
  note: thalamus_resolve_session_type now matches THALAMUS_SESSION_TYPE case-insensitively with whitespace stripped using bash builtins instead of tr, so it still answers on a PATH without coreutils (#403); the rule is the same, declared attended or autonomous wins and otherwise an sdk entrypoint reads autonomous, so the assertion is unaffected

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/harness/hooks/claude-code/resolve-scope.sh · standing · cites-as-live
