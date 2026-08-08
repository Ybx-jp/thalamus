# Harness Integration — MCP, Hooks, Directives, and the Limit Lab

**Status:** implementing — MCP + the full Claude Code hook suite (eight scripts
across five events, over a shared scope-resolution helper) installed and live;
session pinning built ("the process is the pin"); Cursor installed at user scope
by the same `thalamus init`, with every tier crossing except distillation
(lab/010, lab/027). This doc covers how Thalamus meets the Claude Code harness
primarily, the Cursor port's shape and its one remaining wall, and how we find
the harness's limits on purpose.

## Surfaces

- **MCP server** — the primary runtime surface: scoped retrieval/traversal for the
  pinned expert, and consultation requests. The subgraph-scoping rule is enforced
  *server-side* (the session's pin determines the visible scope) — the model is
  never trusted to self-limit its own retrieval scope. It is a **read surface plus
  the consultation exchange**: a session cannot write its own episodic memory from
  inside itself, because distillation will write that session anyway and a live
  second pass phrases the same decisions differently — content-addressed claims
  would not converge, and the duplicate threads would land in the surface every
  next session reads first. Checkpointing an open session is the operator's
  `thalamus extract --session <id> --force --write`, whose Source snapshots already
  carry a SUPERSEDES lineage for a session distilled while still open.
- **Hooks** — the instrumentation and enforcement layer:
  - *Session start:* record the process's pin into the tier-0 ledger, announce it
    in the primed context, and carry the **standing subagent authorization**
    (below).
  - *Post-tool-use on memory calls:* write retrieval traces — the eval loop's
    layer-1 feed ([04-eval-loop.md](04-eval-loop.md)).
  - *Session stop:* distill the session — summary + open threads into the pinned
    expert's episodic subgraph (the base system's maintenance scheme, now
    per-expert and eventually utility-weighted).
  - *Pre-tool-use on Bash (`gremlin-guard.sh`):* block inline gremlin-python
    whose traversal never invokes the iterator — lazy traversals with no
    terminal step silently do nothing, so the hook fails them fast with
    instruction instead. Every gremlin-marker verdict (block or pass) logs to
    `~/.thalamus/guards/` with the command's step fingerprint, the satisfaction
    branch (terminal/wrapper/textedit/no-traversal), and the guard version, so
    the guard grades itself: rescue joins on traversal intent, not "any later
    pass", and friction/false-negative exposure stay auditable per class
    (`thalamus eval gremlin`). The markers that trigger the guard are imports
    and connection setup, so a precision gate runs ahead of every satisfaction
    branch: absent a source step (`.V(`/`.E(`/`.addV(`/`.addE(`/`.inject(`) no
    traversal was built, there is no laziness to guard, and the command passes
    as `no-traversal`. House wrappers, text-editing/search commands and
    commit-message prose are allowed through likewise — markers as data rather
    than as code. The retrospective baseline found every would-be historical
    firing of the unamended guard was a false positive (lab/008), and false
    positives teach agents to route around the guard, so a residual false
    negative is the knowingly cheaper side of the trade. The
    paired dialect guard (gremlin-python spellings on the gremlin-lang
    `memory_query` surface) lives in `substrate/query.py`; authoring rules and
    the proven-query store are the `gremlin-python` skill.
  - *Post-tool-use on Bash (`gremlin-tap.sh`):* record executed ad-hoc gremlin
    commands as `bash_gremlin` lines in the same trace JSONL the memory tap
    writes, so `eval sync` prices them like any recall (docs/04) — the surface
    that used to query the graph in the dark.
  - *Wall clock (`timestamp.sh`, UserPromptSubmit):* inject one line of
    current local datetime on every prompt. The harness stamps `currentDate`
    only at session start, so long-running pinned roster sessions drift and
    hallucinate dates — into answers and into the memory graph's own
    timestamps (operator-observed, 2026-07-18). This is the one deliberate
    exception to the conditional-injection rule below: ~a dozen tokens per
    prompt, unconditional, kept separate from `conditioning.sh` so the
    rescue-rate telemetry stays clean.
  - *Conditioning (`conditioning.sh`, UserPromptSubmit + PostToolUse on
    TaskCreate and on `mcp__thalamus__memory_query`):* tilt the agent toward the
    memory system at the moments it historically under-uses it, and toward
    checking a result before committing it. Lexical intent classes on the user's
    prompt (design intent → ground-in-literature + consult reminder; past-work
    questions → recall-before-archaeology), a multi-step-work milestone on
    task-list creation, and a **falsify** class on the ad-hoc traversal surface
    — name what would make the conclusion wrong and run that query first
    (lab/029, where two correctly-cited consultation answers each had the
    mechanism wrong and each was overturned by one more traversal). It rides
    `memory_query` and not the recall tools because that surface returns raw
    aggregates that become claims, where recall returns prose already labelled
    as data; and it fires on the *first* query, because the reminder has to
    shape which queries get run and nothing observable announces that a
    conclusion is about to be written. Grounded: injection is **conditional,
    never every-prompt** (adaptive beats indiscriminate retrieval — Self-RAG,
    arXiv 2310.11511; locally, the ignored share is real but its magnitude is
    experiments/002's, not lab/006's withdrawn ~50%), **throttled**
    (once per class per **agent**, not per session — subagents share their
    parent's session id, and a session-keyed throttle silently exempts every one
    of them, including the consultation experts the falsify class exists for),
    and **measured per firing** (`thalamus eval conditioning` joins the firing
    log to the trace tap: did the behavior follow, or was the reminder
    wallpaper?). Context-borne conditioning as the behavior-change channel is
    Reflexion's result (arXiv 2303.11366). TaskCreate is deliberately *not
    required*: it is optional harness UI, and the load-bearing tier rides
    UserPromptSubmit, which always fires.
  - *Standing subagent authorization (`session-start.sh`):* some harness
    configurations carry a blanket "do not spawn subagents unless the user
    requested it." The consultation protocol **requires** spawning one — the
    expert is voiced by a subagent, and an agent that declines answers its own
    ticket instead. So the hook grants the permission in advance, scoped to the
    consultation protocol and disposable-context survey work rather than blanket
    agent use, and repeated at the moment of decision by `conditioning.sh`'s
    design class.

    This is **not an override**: that rule's own condition is *the user requested
    it*, and a tier-0 hook in git is the operator speaking, so the authorization
    satisfies the condition rather than contradicting the instruction. Framing it
    as an override would be both weaker and the wrong shape — context that claims
    to lift a restriction is exactly what a poisoning payload looks like
    ([05](05-trust-model.md)), which is why the text identifies its own provenance
    (tier-0, this repo, in git) instead of merely asserting permission.

    Measured cost of its absence (lab/025): a session declined the spawn, answered
    its own ticket, and filed **8 citations where a voiced subagent filed 25** on
    the identical question — missing the one paper in scope that argued against
    the design being written. The two exchange records were byte-identical, which
    is why `eval sync` now stamps `answered_from` (docs/02).
