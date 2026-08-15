# D5 — the memory graph, drawn

The artefact is the Penpot file `D5 memory graph`, exported to
`lab/assets/d5-memory-graph.png` at 2×. This file is the other half: what the picture
claims, what it deliberately does not draw, and what was measured rather than asserted.

The capstone's rule is that a wrong-but-pretty answer and a right-but-ugly answer are
both failures. Everything below is organised around which of those two it was protecting
against.

## The argument

The picture makes one claim, and it is the claim the docs make about themselves
([docs/02](../docs/02-expert-subgraphs.md):45-48):

> The boundary is therefore **one edge, not a partition between scopes**: a `Claim`
> inside a `Session` is episodic and confined; a `Claim` in no session is knowledge and
> shared. Same graph, same vertex label, same query — whether one `CONTAINS` edge exists
> decides who may read it.

So the drawing does three things at once:

1. **Every `Claim` is the same mark.** The dots tethered to sessions and the dots in the
   band below are identical in size and fill. Nothing distinguishes them but the tether.
   If they differed, the image would be asserting the wrong model.
2. **There are no containers.** No box, bubble, lane or region encloses a scope. This is
   the correction: a previous designer session drew this system as seven sealed
   compartments joined by consultation arrows, and that was formally overturned as false
   (`scope:designer:claim:698ae5fd66f05e8e`; decision log 2026-08-11). The wall a reader
   expects between scopes is absent because it is absent in the code — the commons runs
   unbroken beneath all eight columns.
3. **The one edge is the only saturated colour in the frame.** Everything else is
   greyscale. `CONTAINS` is `brand-on-dark`; nothing else in the image is.

## What is drawn

Canvas 2400 × 1350 on `bg #0e1116`. Frame geometry is immutable after creation
(defect 10 in the ladder), so this was committed once and not revised.

| band | y | content |
|---|---|---|
| consultation | 88–161 | one `Exchange`, `CONSULTS` up from main, two `REFERENCES` arcs |
| episodic | 227–405 | 8 `Session` rings, 25 `Claim` dots, 25 `CONTAINS` tethers |
| scope labels | 445 | the roster, `main` at higher luminance |
| knowledge | 606–796 | 30 `Claim` dots + 72 `Chunk` dots, **no tethers** |
| provenance | 756–996 | 18 `DERIVED_FROM` roots, plus one long walk from a main claim |
| sources | 996–1004 | 14 `Source` bars, one tier 1 |
| type | 1072–1268 | wordmark, the claim, the rule, the schematic disclosure |

**Node vocabulary** — four marks, chosen so none needs colour to be told apart:
`Session` = ring ⌀22; `Claim` = filled dot ⌀10; `Chunk` = filled dot ⌀6;
`Source` = bar 76×8; `Exchange` = ring ⌀26 with a filled core, the only ring-in-ring.

**Palette** — D3's tokens unchanged (`lab/d3-identity-spec.md`). `ink #cdd8e4` for
claims, tier-1 sources and the wordmark; `muted #7d8794` for chunks, session strokes,
tier-2 sources and all non-`CONTAINS` edges; `brand-on-dark #9a8cff` for `CONTAINS`
alone. `faint #4d5661` is used nowhere, because everything in this image carries meaning
and `faint` measures 2.54:1 — legal as a hairline, illegal as a carrier (D3 rule 3).

**Type** — IBM Plex Mono for identifiers and the wordmark, IBM Plex Sans for prose.

### The seven scopes are not colour-coded, and that is a finding

The obvious move is a hue per expert. It is not available. The open thread
`roster-identity-palette-luminance-infeasible` records that D4's per-expert palette fits
only **six** distinguishable luminance levels between the 3:1 non-text floor and white at
D3's declared 1.41:1 separation — one short of the roster's seven real scopes. Shipping
seven hues would ship a known-infeasible encoding into the capstone.

Scope is therefore carried by **position and label**, and density carries what
distinguishes `main`: five claims against two-to-four, and the only `Exchange`. `main` is
drawn the same size as every other session, because the architecture says it is *denser
and more connective* ([docs/03](../docs/03-master-plane.md):12-21), not bigger, and
size would assert something the code does not.

## What is deliberately not drawn

Stated, because an omission a viewer cannot detect is a claim of completeness.

- **`Artifact` and `Agent`** — the two global, unscoped node types, and the join key that
  makes two experts touching one file land on the same vertex
  ([docs/09](../docs/09-schema-and-federation.md):269-273). Cut because every `TOUCHES`
  edge would have to cross the knowledge band to reach them, and crossings are the one
  aesthetic with a large measured effect (below). The trade was legibility over coverage.
