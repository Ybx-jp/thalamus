---
id: A0020-codex-profile-and-hooks-are-separate-carriers
kind: claim
stated: 2026-09-13T20:18:06-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 386cba3bee6b9cd68ab36a2841910dbe85b63297024aa199f5ba2697a1218f5e
---

## Assertion

codex's `--profile` selects the charter but tells its hooks nothing; the scope still reaches the hooks separately, through the launched argv's `env` prefix.

## Scope

metric: which carrier delivers the scope to the hooks versus to the charter
cohort: every codex session launched pinned
condition: the argv construction only

## Grounds

- code: src/thalamus/harness/pin.py § "_session_argv" =sha256:c87c3b5f0b3c148b6e6cc00a7fdb4a466eafa5358aec8cc106261e5133680d4b

## Warrant

_session_argv is what builds the launched argv, including the env prefix that carries the scope to the hooks independently of the --profile flag, which is what keeps the two carriers separate.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-16T17:35:24-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/pin.py § "_session_argv" =sha256:c87c3b5f0b3c148b6e6cc00a7fdb4a466eafa5358aec8cc106261e5133680d4b
  artifact: absent
  note: propagated from a withdrawn ground
- 2026-10-16T17:45:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/harness/pin.py § "session_argv" =sha256:e30774a147632902dce927182fcf1a36c16a098e32d0afd0277cb5aa0d6ecd64
  note: `_session_argv` is now `session_argv` and no longer appends room flags (those are console/rooms.py's `launch_flags`); the codex profile write and `launch_argv`'s env prefix are unchanged. Moved by #342, which takes tmux and room handling out of core into console/; the assertion is unaffected.

## References

- docs/concepts.md · standing · cites-as-live
- docs/design/launch-templates.md · standing · cites-as-live
