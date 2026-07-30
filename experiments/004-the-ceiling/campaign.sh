#!/bin/bash
# Experiment 004 — the ceiling campaign. Design fixed in preregistration.md,
# committed before the first arm ran.
#
# 12 arms, alternating so arm order cannot confound the comparison, sandboxed with
# the store isolated. Appends to ~/.thalamus/counterfactuals/runs.jsonl; every arm
# is a separate `eval run` so a death mid-campaign costs one arm, not the batch.
set -uo pipefail

TASK=arm-runner-session-death-classification
PAIRS=${PAIRS:-6}
LOG=${LOG:-$HOME/.thalamus/logs/ceiling-campaign.log}
mkdir -p "$(dirname "$LOG")"

echo "=== ceiling campaign: $PAIRS pairs on $TASK — $(date -u +%FT%TZ)" | tee -a "$LOG"

for i in $(seq 1 "$PAIRS"); do
  # Alternate which side leads, so any order effect is balanced rather than
  # aliased onto one arm.
  if (( i % 2 == 1 )); then ORDER=("ceiling" "memory-off"); else ORDER=("memory-off" "ceiling"); fi
  for arm in "${ORDER[@]}"; do
    echo "--- pair $i: $arm — $(date -u +%FT%TZ)" | tee -a "$LOG"
    uv run --project /home/ybx/code/thalamus thalamus eval run "$TASK" \
      --arm "$arm" --full-auto --sandbox --isolate-store >>"$LOG" 2>&1
    echo "    exit $? — $(date -u +%FT%TZ)" | tee -a "$LOG"
  done
done

echo "=== campaign complete — $(date -u +%FT%TZ)" | tee -a "$LOG"