- **10 of 16 edge types.** `SPAWNS`, `CONTINUES`, `RESOLVES`, `BLOCKS`, `SOLVED_BY`,
  `TOUCHES`, `QUERIES`, `SUPERSEDES`, `ABOUT`, `ANCHORS`, `ADJACENT_IN_TEXT`, `RETURNS`.
- **`Thread`, `Entity`, `Trace`** — 3 of the 10 node types.
- **Tier 0 and tier 3.** The image shows tier 1 and tier 2 only, which is what the write
  paths actually produce (`docs/visual/trust.svg` records tier 3 as having no write path).
- **The consultation *swap*.** The arcs show that consultation routes through a
  main-scope `Exchange` and never expert-to-expert. They do not show that a ticket
  **drops** the ambient commons rather than opening a door (`mcp_server.py:109`) — which
  is the most counter-intuitive fact in the protocol and is not depicted at all.

## What was measured

Nothing below is an estimate.

**Contrast on `#0e1116`** (`thalamus.eval.legibility`): ink 13.09:1, brand 6.82:1,
muted 5.19:1. All clear the 4.5:1 text and 3:1 non-text thresholds.

**Greyscale survival — tested, not asserted.** The two edge families are
`#9a8cff` and `#7d8794`, which are **1.31:1** apart in luminance and desaturate to
`#9b9b9b` and `#868686` — still 1.31:1, and **below D3's own declared 1.41:1 floor**.
Hue is therefore doing real work, which D3 rule 2 forbids as a *sole* carrier. It is not
sole: stroke width differs 2.0 against 1.2, and the two families occupy disjoint bands
(tethers above their claims, roots below). The render was converted to greyscale and
read: structure, tethers, roots, spine, the tier-1 source and the arc all survive. This
is the check the open thread `p6-degraded-rendering-arm` exists to automate; here it was
run by hand, once, on one image.

**Edge crossings: zero, by construction.** Tethers fan downward from a single origin per
session and no two sessions' claim ranges overlap in x. The 18 `DERIVED_FROM` roots were
assigned to source bars by nearest-x and the assignment verified **monotonic**, which
makes crossing impossible. The consultation arcs route *above* every session while every
tether routes below.

**Fonts resolved.** Verified the documented way — `export_frame_svg`, read `font-family`
off the text elements: `IBM Plex Mono` ×5 and `IBM Plex Sans` ×6, 11 matching
`@font-face` blocks, and **`sourcesanspro` absent from the whole export**. A PNG cannot
establish this; the family renders in a lookalike humanist sans when it fails.

**Scale is disclosed in the frame.** The image draws ~140 nodes. The live graph held
27,317 vertices and 94,095 edges at snapshot `pre-scope-move-20260814` — 3.44 edges per
vertex. The picture says so in type, because a schematic that does not admit it is a
schematic is claiming to be a portrait.

## Prior work

Grounded through literature ticket `013c2ad2016c426a`, answered with six validated
citations. Claims are marked measured / inference / convention / not found, per the
discipline in [docs/visual/related-work.md](../docs/visual/related-work.md).

**The signature repeated, a third time.** Recall against `literature` for graph-drawing
aesthetics returned nothing: "graph" retrieves GraphRAG and Mem0, "diagram" retrieves a
bitemporal SQL passage. The expert had to go to primary sources for a question in this
scope's own field — the same tell recorded for tickets `cfd9f409951e48c0` and
`33e3e972ff6c4d99`. The named change for this drill closes it (below).

- **Crossings are the aesthetic that matters, and orthogonality is not** (measured).
  Purchase, *Which aesthetic has the greatest effect on human understanding?*, GD'97,
  n = 55, University of Queensland. Crosses: errors F(1,54)=24.25, reaction time
  **F(1,54)=87.98**, both α=.01 — the largest effect in the study. Bends: errors
  F=14.49 α=.01, RT F=5.84 approaching only. **Minimum angle F=0.09 / 3.05, NS.
  Orthogonality F=0.00 / 1.44, NS.** The orthogonal right-angled routing that is the
  default idiom of nearly every architecture diagram has a measured null behind it on
  both error and time, which is the licence this image takes to route curves. Two
  provenance caveats: the paper states **α levels, not p-values**, and the accessible
  PDF is an **OCR'd scan** — the figures were read through visible OCR damage.
- **Symmetry is free beauty, not comprehension** (measured, same study). Symmetry — the
  aesthetic most associated with a beautiful graph drawing — was **not significant for
  errors** (F=0.09), and significant only for reaction time (F=7.57, α=.01). This is the
  drill's own beauty/truth axis, measured: pursuing symmetry costs nothing and buys
  nothing on accuracy. The layout here is deliberately *not* symmetric.
