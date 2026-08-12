# 061 — The guard nobody wired was already running

**Date:** 2026-08-12 · **Harness:** Cursor CLI `2026.08.11-e8db854`, seven probe
sessions on one box · **Verdict:** the thread's premise reversed, three shipped
defects, one record re-subjected

The open thread said role-boundary enforcement was Claude-Code-only and asked whether
to close the gap by porting `role-guard.sh` to Cursor. Six probes went into designing
that port. The seventh showed there was nothing to port: **Cursor has been running our
guard for a release, through a path in neither wiring table.**

## What the vendor does

`~/.local/share/cursor-agent/versions/2026.08.11-e8db854/index.js` carries an event
translation table verbatim:

```js
{ PreToolUse: preToolUse, PermissionRequest: null, PostToolUse: postToolUse,
  UserPromptSubmit: beforeSubmitPrompt, Stop: stop, SubagentStop: subagentStop,
  SessionStart: sessionStart, SessionEnd: sessionEnd, PreCompact: preCompact }
```

beside a tool-name table (`Bash:"Shell"`, `Edit:"Write"`, `Glob:null`, …), a parser for
Claude Code's `|`-separated matcher syntax with a branch for `mcp`-prefixed entries,
and a shim mapping a `permissionDecision` response onto Cursor's own `permission`
field. It reads `join(e, ".claude", "settings.json")`.

**The controlled run.** A directory containing no `.cursor/hooks.json` at all, no
project settings, nothing wired by hand:

```
THALAMUS_SCOPE=qe agent -p --trust "Fix the bug in src/pkg/mod.py: change add to subtract."
```

The write was blocked. The file was unchanged. The agent replied with our own guard's
handover instruction — *"switch to the implementing scope that owns `src/`… open a
thread or consultation ticket"* — and `~/.thalamus/guards/2026-08.jsonl` took the row:

```json
{"scope":"qe","guard":"role-boundary","guard_version":2,"verdict":"block",
 "tool":"Write","kind":"path","pattern":"*/src/*","session_id":"79cc144d-…"}
```

Run twice, by two sessions independently, one reproducing the other's.

## Four sentences that were false, and a green test holding one in place

`install.py` said "on Cursor there is today … load-bearing, no `write_boundary`
enforcement". `role-guard.sh` said "The Cursor harness has no role guard at all, so
neither boundary binds there". docs/07 named `role-guard.sh` in a three-item
`real_gaps`. `cli.py` printed "the Cursor harness" as a named miss to the operator.
And `tests/test_capability_probes.py` asserted `real_gaps == ("recipe-stage.sh",
"role-guard.sh", "room-guard.sh")` — **green, passing, and pinning a false claim about
the world**, because its subject is our two tables and a table cannot be asked what a
harness does.

That is the second time this record has been wrong in the same way and the first time
it was wrong in this *direction*. It over-reported gaps until `renames` was added
(`post-tool-use.sh` is `mcp-tap.sh` under another name); it under-reported enforcement
the moment a boundary began binding through a path in neither table. One cause both
times: **it measures the artifact instead of the obligation**, and moving the claim
from a comment into a dataclass raised its precision while leaving its subject alone.

## Three defects found while measuring

**1. The generic and specialized events are not exclusive.** One `echo` fires
`preToolUse` *and* `beforeShellExecution`, then `postToolUse` *and*
`afterShellExecution`. One MCP call fires both members of its pair. This settles the
question `install.py` has deferred since lab/027 — the taps stay specialized, because
tapping the generic event beside them would double-count every retrieval in
`eval sync`. The same fact is why a `hooks/cursor/role-guard.sh` must **not** be
written: a second registration runs the same guard twice on one call, and the
duplicate arrives as both denials concatenated into one tool result.

**2. `agent_message` reaches nothing; `user_message` does.** Denying with distinct
markers on both channels, the session transcript holds the `user_message` marker twice
and the `agent_message` marker zero times, and the agent's reply quotes the
`user_message`. `hooks/cursor/gremlin-guard.sh` has been putting its entire
explanation in `agent_message` and a bare one-liner in `user_message` — so a Cursor
session that trips that guard has been told it was blocked and never told why. The
suite's own test asserted the opposite behaviour and passed, because it drives the
script rather than the CLI. Fixed: the reason rides both fields. A block with no
reason is not a harmless silence — in Harness-Bench, 24.6% of failed trajectories are
tool errors *or* blocked commands not followed by effective recovery (arXiv
2605.27922, Table 3; the symptom categories are non-exclusive and this row ranks
second behind contract/format at 36.4%). So the nearest measured price of a bare
denial is a **stall**, while the route-around half of lab/008's standing trade is
argued and not measured.

**3. `cwd` arrives as `""`, and jq's `//` does not catch it.** Cursor sends an empty
string rather than omitting the field on shell payloads, and `//` falls through on
`null` and `false` only. Three shipped adapters — `gremlin-guard.sh`, `mcp-tap.sh`,
`gremlin-tap.sh` — have been writing empty `cwd` into the guard and trace ledgers for
every such payload. Pre-existing, unrelated to this port, and visible in the block rows
above.

