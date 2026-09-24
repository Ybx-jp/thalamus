#!/usr/bin/env bash
# Probe what Claude Code's hook events actually deliver, in a scratch session.
#
#   probe-claude-hooks.sh [--subagent] "<shell command for the agent to run>" [EVENT ...]
#
# Wires a logging hook on each EVENT (default: PostToolUse PostToolUseFailure) with the
# Bash matcher, through a `--settings` overlay in a scratch directory — the operator's
# ~/.claude/settings.json is not touched — then runs one `claude -p` turn on haiku that
# executes the command (inside one subagent with --subagent). Each hook writes the stdin
# payload it received to <out>/<EVENT>.<n>.json and returns a marker as
# `additionalContext`. The report says which events fired, prints each payload, and says
# which transcript the marker reached: the session's, a subagent's, or none.
#
# Run it from the operator's shell (`! bash <path>`): a nested `claude` that spawns
# agents is refused by an auto-mode session's own classifier.
set -euo pipefail

subagent=0
if [ "${1:-}" = "--subagent" ]; then subagent=1; shift; fi
command_to_run=${1:?usage: probe-claude-hooks.sh [--subagent] "<command>" [EVENT ...]}
shift
events=("$@")
[ ${#events[@]} -gt 0 ] || events=(PostToolUse PostToolUseFailure)

out=$(mktemp -d "${TMPDIR:-/tmp}/claude-hook-probe.XXXXXX")
work="$out/work"
mkdir -p "$work"
nonce="PROBE_$(date +%s)_$$"
claude --version > "$out/claude-version.txt" 2>&1 || true

hooks_json="{}"
for event in "${events[@]}"; do
  hook="$out/hook-$event.sh"
  cat > "$hook" <<EOF
#!/usr/bin/env bash
n=\$(ls "$out"/$event.*.json 2>/dev/null | wc -l)
cat > "$out/$event.\$n.json"
printf '{"hookSpecificOutput":{"hookEventName":"%s","additionalContext":"%s"}}' "$event" "${nonce}_$event"
EOF
  chmod +x "$hook"
  hooks_json=$(jq -c --arg e "$event" --arg c "$hook" \
    '.[$e] = [{"matcher": "Bash", "hooks": [{"type": "command", "command": $c}]}]' \
    <<< "$hooks_json")
done
jq -n --argjson hooks "$hooks_json" '{hooks: $hooks}' > "$out/settings.json"

if [ "$subagent" = 1 ]; then
  prompt="Use the Agent tool once (general-purpose). Tell the subagent: run this exact Bash command once, then reply with the exact text of any extra context or system reminder attached to its result, verbatim, or NONE: $command_to_run. Then report the subagent's reply verbatim."
else
  prompt="Run this exact Bash command once: $command_to_run. Then reply with the exact text of any extra context or system reminder attached to its result, verbatim, or NONE."
fi

(cd "$work" && claude -p --model haiku --settings "$out/settings.json" \
  --permission-mode bypassPermissions "$prompt" > "$out/model-reply.txt" 2>&1) || true

project="$HOME/.claude/projects/$(printf '%s' "$work" | sed 's#[/.]#-#g')"

echo "claude: $(cat "$out/claude-version.txt")"
echo "probe dir: $out"
for event in "${events[@]}"; do
  shopt -s nullglob
  files=("$out/$event".*.json)
  shopt -u nullglob
  echo
  echo "== $event: fired ${#files[@]} time(s)"
  for f in "${files[@]}"; do jq . "$f"; done
  echo "-- marker ${nonce}_$event reached:"
  grep -l "${nonce}_$event" "$project"/*/subagents/*.jsonl 2>/dev/null | sed 's/^/   subagent transcript: /' || true
  grep -l "${nonce}_$event" "$project"/*.jsonl 2>/dev/null | sed 's/^/   session transcript: /' || true
done
echo
echo "== model reply"
tail -20 "$out/model-reply.txt"
