#!/bin/bash
# Experiment 005 — conclusion vs problem framing. Design fixed in
# preregistration.md, committed before the first arm ran.
set -uo pipefail

TASK=arm-runner-session-death-classification
PAIRS=${PAIRS:-5}
LOG=${LOG:-$HOME/.thalamus/logs/framing-campaign.log}
mkdir -p "$(dirname "$LOG")"

echo "=== framing campaign: $PAIRS pairs on $TASK — $(date -u +%FT%TZ)" | tee -a "$LOG"

for i in $(seq 1 "$PAIRS"); do
  # Alternate which framing leads, so order cannot alias onto one arm.
  if (( i % 2 == 1 )); then ORDER=("ceiling" "ceiling-problem"); else ORDER=("ceiling-problem" "ceiling"); fi
  for arm in "${ORDER[@]}"; do
    echo "--- pair $i: $arm — $(date -u +%FT%TZ)" | tee -a "$LOG"
    uv run --project /home/ybx/code/thalamus thalamus eval run "$TASK" \
      --arm "$arm" --full-auto --sandbox --isolate-store >>"$LOG" 2>&1
    echo "    exit $? — $(date -u +%FT%TZ)" | tee -a "$LOG"
  done
done

echo "=== campaign complete — $(date -u +%FT%TZ)" | tee -a "$LOG"
