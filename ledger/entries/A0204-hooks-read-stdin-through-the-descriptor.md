---
id: A0204-hooks-read-stdin-through-the-descriptor
kind: claim
stated: 2026-09-25T01:23:53-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: d2431c662f78c52e2456c020b5ee432b579fa9ddd14fa16f5e44471f75ec8ad0
---

## Assertion

Every hook script this repository ships under src/thalamus/harness/hooks/, and every hook it runs for its own development under .claude/hooks/, reads its input from the inherited stdin descriptor and never reopens it by path, and the suite fails on a hook line that names /dev/stdin, /dev/fd/0 or /proc/self/fd/0.

## Scope

metric: how a hook script in this repository reads the input its harness hands it
cohort: the shell scripts directly under src/thalamus/harness/hooks/<harness>/ and .claude/hooks/
condition: a comment line naming the paths is not a read and is not counted; does not cover a hook written by another package into .claude/hooks/ under a name the sweep's glob does not reach

## Grounds

- code: tests/test_hook_scripts.py § "test_no_hook_reopens_its_stdin_by_path" =sha256:aa50412aaebbc1586ed975b550ac1409fd9e3fccd6540103974443d6183a5903
- code: tests/test_hook_scripts.py § "test_a_socket_stdin_refuses_the_path_reopen_and_serves_cat" =sha256:b3fca52017a43f4ffd4bb16c372158c368d398d08e11fc035bedac0008762192
- entry: A0203-claude-code-hook-stdin-is-a-socket · cites-as-live
- search: corpus=src/thalamus/harness/hooks,.claude/hooks; query="/dev/stdin"; date=2026-09-25

## Warrant

The sweep reads every script under both directories and fails on any non-comment line naming one of the three paths, and the control beside it shows the shape it bans reads the input over a pipe and fails with ENXIO over a socket while `cat` reads it over both. Claude Code's hook stdin is a socket (A0203), so a hook passing the sweep reads its input there, and one reopening the path would fail on every call without failing any test that drives it over a pipe.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-18T16:14:12-07:00 · contested · grade: measured · author: propagation
  evidence: code: tests/test_hook_scripts.py § "test_no_hook_reopens_its_stdin_by_path" =sha256:aa50412aaebbc1586ed975b550ac1409fd9e3fccd6540103974443d6183a5903
  artifact: sha256:92932bbb8f66b444fdfb6ae54171c173d917e7b37f9901d68f1a8f906cbaf115
  note: propagated from a moved ground
- 2026-10-18T16:25:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: tests/test_hook_scripts.py § "test_no_hook_reopens_its_stdin_by_path" =sha256:92932bbb8f66b444fdfb6ae54171c173d917e7b37f9901d68f1a8f906cbaf115
  note: the sweep reads every plugin's hooks under packages/*/src/*/hooks/ beside core's, so the two reflex scripts that moved into thalamus-reflex stay under the same test; the assertion is unaffected

## References

- packages/thalamus-reflex/src/thalamus_reflex/hooks/claude-code/reflex-pointer-tap.sh · standing · cites-as-live
