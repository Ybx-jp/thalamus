# 065 — Everything simple at 24px is already something else

**Date:** 2026-08-13 · **Scope:** designer · **Drill:** D2 (iconography, mechanics
ceiling) · **Verdict:** deliverable shipped + 1 defect filed + a measured ink budget
that rewrote the set

D2 of the Penpot drill ladder: six icons — node, edge, memory, recall, thread, expert
— on a 24px grid at uniform 2px stroke, "optically corrected rather than
mathematically aligned". The mechanics were never in doubt after D1. What the drill
actually graded was consistency *across* a set, and the answer arrived in two parts:
a weight budget that is arithmetic, and a semantic collision problem that no amount
of internal consistency touches.

## The deliverable

Penpot file `D2 icon set` (`ba295861-…-79dcdaa7fb32`), one 720×560 board, six 24×24
icon frames on a 120px pitch, 27 shapes.

Shared primitives, which is what makes it a set rather than six drawings:

| primitive | appears in | role |
|---|---|---|
| ⌀8 node ring (path ⌀6 + 2px stroke) | edge, memory, thread, expert | the atom |
| 2px connector, round caps | edge, thread | relation |
| arrowhead, 35° barbs | recall | direction of retrieval |
| free round terminal | thread | unfinished — the semantic of a thread |

## Grounding corrected three things before the first shape

The `ground-in-literature` pass (ticket `535764648f984e82`) changed conclusions I had
already reached, which is the point of running it before drawing rather than after.

- **The circle/square ratio is adopted, not derived.** I intended to justify Material's
  20/18 ≈ 1.111 geometrically via equal-area (2/√π ≈ 1.128). The psychophysics refutes
  the reasoning: area judgement is sub-linear and keyed to a single salient linear
  dimension (Stevens exponents 0.70–0.86; Krider, Raghubir & Krishna, *Marketing
  Science* 20(4), 2001), so equal-area is the wrong target. **1.111 because Material
  publishes it.**
- **There is no diagonal-stroke compensation — and the folk direction is backwards.**
  Not found in the 2026 scan. Diagonals read *heavier*, not lighter, and SVG strokes
  are perpendicular to the subpath, so a rotated stroke already keeps its width. The
  √2 correction I would have applied would have made things worse.
- **There is a measured orthogonal number.** A vertical line must be **5.4% thicker**
  than a horizontal to read equally thick (de Waard, Van der Burg & Olivers, *Vision*
  3(1), 2019).

**The 5.4% was recorded and deliberately not applied.** At 2px it is 0.108px — below a
device pixel even at 2x, so rasterization swallows it while the brief's uniform 2px
stroke pays for it. It binds only above ~16px stroke. The study also does not test
obliques, so it cannot be stretched to cover diagonals.

The wording trap in Google's own docs is real: "4dp of padding around the perimeter"
for the 24dp case and "2dp" for the 20dp case describe identical geometry. **Emit 2dp
per side** or the live area collapses to 16dp.

## The ink budget, which is arithmetic and decided the whole set

Measured off the rendered PNG as dark-pixel coverage of each 24×24 cell. A 24px icon
at uniform 2px stroke has an ink budget of roughly **100px² out of 576**:

| element | cost | note |
|---|---|---|
| ⌀8 node ring | 37.7px² | the atom |
| 2px connector, ~9px | ~18px² | |
| ⌀14 node ring | 75.4px² | node, recall |
| **closed 20×16 container** | **136px²** | the entire budget, before any content |

So `memory` as a container-with-a-node was never going to sit in the same set as
`edge`: it measured 25.42% against edge's 14.97%, a 2.31× spread. **A solid enclosure
is unaffordable at this size.** That is not a matter of trying harder — three nodes
and two edges is also over budget, at ~147px².

The set only converged once every icon was built to roughly *two rings plus a
connector*. First pass 2.31×; final **1.25×** across 14.41–18.03%.

No published tolerance for set consistency exists (not found in the 2026 scan). The
measurement approach is Forsythe et al. (*BRMIC* 35(2), 2003 — structural variability
r_s = .65, edge information r_s = .64) and Donderi (*Perception* 35(6), 2006, compressed
file size). **The 1.5× threshold is mine, declared, uncited.**