- **CLAUDE.md directives** — per-project retrieval policy: default pin for this
  directory, tier policy for this kind of session, when to consult vs. answer thin.
  These start minimal and **evolve organically with use** — every directive change
  gets a line in the lab notebook saying what failure motivated it, so the
  directive set becomes an evolution record rather than accreted folklore.
- **Skills** — operator verbs: pin/re-pin, ingest, roster status, "why did you
  believe that?" (provenance walk), eval-report. Skills stay thin wrappers over MCP
  so nothing load-bearing lives in prompt text.

## The second harness: Cursor

Cursor is supported as a retrieval-and-instrumentation harness, wired at **user
scope** by `thalamus init` (`--harness cursor` to install it alone; the default
installs both editors). Every Cursor hook under `harness/hooks/cursor/` is a
**thin adapter over the Claude Code script** — one detection logic, one set of
on-disk records, two harness dialects (lab/010 has the field mappings, lab/027
the 2026-07-29 re-verification):

- *sessionStart* → memory priming + the tier-0 pin ledger (same record shape).
- *beforeSubmitPrompt* → engagement marking, and the prompt-side half of the
  two injection tiers (below).
- *beforeShellExecution* → the gremlin terminal-step guard (exit-2 protocol
  mapped to `permission: deny` + `agent_message`).
- *afterShellExecution* / *afterMCPExecution* → the two trace taps; Cursor
  reports MCP tools by bare name, and the adapter restores the
  `mcp__thalamus__` prefix so `eval sync` stays harness-blind.
- *postToolUse* → delivery of the spooled injection. It deliberately does **not**
  tap: `postToolUse` is generic (it fires for every tool type, MCP included) and
  the docs do not say whether a tool call fires both it and the specialized
  event. If it does, tapping both double-counts every retrieval in `eval sync`,
  so the taps stay specialized until a live Cursor settles it. The cost of that
  caution is that tracing does not reach Cursor **cloud agents**, where the
  MCP-specific events do not load but `postToolUse` would.

**The two injection tiers cross by splitting compute from delivery.** Cursor
gives the prompt text to an event that cannot inject (`beforeSubmitPrompt`) and
injection to events that never see the prompt — so the prompt-side hooks write
a per-session spool (`~/.thalamus/spool/`) and the next `postToolUse` drains it
into `additional_context`. The clock is *rendered at drain*, never at spool
time: a timestamp computed a tool call earlier is exactly the drift
`timestamp.sh` exists to prevent. Conditioning runs the real Claude Code
classifier against a reshaped payload, so its lexical classes, its
once-per-session throttle and its firing log are one implementation rather than
two. The price, recorded rather than hidden: **injection lands one tool call
late**, a turn that calls no tool carries its *clock* forward, and session end
discards an undelivered spool instead of leaking it into a later session. The
conditioning half is pruned at each new prompt instead of carried: it was
classified against one specific prompt, so late delivery would advise design
work against whatever was asked next — a message past its freshness lifetime
(RFC 9111 §4.2), and agents measurably act on superseded state even when the
fresh state is available (STALE, arXiv 2605.06527).

