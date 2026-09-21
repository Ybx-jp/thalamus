# Concepts

What the pieces are and why they are shaped that way. Read this once and the CLI
stops looking like a pile of verbs.

## The shape of the thing

```
                       ┌──────────────────────────────┐
                       │      MAIN SCOPE              │
                       │  dense, connective: working  │
                       │  memory, audit, provenance   │
                       │  chains, contradictions      │
                       └──────────▲───────────────────┘
                                  │ references by ID (never copies)
        ┌─────────────────────────┼─────────────────────────┐
┌───────┴────────┐       ┌────────┴───────┐        ┌────────┴───────┐
│ EXPERT: domain │       │ EXPERT: domain │        │ EXPERT: domain │
│ subgraph +     │  ...  │ subgraph +     │  ...   │ subgraph +     │
│ episodic memory│       │ episodic memory│        │ episodic memory│
└───────▲────────┘       └────────▲───────┘        └────────▲───────┘
        │      FEDERATION CONTRACT (schema + permissions +  │
        │      trust boundary — every edge above crosses it)│
        └───────────────┬─────────────────┬─────────────────┘
                 ┌──────┴──────┐   ┌──────┴───────┐
                 │  INGESTION  │   │   HARNESS    │
                 │  (curated   │   │ (MCP, hooks, │
                 │   feeds)    │   │   skills)    │
                 └─────────────┘   └──────────────┘
```

## Scope

A **scope** is which expert a piece of memory belongs to. Every node carries one except
`Artifact` and `Agent`, which are global on
purpose.<!-- (A0049-artifact-and-agent-are-global-not-scoped, cites-as-live) -->

`main` is the default — the connective plane where your ordinary work
lands.<!-- (A0002-main-is-default-connective-scope, cites-as-live) -->
It is dense and highly linked, and it references expert nodes by ID rather than copying
them, so there is exactly one home for any given fact.

Scope is not the same thing as **project**. Scope is *which expert*; project is *which
repo*. They are orthogonal, and a node carries
both.<!-- (A0003-scope-and-project-are-orthogonal-fields, cites-as-live) -->

## Experts

An expert is a scope with a curated domain graph plus its own episodic memory. It is
declared by one YAML manifest in `config/experts/` and nothing else — write the file and
the expert exists, with no code to register and no glue to
update.<!-- (A0004-manifest-is-the-whole-of-expert-registration, cites-as-live) -->

```yaml
scope: literature
role: Technical literature expert
domain: |
  What this scope is for, in prose. This text becomes the pinned session's
  system prompt, so write it for the agent that will be living inside it.
```

A manifest can also declare:

- **`write_boundary`** — where a scope is defined by what it must *not* produce. A
  PreToolUse hook enforces it against the file-editing tools, so the boundary is
  structural rather than a paragraph the model is asked to respect. The shipped `qe`
  manifest is the worked example: it holds the adversarial suite and is denied `src/`,
  because a scope that can repair the implementation it asserts against is not
  independent of it. `deny_globs` match absolute POSIX paths; optional `allow_globs` are
  evaluated first and provide narrow exceptions for artifact trees whose file extensions
  would otherwise trip a broad language
  deny.<!-- (A0005-write-boundary-globs-match-absolute-paths, cites-as-live) -->
- **`capability_boundary`** — which skills and tools the scope may
  reach.<!-- (A0006-capability-boundary-scopes-tools-and-skills, cites-as-live) -->
- **MCP servers** of its own, in `config/mcp/<scope>.json`, giving a scope tools no
  other scope has.<!-- (A0007-mcp-servers-are-per-scope, cites-as-live) -->
  `designer` is the worked example.

A boundary can also run the other way. `contract/ownership.PATH_OWNERSHIP` reserves a
tree *for* one scope and denies every other, `main` included — which is the half a
manifest cannot express, since `main` has no manifest to declare it in. `tests/qe/` is
the one row: qe cannot repair what it indicts, and nobody else can soften what it
asserts.<!-- (A0008-path-ownership-reserves-trees-from-every-scope, cites-as-live) -->

The two halves are not symmetric in one respect worth knowing. The deny survives a
manifest's removal and the grant does not, so deleting a manifest whose scope owns a
tree leaves that tree unwritable by everyone rather than reserved for
someone.<!-- (A0009-ownership-deny-outlives-manifest-removal, cites-as-live) -->
A test asserts every owning scope still ships a manifest.

