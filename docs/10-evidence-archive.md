# The Evidence Archive — Retained Transcripts as the Floor of the Provenance Chain

**Status:** 🏗️ implementing. Stage 1 (deterministic bootstrap) is built; stage 2
(model-extracted claims) is not.

## The problem it solves, which was hiding in plain sight

Before this, a tier-1 `Claim` carried `source: session:<id>`. Follow that pointer and you
arrive at a `Session` node whose stored content is… a **summary**. A distillation of the
very thing you were trying to inspect.

So [03](03-master-plane.md)'s headline demo — *pick any belief my agent holds and walk,
hop by hop, to where it came from* — terminated in another summary rather than in
evidence. **The provenance chain had no floor.** Everything above it (trust tiers, the
audit story, the poisoning post-mortem) rested on a pointer into fog.

Retaining the transcript is what puts a floor under it.

## Three things the archive is load-bearing for

**1. Audit ([03](03-master-plane.md), [05](05-trust-model.md)).** The chain now terminates
in primary evidence: `Claim → Session → Source → the exact messages`. A poisoning
post-mortem becomes a graph traversal ending at the bytes, which is the whole
structural-safety claim.

**2. Reversibility ([04](04-eval-loop.md)).** [04](04-eval-loop.md) insists forgetting be
*"archival, never deletion — reversible and auditable."* But **extraction** was the lossy,
irreversible, unauditable step, and nobody had noticed. With the transcript retained, the
graph becomes a **materialized view over an immutable log**: if the view is wrong — a bad
skill, a better model, a changed schema — you rebuild it from evidence.

This is stronger than a safety net. It makes the graph **disposable**, which is a
superpower. The M0.5 schema change is the proof: had a corpus existed, the right move
would have been *re-extract everything*, not *migrate*.

**3. The eval loop cannot exist without it ([04](04-eval-loop.md) layer 1).**
[04](04-eval-loop.md) defines used-vs-ignored as *"lexical/structural matching between
retrieved content and **the session's outputs**"*. The session's outputs **are the
transcript**. You cannot compute whether a retrieved memory changed the agent's behaviour
without the record of that behaviour. The archive is a hard prerequisite for M2 — the
project's differentiating artifact — not a quality nicety.

## `Source` is one node type, tier is the only difference

A session transcript is a **tier-1 Source**. A paper will be a **tier-2 Source**. Same
node, same content-hash identity, same `DERIVED_FROM` edges, same provenance envelope —
they differ only in tier and locator.

That is not a tidy coincidence; it is the sequencing win. **Bootstrapping transcripts is a
zero-risk rehearsal of the M1 ingestion path.** Identical machinery, exercised on tier-1
data where a bug cannot poison anything. When the literature feed lands, it is the same
code with the tier turned up.

## Anchors on the edge, not `Chunk` nodes

Claude Code stamps every message with a stable `uuid`. So the locator rides on the edge:

```
Claim  ──DERIVED_FROM { anchors: [uuid, uuid] }──▶  Source
Session ──TOUCHES     { anchors: [uuid, uuid] }──▶  Artifact
```

This answers *where in the transcript* without a ~100× node explosion. `Chunk` nodes only
earn their keep once something needs per-chunk retrieval or embeddings, and nothing does
yet — [00](00-mission.md)'s non-goals are explicit that Thalamus is graph-first, not a
vector-soup RAG framework.

The payoff is immediate and needs no model: *"which messages edited this file?"* is a
two-hop traversal ending on the exact tool calls.

## Two stages, and only one needs a model

| | Stage 1 — deterministic | Stage 2 — extracted |
|---|---|---|
| **Produces** | `Source`, `Session`, `Artifact`, anchored `TOUCHES` | `Claim`, `Thread` |
| **How** | tool-call records, `ai-title`, `cwd`, `gitBranch` | the extraction skill |
| **Cost** | free, exact, ~5s for 62 sessions | model time |
| **Status** | ✅ built (`thalamus bootstrap`) | ⬜ M2 |

Stage 1 is **not a stopgap, and an LLM would be strictly worse at it.** Which files a
session edited, in which messages, on which branch, is *recorded*. Inference could only
add error. What genuinely needs judgement — decisions, problems, solutions, threads — is
left to a model, and left honestly empty until one runs.

Stage 1 also stands alone legally: a claim-free session would have left every artifact an
orphan and been rejected by the contract, which is why `Session -[TOUCHES]-> Artifact`
exists. The deterministic layer is a first-class subgraph, not a placeholder.

## Where the bytes live, and why not in the repo

`~/.thalamus/archive/`, content-addressed by sha256, sharded, write-then-rename, read
verified against the hash.

- **Thalamus owns the bytes.** Claude Code rotates and compacts its own transcripts;
  `~/.claude/projects/` is not durable storage, and evidence that can vanish is not
  evidence.
- **Outside the repository, not merely gitignored.** stepmania-chart-generator gitignores
  an in-tree `transcripts/`, which is fine for a private repo. Thalamus is going public,
  and a `.gitignore` is one `git add -f` from a bad day.

## The risk, stated plainly

**Transcripts are the highest-risk artifact in this project.** They contain whatever was
on screen — credentials included.

This is not hypothetical. The first bootstrap run flagged **13 occurrences of the
signed database licence key inside this repo's own transcript** — the very key that
was purged from git history at M0. The bytes were gone from the repo and still sitting in
the record of the session that removed them.

So `thalamus bootstrap` scans and **reports**; it does not redact. Evidence that has been
quietly rewritten is not evidence, and a redactor that silently mangles a transcript
destroys the thing the archive exists to preserve. The operator is told, and the operator
decides. Ingestion is allowlisted per project for the same reason: sessions about the
media server carry VPN credentials, and sessions about the résumé carry personal history.

## Open questions

- **Should stage 2 run over everything, or only where it pays?** The stepmania corpus
  already has an `INDEX.md` scoring sessions by *correction signals* — moments where a
  belief was caught wrong and fixed. Those are plausibly the highest-utility sessions to
  extract claims from, and the eval loop could eventually decide this rather than a human.
- **Do `Thread`s survive a re-extraction?** Threads have operator-facing stable slugs and a
  lifecycle; claims are content-addressed and disposable. Re-extraction must not resurrect
  a thread the operator resolved. Unresolved.
- **Retention policy.** 159 MB today, and it only grows. Content addressing makes dedup
  free, but nothing prunes. Probably fine for years; worth a number before it isn't.
