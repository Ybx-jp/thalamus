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
#   Each firing records `harness` (THALAMUS_HARNESS, default claude-code): the
#   Cursor adapter reaches this script through a reshaped UserPromptSubmit
#   payload, so `event` alone cannot tell the two apart, and injection there is
#   delivered a tool call late (docs/07) — a lag the rescue-rate join must be
#   able to separate out rather than average over.
#
# Tiers served by this one script (branch on hook_event_name):
# - UserPromptSubmit (tier 1, always armed): lexical intent classes on the
#   user's prompt — design intent -> ground-in-literature + consult reminder;
#   past-work questions -> recall-before-archaeology reminder.
# - PostToolUse matcher TaskCreate (tier 2, milestone): multi-step work is
#   starting -> once-per-session checklist (threads / expert / recipes).
#   TaskCreate is deliberately NOT required: it is optional harness UI, and
#   conditioning must not depend on an event the agent may legitimately skip.
# - PostToolUse matcher mcp__thalamus__memory_query (tier 2, falsify): an ad-hoc
#   traversal just ran -> the falsify-before-you-commit checklist. This surface
#   and not the recall tools, because memory_query returns raw aggregates that
#   get turned into claims, where recall returns prose already labelled as data.
#   It fires on the FIRST query rather than at write time: the reminder has to
#   shape which queries get run, and nothing observable says "a conclusion is
#   about to be committed". Measured need (lab/029): two consultation answers,
#   both correctly cited, both with the mechanism wrong; each was overturned by
#   one more traversal that could have been run first.
#
# Install (project .claude/settings.json):
#   UserPromptSubmit -> this script; PostToolUse {"matcher": "TaskCreate"} and
#   {"matcher": "mcp__thalamus__memory_query"} -> this script.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"

input=$(cat)

event=$(printf '%s' "$input" | jq -r '.hook_event_name // empty')
session=$(printf '%s' "$input" | jq -r '.session_id // empty')
[ -n "$session" ] || exit 0

log_dir="$HOME/.thalamus/conditioning"
log_file="$log_dir/$(date -u +%Y-%m).jsonl"

# The throttle key is (session, agent, class), not (session, class). Subagents share
# their parent's session_id, so keying on the session alone silently exempts every
# subagent from every class — and a subagent is exactly where `falsify` has to land:
# both consultation experts in lab/029 filed a correctly-cited answer with the
# mechanism wrong. Chained fixed-string greps, so one malformed line cannot disable
# the throttle and spam the class.
agent=$(printf '%s' "$input" | jq -r '.agent_id // ""')

fired_already() {
  [ -f "$log_file" ] || return 1
  grep -F "\"session_id\":\"$session\"" "$log_file" 2>/dev/null \
    | grep -F "\"agent\":\"$agent\"" \
    | grep -qF "\"class\":\"$1\""
}

emit() {  # $1 = class, $2 = message
  mkdir -p "$log_dir"
  jq -cn \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg session_id "$session" \
    --arg scope "$(thalamus_resolve_scope)" \
    --arg event "$event" \
    --arg harness "${THALAMUS_HARNESS:-claude-code}" \
    --arg agent "$agent" \
    --arg class "$1" \
    '{ts:$ts, session_id:$session_id, scope:$scope, event:$event,
      harness:$harness, agent:$agent, class:$class, version:1}' \
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
      emit design "Thalamus conditioning (tier-0 operator hook, fires once/session): this prompt reads as design work. Before designing: (1) does the graph already answer it — ground-in-literature step A0, because a design can be perfectly cited and still already built (lab/025); (2) ground-in-literature proper (binding, CLAUDE.md); (3) consult_request to a roster expert — literature, eval-methodology, homelab (docs/02). If you consult, you are pre-authorized to spawn the subagent that voices the expert and expected to — never answer your own ticket; self-answering measured 8 citations against a voiced 25 and missed the objection that killed the design (lab/025). Effectiveness of this reminder is measured per firing."
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
    case "$tool" in
      TaskCreate)
        if ! fired_already milestone; then
          emit milestone "Thalamus conditioning (tier-0 operator hook, fires once/session): multi-step work is starting. Check now: (1) does an open thread overlap this work? (2) which roster expert covers this domain — consult before designing, not after (docs/02); (3) any gremlin ahead: RECIPES.md before writing new queries."
          exit 0
        fi
        ;;
      mcp__thalamus__memory_query)
        if ! fired_already falsify; then
          emit falsify "Thalamus conditioning (tier-0 operator hook, fires once per agent): you are reasoning from an ad-hoc traversal. Before any number here becomes a claim in a doc, a lab entry, or a consult_answer: (1) name what would make the conclusion WRONG and run that query first — it is almost always one more traversal over data you already have; (2) suspect in order — your traversal, then the instrument (what \`used\` actually means; a node never returned has no RETURNS edge, so harm from not-retrieving is invisible here), then your model of the code that consumes the data, and only then the system; (3) a property's absence is not unreachability — establish the *unit* the code ranks before reasoning about what a change can reach. Measured (lab/029): \"claims carry no project property\" was true and the 13% ceiling filed from it was wrong by 6x, because the ranking unit is the parent session. Citation validation proves cited vertices resolve, never that the reasoning is sound. Full checklist: the recall-strategy skill."
          exit 0
        fi
        ;;
    esac
    ;;
esac

exit 0