Five manifests ship as examples: `architect`, `designer`, `eval-methodology`,
`literature` and `qe`. Point `THALAMUS_CONFIG_DIR` at a directory holding your own
`experts/` to use a different roster; the same variable supplies the eval task battery
from `tasks/`.<!-- (A0010-config-dir-env-var-swaps-the-roster, cites-as-live) -->

## Pinning

Routing between experts is not solved with a classifier. It is solved by **pinning**:
one OS process is one immutable
scope.<!-- (A0011-pinning-binds-one-process-to-one-scope, cites-as-live) -->

`thalamus pin <scope>` launches an agent session whose environment names the
scope.<!-- (A0012-pin-command-launches-scoped-session, cites-as-live) -->
The MCP server reads that at startup, and **no tool accepts a scope argument** — the
server decides what the session can see, and a model cannot widen its own view by
asking.<!-- (A0001-pinned-scope-is-resolved-once-at-process-start, cites-as-live) -->
The pin lasts as long as the process.

`thalamus roster` brings up the `main` anchor and experts are spawned on demand (`--all`
opens one window per expert), so the roster is a set of addressable
processes.<!-- (A0014-roster-command-spawns-on-demand, cites-as-live) -->
That is also what makes the console possible: a browser tab per window. The roster runs
on a tmux server of its own — `tmux -L thalamus`, named by `THALAMUS_TMUX_SOCKET` —
because tmux ignores `HOME` and a socket is the only thing that separates one checkout's
control plane from
another's.<!-- (A0015-roster-runs-on-its-own-tmux-socket, cites-as-live) -->

A pin is not one property, and the harnesses do not carry all of it. Routing and the
boundary bind on all
three.<!-- (A0016-pin-is-checked-per-component-not-as-one-property, cites-as-live) -->
The **charter** — the scope's own text in the session's context — and its **per-scope
MCP arming** ride a generated artifact, and only two harnesses have somewhere to put it:
Claude Code reads `--agent thalamus-<scope>`, an agent file under
`.claude/agents/`;<!-- (A0017-claude-code-carries-the-charter-via-agent-file, cites-as-live) -->
codex reads `--profile thalamus-<scope>`, a `$CODEX_HOME/thalamus-<scope>.config.toml`
whose `developer_instructions` is the same text and whose `[mcp_servers.*]` tables are
the same servers.<!-- (A0018-codex-carries-the-charter-via-profile-file, cites-as-live) -->
Cursor has neither, so a pinned Cursor session routes and is bounded and does not think
like the expert. `contract/pinning.py` records this per component with its evidence, so
"pinned" cannot quietly mean more on one harness than
another.<!-- (A0019-pinning-py-records-evidence-per-component, cites-as-live) -->

Two things about the codex carrier are worth knowing before relying on it. `--profile`
selects the charter but tells the hooks nothing, so the scope still reaches them through
the argv's `env` prefix — the two are separate carriers that happen to travel
together.<!-- (A0020-codex-profile-and-hooks-are-separate-carriers, cites-as-live) -->
And a `--profile` naming a file that does not exist starts an ordinary session with no
charter, no arming and no error, which is why the profile is written on every launch
rather than assumed to be
there.<!-- (A0021-codex-profile-written-every-launch, cites-as-live) -->

## The federation contract

One artifact doing three jobs at once:

- **A data schema.** Ten node types, of which five are episodic — `Session`, `Claim`,
  `Thread`, `Source`, `Artifact`, beside `Entity`, `Chunk`, `Exchange`, `Trace` and
  `Agent` — joined by seventeen edge types including `CONTAINS` / `TOUCHES` / `SPAWNS` /
  `BLOCKS` / `CONTINUES` / `RESOLVES` / `SOLVED_BY` / `DERIVED_FROM` /
  `USES`.<!-- (A0022-ten-node-types-five-episodic, cites-as-live) -->
  An expert manifest declares the *claim kinds* its scope may write, not new node
  types.<!-- (A0023-manifest-declares-claim-kinds-not-node-types, cites-as-live) -->
  Declared once in `contract/ontology.py`.
- **A permission system.** What a scope may write, and where.
- **A trust boundary.** Every edge crossing between scopes crosses
  it.<!-- (A0024-trust-boundary-is-every-cross-scope-edge, cites-as-live) -->

It is enforced at write time, not filtered at read time. Orphans and violations are
rejected when they are written, by the gate every session write goes through
(`conformance.write_session_checked`).<!-- (A0025-contract-enforced-at-write-time, cites-as-live) -->
`thalamus contract check` audits the live graph against
it,<!-- (A0026-contract-check-audits-the-live-graph, cites-as-live) -->
and `thalamus validate` checks a pending extraction before it
lands.<!-- (A0027-validate-checks-a-pending-extraction, cites-as-live) -->