## Optical centring, computed rather than eyeballed

The literature's rule is centroid-not-bounding-box, given for triangles as h/6. It
generalises: compute the **ink centroid** off the render and move the composition until
it lands on (12,12). That is a correction computed from a stated rule, which is what
the brief demanded, and it is checkable — five of six landed within 1.1px.

**One stated exception.** `expert` sits 1.06px low. A bust has a conventional baseline
the way a letter does; grounding it beats centring it. The rule is a default, not a law.

## The real failure: consistency inside a set buys nothing against the world's sets

Every first-pass icon was internally consistent and three were unusable, because I
designed from primitives outward and never checked the silhouette against the ambient
icon language:

| icon | what it actually read as | fate |
|---|---|---|
| memory v1 — container + centred node | **camera** | redrawn |
| recall v1 — box + arrow through right edge | **logout** | redrawn |
| expert v1 — node + concentric arcs | **RSS / wifi** | redrawn |
| recall v2 — ring + 45° arrow up-right | **Mars symbol ♂** | redrawn |
| expert v4 — open boundary + centred node | **camera again** | redrawn |

The camera collision landing twice, from two unrelated starting points, is the finding:
**at 24px, an enclosure containing a centred circle is a camera**, and a gap in the
boundary is too subtle to rescue it.

The mature move is not to escape collision — at this size nothing does — but to choose
one whose misreading is *semantically adjacent*. `expert` as a person silhouette
misreads as "user", which still points at a persona. It cost the vocabulary: it is the
only icon sharing no structural primitive with the others, mitigated by holding the
head to the exact ⌀8 node ring.

## Instrument facts gained

- **Round caps are authorable, and verifiable.** `set_stroke` exposes no cap parameter,
  but `modify_shape` writing the whole `strokes` array reaches `stroke-cap-start` /
  `stroke-cap-end`. Confirmed in the rendered SVG (`stroke-linecap: round`) *and* read
  back through `get_shape_details` — unlike path content, caps survive a round trip.
- **Writing the `strokes` array wholesale drops every field you omit.** A probe that
  set caps without restating `stroke-opacity` lost it. Write the full stroke map every
  time. This is the text-mutation reset hazard, in `modify_shape`.
- **A path's bounding box is the only machine-checkable assertion available on vector
  work.** Content reads back as `null`, but `x`/`y`/`width`/`height` are exact — and
  they are the *true cubic extent*, not the endpoint box. Proved decisively with an arc
  whose control points push outside its endpoints: predicted apex y=30 analytically
  ((60+3·20+3·20+60)/8), read back y=30, height=30, where an endpoints-only selrect
  would have reported height 0. So every path can carry a predicted-extent check.
- **Absolute coordinates are the slip.** Paths take canvas coordinates while frames are
  placed in them; writing a frame-relative y as an absolute puts the shape 2000px away
  and the tool returns 200.

## The defect: dash geometry is not authorable

`stroke-style: "dashed"` renders as a hardcoded **`stroke-dasharray: 12, 12`**
regardless of shape size. On a 16×16 boundary — perimeter ~64 — that is 2.7 dashes, so
a dashed enclosure lands as four corner brackets and reads as a crop/scan frame. There
is no dash-length, dash-gap or dash-offset parameter anywhere on the tool surface, and
Penpot's data model carries only the `solid`/`dotted`/`dashed`/`mixed` keyword.

At icon scale a dashed 24px form needs roughly `2, 2`. **Dashed strokes are therefore
unusable below about 100px.** Filed under the ladder's open findings; owner `architect`.

This one killed a design decision the operator had already made — dashed enclosure for
`expert`, chosen so that line style would carry meaning systematically (solid = store,
dashed = scope). The fallback to an open boundary failed for the independent camera
reason above, and the decision went to the person silhouette.

## Named change

`lab/penpot-drill-ladder.md`: three instrument facts added (authorable round caps, the
`strokes`-array reset hazard, path bbox as the only vector assertion), the ink-budget
finding recorded as a design constraint on every future drill at icon scale, and the
dash defect filed under open findings.
