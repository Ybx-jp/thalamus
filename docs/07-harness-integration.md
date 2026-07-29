# Harness Integration — MCP, Hooks, Directives, and the Limit Lab

**Status:** implementing — MCP + the full Claude Code hook suite (eight scripts
across five events, over a shared scope-resolution helper) installed and live;
session pinning built ("the process is the pin"); Cursor hook suite ported as
adapters (four of the five events cross — lab/010). This doc covers how Thalamus meets the Claude Code harness primarily,
the Cursor port's shape and walls, and how we find the harness's limits on
purpose.

## Surfaces

- **MCP server** — the primary runtime surface: scoped retrieval/traversal for the
  pinned expert, consultation requests, episodic writes. The subgraph-scoping rule
  is enforced *server-side* (the session's pin determines the visible scope) — the
  model is never trusted to self-limit its own retrieval scope.
- **Hooks** — the instrumentation and enforcement layer:
  - *Session start:* record the process's pin into the tier-0 ledger and announce
    it in the primed context.
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
    TaskCreate):* tilt the agent toward the memory system at the moments it
    historically under-uses it. Lexical intent classes on the user's prompt
    (design intent → ground-in-literature + consult reminder; past-work
    questions → recall-before-archaeology) plus a multi-step-work milestone on
    task-list creation. Grounded: injection is **conditional, never
    every-prompt** (adaptive beats indiscriminate retrieval — Self-RAG, arXiv
    2310.11511; locally, lab/006's ~50% ignored share), **throttled**
    (once per class per session), and **measured per firing** (`thalamus eval
    conditioning` joins the firing log to the trace tap: did the behavior
    follow, or was the reminder wallpaper?). Context-borne conditioning as the
    behavior-change channel is Reflexion's result (arXiv 2303.11366).
    TaskCreate is deliberately *not required*: it is optional harness UI, and
    the load-bearing tier rides UserPromptSubmit, which always fires.
- **CLAUDE.md directives** — per-project retrieval policy: default pin for this
  directory, tier policy for this kind of session, when to consult vs. answer thin.
  These start minimal and **evolve organically with use** — every directive change
  gets a line in the lab notebook saying what failure motivated it, so the
  directive set becomes an evolution record rather than accreted folklore.
- **Skills** — operator verbs: pin/re-pin, ingest, roster status, "why did you
  believe that?" (provenance walk), eval-report. Skills stay thin wrappers over MCP
  so nothing load-bearing lives in prompt text.

## The second harness: Cursor

Cursor is supported as a retrieval-and-instrumentation harness, wired by two
committed files: `.cursor/mcp.json` (the same MCP server, defaulting to `main`
scope) and `.cursor/hooks.json` (hooks.json v1). Every Cursor hook under
`harness/hooks/cursor/` is a **thin adapter over the Claude Code script** —
one detection logic, one set of on-disk records, two harness dialects
(lab/010 has the field mappings):

- *sessionStart* → memory priming + the tier-0 pin ledger (same record shape).
- *beforeSubmitPrompt* → engagement marking only.
- *beforeShellExecution* → the gremlin terminal-step guard (exit-2 protocol
  mapped to `permission: deny` + `agent_message`).
- *afterShellExecution* / *afterMCPExecution* → the two trace taps; Cursor
  reports MCP tools by bare name, and the adapter restores the
  `mcp__thalamus__` prefix so `eval sync` stays harness-blind.

What does **not** cross (both walls in lab/010): per-prompt context injection
(`beforeSubmitPrompt` can block but not inject, so the timestamp and
conditioning tiers are Claude-Code-only — cross-harness utilization numbers
are confounded by design), and **distillation** (`thalamus extract` parses
Claude Code JSONL transcripts only; the Cursor session-end hook logs the ended
session with `distilled: false` and its `transcript_path` to
`~/.thalamus/logs/cursor-session-end.jsonl` instead of silently dropping it).
Pin resolution on Cursor is env-only — no agent picker — so a Cursor session
is `main` unless launched with `THALAMUS_SCOPE`. Cursor cloud agents load none
of the session/MCP hooks; local Cursor only. Conformance is tested with
synthetic payloads (`tests/test_cursor_hooks.py`); the payload shapes were
read from Cursor's docs (2026-07-19), not yet confirmed against a live Cursor.

## Session pinning mechanics: the process is the pin

Pinning is session-granular routing ([02-expert-subgraphs.md](02-expert-subgraphs.md)).
The harness cannot resolve a per-call pin — MCP calls don't carry the caller's
session, and config arms per *process* (measured, lab/001) — so the process
boundary is the mechanism: **one OS process = one immutable pin**.

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
   argument. All the hooks are children of the same process, inherit the same
   env, and apply the same precedence: SessionStart
   appends the tier-0 pin record to `~/.thalamus/pins/pins.jsonl` and announces
   the pin in the primed context; PostToolUse stamps the pin into every tap line;
   SessionEnd resolves the distillation scope **ledger-first, env fallback** and
   passes `--scope` to extraction, so the session's episodic memory lands in the
   pinned expert's subgraph. Ledger-first keeps re-extraction from any later,
   differently-pinned shell landing in the wrong scope and forking the Session
   vertex identity (vids include scope). After extraction the same detached run
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

## Agent Teams as an instrument (experimental track)

Claude Code's experimental Agent Teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)
make each teammate its own process — own session id, own MCP server instances, own
hooks. Under "the process is the pin" that means **each teammate is a pinnable
unit**, and a team is a roster of concurrently-pinned experts with a shared task
list and a mailbox. That makes teams less a product feature than a *measurement
instrument* for exactly the questions this project exists to answer. The generated
`.claude/agents/thalamus-<scope>.md` files double as teammate blueprints — the
zero-glue test extends to teams.

Two channels matter and they are not equal: consultation (ticketed, cited,
recorded — the collaboration graph sees it) and the **teams mailbox** (JSON files
the harness delivers between teammates — unprovenanced, invisible to the graph,
and distilled into the receiver's transcript as tier-1). The mailbox is the
agent-authored variant of the transcript-mediated-laundering gap
([05-trust-model.md](05-trust-model.md)).

Experiments, ranked by information-per-effort (each run produces a lab entry):

| # | Experiment | Hypothesis | Status (lab/004, 2026-07-16) |
|---|---|---|---|
| T0 | Per-teammate env inheritance | Teammates inherit the lead's env — one team, one pin, unless launched otherwise | **Confirmed** (n=1): teammate ran pinned `literature`, own session/ledger row/tap lines. Distinct per-teammate pins need per-teammate launch control |
| T5 | Mailbox traffic vs collaboration graph | Most inter-teammate coordination bypasses the consultation protocol | **Confirmed a fortiori**: no `inboxes/*.json` materialized at all (`in-process` delivery), zero Exchange/CONSULTS — the only durable record is the transcripts |
| T2 | Per-teammate distillation | N teammates → N SessionEnd distillations → per-expert episodic memory at process level | **Confirmed** (free ride on the T0 run): teammate distilled into its pinned scope, own SessionEnd |
| T1 | Pin-quality A/B | Same task, literature-pinned vs main-pinned teammate: pinned retrievals show a higher used-ratio in-domain | Unblocked in design (env per teammate, or pinned windows joined as a team); parked pending the lead-cwd anomaly |
| T4 | Mailbox canary (M5) | A canary claim in teammate A's scope, relayed inter-teammate, lands tier-1 in teammate B's scope | Rescoped by T5: there may be no mailbox file to plant into — the channel to red-team is transcript distillation itself |
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
