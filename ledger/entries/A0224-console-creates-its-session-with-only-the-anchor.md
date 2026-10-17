---
id: A0224-console-creates-its-session-with-only-the-anchor
kind: claim
stated: 2026-10-16T21:13:15-07:00
author: architect
grade: measured
supersedes: A0014-roster-command-spawns-on-demand
verbatim_change: the command that creates the session moved from `thalamus roster` to `thalamus console`, and `--all`, the one path that opened every expert at once, is gone
verbatim_sha: dba4ee4af6397f8845cb083f8aa8c910dbf1369c9bb561b669aabae4839fd388
---

## Assertion

`thalamus console` creates its tmux session with only the `main` anchor window when the session is missing, and experts are spawned on demand.

## Scope

metric: what the console opens when it creates its session, and when each expert window opens
cohort: every window the console's session creation can open
condition: the spawn behavior only

## Grounds

- code: src/thalamus/console/windows.py § "ensure_anchor" =sha256:e4534595d28cf54eb7d2750ffca3dee6ae6fb9d6cd5d1acefd90023fb5661ba7
- code: src/thalamus/cli.py § "_cmd_console" =sha256:f3285b856c0c1f0c41c8c98ae463a434d4f478bd5ef112036ca0a1ed99ba9f58

## Warrant

ensure_anchor is the only path that opens a window as part of creating the session, and it opens `main` alone; _cmd_console calls it exactly when the session is missing. Any expert window therefore comes from a later spawn.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-16T21:58:03-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/cli.py § "_cmd_console" =sha256:f3285b856c0c1f0c41c8c98ae463a434d4f478bd5ef112036ca0a1ed99ba9f58
  artifact: sha256:64c760e0f7b1bc61fec9eba101a408f4ade8864925e235e76ad9c008e01c3ea6
  note: propagated from a moved ground
- 2026-10-16T22:10:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/cli.py § "_cmd_console" =sha256:64c760e0f7b1bc61fec9eba101a408f4ade8864925e235e76ad9c008e01c3ea6
  note: _cmd_console's default project root comes from paths.default_project_dir; session creation is unchanged. #35 makes an installed wheel resolve its own files and run itself (contract/paths.py). The assertion is unaffected.

## References

- docs/console.md · standing · cites-as-live