- **Crossing angle is separable from crossing existence, but additive on it** (measured).
  Huang, Hong & Eades, [arXiv:0810.4431](https://arxiv.org/abs/0810.4431), n = 16, eye
  tracking. Path task p < 0.001 with every pairwise comparison significant: no-crossing
  < 90° < acute. A right-angled crossing is better than an acute one and still worse
  than none — so "make crossings orthogonal" does not substitute for having none.
- **Containment is the measurably worse encoding for sets** (measured). Wallinger,
  Jacobsen, Kobourov & Nöllenburg,
  [arXiv:2101.08155](https://arxiv.org/abs/2101.08155), n = 116, **static images with no
  interaction** — the closest condition to this artefact in the whole scan. Containment
  (EulerView) scored **65% against ~92%** element-task accuracy and **50% against 85%**
  on set tasks, falling to roughly **15% — chance** — on some large-set tasks. The
  no-container decision was taken for a semantic reason and this is independent support
  for it, arrived at afterwards.
- **Node-link is not disqualified at this size** (measured). Okoe, Jianu & Kobourov,
  [arXiv:1709.00293](https://arxiv.org/abs/1709.00293), n = 557, on graphs of **258
  nodes and 1090 edges** — node-link won path tasks and memorability. Ghoniem's
  crossover parameters reach 20/50/100 nodes at densities 0.2/0.4/0.6 (secondhand,
  via Okoe — the original was not read this session). At ~140 marks this image is
  inside the range where node-link has been measured to work. **No measured node-count
  threshold for "decorative" exists** (not found); the fear that drove the early
  decision to draw few nodes turns out to be unsupported in either direction.
- **An absence drawn as nothing is under-noticed** (measured, but conditions not met —
  and this is the sharpest objection to the design). Six converging studies — Eaton,
  Plaisant & Drizd 2005; Andreasson & Riveiro 2014; Song & Szafir 2019; Song et al.
  2021; Bäuerle et al. 2022; Fernstad & Westberg 2022, surveyed in
  [arXiv:2410.03712](https://arxiv.org/abs/2410.03712) — find that readers **generalise
  over** an absence rendered as blank space, while an absence given a positive mark is
  seen and raises decision confidence. The domain is **missing values in quantitative
  charts, not graph topology**, so transfer is *inference*, not measurement. But this
  image's entire thesis is an absence: the shared claims are shared *because a tether is
  not there*. The nearest measured evidence says that is the weak encoding. The response
  was to give the absence a **positive statement in type** — "A Claim inside a Session is
  private. The same Claim in no Session is the shared commons." — rather than leaving the
  blank to speak. Whether that is sufficient is untested. Recorded as a live exposure.
- **Data-ink has no derivation** (convention — confirmed). Wilbanks et al.,
  [arXiv:2109.10132](https://arxiv.org/abs/2109.10132), state that Tufte proclaimed the
  data-ink direction without proof. **Not found:** any test of data-ink against Bateman.
- **Embellishment's memorability advantage does not replicate cleanly** (measured).
  Syeda et al. 2023 ([osf.io/dferj](https://osf.io/dferj)) ran a four-way replication of
  Bateman's *Useful Junk?*: Study 1 (n = 19) found **no significant recall differences**;
  Study 2 reproduced the original. So neither "embellishment helps recall" nor its denial
  is safe to lean on, and this image's restraint is a choice, not a finding.
- **Mayer's coherence and signalling: conditions not met** (stated rather than smuggled).
  Mautone & Mayer 2001, *J Ed Psych* 93(2):377, is multimedia learning; Butcher 2006,
  98(1):182, is text-plus-diagram learning and was paywalled and unread; Larkin & Simon
  1987 is a computational analysis with **no human participants**. None measures a static
  structural diagram. The omissions above are therefore argued, not cited.

**The standing caveat over all of it.** Every result here is a *task-performance* result
— find the path, identify the set, recall the chart. **No study in the scan measures
reading a diagram without a task**, which is the only condition a hero illustration
actually meets. The evidence constrains the parts of this image that answer questions;
it says nothing measured about the part that has to be looked at.

**Also not found:** any measurement comparing curved against straight edge routing, and
any measurement of global crossing-count minimisation as distinct from path-local
crossings — Ware, Purchase, Colpoys & McGill measured only edges crossing *the traced
path*, so "minimise crossings everywhere" is a generalisation beyond what was tested.

## Live exposures

1. **The absence is encoded as blank space.** See above. Mitigated with a typographic
   statement, not with a mark. Untested.
2. **Edge-family separation is 1.31:1, under D3's declared 1.41:1.** Survives greyscale
   on width and position. The floor was declared for a status ramp where hue is the sole
   channel; applying it here is arguably the wrong reading of D3's own rule, but the
   number is under it either way and is recorded rather than argued away.
3. **The greyscale check was run once, by hand, on one image.** That is exactly what
   `p6-degraded-rendering-arm` exists to replace.
4. **Nothing has adopted this.** Like D3's identity, the artefact is a drill deliverable.
