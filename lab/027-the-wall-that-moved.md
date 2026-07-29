# 027 — Cursor re-verified: the contract held, one wall moved, the installer was the real gap

**Date:** 2026-07-29 · **Component:** harness install + hooks (Cursor suite) · **Status:** installer built, injection tiers ported, still no live-Cursor validation

## What broke

Nothing at runtime — this entry is the ten-month re-check of lab/010's port
against Cursor's current contract (`cursor.com/docs/hooks.md`, read
2026-07-29), prompted by the question of whether Thalamus is usable on a
Cursor-only work machine.

The port itself was fine. What was not usable was **reaching the port at all**:
`thalamus init` wired Claude Code only, and the sole Cursor wiring was the
checkout's committed `.cursor/hooks.json` with *relative* commands
(`./src/thalamus/harness/hooks/cursor/…`). Cursor runs project hooks from the
project root, so those commands resolved only for a session whose workspace root
*was* this checkout. Open any other repo — which is the entire point of a work
machine — and every hook silently no-ops. This is `install.py`'s own founding
fault (latent configuration error, Xu et al. OSDI 2016) left standing on the
second harness.

## What the re-check found: the contract held

All six ported events still exist with the field names the adapters read
(`sessionStart`, `sessionEnd`, `beforeSubmitPrompt`, `beforeShellExecution`,
`afterShellExecution`, `afterMCPExecution`); `hooks.json` is still `version: 1`;
the cloud-agent exclusions still match lab/010 exactly. Nine months of drift, no
breakage. The synthetic conformance suite was checking the right shapes.

## Wall 1 moved: injection has a carrier now

lab/010 recorded "no per-prompt context injection" as a wall, with a noted-but-
unbuilt workaround. `beforeSubmitPrompt` still cannot inject — that half stands.
But the surface now names exactly two events that can (`sessionStart`, already
used for priming, and `postToolUse`), and `postToolUse` is *generic*: it fires
for every tool type.

So the tiers cross by **splitting compute from delivery**. `beforeSubmitPrompt`
sees the prompt and writes to a per-session spool (`~/.thalamus/spool/`);
the next `postToolUse` drains it into `additional_context`. Both prompt-side
tiers now reach Cursor:

- **timestamp** — the spooled marker carries *no* rendered time. The clock is
  generated at drain, because a timestamp computed on the prompt and delivered a
  tool call later is precisely the drift the tier exists to prevent.
- **conditioning** — the adapter runs the real Claude Code classifier against a
  reshaped payload, so the lexical classes, the once-per-session throttle and
  the `~/.thalamus/conditioning/` firing log are one implementation, not two.

Cost, recorded rather than hidden: injection lands **one tool call late**, and a
turn that calls no tool carries its injection to the next turn. Session end
discards an undelivered spool rather than leaking it into a later session.

Because Cursor firings now reach the same log as Claude Code ones through a
payload that *claims* to be `UserPromptSubmit`, the log gained a `harness`
field and `thalamus eval conditioning` splits by it. Without that the two
harnesses' rescue rates would silently average — re-confounding the exact
comparison this port unblocks.

**No carrier still:** the `PostToolUse:TaskCreate` milestone class. TaskCreate is
Claude Code task-list UI; Cursor's `Task` tool type is subagent spawning, a
different event that would fire on the wrong thing. The two lexical classes are
the load-bearing ones and both cross.

## Wall 2 stands: still no distillation

`thalamus extract` still parses Claude Code JSONL only. A Cursor session
retrieves, traces, gets primed, guarded and conditioned — and leaves no episodic
memory. `session-end.sh` still logs `distilled: false` with the transcript path
for a future adapter to backfill. This remains the single biggest functional gap
of running Thalamus under Cursor, and it is now the *only* structural one.

## The deliberate non-change: taps stay on the specialized events

`postToolUse` being generic means it could replace `afterMCPExecution` and
`afterShellExecution` — and would additionally work in Cursor **cloud agents**,
where the specialized MCP events do not load at all. Tempting, and not taken:
the docs do not state whether a tool call fires both the generic and the
specialized hook. If it does, tapping both double-counts every retrieval in
`eval sync`, which corrupts layer 1 rather than merely adding noise. That is a
question a live Cursor answers in one session; until then the injection hook
rides `postToolUse` and writes no traces, and a test pins that separation.