The audit runs in **four directions**. Three of them close the loop declared → written →
read. Checking written nodes against the ontology catches a bad
write.<!-- (A0028-audit-direction-vertices-against-ontology, cites-as-live) -->
Checking the ontology against what writers produce catches a declaration with nothing
behind it — a node type, kind, edge type or edge property that consumers may plan
against and no code
writes.<!-- (A0029-audit-direction-ontology-against-writers, cites-as-live) -->
Checking what writers produce against what readers project catches the opposite gap: a
field written onto every vertex of its label that no read path ever names, so the value
is persisted and no caller can obtain
it.<!-- (A0030-audit-direction-writers-against-readers, cites-as-live) -->

A fourth check stands outside that triangle and needs no second party: a `Claim`'s
vertex id contains a hash of its own `(kind, description)`, so the id is a claim about
the content, and re-hashing the content asks whether the address still
agrees.<!-- (A0031-claim-vertex-id-hashes-kind-and-description, cites-as-live) -->
It goes stale when an identity formula changes under vertices already written, or when
an identity-bearing property is rewritten in place. The disagreement matters because the
vertex left behind by a re-key keeps the edges it acquired afterwards but not the
`CONTAINS` that moved to its twin — so it is retrievable, and a provenance walk from it
dead-ends with no session.

Findings in the second, third and fourth directions are **advisories**: they are printed
and never fail the check, because absence in one graph — or in one scan — is not proof,
and a rule that can fail forever on history nobody can fix is a rule that gets switched
off.<!-- (A0032-advisory-findings-never-fail-the-check, cites-as-live) -->

### Four load-bearing properties

**Claims are one label, discriminated by `kind`.** Decisions, problems and solutions are
claim *subtypes*, not sibling
labels.<!-- (A0033-claim-is-one-label-with-subtypes, cites-as-live) -->
A decision is an assertion with a rationale from the agent; a literature claim is an
assertion with a citation from a source — same node type, different provenance.
Consumers query `Claim`, so a new expert adding `kind: literature/finding` breaks
nobody. Claim identity is **(kind, normalized description)**, so the same claim reached
in two sessions converges on one
node.<!-- (A0034-claim-identity-converges-on-kind-and-normalized-description, cites-as-live) -->

**Every node carries provenance** — trust tier, source, ingestion
time.<!-- (A0035-every-node-carries-provenance, cites-as-live) -->

**`Source` is retained primary evidence** — a transcript, or an ingested paper. Same
node type, different
tier.<!-- (A0036-source-is-retained-primary-evidence, cites-as-live) -->
It is the floor of the provenance chain: `DERIVED_FROM` lands a belief on the evidence
it came from, `TOUCHES` carries the `anchors` that name the exact messages, and
`ANCHORS` puts a literature claim on the passage it
quotes.<!-- (A0037-derived-from-touches-anchors-carry-the-provenance-chain, cites-as-live) -->

**A claim records what it reasoned with.** A decision or solution that used something
recalled as grounds carries a `USES` edge to it, with `role` saying how (`reason`, or
`rejected` for an alternative the decision turned
down).<!-- (A0038-uses-edge-records-what-a-claim-reasoned-with, cites-as-live) -->

**Attribution is scope-closed.** The edge reaches the claim's own scope, or session-less
knowledge in any scope — the reader serves those everywhere, so the scope segment on a
literature claim says which expert ingested it, not who may read it. It does not reach
another scope's episodic memory, even though a consultation ticket serves exactly that
into the asking session. The subgraph these edges form is meant to compound one scope's
experience and the knowledge it applied into a concept a later task can reuse; one
spanning two scopes' experience is a wider thing, and not the thing being built. The
write path drops such a target and `contract check` gates the graph on
it.<!-- (A0039-attribution-edges-are-scope-closed, cites-as-live) -->

Distillation writes the edge from the extractor's references, which it names by
8-character handles taken from the served-memory list in the prompt — the digest clips a
tool result at 400
characters,<!-- (A0041-tool-result-digest-clips-at-400-characters, cites-as-live) -->
so a vertex ID rendered inside a recall bundle is usually cut off, and a handle short
enough to survive that is also short enough to copy without
transcribing.<!-- (A0040-distillation-names-references-by-short-handles, cites-as-live) -->
A handle naming nothing the session was served is dropped rather than
written.<!-- (A0042-unresolvable-handle-is-dropped-not-written, cites-as-live) -->