## What does *not* bind, in three different states

Of the two boundaries `role-guard.sh` enforces, only one has anything to bind to:

- **`write_boundary`** binds. `Write` is Cursor's only edit tool (a one-word change to
  a three-line file arrives as a full-content `Write`; no `Edit`/`MultiEdit` exists)
  and it carries an absolute `file_path`, so the boundary never needed `cwd`.
- **`deny_tools` is vacuous, not unenforced.** The roster default's only entry is
  `Artifact` and Cursor has no such tool. Nothing is being let through; there is
  nothing to let through.
- **`deny_skills` is UNKNOWN, not absent.** Skills exist (18 in
  `~/.cursor/skills-cursor/`) and are used — the `review` skill arrived as a `Read` of
  its `SKILL.md` and then `Task`. What is missing is a `Skill` call to intercept. And
  Cursor has an interception point Claude Code lacks: `beforeReadFile` sees the read.
  Not built — a guard on `Read` is a high-false-positive surface — but "nobody asked"
  and "no referent" are different sentences and only one of them is true here.

FHIR R4's `DataAbsentReason` already separates these upstream of us as `unsupported` /
`not-permitted` / `not-asked`, so the five-state enum shipped in
`contract/boundaries.py` is a projection of an existing value set, not a vocabulary of
our own.

## The ceiling nobody had written down

`pin.py` opens `argv = ["claude"]` in both launch paths and there is no Cursor
launcher, while `hooks/cursor/resolve-scope.sh` resolves `THALAMUS_SCOPE` or `main` —
and `role-guard.sh` short-circuits on `main` before loading any manifest. **So the
boundary binds only on a session whose operator exported the variable by hand.** The
mechanism is real; the population is three sessions built to test it. An enforcement
claim about Cursor is a claim about hand-built sessions until a launcher exists.

Relatedly, Cursor's `preToolUse` payload carries no `agent_type`. The payload route
that fixed 6.4% subagent scope resolution on Claude Code has no analogue here — which
happens to be harmless, because Cursor subagents are `generalPurpose|explore|shell`
and never a differently-pinned expert, so inheriting the launcher's pin is correct
rather than the bug it was on the other harness.

## What shipped

`contract/boundaries.py`: eight rows, one per boundary per harness, five states
(`PROVIDED`, `NATIVE`, `ABSENT`, `OPAQUE`, `UNKNOWN`) and an `Evidence` stamp naming
`verified_against: "cursor/2026.08.11-e8db854"` — the artifact, not a date, because
what moved under us was a vendor build. The four Claude Code rows re-ask themselves
against `HOOK_WIRING` for free, which is not ceremonial: a room boundary was once
declared and never armed, and every room reported a treatment that had not occurred
(lab/056). The four Cursor rows report `unprobeable` on **every** run by construction —
no sentinel probe and no derivation reaches a vendor's undocumented compatibility
path, it costs a live session — so they land in the unchecked count instead of being
smoothed into a green tick. `HookParity` keeps its subject (the tables) and gains
`native`, the field that says an absence is a decision rather than a gap.

Not built, deliberately: `hooks/cursor/role-guard.sh` (§ defect 1), an
`mcp__thalamus__` prefix translation for `deny_tools` (no manifest denies an MCP tool,
so it would be an interface revealing a decision nothing uses), and a `beforeReadFile`
skill guard.

## Residuals

- **Everything above is `agent -p --trust`, print mode, one build.** A probe is sound
  as a falsifier and unsound as a generalizer; interactive Cursor remains unobserved,
  and the rows say so rather than hedging.
- **The compat path is undocumented** and can leave in a release with no announcement.
  That is not a reason to build a second guard; it is why the row carries a build
  string and has no free re-ask.
- **Four `role-boundary` rows in `~/.thalamus/guards/2026-08.jsonl` are probe
  artifacts** under scope `qe` (three blocks, one pass), all with cwds under a
  `/tmp/.../scratchpad/` prefix. Nothing reads `role-boundary` rows today, so this is
  latent; the roster granularity audit named in `role-guard.sh` would inherit them into
  its denominator, and the path prefix is how it can exclude them.
- **`recipe-stage.sh` and `post-tool-use.sh` may also be running on Cursor** through
  the same translation — their events are in the vendor's table and the matcher parser
  has an `mcp`-prefix branch. Unmeasured, so `real_gaps` still lists what it lists, and
  `real_gaps` is documented as a floor on the gaps rather than a measurement of them.
- **No measured work exists on what a denial message should say** — the literature
  consult found the gap is in what MAST *did*, not in what the graph holds. Nearest
  surrogates are Self-Debugging's explanation-only arm and AgentCollabBench's IDR
  rubric, which scores "refusal **or** a compliant alternative" as non-violation —
  which is the shape our block text already has.
