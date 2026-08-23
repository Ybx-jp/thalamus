#!/bin/bash
# Thalamus conditioning hook — tilt the agent toward the memory system (Claude Code).
#
# The failure this automates away is measured, not hypothetical: a session
# answered a past-work question with an hour of transcript archaeology when the
# graph held the answer one recall away, and design work proceeded until the
# operator manually said "consult the expert".
# Conditioning is context injection at harness events — the same channel
# Reflexion shows changes later behavior without weight updates (arXiv
# 2303.11366).
#
# Design constraints, grounded:
# - CONDITIONAL, never every-prompt. Selective reminder injection beats always-on
#   (arXiv 2607.08716, the direct agent-side ablation; margins are small and no
#   token comparison is reported, so the cost half of this argument is uncited).
#   Locally the ignored share of injected retrieval tokens is real at roughly a
#   third, and every injected token rides every later call.
# - THROTTLED: each trigger class fires at most once per session.
# - MEASURED: every firing is one JSONL event in ~/.thalamus/conditioning/.
#   Effectiveness is the per-firing behavioral join (`thalamus eval
#   conditioning`): did a thalamus call follow the injection? Fire counts are
#   activity, not effectiveness.
#   Each firing records `harness` (THALAMUS_HARNESS, default claude-code): the
#   Cursor adapter reaches this script through a reshaped UserPromptSubmit
#   payload, so `event` alone cannot tell the two apart, and injection there is
#   delivered a tool call late — a lag the rescue-rate join must be
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
#   about to be committed". Measured need: two consultation answers,
#   both correctly cited, both with the mechanism wrong; each was overturned by
#   one more traversal that could have been run first.
# - PostToolUse matcher Agent (tier 2, selfticket): a pinned session spawned a
#   plain subagent for judgement work inside its own domain -> name the
#   self-ticket, which buys the same fresh context plus a brief, a cited close
#   and an exchange record. Fires after the spawn because there is no earlier
#   observable: the class shapes the next pass and the decision this one feeds.
#   The filter is three conjunctions deep because a looser one is wallpaper —
#   measured over 135 real non-thalamus spawns, matching design vocabulary
#   anywhere in the *prompt* fires on 46 (surveys, ingestion passes, issue
#   filing); matching the caller-written `description` and excluding
#   reconnaissance verbs fires on 3.
#
# Install (project .claude/settings.json):
#   UserPromptSubmit -> this script; PostToolUse {"matcher": "TaskCreate"},
#   {"matcher": "Agent"} and {"matcher": "mcp__thalamus__memory_query"} -> this
#   script.

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

input=$(cat)

event=$(printf '%s' "$input" | jq -r '.hook_event_name // empty')
session=$(printf '%s' "$input" | jq -r '.session_id // empty')
[ -n "$session" ] || exit 0

log_dir="$HOME/.thalamus/conditioning"
log_file="$log_dir/$(date -u +%Y-%m).jsonl"

# The pin, resolved once: it is both a logged field and — for the design class — part
# of what gets injected. A reminder that tells every session to consult the same three
# experts is wrong twice over on an expert session: it names a subset of the roster,
# and it puts the reader's own scope in a list whose sentence is "where the design
# crosses out of your domain", which its own scope by definition does not. The
# self-ticket is a different move and is named separately in the pinned branch.
scope="$(thalamus_scope_from_payload "$input")"

