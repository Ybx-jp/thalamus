# 009 — Memory disagreement: the graph out-remembered the operator

**Date:** 2026-07-18 · **Component:** open-thread surface, provenance chain, cross-scope resolution · **Status:** adjudicated (human-stale); staleness metric designed, not built

## The incident

The operator challenged homelab's open thread
`scope:homelab:thread:verify-pwa-gear-visible-after-sw-v9` ("plane-v9 SW fix not
yet confirmed by the user"), recalling that they *had* confirmed — "I said
something like 'thanks my closing agent experience has ascended'" — and asked,
in order: is the confirmation in the graph, did homelab fail to retrieve, is
this memory poisoning?

## The adjudication (provenance walk, then archive)

The provenance chain answered all three. From the retained evidence:

- The remembered message exists, retained in archive snapshot `820f11c9…`:
  *"thank you. my personal coding agent experience has ascended to the realm of
  gods"* — **2026-07-18T01:19**, in main-scope session `5f8ad588…`, followed by
  the proposal to mint the homelab expert. It praises the plane generally.
- The gear bug was first reported at **05:53** and the v9 fix + "do a full
  close + reopen" instruction shipped **05:54–05:55** in homelab session
  `a6bb64ee…` (HEAD snapshot `cfb3c13a…`), whose transcript **ends at 05:55:15
  with no further user turn**.
- Therefore the remembered confirmation predates the bug it would confirm by
  ~4.5 hours and sits in a different scope. The thread was accurate at
  distillation time; the stale memory was the human one. First genuine
  confirmation: the operator's statement in the 2026-07-18 main session that
  produced this entry ("for the record, closing and opening the app worked").

**Verdicts:** in the graph? — the *message* yes (retained + main-scope), as a
v9 confirmation no, because it wasn't one. Retrieval failure? — no; homelab
served its scope faithfully. Poisoning? — no; nothing untrusted wrote, and the
write path held. Adjudication class: **human-stale**.

## The near-miss that is real

Had the operator confirmed in the main window, the evidence would sit in main
scope with no writer able to close homelab's thread: `thread_refs` resolve
scope-locally, cross-scope edges are REFERENCES-only by design, and the ingest
feed correctly refuses event-shaped facts (its kinds are durable
finding/technique — measured below). Resolution evidence landing outside the
opening scope leaves the thread stale forever. This session lived the benign
variant.

Measured en route: the ingest extractor, asked twice (dry-runs, $0.13 each) to
extract a prominently-stated confirmation *event* from the ops-notes feed,
dropped it both times while keeping all durable technical claims — the kind
vocabulary is doing its job; episodic facts belong to session distillation,
not the knowledge feed.

## Measurement design (eval-methodology consultation `2e0f6a574658470a`)

The consulted answer (5 validated citations, MQuAKE/judge cluster) framed
thread resolution as a **consequence-level fact**: checking a thread exists
and says "open" is recall-only validation; "given evidence in another scope,
this thread should close" is the multi-hop consequence where systems fail even
with perfect single-fact recall. Design adopted from the answer (decisions are
main's):

1. **Taxonomy.** Record each operator-vs-graph disagreement as a
   memory-disagreement incident with a provenance-adjudicated verdict from
   {graph-stale, human-stale, both-stale, retrieval-failure, poisoning,
   unadjudicable}. Accumulated verdicts give base rates, so the next
   disagreement starts from priors, not suspicion. This entry is incident #1:
   human-stale.
2. **Detector/closer split.** At eval-sync, sweep open threads against all
   scopes' session summaries (slug + artifact match, post-open window) for
   RESOLVES *candidates*. The detector may be noisy; **the closer must be
   evidence-anchored** — a RESOLVES edge cites the specific confirming
   evidence, and nothing auto-closes.
3. **Metric.** Resolution latency (not raw age), overdue = high quantile of
   the closed-thread distribution; still-open threads are censored
   observations, not exclusions. Quantiles flag for review only until closure
   counts clear a floor. Counter-metric: re-open rate (Goodhart guard).
4. **Deferred.** A typed "awaiting external confirmation" thread state was
   recommended as a stratification variable; deferred to the buildout thread —
   it is a schema change and gets its own grounded design when the sweep is
   built.

## Open thread

`thread-staleness-cross-scope-resolves` — build the eval-sync sweep +
resolution-latency report per the consultation; adopt the typed marker
decision there. Until built, cross-scope confirmations route the way this one
did: stated in the owning scope's next pinned session, which closes the thread
scope-locally.
