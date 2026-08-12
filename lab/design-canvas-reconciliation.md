# Design — a reconciliation engine for authoring tools

**Status:** design, not built. **Scope:** `designer` specifies; it cannot implement
(`write_boundary` denies `*.py`/`*.js`/`*.ts`). **Grounding:** consultation
`scope:main:exchange:f4b9a75d41334cd9` (literature, 27 validated citations).

The problem this solves: an agent authoring into a tool it cannot fully observe has no
record of what it made except the calls it happens to remember making. The motivating
defect was `get_shape_details` returning null content for paths — but the defect that
actually proves the case is smaller and worse, and is in §4.

## 1. Prior work

Established: **level-triggered reconciliation over declared desired state** is the
industrial answer to "keep an external system matching a description of it."
Terraform's state file *is* a shadow model, drift is its named hazard, and
`refresh`/`plan`/`apply`/`import` are its worked remedies; Kubernetes' spec-vs-status
loop re-derives from observed state rather than trusting an event stream, which is what
makes it robust to missed events and to other writers. Both are cited in the
consultation above.

Also established, and each of these changed this design:

- **Recognising a stale belief does not imply acting on it.** STALE (arXiv 2605.06527)
  measures latent-state tracking over 400 conflict scenarios and finds cascading
  invalidation the hardest case — LightMem, Zep, LiCoMemory, A-mem and mem0 all struggle.
  Marking a node stale is not the same as propagating what its staleness implies. §5.
- **Missing data must not silently collapse.** The "Ontology Trap" claim — a model
  should not decide on its own whether absent data means unknown, false, invalid or
  not-applicable. §3.
- **Recording procedures has a measured cost.** Agent Workflow Memory scored *lower*
  action F1 than its no-workflow baseline, because stored procedures steer toward
  actions irrelevant to the current environment state. This is evidence against §8.
- **Identity without host keys falls back to position.** Buneman's where-provenance:
  absent stable keys, a tree is identified positionally, which is exactly what breaks
  when a sibling is inserted. §3.
- **Event sourcing gives replay, not truth.** ESAA (arXiv 2602.23193) commits a
  SHA-256 projection hash and replays from event zero — which detects log-vs-projection
  divergence, not projection-vs-host divergence. §6.
- **Concurrency makes divergence a merge.** Penpot is multi-user; replicated tree move
  (arXiv 2103.04828) is the relevant lineage. §7.

**Positioning.** This is a **convergence** on Terraform and Kubernetes, and an
**instantiation** of level-triggered reconciliation in a domain those tools were not
built for. It is not an extension of them and claims no new mechanism. USD was
considered and set aside: it solves interchange between tools that can all load a
stage, which is a different problem from driving a tool that answers questions poorly.
Whether anyone has applied reconciliation to creative authoring tools specifically is
**unknown** — the `literature` scope holds nothing on scene graphs, interchange formats
or procedural authoring, and absence in one scope is not absence in the field. No
novelty is claimed here and none should be written elsewhere until docs/11 §4 records a
real scan.

## 2. The decision that makes this not a lowest common denominator

The obvious failure of "one model, many tools" is a shared schema that degrades to
whatever Penpot and Unreal both understand, which is almost nothing.

**Terraform does not have that problem, because Terraform core has no model of a
compute instance.** It has a model of *resource lifecycle* — addressing, dependency,
create/read/update/delete, state, diff. Providers own all semantics. AWS and Cloudflare
share no vocabulary and reuse the entire engine.

So: **the shared thing is the lifecycle, not the schema.** Penpot resources and Remotion
resources need not correspond in any way. What is written once and reused forever is
identity, addressing, refresh, diffing, planning, drift detection and the audit log.
What is written per tool is a set of resource types and their CRUD.

This is the direct answer to "not start from zero every time," and it is the reason the
answer is honest rather than aspirational: the reuse claim is about machinery that
demonstrably transfers across wildly different providers, not about a visual vocabulary
that demonstrably does not.