# The throttle key is (session, agent, class), not (session, class). Subagents share
# their parent's session_id, so keying on the session alone silently exempts every
# subagent from every class — and a subagent is exactly where `falsify` has to land:
# both consultation experts in the case that established this filed a correctly-cited
# answer with the mechanism wrong. Chained fixed-string greps, so one malformed line
# cannot disable the throttle and spam the class.
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
    --arg scope "$scope" \
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
      others="$(thalamus_roster "$scope")"
      if [ "$scope" = "main" ]; then
        routing="consult_request to whichever roster expert owns this domain — $others"
      else
        routing="you are pinned to \`$scope\`, so design inside that domain is yours to do — and when it is big enough that you would otherwise spawn a general-purpose subagent to second-pass it, the move is \`consult_request(expert=\"$scope\")\`, a self-ticket: same fresh context, plus a brief assembled against the question, a close the server refuses unless reads happened under the ticket, and an exchange record. consult_request where the design crosses out of \`$scope\` — $others"
      fi
      emit design "Thalamus conditioning (tier-0 operator hook, fires once/session): this prompt reads as design work. Before designing: (1) does the graph already answer it — ground-in-literature step A0, because a design can be perfectly cited and still already built; (2) ground-in-literature proper (binding, CLAUDE.md); (3) $routing. If you consult, you are pre-authorized to spawn the subagent that voices the expert and expected to — never answer the ticket inline, a self-ticket least of all, where the subagent is the whole of what it buys; self-answering measured 8 citations against a voiced 25 and missed the objection that killed the design. Effectiveness of this reminder is measured per firing."
      exit 0
    fi

    if printf '%s' "$prompt" | grep -qiE \
      "\b(why did|what happened|(last|previous|prior|earlier) session|did (we|it|that) (already|ever|actually)|history of|how did .* (end|go|resolve))\b" \
      && ! fired_already retrospect; then
      emit retrospect "Thalamus conditioning (tier-0 operator hook, fires once/session): this prompt asks about past work. memory_recall FIRST (recall-strategy L1) — the graph may already hold the answer; transcript/archive archaeology is the expensive second resort (measured: the orphan-cleanup story was one recall away while an hour was spent grepping transcripts)."
      exit 0
    fi
    ;;

  PostToolUse)
    tool=$(printf '%s' "$input" | jq -r '.tool_name // empty')
    case "$tool" in
      TaskCreate)
        if ! fired_already milestone; then
          emit milestone "Thalamus conditioning (tier-0 operator hook, fires once/session): multi-step work is starting. Check now: (1) does an open thread overlap this work? (2) which roster expert covers this domain — consult before designing, not after; (3) any gremlin ahead: RECIPES.md before writing new queries."
          exit 0
        fi
        ;;
      Agent)
        # Every conjunct removes a population that should not be nudged, and the
        # order is cheapest-first.
        #
        # `main` cannot self-consult at all: there is no `main.yaml`, so
        # `consult_request(expert="main")` is refused at the mint. A `thalamus-*`
        # spawn is the consultation protocol already running — voicing a ticket is
        # the behavior this class exists to produce, so nudging it would be telling
        # a session to do what it is doing.
        #
        # The `description` is the surface, not the prompt: it is the three to five
        # words the caller wrote to name the task, where the prompt is a page of
        # context in which "design" and "review" appear incidentally. Reconnaissance
        # is excluded by its opening verb — a survey is not the class, and the
        # standing operator authorization blesses disposable-context sweeps.
        spawned=$(printf '%s' "$input" | jq -r '.tool_input.subagent_type // ""')
        desc=$(printf '%s' "$input" | jq -r '.tool_input.description // ""')
        if [ "$scope" != "main" ] \
          && [ "${spawned#thalamus-}" = "$spawned" ] \
          && printf '%s' "$desc" | grep -qiE "\b(design|architect|propose|proposal|critique|review|assess|evaluate|spec|plan)\b" \
          && ! printf '%s' "$desc" | grep -qiE "^[[:space:]]*(survey|map|trace|find|search|extract|check|read|list|probe|mine|locate|grep|inventory)\b" \
          && ! fired_already selfticket; then
          emit selfticket "Thalamus conditioning (tier-0 operator hook, fires once/session): you are pinned to \`$scope\` and spawned a plain subagent for judgement work inside your own domain (\"$desc\"). The instrument for that is \`consult_request(expert=\"$scope\")\` — a self-ticket, which is allowed and buys what the spawn does not: a brief assembled against the question, a close the server refuses unless reads happened under the ticket, and an exchange record a later session and the eval loop can find. It grants no reach you do not already have and corroborates nothing — one memory agreeing with itself is not a second source — so mint it for the independent pass, not for confirmation, and voice it with a subagent like any other ticket. Surveys, searches and mechanical work are not this class; keep spawning those. Procedure: the consult-an-expert skill."
          exit 0
        fi
        ;;
      mcp__thalamus__memory_query)
        if ! fired_already falsify; then
          emit falsify "Thalamus conditioning (tier-0 operator hook, fires once per agent): you are reasoning from an ad-hoc traversal. Before any number here becomes a claim in a doc, a written finding, or a consult_answer: (1) name what would make the conclusion WRONG and run that query first — it is almost always one more traversal over data you already have; (2) suspect in order — your traversal, then the instrument (what \`used\` actually means; a node never returned has no RETURNS edge, so harm from not-retrieving is invisible here), then your model of the code that consumes the data, and only then the system; (3) a property's absence is not unreachability — establish the *unit* the code ranks before reasoning about what a change can reach. Measured: \"claims carry no project property\" was true and the 13% ceiling filed from it was wrong by 6x, because the ranking unit is the parent session. Citation validation proves cited vertices resolve, never that the reasoning is sound. Full checklist: the recall-strategy skill."
          exit 0
        fi
        ;;
    esac
    ;;
esac

exit 0