`thalamus eval sync` then stamps `verified` from the session's own traces — true when a
retrieval actually served that target into a session containing the claim, false when
sync looked and none did, absent when sync has not looked. Served is not used: the used
verdict stays on the trace's `RETURNS`
edge.<!-- (A0043-eval-sync-stamps-verified-served-not-used, cites-as-live) -->
Nothing gates the write on the stamp — whether a reference was *served* is provenance,
which the write path cannot see, and an unverifiable reference is itself evidence rather
than grounds to drop one — so `contract check` reports a cross-scope `USES` stamped
false as an advisory
instead.<!-- (A0044-contract-check-reports-false-stamp-as-advisory, cites-as-live) -->
Recall renders each reference as one line under the claim, without a backticked ID, so
the citation is never priced as a node the retrieval
returned.<!-- (A0045-recall-renders-reference-without-backticked-id, cites-as-live) -->

The same edge carries what a decision turned down. An alternative the session considered
and refused is written as a claim of kind `<scope>/rejected`, reached from the decision
by `USES {role: rejected, reason}`, so the reason an option lost is a node that can cite
its own references rather than a sentence inside the
rationale.<!-- (A0046-rejected-alternative-is-its-own-claim-node, cites-as-live) -->
A solution says how it ended: `worked` is a finding rather than a default, and
`outcome_kind` (`unresolved`, `reversed`, `rejected`, `residual`) tells a fix that did
not hold from one that was undone or
refused.<!-- (A0047-solution-outcome-is-a-finding-not-a-default, cites-as-live) -->
Both carry `anchors`, the message UUIDs that show the outcome, resolved from the handles
the digest
exposes.<!-- (A0048-outcome-anchors-resolve-from-digest-handles, cites-as-live) -->

**Every node carries a scope, except `Artifact` and `Agent`.** Both are deliberately
**global** — one vertex per identifier, shared by every
scope.<!-- (A0049-artifact-and-agent-are-global-not-scoped, cites-as-live) -->
A file touched by two experts is one node, which makes it the join key between
them.<!-- (A0050-shared-artifact-is-the-join-key-between-experts, cites-as-live) -->

## Trust tiers

Trust is not a label a writer chooses. It is the **floor** over a node's whole
derivation chain, computed across `DERIVED_FROM`
edges.<!-- (A0051-trust-is-the-floor-over-derivation-chain, cites-as-live) -->

The consequence that matters: a claim distilled from a session that read a fetched web
page cannot come out trusted like a claim you reasoned to yourself. The transcript
ingress floor down-tiers
it.<!-- (A0052-transcript-ingress-floor-down-tiers-fetched-content, cites-as-live) -->
**Distillation does not launder.**

The floor reaches every extracted node that carries a tier — claims, threads and
artifacts alike — so a thread opened out of a fetched page, or a dependency the page
named, keeps third-party trust
too.<!-- (A0053-ingress-floor-reaches-every-tiered-node-type, cites-as-live) -->

When retrieval returns knowledge from an expert scope, it comes back blockquoted, with
its citation and its tier attached. **Tier-2 content informs; it never
instructs**.<!-- (A0054-tier-2-recall-informs-never-instructs, cites-as-live) -->
That is a property of how it is presented, not a request to the model.

## Distillation — how memory gets written

**A session does not write its own memory.**

The only episodic write available inside a live session is the consultation exchange,
which records a crossing between scopes rather than a session's
beliefs.<!-- (A0055-consultation-exchange-is-the-only-live-write, cites-as-live) -->
Everything else is written afterwards:

```
Session ends → SessionEnd hook → thalamus extract → graph → eval sync
                                                               ↓
New session → session-start hook → memory_open_threads → context
```

The reason is convergence. Claims are content-addressed on `(kind, normalized
description)`. If a session wrote its beliefs live *and* was distilled at the end, you
would get two phrasings of the same decision, which would not converge into one node,
and duplicate threads would surface in `memory_open_threads` — the first thing the
next session reads.

Distilling before a session ends is supported; it is just run from outside the
session, by you.

## Threads

A **thread** is an open continuation point — unfinished work, a next step, an open
question. `memory_open_threads` is the entrypoint to the whole retrieval surface: it is
what a new session asks for
first.<!-- (A0056-open-threads-is-the-retrieval-entrypoint, cites-as-live) -->