## 3. The model

**Address.** Every managed element has a stable logical address assigned by the author —
`penpot.frame.d0`, `penpot.text.title` — independent of any host id. State maps address
to host id. This is Terraform's mechanism and it is the answer to Buneman's positional
identity problem: the address survives reordering, re-creation and host-id churn,
because nothing about it is derived from the host.

**Resource.** A typed, adapter-declared object at an address, holding attributes.

**Three-state attributes.** Every attribute carries which of these it is, never
collapsing them:

| state | meaning |
|---|---|
| `asserted` | the author declared it; nobody has checked |
| `observed` | read back from the host, with the read strategy that produced it |
| `unobservable` | the host is known to be unable to report it |

`unobservable` is a first-class value, not a missing one, and it is per attribute per
adapter — not a property of the resource. It is the Ontology Trap claim applied
literally: "no value" must not be able to mean four things at once.

**Bitemporal stamps.** Each attribute carries when it was asserted and when it was last
observed. "Last observed 40 calls ago" and "never observed" are different confidences
and the model must be able to say which.

## 4. The example that justifies all of the above

`create_text(font_family="worksans")` on this Penpot instance:

- `get_shape_details` reads back `font-family: worksans`.
- `export_frame_svg` renders `font-family: sourcesanspro`, and declares only that face.

Both reads succeed. **They disagree**, because Penpot keys font loading off a `font-id`
that no tool writes, so the family string is stored and inert. Every text renders in the
default whatever was asked for.

A single-valued model records `worksans` and is wrong. A two-state believed/unknown
model records `worksans` as known-good and is wrong. Only a model that holds
`asserted: worksans` beside `observed: sourcesanspro` can represent the situation, and
the diff between those two fields **is** the defect report.

This was missed once here by rendering the frame and looking at it — a humanist sans at
24/700 is not separable from another by eye, and the observer read confirmation into the
image. The structured read caught what render-and-look could not. That is the whole
argument for this design in one case, and it is not hypothetical.

## 5. The loop

**refresh** — read the host, per attribute, by the adapter's declared strategy. Populate
`observed`. Mark what the strategy cannot reach as `unobservable`.

**plan** — diff `asserted` against `observed` and emit creates, updates, deletes and
**drifts**. A drift is the third thing Terraform names and the one that matters here:
the host disagrees with the declaration and nobody asked it to.

Per STALE, a plan must **propagate** a drift's consequences, not merely flag the node.
If a frame moved, everything positioned relative to it is now suspect, and a plan that
reports one changed node and stays silent about its dependents reproduces exactly the
cascading-invalidation failure that paper measures. Dependency edges exist for this.

**apply** — execute through the adapter. Every host call records intent and result.

**import** — adopt an existing host object at an address. Required from day one, not
later: the scratch file already contains shapes this model did not author, and any real
file will contain more. Unmanaged objects must be visible as unmanaged rather than
invisible.

## 6. Audit

An append-only log of intents and outcomes, with a periodic content hash of the
projection (ESAA). This buys replay and a tamper-evident record of what was done.

Stated plainly because the consultation was: **replay detects log-vs-projection
divergence, not projection-vs-host divergence.** Only `refresh` detects the latter. The
log is an audit trail, not a substitute for observation, and any claim that replay
"verifies" the design is false.

## 7. Concurrency

Penpot is multi-user and the plugin bridge means a human may be editing the same file
live. Sole ownership must not be assumed anywhere.

v1 position: detect and report, never silently revert. A drift on an unmanaged
attribute is information; a drift on a managed one is a conflict for the operator to
resolve. Automatic merge is out of scope and the replicated-tree-move literature is the
place to start when it stops being.

## 8. The program framing — recorded, not chosen

The alternative considered was recording the **generating program** rather than the
resulting state: not "rounded rect at 24,24 radius 8" but "a 24px icon grid, 2px
strokes, six glyphs from these primitives," with the artifact a render of the program.

