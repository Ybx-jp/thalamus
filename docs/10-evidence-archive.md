# The Evidence Archive — Retained Transcripts as the Floor of the Provenance Chain

**Status:** 📦 shipped. Both stages run over the full corpus; the graph is derived
from retained transcripts, chronologically, so threads resolve forward in time.

## The problem it solves

Without retained transcripts, a tier-1 `Claim` carries `source: session:<id>` —
and that pointer lands on a `Session` node whose stored content is a **summary**:
a distillation of the very thing being inspected. [03](03-master-plane.md)'s
headline demo — *pick any belief my agent holds and walk, hop by hop, to where it
came from* — would terminate in another summary rather than in evidence. Trust
tiers, the audit story, and the poisoning post-mortem would all rest on a pointer
into fog.

Retaining the transcript puts a floor under the provenance chain.

## Three things the archive is load-bearing for

**1. Audit ([03](03-master-plane.md), [05](05-trust-model.md)).** The chain
terminates in primary evidence: `Claim → Session → Source → the exact messages`. A
poisoning post-mortem is a graph traversal ending at the bytes, which is the whole
structural-safety claim.

**2. Reversibility ([04](04-eval-loop.md)).** [04](04-eval-loop.md) insists
forgetting be *"archival, never deletion — reversible and auditable"* — and
extraction must meet the same bar, or it is the lossy, irreversible step in the
pipeline. With the transcript retained, the graph is a **materialized view over an
immutable log**: if the view is wrong — a bad skill, a better model, a changed
schema — rebuild it from evidence. This makes the graph **disposable**, which is a
superpower: a schema change means *re-extract everything*, not *migrate*.

**3. The eval loop cannot exist without it ([04](04-eval-loop.md) layer 1).**
Used-vs-ignored is defined as *"lexical/structural matching between retrieved
content and **the session's outputs**"*. The session's outputs **are the
transcript**. You cannot compute whether a retrieved memory changed the agent's
behaviour without the record of that behaviour.

## `Source` is one node type, tier is the only difference

A session transcript is a **tier-1 Source**. A paper is a **tier-2 Source**. Same
node, same content-hash identity, same `DERIVED_FROM` edges, same provenance
envelope — they differ only in tier and locator. The ingestion path and the
bootstrap path are the same machinery with the tier turned up.

## Anchors on the edge, not `Chunk` nodes

Claude Code stamps every message with a stable `uuid`. So the locator rides on the edge:

```
Claim  ──DERIVED_FROM { anchors: [uuid, uuid] }──▶  Source
Session ──TOUCHES     { anchors: [uuid, uuid] }──▶  Artifact
```

This answers *where in the transcript* without a ~100× node explosion. `Chunk` nodes
only earn their keep once something needs per-chunk retrieval or embeddings, and
nothing does — [00](00-mission.md)'s non-goals are explicit that Thalamus is
graph-first, not a vector-soup RAG framework.

The payoff needs no model: *"which messages edited this file?"* is a two-hop
traversal ending on the exact tool calls.

## Two stages, and only one needs a model

| | Stage 1 — deterministic | Stage 2 — extracted |
|---|---|---|
| **Produces** | `Source`, `Session`, `Artifact`, anchored `TOUCHES` | `Claim`, `Thread` |
| **How** | tool-call records, `ai-title`, `cwd`, `gitBranch` | the extraction skill |
| **Cost** | free, exact, seconds for the whole corpus | model time (~$0.50/session via headless `claude -p`) |
| **Command** | `thalamus bootstrap` | `thalamus extract` |

Stage 1 is **not a stopgap, and an LLM would be strictly worse at it.** Which files a
session edited, in which messages, on which branch, is *recorded*. Inference could only
add error. What genuinely needs judgement — decisions, problems, solutions, threads — is
left to a model, and left honestly empty until one runs.

Stage 1 also stands alone legally: a claim-free session would have left every artifact an
orphan and been rejected by the contract, which is why `Session -[TOUCHES]-> Artifact`
exists. The deterministic layer is a first-class subgraph, not a placeholder.

Extraction replays chronologically with the graph's currently-open threads (and
recent known claims) fed into each session's prompt, so later sessions resolve and
continue threads instead of duplicating them, and claims converge on wording the
model can see.

**Models reference memory that was never formed.** Extraction can emit a
`thread_ref` to a thread id that never existed; the writer drops such refs with a
warning (mergeE cannot edge to a missing vertex). Hallucinated memory references
are real — plan every cross-boundary interface around them.

## Snapshots and supersession

A session distilled while still open archives its transcript as it stands; a grown
file hashes to a new blob, so a session can have several Sources. The writer links
each new snapshot to the previous head with `SUPERSEDES`, consumers read the chain
head, and superseded snapshots remain archived and walkable — splitting is made
legible, not prevented, because preventing it would mean mutating archived evidence.

## Where the bytes live, and why not in the repo

`~/.thalamus/archive/`, content-addressed by sha256, sharded, write-then-rename, read
verified against the hash.

- **Thalamus owns the bytes.** Claude Code rotates and compacts its own transcripts;
  `~/.claude/projects/` is not durable storage, and evidence that can vanish is not
  evidence.
- **Outside the repository, not merely gitignored.** Thalamus is going public, and a
  `.gitignore` is one `git add -f` from a bad day.

## The risk, stated plainly

**Transcripts are the highest-risk artifact in this project.** They contain whatever was
on screen — credentials included. Bootstrap scans have flagged real secrets inside this
repo's own transcripts, including a key that had already been purged from git history:
the bytes were gone from the repo and still sitting in the record of the session that
removed them.

So `thalamus bootstrap` scans and **reports**; it does not redact. Evidence that has been
quietly rewritten is not evidence, and a redactor that silently mangles a transcript
destroys the thing the archive exists to preserve. The operator is told, and the operator
decides. Ingestion is allowlisted per project for the same reason: sessions about the
media server carry VPN credentials, and sessions about the résumé carry personal history.

## Open questions

- **Do `Thread`s survive a re-extraction?** Threads have operator-facing stable slugs and a
  lifecycle; claims are content-addressed and disposable. Re-extraction must not resurrect
  a thread the operator resolved. Unresolved.
- **Live sessions snapshot per run.** A still-growing transcript hashes to a new Source
  each time bootstrap touches it — content-addressing working as designed, but bootstrap
  should perhaps skip or flag the currently-active session.
- **Retention policy.** Content addressing makes dedup free, but nothing prunes.
  Probably fine for years; worth a number before it isn't.
- **Claim convergence rate.** The (kind, normalized description) identity is live;
  whether the cross-session convergence rate is meaningful awaits the next full
  extraction batch. Semantic matching stays parked.
