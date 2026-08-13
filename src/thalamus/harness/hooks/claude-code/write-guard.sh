#!/bin/bash
# Thalamus PreToolUse hook — a session does not write its own memory (Claude Code).
#
# The 2026-08-03 decision (docs/index.md) removed the `memorize` MCP tool and reduced
# the runtime surface to reads plus the consultation exchange. Episodic writes happen
# *after* a session ends, by `thalamus extract` over the retained transcript. The two
# hand-authored commands survive as operator actions **from outside a session** —
# `thalamus write` for a hand-written subgraph, and `thalamus extract --force --write`
# for checkpointing an open one.
#
# That distinction lives in prose and nothing enforced it, which is exactly how it was
# broken: a session read "`thalamus write` keeps the hand-authored path" as a general
# permission and wrote itself a Thread mid-flight. The decision's own rationale names
# the cost — distillation writes the session regardless, so a live write is a second
# pass over the same session, and "threads get fresh ids and both stay open in
# `memory_open_threads`, the surface a new session reads first." The 2026-08-11 close
# design rejected one of its three alternatives for the same reason: "a synthetic
# Session corrupts the entrypoint the 2026-08-03 decision protects."
#
# So the boundary is structural now. Inside a session these commands are blocked; from
# a plain terminal no hook fires and the operator keeps both, unchanged.
#
# WHAT IS DELIBERATELY NOT BLOCKED, because it is not this decision's subject:
#
#   - `thalamus ingest` — third-party documents into an expert's knowledge, gated by
#     its own allowlist and dry-run-by-default (docs/06). It is not self-memory.
#   - Graph maintenance that operates over the whole graph rather than distilling this
#     session: `repair-projects`, `derive-artifact-paths`, `backfill-chunks`,
#     `snapshot`. These mutate, and an operator may well want them gated one day, but
#     gating them here would attach an unrelated decision to this one.
#   - `thalamus thread approve` — the close path is explicitly an in-session verb with
#     operator approval (2026-08-11), and blocking it would invert that decision.
#
# NAMED MISSES, in lab/008's standing trade where a miss is the cheaper error:
#
#   - Ad-hoc gremlin mutation. `g.V(...).drop()` in an inline python one-liner writes
#     the graph without naming `thalamus` at all. The gremlin-python skill's Rule 4
#     forbids it by convention and `substrate/query.py` guards only `memory_query`.
#     That hole is real and was used — the thread this hook exists to prevent was
#     removed through it.
#   - A script file. The command is `python repair.py`; the write is in the file, and
#     no matcher on the command line can see it.
#   - Renaming or aliasing the entrypoint.
#
# Install (user or project settings.json):
#   {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
#     "command": ".../hooks/claude-code/write-guard.sh"}]}]}}

set -euo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/resolve-scope.sh"
thalamus_sandbox_guard

input=$(cat)

# Fail CLOSED on a payload this cannot parse, which is the opposite of the posture the
# other guards take and is deliberate. `guards-fail-closed-on-unparseable-input` is an
# open qe finding against them: they permit when jq is missing or the JSON is
# malformed, so the guard is absent precisely when something unusual is happening. The
# other guards can afford it because their failure is a bad edit; this one's failure is
# a graph write that distillation will then duplicate. So when the structured read
# fails, the RAW payload is searched instead — no jq, no schema, still a haystack.
command=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[ -n "$command" ] || command="$input"

# `thalamus write <file>` and `thalamus extract ... --write`. Matched on the
# subcommand rather than on the bare flag: `--write` alone appears on the maintenance
# commands above, which are not this decision's subject.
# Markers carried as prose. A commit message describing this boundary names the
# command it describes, and lab/008 already paid for this exact class on the gremlin
# guard: its amendment tripped on the commit message explaining the amendment. The
# residual — a real write chained after a `git commit` — is accepted knowingly, on the
# standing trade that a false positive teaches route-around and route-around costs
# more than a gap.
case "$command" in
  git\ commit*|git\ tag*|git\ notes*|echo\ *|printf\ *|cat\ *|grep\ *|rg\ *|sed\ *|awk\ *)
    exit 0 ;;
esac

is_self_write=0
case "$command" in
  *thalamus*write*)
    # Narrow to the two real cases. `grep -E` rather than a case glob because the
    # subcommand and its flag can be separated by arbitrary arguments.
    if printf '%s' "$command" | grep -Eq '(^|[^-[:alnum:]])thalamus[[:space:]]+write([[:space:]]|$)'; then
      is_self_write=1
      verb="thalamus write"
    elif printf '%s' "$command" | grep -Eq '(^|[^-[:alnum:]])thalamus[[:space:]]+extract([[:space:]].*)?--write'; then
      is_self_write=1
      verb="thalamus extract --write"
    fi ;;
esac
[ "$is_self_write" = "1" ] || exit 0

log_event block "$verb" 2>/dev/null || true

cat >&2 <<EOF
Blocked: \`${verb}\` writes memory from inside a session, and a session does not
write its own memory (docs/index.md, 2026-08-03).

Episodic writes happen after this session ends, by \`thalamus extract\` over the
retained transcript. Running it now is a *second* pass over the same session: claims
are content-addressed on (kind, normalized description) so a re-phrased one mints a
new node instead of converging, and threads get fresh ids — both then sit open in
\`memory_open_threads\`, the surface the next session reads first. The cost lands on
the entrypoint, as dedup work nobody asked for.

What to do instead:

  - A durable record for a future session — file it in the tracker, where the
    operator can see and order it. See the \`track-open-work\` skill.
  - Something this session learned — say it plainly in your final message. The
    SessionEnd distillation reads the transcript and writes it properly, once.
  - Closing a thread — that IS an in-session verb: \`thalamus thread propose\`, then
    the operator approves (2026-08-11). Report the title, a 1-2 sentence description,
    and the proposal id, all three.
  - A genuinely hand-authored subgraph — that is an operator action from a plain
    terminal, where no hook fires. Ask for it rather than running it here.

If this boundary is wrong, it is an operator decision and an edit to the decision
log — say so rather than routing around it.
EOF
exit 2