**Why it was not chosen now.** Two reasons, one measured and one discovered:

1. AWM measured a real cost — stored procedures steering toward actions irrelevant to
   current environment state, scoring below the no-workflow baseline. The framing is not
   free.
2. The strongest argument for it was that shadow state drifts and cannot be
   re-observed. That argument was **falsified**: `export_frame_svg` round-trips full
   path geometry including Bézier control points, so a read path exists and drift is
   detectable. The case for paying a language-design cost to avoid observation
   collapsed when observation turned out to be available.

**Why it stays on the table.** Its remaining advantage is untouched by any of that: a
program transfers across tools whose primitives do not correspond, where declared state
cannot. `M40,270L140,180L240,270Z` means nothing in Unreal; "a triangular mark at this
weight" does. Cross-tool transfer is the stated long-term goal, so the argument is
deferred, not defeated.

**Why the fork is smaller than it looked.** The two do not compete. Terraform has
modules and CDKs; Kubernetes has operators. A program layer sits **above** a
reconciliation engine and emits desired state into it — it does not replace it. Adopting
reconciliation first therefore costs nothing against adopting a program layer later, and
buys the identity, diffing and observation machinery a program layer would otherwise
have to invent.

**The trigger to revisit:** the first time a resource type cannot be expressed in both
the Penpot and Remotion adapters without one of them degrading. That is the empirical
signal that declared state has hit its ceiling, and it is what the second adapter is for.

## 9. Where it lives

- **Design source and state: a dedicated design repo**, separate from this one. Design
  sources are deliverables in their own right, they version and review on their own
  cadence, and keeping them out of the Thalamus checkout keeps a design change from
  reading as a code change.
- **The graph indexes it.** The file is truth; the graph holds a queryable projection
  with provenance edges back to it — the pattern `Source` and `Chunk` already establish
  for text, reused rather than reinvented.

This is the half of the memory-representation handoff
(`lab/handoff-designer-memory-representation.md`) that this design actually closes: what
was built becomes queryable across sessions. It does **not** close the perceptual half.
"Show me the compositions that worked" remains unanswerable, and nothing here should be
read as addressing it.

## 10. The Penpot adapter, concretely

Read strategies, measured on this instance:

| attribute | strategy | state |
|---|---|---|
| geometry, fills, strokes, radius | `get_shape_details` | observable |
| path content | `export_frame_svg`, parse `d` | observable — **not** via `get_shape_details`, which returns null |
| rendered font | `export_frame_svg`, parse `font-family` | observable, and differs from the asserted value |
| declared font | `get_shape_details` | asserted only |
| component registration | — | unobservable |

The path row is worth stating as a general lesson: `get_shape_details` returning null
was read as "the host cannot report this," and it was actually "this reader does not
decode it." **`unobservable` must be justified by a failed strategy, never assumed from
one failed call** — otherwise the model encodes a tool's bug as a property of the world.

## 11. What this does not decide

- **The name.** Working title only. A design object that is neither the artifact nor the
  code deserves a better one than "the reconciler."
- **Resource granularity** — whether a Penpot frame and its children are one resource or
  many. This is the decision most likely to be wrong first.
- **Whether the graph projection is worth its node count.** TinkerGraph is in memory and
  the 2026-07-14 decision against chunk nodes was a node-count argument. A per-shape
  vertex may lose that argument, and §9's graph half should be treated as contingent.
- **Ownership.** This is harness capability, not a designer deliverable — it serves any
  scope driving a stateful external tool. `designer` specified it because `designer` felt
  the defect and because it is an interface-design problem; it should not own it.

## 12. What would falsify this

If a second adapter can be written for Remotion without the core changing, the
lifecycle-not-schema claim in §2 holds. If Remotion's adapter forces core changes —
particularly around time, which Penpot has no analogue for — then the shared lifecycle
is not as tool-agnostic as Terraform's, and §8's program framing should be reopened
immediately rather than at its stated trigger.
