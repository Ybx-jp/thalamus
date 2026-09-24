#!/usr/bin/env bash
# PostToolUse (Edit|Write|MultiEdit) — flag an edit that states how a harness behaves.
#
# A sentence about what Claude Code, codex or Cursor does is a claim about code this
# repository does not control: nothing here keeps it true and nothing fails when it
# stops being true. When an edit to a repo surface adds a line naming a harness beside a
# behaviour word (fires, payload, delivers, event, exit status, never, only, ...) and the
# added text cites no ledger entry, this returns a reminder to measure the behaviour and
# pin it, pointing at the probe-harness-behaviour skill. It reminds; it never blocks.
#
# Once per file per session, so a long edit series on one document says it once.
# Project scope only: it arms in this checkout, for work on this repository, and is not
# installed for users.
set -euo pipefail

input=$(</dev/stdin)
command -v jq >/dev/null 2>&1 || exit 0

path=$(jq -r '.tool_input.file_path // empty' <<< "$input")
[ -n "$path" ] || exit 0
root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
rel="${path#"$root"/}"
case "$rel" in
  src/thalamus/*|docs/*|config/*|.claude/skills/*|CLAUDE.md|CONTRIBUTING.md|README.md) ;;
  *) exit 0 ;;
esac

added=$(jq -r '[.tool_input.new_string // empty, .tool_input.content // empty,
                (.tool_input.edits // [] | .[].new_string // empty)] | join("\n")' <<< "$input")
[ -n "$added" ] || exit 0
if grep -qE 'A[0-9]{4}(-[a-z0-9-]+)?, cites-' <<< "$added"; then exit 0; fi

vendor='(Claude Code|\bcodex\b|\bCursor\b|the harness)'
behaviour='\b(fires?|fired|firing|payloads?|deliver(s|ed)?|reach(es)?|routes?|carr(y|ies)|exposes?|events?|exit (code|status)|never|always|only|cannot|can.t|not (in|available|observable|exposed))\b'
lines=$(grep -E "$vendor" <<< "$added" | grep -iE "$behaviour" | head -3) || true
[ -n "$lines" ] || exit 0

session=$(jq -r '.session_id // "unknown"' <<< "$input")
seen="${TMPDIR:-/tmp}/thalamus-harness-fact-reminder/$session"
mkdir -p "$seen"
key=$(printf '%s' "$rel" | cksum | cut -d' ' -f1)
[ -e "$seen/$key" ] && exit 0
: > "$seen/$key"

message="This edit to $rel states how a harness behaves, and cites no ledger entry:
$(sed 's/^[[:space:]]*/  > /' <<< "$lines")
A harness fact is a claim about code this repository does not control (CLAUDE.md, \"Claims about a harness\"). If the sentence is load-bearing, measure it on the installed version and pin it: the probe-harness-behaviour skill has the procedure and a hook-event probe. If it only restates a cited fact, cite the entry that holds it."

jq -cn --arg ctx "$message" \
  '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}'