Threads are minted only by distillation from a session that actually happened. That is
what makes an open thread evidence rather than an assertion — an agent that could file
one directly would be writing its own intentions into your queue. An agent's reach is
`thalamus thread propose`; you
approve.<!-- (A0057-threads-are-minted-only-by-distillation, cites-as-live) -->

## Consultation

When a session pinned to one scope needs another scope's knowledge, it does not silently
read across the boundary. It mints a **consultation ticket**, and minting the ticket
*is* writing the exchange record — the crossing is recorded before the answer
exists.<!-- (A0094-minting-the-ticket-is-the-write, cites-as-live) -->

The answer must cite nodes inside the consulted scope, and citations are validated
before the ticket closes. Tickets are
single-use.<!-- (A0059-consultation-answer-must-cite-inside-consulted-scope, cites-as-live) -->

A scope may also consult **itself**. That ticket grants no reach the session did not
already have and its answer corroborates nothing; what it buys is an independent pass —
a fresh context, a brief built against the question, a cited close, and a recorded
exchange.<!-- (A0060-self-consultation-grants-no-extra-reach, cites-as-live) -->
It is not a way of retrieving less: the close is refused unless the server served a
recall under the
ticket,<!-- (A0061-self-consultation-close-requires-a-served-recall, cites-as-live) -->
and the grant keeps the knowledge commons so a ticketed read is never poorer than an
ambient one.<!-- (A0062-consultation-grant-keeps-the-knowledge-commons, cites-as-live) -->

`thalamus quick ask <scope> "<question>"` is the second tier: rather than cold-starting
an expert, it forks that expert's live session, so the answer comes from a process that
is already warm.<!-- (A0063-quick-ask-forks-the-experts-live-session, cites-as-live) -->
A fork distills its own delta, never the parent's
transcript.<!-- (A0064-fork-distills-only-its-own-delta, cites-as-live) -->

## Rooms

A **room** is a private roster. Members see and message each other and nobody else,
enforced by a per-room config directory and an outbound guard rather than by
convention. Sessions are launched into a room with `--room`.

## Ingestion

Deliberately the smallest component in the system. `thalamus ingest <url> --scope
<expert>` feeds one document into one expert's subgraph: allowlist-gated,
evidence-first, and nothing reaches the graph without `--write`. The document is
co-indexed as `Chunk` vertices beside the claims drawn from it, so a claim can be traced
back to the passage it came from.

`--feed` names what the document was procured for, and the name lands on the `Source`
— the ingestion event — rather than on the claims, which converge across feeds. A
document procured for two projects keeps both names: the feed accumulates on
re-ingest instead of replacing what was there, so "what was this brought in for" has
every answer rather than the most recent one.

The model pass is the only irreversible spend on the path, so everything that can be
known before it is. `--check` runs the path and stops at the model
call,<!-- (A0089-check-stops-before-the-model-call, cites-as-live) -->
which is how a source is verified without paying for it; the allowlist gate sits ahead
of both the archive and the model; and the contract refuses a batch one claim at a time,
so a single mistyped claim costs itself rather than the extraction it arrived in.

Leaving `--write` off is not the same thing as `--check`. The bytes are retained on
every pass, and a run without `--check` calls the model whether or not it goes on to
write — so a bare run used as a check bills the model twice for one
source.<!-- (A0138-ingest-always-spends-a-model-pass, cites-as-live) -->

Feeding a document *is* the curation decision. There is no crawler racing ahead of
demand.

## The eval loop

The part that asks whether any of this is actually helping.

**Layer 1 — what retrieval did.** Every memory-tool call is trace-tapped and landed as
a `Trace` node. Each retrieved node is judged used-vs-ignored against the session's
retained transcript, and priced in injected tokens. Decay candidates rank by wasted
tokens.

**Layer 2 — whether it mattered.** A counterfactual harness runs one task from a
battery under arms — memory-on, memory-off, scoping-degraded — each in a confined
worktree with its own `HOME` and its own store, so an arm cannot read state it was not
given. A graded oracle scores the result against pre-registered rungs, and the oracle's
rungs are themselves validated against a mutant set before any arm is scored.

What is measured today is that memory gets *surfaced*. Whether it changes task
outcomes is the open question, and the harness exists to answer it rather than to
assume it.

## The harness

Where all of this meets your editor.