Each firing records its `harness` and `thalamus eval conditioning` splits by it.
That split prevents pooling; it does **not** license a cross-harness comparison.
The two arms differ configurally — the Cursor arm is missing indicators the
Claude Code arm has (no milestone class) and delivers the rest through a
different channel — and configural invariance is the precondition for any
cross-group comparison, not something a scaling factor repairs (Vandenberg &
Lance 2000). Harness configuration is a first-order effect on agent behaviour in
its own right (Harness-Bench, arXiv 2605.27922). So **the Cursor arm is a
within-harness longitudinal instrument, not a comparator against Claude Code**,
until the channel question below is settled.

**The open risk is the delivery slot, not the one-call delay.** Cursor's
conditioning arrives in the tool-result slot, and the only positional
measurement that exists for text in that slot is adversarial: instruction
efficacy from the observation stream falls from 60% at depth 1 to 0% at depth 4
(arXiv 2605.30686), because models are deliberately trained to discount
instructions arriving in tool output — otherwise indirect prompt injection would
be trivial. Whether *benign* guidance in that slot gets the same uptake as the
same guidance in the user turn is unmeasured anywhere (see
[11](11-related-work.md) §4). If it does not, a `harness` split reports a
difference it cannot attribute — channel, not latency. This is measurable
in-house with instruments that already exist and is the next thing to run.

**Distillation crosses too, at reduced fidelity** (`harness/cursor_transcripts.py`,
lab/028). `thalamus extract --harness cursor` sweeps the sessionEnd log,
producing the same `TranscriptFacts` the Claude Code reader produces so
extraction, merging and provenance stay unchanged. Three gaps are structural in
Cursor's format and each is carried explicitly rather than inferred away:

- **No tool results, for any tool** — excluded deliberately because they can be
  large. So the ingress floor's evidence does not exist, and a Cursor session is
  floored whole rather than checked ([05](05-trust-model.md)). Ingress tool
  *calls* are still counted: their inputs survive, so we can see that a session
  fetched, only not what came back.
- **No message ids**, so Touch anchors are positional (`cursor:msg:<row>`),
  namespaced so a synthesized anchor cannot pass for a real UUID.
- **No timestamps and no cwd on any row.** Both come from the hooks' own
  ledgers — `pins.jsonl` for the start and the workspace, the sessionEnd log for
  the end — which is why those hooks shipping first is what makes backfill of
  everything logged since possible at all.

Extraction runs as a **later sweep, not at sessionEnd**: Cursor is not documented
to flush the transcript before firing the hook (an open request asks it to fsync
first, or to add `transcript_ready`), so reading at session end races an async
writer and can distill a truncated session. Scope comes from each session's own
sessionEnd record, ledger-first, not from the `--scope` flag.

**Every headless invocation resolves its CLI from one registry**
(`harness/agents.py`): binary, default model, whether the envelope prices the
call, and what the CLI cannot yet do. Nothing spells `claude` inline any more,
because a hardcoded vendor binary is invisible until the machine that lacks it
tries to use it — and then it fails as "distillation stopped happening" rather
than as an error anyone reads.

A session distills through its own harness's CLI: Claude Code sessions go to
`claude -p`, Cursor sessions to Cursor's `agent -p` defaulting to Composer 2.5.
Both take `-p`, `--model` and `--output-format json`, and both return an envelope
carrying `result`, `is_error` and `duration_ms` under those exact names, so one
invocation path serves both. Two reasons this is not merely tidy: a Cursor-only
machine should not need Claude Code installed and authenticated before its
sessions can become memory, and each harness's session content stays with the
vendor the operator already chose for that machine — a policy question on a work
box, not only a convenience. `thalamus ingest` takes `--harness` for the same
reason, though ingestion has no harness of its own: it picks whichever CLI the
machine actually has.

**A sandbox is not a session.** Every headless invocation — distillation and
`thalamus ingest` alike — is a full session to its own harness: it gets a session
id, a transcript on disk, and the hook suite armed at user scope. Left alone, the
hooks that make memory fire inside the machinery that makes memory, and the graph
fills with memory about the act of remembering: a Session whose summary
paraphrases the session it was distilling, its own Claims, its own open Threads,
and its own headless run one level deeper.

Three refusals close it, because the marker that stops the live loop is gone by
the time a retroactive sweep reads the same transcript:

- The subprocess runs marked. `agents.sandbox_env` sets `THALAMUS_SANDBOX`, which
  the CLI passes to its hooks, and `thalamus_sandbox_guard` (`resolve-scope.sh`,
  both harnesses) exits every hook that sees it — no distillation, no pin ledger,
  no traces, no injected context. The rule is uniform across the suite so no
  future hook has to rediscover it.
