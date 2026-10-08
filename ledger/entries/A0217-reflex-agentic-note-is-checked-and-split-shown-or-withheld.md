---
id: A0217-reflex-agentic-note-is-checked-and-split-shown-or-withheld
kind: claim
stated: 2026-10-08T00:17:50-07:00
author: main
grade: measured
supersedes: A0190-reflex-agentic-note-is-checked-and-split-shown-or-withheld
verbatim_change: the note is written by the channel's model, Haiku through claude -p by default or the local model, where it had always been the local model, and the cohort names both channels
verbatim_sha: 29a7fc333d0cb2112bd3d20caea12ba10bc4bce3c593f197f0b4652f97a48c26
---

## Assertion

The agentic plan's note, written by the channel's model on its stop call, reaches the agent only when it is at most 500 characters, every sentence cites at least one handle, every cited handle is one the digest serves, and nothing in it reads as an instruction to the reader; a note that fails is not delivered and the job's records go out without it, with the failed check recorded by name. A note that passes is assigned, in balanced blocks of two within the session in an order drawn from the session id and the block's index, to being shown in the digest or withheld from it, and in either arm the note's text, check and arm are carried in the job's trace line.

## Scope

metric: whether an agentic job's note is delivered, and what records it
cohort: agentic reflex jobs the worker leaves ready, delivered by the carrier, on either channel
condition: whether each sentence is entailed by the records it cites is not checked; blocks count the valid notes recorded under ~/.thalamus/reflex/note_arms for the session

## Grounds

- code: src/thalamus/harness/reflex_note.py § "check_note" =sha256:b3733f15092a1d97ef0fa2a194cadc6fd3f1cb9aeffc4182d77b0e0d37841bf1
- code: src/thalamus/harness/reflex_note.py § "assign_note_arm" =sha256:192af57a750d9bdf1e1f97fa9a9867327c49bceb1688406699642df893949e30
- code: src/thalamus/harness/reflex_note.py § "NOTE_CHAR_CAP" =sha256:8f9c8fe79c50bc90ef998c6cdf20a554820889cbeb282a8e302fad361cfb4d06
- code: src/thalamus/harness/reflex_worker.py § "run_job" =sha256:1f096a228a3e13b5ae7611ef68f722bf9bb14401ae6a3b3c657b55a0dbf132a8

## Warrant

check_note returns absent for an empty note, too_long past NOTE_CHAR_CAP, uncited_sentence when a sentence split on terminal punctuation has no handle, unknown_handle when a cited handle is not in the served set, imperative when reflex.imperative_voice matches, and valid otherwise. run_job calls it with the handles the digest serves, whichever channel's model wrote the note, calls assign_note_arm only on a valid note, renders the note into the digest only on the shown arm, and writes the note, its status, its arm and the handles it cited into the ready result that deliver copies into the trace's tool_input. assign_note_arm counts the session's recorded arms, splits the count into a block and a slot, and returns the slot of NOTE_ARMS shuffled by a generator seeded with the session id and the block, recording the assignment before it returns.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/cli.md · standing · cites-as-live
