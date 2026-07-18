#!/bin/bash
# Thalamus timestamp hook — keep every session (especially long-running pinned
# expert tmux sessions) aware of the actual wall clock.
#
# Why: the harness stamps currentDate once at session start. Pinned roster
# sessions run for days, so their notion of "today" drifts and they hallucinate
# dates in answers, distillations, and doc edits (operator-observed,
# 2026-07-18). This injects one short line of ground truth on every prompt.
#
# Deliberately UNCONDITIONAL and separate from conditioning.sh: conditioning
# firings are measured for rescue rate (`thalamus eval conditioning`), and a
# per-prompt clock line must not pollute that telemetry. Cost is ~a dozen
# tokens per prompt — the drift it prevents corrupts timestamps in the memory
# graph itself, which is worth strictly more.

now=$(date '+%A %Y-%m-%d %H:%M %Z')
jq -cn --arg ctx "Current date and time: ${now}" \
  '{hookSpecificOutput:{hookEventName:"UserPromptSubmit", additionalContext:$ctx}}'