- The reader refuses by name. `transcripts.discover()` withholds project dirs from
  the sandbox cwd (`agents.SANDBOX_TMP_PREFIX`), so `thalamus bootstrap` never
  lists one and `thalamus extract -- <sandbox-dir>` is an unknown project.
- `thalamus extract` re-checks the cwd each transcript recorded, so a sandbox
  transcript reached any other way is still skipped.

**Capability is declared, not assumed.** Two surfaces stay Claude-Code-only, and
both say so rather than substituting a binary:

- **Eval arms** (`arms.agent_cli`) refuse a harness they cannot honestly drive,
  itemising why — staged credentials from `~/.claude.json`, `--max-turns` and the
  permission flags, an envelope reporting `num_turns` and `total_cost_usd`, and a
  transcript the escape detectors and fault classifier can read. A partial port
  would emit records that read as measurements and are not, which is the failure
  lab/016 and lab/022 are both about.
- **`thalamus pin`** launches through the agent picker (`--agent thalamus-<scope>`),
  which Cursor has no equivalent of — a Cursor session is pinned by
  `THALAMUS_SCOPE` in its environment instead. There is no second thing for the
  launcher to launch, so it is not routed through the registry at all.

The deliberately-not-fast variant is the batch argument: distillation is a sweep
where nothing waits on the result, so the quality/latency trade runs the other way
from interactive use. Two honest caveats. Cursor's envelope carries **no cost or
token fields**, so `ExtractionRun.cost_usd` is `None` rather than `0.0` and the
sweep counts unpriced runs separately — a zero meaning "not reported" is
indistinguishable from a zero meaning "free", which is the same absent-vs-negative
trap as the ingress floor. And the Composer identifier is **unverified**: Cursor
documents `--model` and `--list-models` but publishes no identifier strings, and
Composer 2.5 has no public API model id. A wrong string fails at invocation rather
than silently selecting another model, and the error carries
`agent --list-models` so the fix is one command away.

The `PostToolUse:TaskCreate` milestone conditioning class remains without a
carrier — TaskCreate is Claude Code task-list UI, while Cursor's `Task` tool type
is subagent spawning.

**Open, and the way to earn tier-1 back on Cursor:** capture tool outputs
out-of-band. Cursor's own recommendation for full traces is a `postToolUse` hook
writing them to a file, and Thalamus already runs a hook on that event. The
blocker is not the mechanism but the roster — Cursor's built-in web-tool names
are undocumented and unobserved, so the ingress set would be a guess. A live
session settles it; until then the conservative floor stands and costs emphasis
rather than correctness.

### Prior work