## Also found

- **Precedence is documented here and not on Claude Code:** Enterprise > Team >
  Project > User, with user scope *last*. The install therefore strips the
  checkout's project-scope block for a sharper reason than the Claude Code leg
  had — a surviving project block does not merely risk undocumented merge
  behaviour, it is documented to outrank what we just wrote. Stripping it also
  retires the consent problem lab/010 flagged: a committed `.cursor/hooks.json`
  runs for anyone who opens this repo in Cursor.
- **User-scope hooks run from `~/.cursor/`, project hooks from the project
  root** — the same command string cannot be correct in both scopes, which is
  the direct argument for absolute paths that `build_cursor_hook_block()` makes.
- New events worth a later look, both bearing on standing open questions:
  `preCompact` and `stop` (docs/07's distillation-trigger question), and
  `subagentStart`/`subagentStop` — the latter carrying `agent_transcript_path`,
  which is the consultation protocol's substrate.

## What the grounding pass caught (retroactive, and it found a bug)

The literature consultation ran *after* the code shipped, which is the wrong
order and caught something because of it: **late binding was applied to half the
payload**. The clock was correctly deferred (bare marker, rendered at drain) but
the conditioning text was not. It is time-sensitive in a different currency — it
was classified against one specific prompt — and nothing pruned it, so a turn
that fired conditioning and then called no tool would deliver a design reminder
against whatever the user asked next. The spool header asserted "at most one
turn's worth"; the append-only writer did not enforce it. Fixed by pruning
conditioning entries at each new prompt, with a test that fires the class, skips
the tool call, and asserts the stale reminder is gone while the fresh clock
survives. Named in the literature: a message past its freshness lifetime (RFC
9111 §4.2), and agents measurably act on superseded state even when the fresh
state is retrievable (STALE, arXiv 2605.06527, best frontier accuracy 55.2%).

Two framing corrections, both applied to docs/07:

- **The `harness` split prevents pooling; it does not license a comparison.**
  The two arms differ *configurally* — the Cursor arm is missing indicators
  entirely (no milestone class) — and configural invariance is the precondition
  for cross-group comparison, not something a scaling factor repairs (Vandenberg
  & Lance 2000; Harness-Bench arXiv 2605.27922 is the agent-specific version).
  The Cursor arm is a within-harness longitudinal instrument. The earlier claim
  that the split "unblocks the cross-harness comparison" was too strong.
- **The real risk is the delivery slot, not the one-call delay.** Cursor's
  conditioning arrives in the tool-result slot, and the only positional
  measurement for that slot is adversarial: efficacy 60% at depth 1 → 0% at
  depth 4 (arXiv 2605.30686), because models are trained to discount
  instructions in tool output. Whether *benign* guidance there gets the same
  uptake as the same text in the user turn is unmeasured anywhere. If it does
  not, the `harness` split reports a difference it cannot attribute.

Counterweight worth holding: intervention timing has no stable ground truth —
three trained annotators agreed on where to intervene barely above chance
(α = +0.047), and the recommendation is to build for recoverability rather than
precision timing (arXiv 2606.04296). That puts the one-tool-call offset inside
the noise floor of the construct, and makes the slot question, not the latency
question, the one worth spending on.

**Next measurement, and it is cheap:** run the same conditioning class through
Claude Code's `UserPromptSubmit` and Cursor's `postToolUse` `additional_context`
and compare follow-rate. `thalamus eval conditioning` already joins each firing
to the trace tap and already stamps `harness`, so the instrument exists. It is
an in-house answer to a question the 2026 scan says nobody has published.

## Wall or workaround

**Workaround** for the install gap and for wall 1. **Wall** still for
distillation. And the standing caveat from lab/010 is unchanged and now the
main risk: everything here is verified against Cursor's *documentation* and a
synthetic conformance suite. No Thalamus code has yet run inside a live Cursor.
The first real session should confirm payload shapes, the generic-vs-specialized
double-fire question, and that `additional_context` from `postToolUse` actually
reaches the model.
