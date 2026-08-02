# 039 — The benchmark that could not tell our defense from the model's refusal

**Date:** 2026-08-01 · **Component:** eval design (instrument selection) · **Status:** declined — instrument rejected, taxonomy adopted, two canaries specced

## What was asked

Should we run **MPBench** against Thalamus? MPBench is the benchmark from *From
Untrusted Input to Trusted Memory: A Systematic Study of Memory Poisoning Attacks in
LLM Agents* (arXiv 2606.04329), already held in the `literature` scope at
abstract level and cited in [docs/11 §](../docs/11-related-work.md) alongside MINJA,
MemoryGraft and SMSR. It is the only instrument in that citation set whose unit of
measurement is the one this project's threat model names: content that entered
persistent memory from an untrusted read and later changed behaviour.

Routed as a consultation to the literature expert (ticket `217232caf5284252`,
12 validated citations) rather than answered from the four held claims.

## What the instrument actually is

The consult's most useful product was its epistemic boundary, not its content. The
`literature` scope holds **four** claims on 2606.04329, all abstract-level: the
benchmark exists, the taxonomy has six classes, aggressive write/retrieve implies
more exploitable, prompt-injection defenses do not cover memory poisoning. Every
operational fact below was fetched from the source during the consult and **is not in
the graph** — which is itself a finding, and the reason the ingestion item exists
below.

Fetched specification, in brief. Four write channels — explicit instruction-executed,
system-prompt-driven, compaction-driven, experience-to-procedure — carrying six attack
classes and nine structural vulnerabilities. Two metrics, deliberately split into
phases: **ASR**, whether the payload reached persistent storage (measured by
inspecting the store), and **RSR**, conditioned on ASR, whether the stored entry
changed behaviour on a later query. 3,240 adversarial cases over seven domains
(files, browsing, email, calendar, Slack, code exec, skills) plus 2,997 benign cases
for a false-positive rate. Evaluated against two agents — OpenClaw and HERMES — both
on GPT-OSS-120B at default memory configuration.

## Three reasons it was declined

**1. The artifact is a dataset, not a benchmark.** `Digital-Trust-Lab/mp-bench` is two
JSONL files under Apache-2.0 and nothing else: no harness, no attack generators, no
evaluation code, no stated interface contract for a system under test. Running it
means writing the harness — including the part that decides what "the instruction was
written" means for a graph store — and then reporting a number not comparable to the
paper's, which was measured on a different scaffold and a different model. Baseline
comparability is the only thing an external benchmark buys over a bespoke eval, and
here it is exactly zero.

**2. Two of six attack classes have a surface on us.** Its channels assume an agent
that autonomously decides what persists, across seven tool domains. Against our real
ingress points (`harness/hooks/claude-code/session-end.sh`, `harness/ingest.py`,
`mcp_server.py`, `consultation.py`, `eval/sync.py`): compaction-driven poisoning maps
cleanly onto SessionEnd distillation, the one fully-automatic ungated write path;
explicit-command insertion maps loosely onto `memorize`. Experience-to-procedure has
no surface at all — skills here are hand-written, never synthesized. And `ingest`, the
path most exposed to hostile web text, is dry-run-by-default behind a host allowlist
with tier stamped server-side, so most of the corpus meets a human gate and scores
trivially. A benchmark whose cases mostly cannot reach the system is not measuring the
system.

**3. The null is confounded, and the benchmark has no arm that separates it.** We
would almost certainly measure 0% ASR. Two explanations share that number: *the
write-path floor worked*, and *the model would not have complied anyway*. The second
is not hypothetical — the depth-dependent indirect-prompt-injection work we hold
measures Claude Haiku at 0% ASR at every depth
(`scope:literature:claim:fe8f757b416cb0af`), and our candidates are Claude-family.
MPBench ships no defense-off condition, so nothing in it distinguishes a working floor
from a refusing model.

## The reason that generalizes

Reason 3 is [lab/024](024-the-endpoint-was-in-the-wrong-place.md) again, one level up.
There, the pre-registered endpoint (rung ≥ 4) sat above where the treatment acted, so
the primary reading was null while the effect was real at rung ≥ 3. Here the endpoint
sits where two causes are indistinguishable, so the reading is null whether or not the
effect exists. Both are the same failure: choosing an endpoint before asking what
distribution of outcomes it can produce and which of those outcomes are informative.

The correction is the same too, and it is an ablation-design point rather than a
metric one. An ASR number is interpretable only beside a **defense-off control** — the
ingress floor at `harness/extraction.py` disabled — because the contrast, not the
level, is the measurement. Once that control is in the design, the corpus is
interchangeable and MPBench is a case file, not an instrument. That is the whole
argument for declining: what we would have to build to make its number mean anything
is the thing that makes its number unnecessary.

## What is adopted instead

**The taxonomy, as a pre-registration spine.** The six classes and nine structural
vulnerabilities are a channel list written down in advance, which is precisely what
the open thread `leak-channel-audit-should-be-pre-registered` has wanted since
2026-07-27. Our known channels — filesystem paths, git object store, Bash `curl`,
the live gremlin endpoint, `~/.claude` transcript history — were each found by a
separate post-hoc scan, and the dominant one (git object store, 9/88 arms) was not
the one anyone thought to check. V-S1 (no write-path validation), V-S2 (shared
multi-source context) and V-S3 (manipulable compaction trigger) give the audit a
standing frame in which every channel carries either a detector or an explicit
`unchecked` label.

**The citation.** The paper's load-bearing negative — input-boundary prompt-injection
defenses do not move the write-phase number
(`scope:literature:claim:001c26c884bd8c30`) — is external support for an architecture
this project already chose: the floor sits at the write path
(`harness/extraction.py`), audited by the contract (`external ∧ tier<2`), not at the
input boundary. [docs/05](../docs/05-trust-model.md) records that stance as its own
reasoning; it should record the convergence.

**Two canaries, not a campaign.** [lab/005](005-transcript-ingress-canary.md) closed
the WebFetch channel with a fixture transcript through the real pipeline for $0.09,
and named two residuals that are still open and still untested: Bash-tunnelled
`curl`/`wget`, and the Agent Teams mailbox — the sharper of the two, because it has no
ingress tool at all. `tests/` currently contains zero occurrences of
`curl|wget|mailbox|SendMessage`. Two canaries at roughly lab/005's cost close more
real uncertainty about this system than a full MPBench port, and each carries the
defense-off control that MPBench lacks.

## Blockers on record, for whenever attack *arms* are wanted

Not needed for the canaries, which do not go through the arm machinery, but both are
real and both would surface late:

1. Arms strip write-back in every arm including memory-on (`eval/arms.py`) and read
   the live graph, so planting a poisoned node contaminates real memory.
2. `eval/snapshots.py`'s `serve()` is read-only by design, so a pinned snapshot cannot
   host a write-path attack.

## Moral

An external benchmark is worth its port cost when it buys comparability to a published
baseline or a control you would not otherwise build. MPBench offers neither here: its
harness does not exist, and its metric is a level where ours needs a contrast. Take
the taxonomy, take the citation, and spend the money on the two channels we already
know are open.