Splitting *where context is computed* from *where it is delivered* inside an
agent loop has no name in the literature — not found in the 2026 scan (see
[11](11-related-work.md) §4) — but each half is grounded. Deferring computation
off the critical path is measured: sleep-time compute cuts test-time compute
~5× at equal accuracy (arXiv 2504.13171), and asynchronous writes are a standard
latency mitigation in the agent-memory survey (arXiv 2603.07670). Rendering the
volatile field at delivery rather than at enqueue is **late binding** in the
call-by-name sense — the payload carries the expression, not its result
(Henderson & Morris, POPL 1976; Ingerman, CACM 4(1) 1961) — the same axis as
deferred vs immediate materialized-view maintenance (Colby et al., SIGMOD 1996)
and Fowler's Event Notification over Event-Carried State Transfer (2017); the
alternative, shipping a snapshot, is early binding, and RFC 9111 and EIP Message
Expiration (Hohpe & Woolf 2003) only detect or discard staleness rather than
prevent it. Injecting once per prompt rather than per tool call is an
*instantiation* of Self-RAG's adaptive-vs-indiscriminate retrieval (arXiv
2310.11511), with a direct agent-side ablation behind it: selective reminder
injection beats an always-on baseline on Terminal-Bench 2.0 and τ²-Bench (arXiv
2607.08716) — though by small margins, and that paper reports no token or
latency comparison, so the cost half of the throttle argument remains uncited.
One finding argues the lag matters less than feared: intervention timing has no
stable ground truth — three trained annotators agreed on *where* to intervene
barely above chance (Krippendorff's α = +0.047), and the paper's conclusion is
to build for recoverability rather than precision timing (arXiv 2606.04296),
which puts a one-tool-call offset inside the construct's noise floor. The
adapter layer itself is an Anti-Corruption Layer (Evans 2003) — vocabulary, not
evidence. The atomic drain, the filename sanitization, the fire-and-forget
semantics and the decision not to tap in `postToolUse` are plain engineering
with no research claim to make.

Pin resolution on Cursor is env-only — no agent picker — so a Cursor session is
`main` unless launched with `THALAMUS_SCOPE`. Cursor cloud agents load neither
the session hooks nor the MCP hooks; local Cursor only. Conformance is tested
with synthetic payloads (`tests/test_cursor_hooks.py`) against shapes read from
Cursor's docs and re-verified 2026-07-29 — **no Thalamus code has yet run inside
a live Cursor**, which remains the standing caveat on everything in this
section.

## Session pinning mechanics: the process is the pin

Pinning is session-granular routing ([02-expert-subgraphs.md](02-expert-subgraphs.md)).
The harness cannot resolve a per-call pin — MCP calls don't carry the caller's
session, and config arms per *process* (measured, lab/001) — so the process
boundary is the mechanism: **one OS process = one immutable pin**.

0. **Install is what makes the harness reach past the checkout.** `thalamus init`
   writes the hook block to `~/.claude/settings.json` with **absolute** paths and
   registers the MCP server at user scope through `claude mcp add` (never by
   editing `~/.claude.json`, which every live session on the box writes). It then
   **removes** the checkout's project-scope hook block and `.mcp.json` entry, so
   exactly one definition of each exists: Claude Code deduplicates identical
   handlers by command string, but the two cannot be textually identical — the
   whole point is that one stops using `$CLAUDE_PROJECT_DIR` — and the docs do
   not state whether hook arrays across scopes merge or override. Mutual
   exclusion keeps that undocumented behaviour off the critical path. It also
   links the package's skills into `~/.claude/skills/`, because a session opened
   elsewhere otherwise gets the hooks, the server and the agents but none of
   `recall-strategy`, `ground-in-literature` or `gremlin-python` — the three that
   govern how it queries the graph and grounds a design, and whose absence is
   silent. Skills are the one artifact **not** made mutually exclusive: both
   scopes are symlinks onto the same package directory, so they are not rival
   definitions, and keeping the checkout's links means a fresh clone has its
   skills before `init` has run. A user-scope name that is not our symlink is
   left untouched, and a `SKILL.md` without frontmatter is prose rather than an
   invocable skill, so it is not installed. Install is idempotent, leaves
   non-Thalamus hooks
   and unrelated settings alone, and ends
   by **exercising** what it wired rather than asserting it (see
   [11 §2a0](11-related-work.md) — these are latent configuration errors, inert
   until an event fires, and SessionEnd fires detached). `--dry-run` reports
   without writing; `--check` verifies an existing install. Arming is
   per-process, so existing sessions need a relaunch — `/clear` is not enough.
   When the MCP server's **env** changes, that stops being a nicety and becomes
   an advisory naming the variable and both values: an open session keeps the old
   env for its whole lifetime while looking entirely normal from the inside, so a
   withholding rate that moves mid-campaign yields records at two rates under the
   belief they ran at one (experiments/003 requires the rate to hold for the
   campaign's duration).

   Install **reports on the environment, never changes it.** Two things it wires
   toward but does not own — a running graph and a coding-agent CLI on PATH — are
   checked and reported as *advisories*: the finding, plus the command that fixes
   it, and no effect on the exit code. Both are otherwise silent in the Xu et al.
   sense and neither was checked anywhere before. An unreachable graph surfaces as
   a recall that returns nothing, which reads as "no memory yet" rather than as an
   error; a missing CLI surfaces as memory that quietly stopped accumulating,
   because distillation runs detached from SessionEnd. Neither is a reason to
   refuse to wire a machine, and a tool that silently started containers would be
   harder to trust than one that says what to run. **A graph with zero vertices
   passes** — see below.

   **The graph is never shipped.** It holds one operator's session history, and
   the archive holds their transcripts verbatim, so there is no seed graph, no
   export path and no fixture corpus: every install is fresh, for everyone. An
   empty graph is therefore the normal starting state rather than a fault, and
   the advisory says so. Both stores live outside the checkout by construction (a
   named Docker volume; `~/.thalamus/`), with `.gitignore` guarding the paths
   against a stray `snapshot --path ./…` or a hand-copied archive.

   The same command installs **Cursor** (`--harness claude|cursor|both`,
   default both): `~/.cursor/hooks.json` and the `thalamus` server in
   `~/.cursor/mcp.json`, with the checkout's project-scope copies stripped. The
   mutual-exclusion argument is sharper here than on Claude Code — Cursor
   documents its precedence as Enterprise > Team > Project > User, with user
   scope *last*, so a surviving project block is documented to outrank what was
   just written rather than merely risking it. Commands are absolute for a
   reason specific to Cursor: user-scope hooks run from `~/.cursor/` and
   project-scope hooks from the project root, so no relative path is correct in
   both scopes — the checkout's former `./src/...` wiring armed only for a
   session whose workspace root was the checkout itself. Verification exercises
   the deferred-injection round trip (spool a turn, drain it) rather than
   checking that files exist, because a broken spool costs a session its clock
   and its conditioning and reports nothing at all.
1. **Launch is the pin decision.** `thalamus pin <scope>` validates the scope
   against the tier-0 manifests, regenerates the derived agent definition
   (`.claude/agents/thalamus-<scope>.md` — generated from the manifest, never
   hand-written), and hands the terminal to
   `THALAMUS_SCOPE=<scope> claude --agent thalamus-<scope>` (a tmux window when
   available, `execvp` otherwise). `thalamus roster` brings up the control plane:
   by default just the `main` **anchor** window (idempotent); `--all` opens one
   window per expert manifest (the legacy full roster). Experts are otherwise
   **spawned on demand** — `thalamus spawn <scope> --dir <path>` opens one
   detached pinned window in a chosen directory, so a pinned expert session can
   work in any project while its distilled memory still scopes to the expert
   (Thalamus memory spans projects). Spawn writes the derived agents to
   `~/.claude/agents/` (not only the repo's) so `--agent` — and sibling
   consultation subagents — resolve regardless of the window's cwd. On-demand
   replaced always-on expert windows because an idle window still writes a
   pin-ledger spawn, inflating the `pinned, never retrieved` metric (lab/roster
   metric-confound, 2026-07-19). `main` is the default for any plainly-launched
   process — an unpinned session *is* a main-plane session.
2. **The pin is resolved once, everywhere, by the same rule.** Resolution is
   **picked-agent-first, env-fallback** (`harness/pin.resolve_pin`; hooks source
   the mirror `resolve-scope.sh`): `CLAUDE_CODE_AGENT=thalamus-<scope>` wins
   when it names a real manifest, else `THALAMUS_SCOPE`, else `main`. Agent-first
   exists because the agent picker (FleetView, `claude --agent`, the plane's
   launch surfaces) starts a pinned persona without going through `thalamus pin`,
   so the env carries whatever the surrounding shell had — measured 2026-07-18:
   all three roster expert sessions ran with the expert agent picked and
   `THALAMUS_SCOPE=main`, every memory op silently hitting main. The harness
   exports `CLAUDE_CODE_AGENT` into the MCP server's own environment (measured
   on the live server processes), the server applies the rule at process
   startup, and it scopes every retrieval and write server-side — the model is
   never trusted to self-limit its own scope, and no tool accepts a scope
   argument. Both surfaces resolve the manifest against the **checkout** —
   `THALAMUS_CONFIG_DIR`, else the tree the code itself sits in
   (`contract/manifest._DEFAULT_CONFIG` in Python, `thalamus_repo_root` in the
   bash mirror). Neither reads `CLAUDE_PROJECT_DIR`: that names the session's
   *working* project, which is a different repo whenever a session is opened
   outside the checkout (`thalamus spawn --dir`). Anchoring the mirror on it
   made hooks resolve `main` while the server enforced the real scope, and
   because SessionEnd is ledger-first, the whole session then distilled into the
   wrong subgraph — the 2026-07-18 leak arriving through the ledger rather than
   the env. For the same reason SessionEnd invokes extraction as
   `uv run --project <checkout>`: a foreign cwd is not a uv project with
   thalamus in it, and detached extraction fails invisibly.
   All the hooks are children of the same process, inherit the same
   env, and apply the same precedence: SessionStart
   appends the tier-0 pin record to `~/.thalamus/pins/pins.jsonl` and announces
   the pin in the primed context. That record carries both the resolved `scope`
   **and** the raw `agent` (`CLAUDE_CODE_AGENT`) it was resolved from, because a
   ledger holding only the resolution cannot audit the resolution: when the two
   disagreed before `ed18887`, the stored value was the wrong one, and the
   retained transcript could not settle it either — consultation subagents carry
   the same pinned-agent text as a real pin, so its presence is not evidence the
   session was pinned. SessionStart also states the session's **own id** in the
   injected context, marked authoritative: a session is otherwise blind to which
   session it is, and self-referential reasoning then guesses its subject —
   lab/026 records a session inferring its id from a subagent task path, landing
   on a real adjacent session, and acting on it. When the routing decision itself
   was wrong — a pinned
   window used for main-plane work — `thalamus rescope <session> <scope>` appends
   a correction row, which SessionEnd's `tail -1` resolution then honours. The
   session argument is optional and defaults to `$CLAUDE_CODE_SESSION_ID`, the
   harness's own export; with that unset it **refuses** rather than resolving
   from the ledger, since concurrent sessions routinely share a cwd and a
   "most recent entry here" heuristic reintroduces the wrong-subject bug. An
   explicitly-passed id that differs from the live one is refused unless
   `--other-session` acknowledges it — the mismatch is **detected**, not
   self-declared, so a caller wrong about its own identity cannot assert its way
   past it, and acknowledged crossings are stamped `cross_session`. Every row
   records `by_session`: who performed the correction, not only who it was
   performed on. It
   **appends, never edits**: the original pin record survives beside the
   correction, because an audit log that can be rewritten cannot audit anything.
   It **refuses once the session has distilled**, since vertex IDs include scope
   — a late correction would not move the Session vertex, it would mint a second
   one under the new scope and leave the first holding a stale half of the
   transcript (`--allow-distilled` overrides and records `forked_from`).
   PostToolUse stamps the pin into every tap line;
   SessionEnd resolves the distillation scope **ledger-first, env fallback** and
   passes `--scope` to extraction, so the session's episodic memory lands in the
   pinned expert's subgraph. Ledger-first keeps re-extraction from any later,
   differently-pinned shell landing in the wrong scope and forking the Session
   vertex identity (vids include scope). The *project dir* it hands extraction
   comes from the payload's `transcript_path` — `basename(dirname(...))`, exactly
   the key `transcripts.discover()` returns — never from the cwd. Claude Code
   files a transcript under the dir named for the cwd the session **started** in,
   while the payload's `cwd` is the cwd at exit, so a session that `cd`s away
   would otherwise point extraction at a different project dir and select no
   session at all. Behind that, a second floor: an explicit `--session` that
   matches nothing **exits non-zero** rather than reporting "0 sessions to
   extract" and succeeding. Distillation runs detached into a log, where a
   zero-count success is indistinguishable from a session that legitimately had
   nothing to distill — the shape that hid three lost sessions. Selection runs
   before the graph connection, so the refusal survives a graph that is down.
   After extraction the same detached run
   chains `thalamus eval sync --write`: the just-distilled session's tap traces
   land as priced Trace nodes, and any backlog from other distilled sessions is
   swept in the same pass (trace identity is content-addressed, so concurrent
   session-ends converge). The Pulse dashboard's pending stamp (docs/03) is the
   observable for this loop.
3. **Pin immutability is enforced by process lifetime, not policy.** A pin cannot
   change mid-session because nothing can re-scope a running process (lab/001) —
   the property v1 wanted is the property the harness gives. "Wrong pin" is data,
   not a failure: it feeds pin-quality grading, and env≠ledger mismatches are
   logged, never fatal.

Every leg is measured live in lab/003.

### Prior work

Access-governed shared memory — explicit authority and scope on multi-agent memory
reads and writes — is a named first-class concern of the agent-infrastructure
literature (arXiv 2606.20570, in the graph as feed `thalamus`), and governance of
persistent agent memory/state is a surveyed subfield of its own (arXiv 2606.30306,
same feed). Pinning is an *instantiation* of that consensus with the OS process as
the authority boundary: the scope grant is fixed at process creation, outside the
model's reach, which is the write-path stance (arXiv 2606.04329) applied to
routing. What it trades away is exactly what docs/02 already conceded — per-query
routing flexibility — accepted for legibility and episodic coherence. The specific
coupling (harness process lifetime = pin immutability) is engineering, not
research.

## Inter-expert consultation via subagents

Consultation rides the harness's native subagent protocol rather than a bespoke
bus: the pinned session spawns a subagent whose context is scoped to the consulted
expert, the subagent answers from that scope, and the exchange is written to both
experts' episodic subgraphs plus the master plane's exchange graph. Depth 1 only in
v1. Two properties matter:

- The consulted scope returns **data with provenance, never directives**
  ([05-trust-model.md](05-trust-model.md)).
- The transcript is not lost context — it is distilled into episodic memory on both
  sides. The harness's subagent mechanism becomes memory-forming machinery.

## Peer sessions as an instrument

Claude Code makes each teammate and each session its own process — own session id,
own MCP server instances, own hooks. Under "the process is the pin" that means
**every session is a pinnable unit**, and a team is a roster of concurrently-pinned
experts with a shared task list. That makes the harness's coordination surfaces less
a product feature than a *measurement instrument* for exactly the questions this
project exists to answer. The generated `.claude/agents/thalamus-<scope>.md` files
double as teammate blueprints — the zero-glue test extends to teams.

Teammates remain behind `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`; **peer-session
messaging is generally available**. `ListAgents` enumerates every reachable session —
in-process subagents, other local sessions, cloud sessions, remote bridge sessions —
and `SendMessage` delivers a sender-authored summary to any of them, which the
receiver takes up mid-task.

Two channels matter and they are not equal: consultation (ticketed, cited,
recorded — the collaboration graph sees it) and **peer messaging** (a sender's
summary the harness delivers between sessions — unprovenanced, invisible to the
graph, and distilled into the receiver's transcript as tier-1). Peer messaging is
the agent-authored variant of the transcript-mediated-laundering gap
([05-trust-model.md](05-trust-model.md)), and general availability is what sets its
blast radius: the reachable set is every live session on the machine and in the
cloud, not the teammates of one team.

The harness guards the adjacent axis, not this one. `SendMessage`'s own
documentation forbids asking a peer to perform work the sender's permissions
blocked — "cross-session permission laundering" — a norm stated in a tool
description, enforced by nothing, and orthogonal to trust tier. Nothing in the
channel marks a claim that crosses scopes.

**The room boundary is enforced at the sender** (`room-guard.sh`, PreToolUse on
`SendMessage`). A session with `THALAMUS_ROOM` set may message only room-mates —
names prefixed `<room>-`, the form the launcher gives members — plus `main` and
raw agent ids, because the same tool serves in-process subagents and the
consultation protocol runs over it. Everything else is blocked with the ticket
named as the sanctioned route. Sessions outside a room are untouched.

Two limits, both deliberate. It governs **outbound only**: an outsider can still
message a member, since nothing at that sender's end is ours to gate, and
`crossSessionInbound` cannot discriminate by sender. And it is policy where
structure would be better — peer discovery reads the socket registry at
`$XDG_RUNTIME_DIR/cc-socks`, but overriding that variable does not relocate the
registry, it stops the session binding a socket at all
([lab/044](../lab/044-the-runtime-dir-is-an-off-switch.md)), and relocating it
needs a bind mount in a mount namespace that this box refuses unprivileged. Until
a privileged bind mount or a container per room exists, a room is one whose
members will not talk out rather than one nobody can talk into. Verdicts are
events in the same guard ledger `thalamus eval gremlin` reads, so the
false-positive rate is measurable rather than assumed.

**The channel is instrumentable, which the in-process teams mailbox was not.** An
incoming message lands in the receiver's transcript wrapped as
`<cross-session-message from="...">`. That wrapper is a syntactic boundary
collection can key on — a sender attribute and a delimited payload, where the
mailbox offered no artifact at all — and it is what makes T4 buildable.

Experiments, ranked by information-per-effort (each run produces a lab entry):

| # | Experiment | Hypothesis | Status (lab/004, 2026-07-16) |
|---|---|---|---|
| T0 | Per-teammate env inheritance | Teammates inherit the lead's env — one team, one pin, unless launched otherwise | **Confirmed** (n=1): teammate ran pinned `literature`, own session/ledger row/tap lines. Distinct per-teammate pins need per-teammate launch control |
| T5 | Peer traffic vs collaboration graph | Most inter-session coordination bypasses the consultation protocol | **Confirmed a fortiori**: no `inboxes/*.json` materialized at all (`in-process` delivery), zero Exchange/CONSULTS — the only durable record is the transcripts. Unchanged by GA messaging, which writes no artifact of its own either |
| T2 | Per-teammate distillation | N teammates → N SessionEnd distillations → per-expert episodic memory at process level | **Confirmed** (free ride on the T0 run): teammate distilled into its pinned scope, own SessionEnd |
| T1 | Pin-quality A/B | Same task, literature-pinned vs main-pinned teammate: pinned retrievals show a higher used-ratio in-domain | Unblocked in design (env per teammate, or pinned windows joined as a team); parked pending the lead-cwd anomaly |
| T4 | Peer-message canary (M5) | A canary claim in session A's scope, relayed by `SendMessage`, lands tier-1 in session B's scope | **Unblocked**: the `<cross-session-message from="...">` wrapper is a collectable boundary in the receiver's transcript. Needs the defense-off control (lab/039) |
| T3 | Counterfactual arm (M4) | Memory-on vs memory-degraded teammate on one task: the memory arm resolves faster / reuses decisions | Parked; same unblock as T1 |

**Measured anomaly to re-check before trusting lead-side behavior:** a headless
teams lead launched from this repo armed the *stepmania* project's harness (wrong
cwd recorded in the team config; transcript landed in the wrong project dir; no
thalamus hooks or MCP for the lead). n=1, cause unknown — lab/004 §4.

## The limit lab (the senior story)

The stated best outcome: it works brilliantly, *then breaks somewhere honest*, and
each break gets engineered around until we hit genuine limits of the Claude Code
harness. That only counts if it's documented. `lab/` (started at M2) collects
one-page entries: **what broke → why (root cause in harness terms) → workaround or
wall**.

Candidate pressure points to probe deliberately, once the eval loop can measure
their effects: context budget vs. retrieval depth (when does more memory hurt?);
hook latency on memory-heavy sessions; subagent context isolation (what leaks,
what's lost) for the consultation protocol; MCP payload limits vs. subgraph result
sizes; session-summary quality drift as episodic history compounds; where scoping
enforcement *has* to live server-side because the harness can't hold it.

Entries that end in "wall" are as valuable as ones that end in "workaround" — a
documented, measured limit of the harness is exactly the artifact this lab exists
to produce.

## Open questions

- Which hook events are the right distillation trigger in long-running sessions
  (stop only, or periodic compaction too)?
- How much retrieval the *hooks themselves* may do (pre-loading pinned-expert
  entrypoints at session start vs. keeping startup thin).
- Whether consultation subagents should be a custom agent type or the stock
  general-purpose agent with a scoped MCP config. Start stock; let a failure
  justify custom.
