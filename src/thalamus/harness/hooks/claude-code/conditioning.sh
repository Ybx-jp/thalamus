#!/bin/bash
# Thalamus conditioning hook — tilt the agent toward the memory system (Claude Code).
#
# The failure this automates away is measured, not hypothetical: a session
# answered a past-work question with an hour of transcript archaeology when the
# graph held the answer one recall away, and design work proceeded until the
# operator manually said "consult the expert" (lab/008 coda; 2026-07-18).
# Conditioning is context injection at harness events — the same channel
# Reflexion shows changes later behavior without weight updates (arXiv
# 2303.11366).
#
# Design constraints, grounded:
# - CONDITIONAL, never every-prompt. Adaptive beats indiscriminate retrieval
#   (Self-RAG, arXiv 2310.11511); locally, lab/006 measured ~50% of
#   indiscriminately injected tokens ignored — and every injected token rides
#   every later call (docs/04 layer 1b).
# - THROTTLED: each trigger class fires at most once per session.
# - MEASURED: every firing is one JSONL event in ~/.thalamus/conditioning/.
#   Effectiveness is the per-firing behavioral join (`thalamus eval
#   conditioning`): did a thalamus call follow the injection? Fire counts are
#   activity, not effectiveness (lab/008 discipline).
#
# Tiers served by this one script (branch on hook_event_name):
# - UserPromptSubmit (tier 1, always armed): lexical intent classes on the
#   user's prompt — design intent -> ground-in-literature + consult reminder;
#   past-work questions -> recall-before-archaeology reminder.
# - PostToolUse matcher TaskCreate (tier 2, milestone): multi-step work is
#   starting -> once-per-session checklist (threads / expert / recipes).
#   TaskCreate is deliberately NOT required: it is optional harness UI, and
#   conditioning must not depend on an event the agent may legitimately skip.
#
# Install (project .claude/settings.json):
#   UserPromptSubmit -> this script; PostToolUse {"matcher": "TaskCreate"} -> this script.

set -euo pipefail

input=$(cat)

event=$(printf '%s' "$input" | jq -r '.hook_event_name // empty')
session=$(printf '%s' "$input" | jq -r '.session_id // empty')
[ -n "$session" ] || exit 0

log_dir="$HOME/.thalamus/conditioning"
log_file="$log_dir/$(date -u +%Y-%m).jsonl"

fired_already() {
  [ -f "$log_file" ] && grep -q "\"session_id\":\"$session\".*\"class\":\"$1\"" "$log_file"
}

emit() {  # $1 = class, $2 = message
  mkdir -p "$log_dir"
  jq -cn \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg session_id "$session" \
    --arg scope "${THALAMUS_SCOPE:-main}" \
    --arg event "$event" \
    --arg class "$1" \
    '{ts:$ts, session_id:$session_id, scope:$scope, event:$event, class:$class, version:1}' \
    >> "$log_file" || true
  jq -cn --arg e "$event" --arg ctx "$2" \
    '{hookSpecificOutput:{hookEventName:$e, additionalContext:$ctx}}'
}

case "$event" in
  UserPromptSubmit)
    prompt=$(printf '%s' "$input" | jq -r '.prompt // empty')
    [ -n "$prompt" ] || exit 0

    if printf '%s' "$prompt" | grep -qiE \
      "\b(design|architect|propose|new (feature|component|skill|hook|expert|metric|schema)|should we (build|add|write|create)|let'?s (build|add|write|create|implement|enhance))\b" \
      && ! fired_already design; then
      emit design "Thalamus conditioning (tier-0 operator hook, fires once/session): this prompt reads as design work. Before designing: ground-in-literature (binding, CLAUDE.md), and consider consult_request to a roster expert — literature, eval-methodology, homelab (docs/02). Effectiveness of this reminder is measured per firing."
      exit 0
    fi

    if printf '%s' "$prompt" | grep -qiE \
      "\b(why did|what happened|(last|previous|prior|earlier) session|did (we|it|that) (already|ever|actually)|history of|how did .* (end|go|resolve))\b" \
      && ! fired_already retrospect; then
      emit retrospect "Thalamus conditioning (tier-0 operator hook, fires once/session): this prompt asks about past work. memory_recall FIRST (recall-strategy L1) — the graph may already hold the answer; transcript/archive archaeology is the expensive second resort (measured: the orphan-cleanup story was one recall away while an hour was spent grepping transcripts, lab/008)."
      exit 0
    fi
    ;;

  PostToolUse)
    tool=$(printf '%s' "$input" | jq -r '.tool_name // empty')
    [ "$tool" = "TaskCreate" ] || exit 0
    if ! fired_already milestone; then
      emit milestone "Thalamus conditioning (tier-0 operator hook, fires once/session): multi-step work is starting. Check now: (1) does an open thread overlap this work? (2) which roster expert covers this domain — consult before designing, not after (docs/02); (3) any gremlin ahead: RECIPES.md before writing new queries."
      exit 0
    fi
    ;;
esac

exit 0
