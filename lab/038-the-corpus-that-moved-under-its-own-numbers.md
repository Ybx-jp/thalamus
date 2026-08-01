# 038 — The corpus that moved under its own numbers

**Date:** 2026-08-01 · **Component:** eval layer 2 (`eval/corpora.py`, `eval/rescore.py`, `eval/arms.py`) · **Status:** built; lab/037 #5 closed; one falsifier named and not yet run.

## The gap

`experiments/` pins reproducibility to a named graph snapshot. It pins nothing about
the corpus the campaign numbers are actually computed from. `runs.jsonl` is appended
to by every arm and was **rewritten in place** by every re-scoring pass, with two
hand-made backups beside it as the only record of anything prior.

The activation-probe study scoped in docs/11 §7f would be the first study to train on
that corpus rather than merely report from it, which is what made the absence worth
closing now.

## What the corpus actually said, measured

The consult's first move was to check the premise the task was written on, and it did
not survive. Measured over the three files:

| | records | `rescored_at` | `restamped_by` |
|---|---|---|---|
| `runs.jsonl` | 140 | 88 | 23 |
| `runs.jsonl.pre-rescore` | 140 | 88 | 23 |
| `runs.jsonl.pre-voidfix` | 90 | 88 | 0 |

**Neither backup predates the contamination rescore.** Both already carry all 88
stamps — and all 88 share a single timestamp, so it was one rescore event, not 88. The
pre-rescore judgements of those 88 records exist **nowhere on disk**. The `.pre-rescore`
filename names the pass it was taken *for*, not the state it holds.

The other two diffs:

- `pre-voidfix` → current: all 90 records survive, 50 are appends, and **23 changed
  under their own identity** on exactly `void`, `infra_fault`, `attributable` and
  `restamped_by`. Appends and rewrites are tangled in one artifact, which is precisely
  why it cannot answer "what did record X say on date D".
- `pre-rescore` → current: **one** record, the 2026-07-31 memo-echo pass — and that one
  kept `memo_echoed_prior` beside the fresh value with `judge_config` stamped. The
  right pattern already existed in the corpus, applied exactly once.

And the corpus carries **no identity field at all** — no `run_id`, no `id`. The only
working key is the composite `(ts, task, arm, order_index)`, verified unique across all
140.

## What was built

**Identity is derived, not assigned.** `run_id` digests the fields fixed when an arm is
born. Rewriting 140 records to add an id column would have been the very mutation the
work exists to end, so the existing corpus acquires a stable identity without a byte
moving. New records carry it explicitly.

**A flat manifest, not a Merkle tree.** `thalamus eval corpus --name` seals the log
read-only, writes one manifest line per run (`run_id`, `body_sha256`, `revision`), and
appends a registry row — the snapshot-registry pattern with one added column. A whole-
file digest says *changed*; the manifest says **which records changed and which are
new**, and `--diff` reports appends, supersessions, in-place rewrites and removals as
four separate counts. A Merkle root would destroy exactly that diff to buy proofs to a
verifier who does not exist here (one operator, no adversary, 140 records).

Whole-file hashing was the thing I went in suspecting was wrong. It is not: the wrong
move is hashing a file that is *mutated in place* and calling the digest a version.

**Re-scoring appends.** `apply_outcomes` no longer touches the record it reads; it
returns revisions carrying the same `run_id`, one higher `revision`, and `supersedes`
holding the digest of the body replaced, stamped with the detector or judge
fingerprint. Readers take the head revision per run, which is why every existing
analysis reads the numbers it read before. The old atomic-rewrite-with-backup path
guarded against a crash mid-rewrite and not against the rewrite *succeeding*.

**lab/037 #5, closed.** Every record now carries `derivation`: `task_digest` over the
YAML **bytes**, `fix_ref`, the resolved `fix_paths` and their digest, and
`detector_config`. The boundary applied — config may be re-derived only if it is a pure
function of pinned inputs *and every input to that derivation is itself pinned* — is
what puts the path set on the pinned side. Not hypothetical: the 2026-07-29
`git-filter-repo` rewrite changed every SHA and left both task refs dangling, remapped
by hand through `commit-map`, and that remapping note lives in a YAML **comment**,
which a parsed-model digest would have called no change.

## What it does not fix

Nothing backfills, and the pin cannot rescue what is already gone. The 88 pre-rescore
judgements stay unrecoverable; sealing the corpus today makes every *future* revision
recoverable and makes the hole visible rather than closing it. Same stance as lab/037:
the absence is the measurement.

## The objection worth keeping

From the consult, and it cuts against the work just shipped:

> Pinning does not make a probe AUROC valid. It makes an invalid one *replayable*. …
> A perfectly pinned corpus with an unablated leak channel yields a reproducibly wrong
> number, which is arguably worse than an unpinned one because it recruits the pin as
> evidence of rigour.

The instrument that catches the git-object-store answer key in a downstream probe is
the leak-ablation control, not the audit trail. Both are now written into docs/11 §7f,
with the pinning work explicitly not standing in for the ablation.

**The falsifier, named and not yet run:** score the 8-of-88 contamination finding under
a second detector configuration. A controlled audit of medical VLM benchmarks measured
the same benchmark at 19.8% and 4.2% under two encoders (arXiv 2606.10066) — if this
corpus's count moves like that, every prior contamination number is one member of a
family and the verdict layer is unpinnable as it stands. If it is stable, the pinning
obligation argued here is weaker than argued.

**Ends in:** one premise falsified before it was built on, one module, one closed
lab/037 item, one unrun falsifier.
