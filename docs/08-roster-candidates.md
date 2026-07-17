# Roster Candidates — Granularity, Kinds, and the Parked List

**Status:** design. Candidate experts and the rule that decides how finely to cut
them. This doc parks a backlog; it does not commit the roster. Roster discipline
lives in [02-expert-subgraphs.md](02-expert-subgraphs.md) ("two proves N", null
hypothesis, cattle-behind-the-contract) — this is the shortlist that discipline
gets applied to.

## The granularity rule: two kinds fall out of pinning

"Many narrow experts vs. few broad" is not a taste question; the pinning
architecture ([02-expert-subgraphs.md](02-expert-subgraphs.md)) resolves it. An
expert is a **retrieval scope**, and the scope that governs granularity is *the
dominant domain of a session* — the thing you pin. So the litmus for any candidate
is not "narrow or broad" but:

> Does this knowledge form the **spine** of whole sessions, or does it get
> **consulted across** many different sessions' spines?

That yields two kinds, and the split falls straight out of the consultation
protocol:

- **Spine experts** — coarse, one per dominant-session-domain, the thing you *pin*.
  Should be **few and broad**: they must match how sessions actually cluster, and
  breadth keeps each one's episodic narrative coherent.
- **Consultant experts** — narrow, cross-cutting, rarely pinned but frequently
  *consulted* from many spines. Should be **narrow**: their value is being a sharp,
  reusable answer source that recurs across many sessions' collaboration edges.

**The collaboration graph audits the granularity.** A narrow consultant nobody
consults → archive it (cattle). A spine expert that consults the same narrow one
every session → they are one expert; merge. Granularity is not decided up front;
it is instrumented.

### Default move: split top-down, don't merge bottom-up

Start broad (few spine experts). Let the eval loop **split** a spine expert only
when its retrievals bifurcate into two non-overlapping clusters. Splitting is the
safer default than starting narrow and merging: splitting preserves clean episodic
narratives ("this session was about X"), whereas merging two histories destroys the
per-session coherence [02](02-expert-subgraphs.md) explicitly protects. This is
also the honest position for a project whose identity is measuring hard-to-measure
quality — "if retrievals don't cluster, it isn't an expert" is a *measurement*
claim, so measurement makes the cut.

## Skill vs. expert — the boundary that keeps the roster honest

Not everything worth an agent's attention is an expert. Several operator workflows
already exist as **skills** (procedures) and must not be rebuilt as experts.

- A **skill** is a *procedure* — "do X the right way." Stateless; correct on first
  run.
- An **expert** is a *retrieval scope that learns* — "know about X and remember what
  happened the last fifty times." It earns a roster slot only if **episodic
  accumulation** adds value the procedure cannot.

**Candidate test:** would this expert be materially better after 50 sessions than
its curated knowledge subgraph alone? If no, it is a skill or an ingestion feed, not
an expert. (Applies the "materially better than its knowledge graph alone" claim
from [02](02-expert-subgraphs.md).)

## Parked candidates

Shortlist only. Each must still clear the null hypothesis ("just put it in an
existing expert") before it ships.

| Candidate | Kind | Serves | Status / note |
|---|---|---|---|
| Technical-literature | Consultant | everything | **Live** (`config/experts/literature.yaml`). GraphRAG/retrieval papers are a *feed into this*, not a separate expert. |
| Evaluation-methodology | Consultant | all projects + career | **Live** (`config/experts/eval-methodology.yaml`) — see below. Metrics design, LLM-as-judge, ablation/counterfactual design, calibration, taste-critic patterns. The through-line made a node; the eval loop dogfooded. |
| DL / training | Spine | StepMania | PyTorch, autoregressive decoding, KV-cache, CFG, sampling. Compounds via "what training run did what." |
| Agent-systems | Spine | Thalamus, Nodeglass | Harness design, MCP, tool-use, context mgmt, subagent orchestration. Spine for infra sessions. |
| Structural-safety / trust | Consultant | Nodeglass, Thalamus | Provenance, gating, poisoning, policy engines, red-teaming. Second pillar. |
| Retrieval / memory-architecture | Consultant | Thalamus | Vector vs. graph memory, chunking, reranking, RAG eval. Self-referential dogfooding; where the "graphrag expert" instinct actually belongs. |
| Rhythm-game / music-domain | Consultant | StepMania | Chart conventions, biomechanics, groove radar, onset/music-theory. The *taste* side; pairs with DL expert. |
| Homelab / self-hosting | Spine (ops) | media server + machine | Linux/systemd/Tailscale/VPN-namespace. Cheap, real episodic accumulation. |
| Career-narrative / interview | Consultant | job hunt | Experience library + STAR stories + honest-claim guardrails as knowledge; accumulates which framings landed. Complements the resume skill. |

## The second expert: evaluation-methodology (two proves N)

[02](02-expert-subgraphs.md) reserves the second roster slot for the expert that
proves the contract. It is **evaluation-methodology**, shipped as
`config/experts/eval-methodology.yaml` — the zero-glue test held: a new manifest
and *nothing else*. Two facts settled the choice:

1. **Consultants are exercised by consultation, which is live.** Eval-methodology
   is consultable the day its manifest exists, and the tap instruments it from its
   first retrieval.
2. **The spine alternative (homelab) has no corpus**: the media-server sessions
   are deliberately outside the bootstrap allowlist (VPN credentials), so a
   homelab expert would sit inert and unmeasured.

The null hypothesis ("a feed into literature") stays open on purpose: the split
stands until retrieval clustering says merge — this doc's own discipline;
measurement makes the cut.

**Prior work.** A second access-governed scope instantiates published consensus,
not new ground: explicit authority and scope on multi-agent memory reads/writes
is a named first-class concern of the agentic-web infrastructure survey (arXiv
2606.20570), and shared graph memory with provenance-linked traces is production
tooling (Neo4j, NODES AI 2026) — see [11](11-related-work.md) §3. The domain
choice *converges* on the field's own turn from retrieval-QA proxies to
downstream-utility evaluation (survey arXiv 2603.07670; Mem2ActBench arXiv
2601.19935). The expert's anchor knowledge is the judge/meta-evaluation
literature (A Survey on LLM-as-a-Judge, arXiv 2411.15594) and counterfactual
consequence-level evaluation (MQuAKE, arXiv 2305.14795), procured against
recorded demands: the eval loop's lexical-only attribution ([11](11-related-work.md)
§5) and the M4 counterfactual harness. The roster mechanics
(split-until-measurement-says-merge) are this project's own discipline.

## Anti-candidate (recorded so it stays dead)

- **A broad "AI engineer" expert.** Worst of both kinds: too coarse for sharp
  retrievals, too broad for episodic coherence. Correct decomposition is DL /
  agent-systems / eval-methodology / structural-safety — which is the operator's own
  four pillars. That the partition matches the pillars is the point, not a
  coincidence.