- **The MCP server** — the retrieval surface. Scope comes from the environment.
- **Hooks** — session start (memory priming, pin ledger), session end (distillation),
  PreToolUse guards (the role boundary, the Gremlin guard, the room boundary, and the
  graph boundary — outside `main` the graph is reached through the MCP tools, which
  confine a read to the caller's scope, rather than through a connection that reaches
  the whole graph),<!-- (A0148-graph-connection-carries-no-scope-filter, cites-as-live) -->
  and PostToolUse taps and injections (the retrieval trace tap, conditioning reminders,
  and the memory reflex, which recalls against a failed Bash result unasked).
- **Skills** — procedures the agent loads when a task calls for them.

**Claude Code**, **Cursor** and **codex** are supported. Their hook contracts differ,
so each has its own suite under `src/thalamus/harness/hooks/`, over one set of
detection logic and one set of on-disk records — Cursor's scripts are adapters that
reshape its payloads into the Claude Code shape, while codex's are delegators, because
its payloads already *are* that shape: the same hook config schema, the same stdin
keys, the same regex matchers, the same exit-2-and-stderr blocking channel. Two codex
scripts do more than delegate, and they mark the two places the harnesses genuinely
differ: a shell result arrives as one string where Claude Code sends `{stdout,
stderr}`, and the editing tool is `apply_patch`, whose argument is a patch envelope
naming several files rather than one `file_path`.

The three do not have equal fidelity, and the system says which is which rather than
flattening them.

Cursor is the reduced one. It gives prompt text to an event that cannot inject and
injection to events that never see the prompt, so the injection tiers compute into a
per-session spool and deliver one tool call late. Cursor transcripts also exclude tool
outputs entirely, so those sessions are floored whole by the ingress defence rather
than checked against evidence that does not exist, and a Cursor session distills on a
later sweep because its transcript is not flushed when the hook fires.

Codex is close to Claude Code and differs in four places worth knowing. Its rollout is
filed under the day it ran rather than under its project, so a codex session is
addressed by session id. Its tool calls arrive as *code mode* — a call is a JavaScript
program calling `tools.exec_command(...)` or `tools.apply_patch(...)` — so the files a
session touched are read from the structured `patch_apply_end` event beside the call
rather than from the program, which the deterministic layer would have to guess at. Its
`SessionStart` hook fires at the first submitted turn rather than at launch, so a codex
window opened and never used leaves no pin-ledger row. And it publishes no session
descriptor at all, which is what the next paragraph is about.

Claude Code writes `$CLAUDE_CONFIG_DIR/sessions/<pid>.json` — identity, liveness and a
`status` its runtime keeps from inside its own event loop — and the console reads a
row's whole liveness half out of it. Codex writes nothing of the kind, and its hook
table has no turn-*end* event to build one from: `SessionStart`, `SessionEnd`,
`UserPromptSubmit`, `PreToolUse` and `PostToolUse` can each say a turn began and none
can say it finished. What answers instead is the rollout, which carries `task_started`
and `task_complete` rows codex writes itself, one pair per turn — so a codex row reads
`busy` while the last boundary is a start and `idle` once a completion lands, and reads
as unobserved whenever neither is in reach. It does **not** carry the `waiting` half:
nothing in that record says an approval prompt is up, so `blocked` on a codex row means
*not known* rather than *not blocked*. The gap is bounded by the record's own shape — a
prompt can only be held mid-turn, and mid-turn is exactly when the row says `busy` — so
a codex session stuck at one understates as long-running and never renders as resting.

A codex session claims its tmux pane, which is what lets the console join a window to a
session at all, and the claim is gated: only an interactive TUI may make one. Nothing in
codex's hook payload separates a TUI turn from a headless `codex exec` run, but the
rollout's first record does — `originator` and `source` together, `codex-tui`/`"cli"`
against `codex_exec`/`"exec"`, with a subagent run distinguished by a `source` that is
an
object rather than a string. Both fields are read, because a subagent inherits its
parent's originator and is precisely the nested case the gate exists for: a headless run
shelled out of a roster window inherits that window's `TMUX_PANE`, and an unconditional
claim would hand the operator's read view to a probe.

Codex also gates its hooks behind a trust record the operator grants once, per
configured entry, in the TUI. Until it is granted the suite is installed and inert —
a headless run finishes, exits 0 and distills nothing — so `thalamus init` reports the
trust state as its own finding rather than folding it into "the hooks are wired".
Granting it is not something the installer does on the operator's behalf: it is a
supply-chain control, and satisfying it from inside the thing being trusted would
answer the question it exists to ask.

Where a harness lacks something, that is recorded as a state and not as a silence:
`contract/boundaries.py` distinguishes a capability the harness provides natively, one
with no referent to enforce, and one nobody has asked about yet.
