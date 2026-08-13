# 064 — The escape hatch cannot spell a keyword

**Date:** 2026-08-12 · **Scope:** designer · **Drill:** D1 (product UI, fully
specified) · **Verdict:** deliverable shipped + 1 defect filed + 3 instrument-fact
corrections

D1 of the Penpot drill ladder: a button matrix, three variants by three states, on an
8px grid, with padding redlines. The brief leaves nothing to interpret, so it grades
execution. Execution was clean — every box landed on its specified pixel. What the
drill surfaced instead was that `modify_shape`, documented in the ladder as *"the
escape hatch — the only route to shadows, blur, blend modes, per-corner radii,
rotation, constraints"*, cannot reach roughly half of that list, and for a reason no
amount of argument-fixing repairs.

## The deliverable

Penpot file `D1 button matrix` (`ba295861-…-79b4f5486567`), one 960×720 board, 53
shapes. Nine cells: primary/secondary/ghost × default/hover/disabled, plus a redlined
exemplar of primary/default.

Control geometry, all multiples of 8:

| token | value |
|---|---|
| control height | 40 |
| padding x | 16 |
| padding y | 8 |
| label box | 88 × 24 (16px text, line-height 1.5) |
| corner radius | 8 |
| resolved width | 120 = 16 + 88 + 16 |

Redlines measure to the **label box**, which is a real text object in the file, not to
the glyphs — so the padding a redline claims is a padding an implementer can verify
against the shape tree rather than against a screenshot.

## Contrast, measured before drawing

The palette was run through a WCAG 2.x contrast calculation *before* the first shape
was created, which caught two failures while they were still free to fix.

| pair | ratio | verdict |
|---|---|---|
| white on primary `#3B49D6` | 6.75 | AA |
| white on primary-hover `#2C38AE` | 9.19 | AA |
| accent label on board `#F4F5F7` | 6.19 | AA |
| accent label on tint `#ECEEFC` | 5.85 | AA |
| disabled ink `#5A6172` on disabled fill `#E3E6EC` | 4.96 | AA |
| secondary border = accent, on board | 6.19 | 1.4.11 ✓ |

Two caught before drawing:

- **The first secondary border, `#C9CEDA`, scored 1.44 against the board.** A control
  boundary is non-text content carrying information, so SC 1.4.11 wants 3:1. Making
  the border the accent colour fixes the conformance *and* the design — secondary
  becomes an outlined accent rather than a grey box.
- **Disabled was going to use `#969CAC` on `#DDE0EA` — 2.08.** Disabled controls are
  exempt from 1.4.3 and 1.4.11, so this would have shipped as "conformant". It was
  changed anyway to `#5A6172`, which clears AA at 4.96. The affordance loss for
  disabled is then carried by the desaturated *fill*, not by an unreadable label. The
  exemption is a floor, not a target.

Residual, stated rather than fixed: the disabled secondary border `#C6CBD6` scores
1.49 against the board, and ghost/default and ghost/disabled have **no** visible
boundary at rest — the hit target exists as a shape but is invisible until hover. Both
are deliberate and both are the kind of thing a built surface should be re-checked
against; they are the hand-off to qe, not a closed question.

## The defect: enum-valued attributes are unreachable

`set_layout` returned a bare `500` from `update-file`. Isolating one attribute at a
time through `modify_shape`, on a throwaway frame:

| attribute set | value kind | result |
|---|---|---|
| `layout-gap` `{row-gap, column-gap}` | map of numbers | 200 |
| `layout-padding` `{p1..p4}` | map of numbers | 200 |
| `r1`–`r4` | numbers | 200 |
| `rotation` | number | 200 |
| `layout` `"flex"` | enum | **500** |
| `layout-flex-dir` `"row"` | enum | **500** |
| `blend-mode` `"multiply"` | enum | **500** |
| `constraints-h` `"left"` | enum | **500** |

Six for six on the rule: **number- and map-valued attributes apply; enum-valued ones
fail.**

The diagnosis is not a wrong argument spelling. `api.command` posts the RPC body as
plain JSON (`self._client.post(url, json=params)`). A `mod-obj` change carries
operations shaped `{type: set, attr, val}` where `val` is schema-typed `any`, so no
string→keyword coercion happens on the way in; the literal string `"flex"` lands in
the shape, and the *shape* is then validated against a schema that types `:layout` as
`[:enum :flex :grid]`. Validation fails, and the failure surfaces as a 500.

This also explains why `create_frame` works while `set_layout` does not: `add-obj`
carries a whole shape object decoded against the shape schema, where `"frame"` →
`:frame` coercion is available. `mod-obj` has no such path.

Sending the transit spelling `"~:flex"` was tried and **also 500s** — there is no
transit decoding on a JSON body, so it arrives as the literal seven-character string.
That rules out the obvious client-side fix: no argument value expressible in a JSON
body can produce a keyword. The repair belongs in the transport
(`application/transit+json`), not in `set_layout`'s parameter handling.

Filed as **P3** in the drill ladder's open findings. Owner is architect; `designer`'s
`write_boundary` denies `*.py`.

## Corrections to the ladder's instrument facts

1. **`modify_shape` is a narrower escape hatch than documented.** Of the six routes it
   claims, shadows and blur (maps), per-corner radii and rotation (numbers) work;
   **blend modes and constraints do not**, and neither does any other enum-valued
   attribute — stroke alignment, stroke cap, grow type, layout alignment. The
   documented sentence is true of half its own list.
2. **`set_layout` is not merely awkward for this brief, it is inoperative.** The
   drill expected to surface "whether `set_layout` flex is usable for real
   composition". It is not usable at all: two of its five ops 500 the request. A
   second, softer limit sits behind the first — `padding` is a single scalar written
   to all four sides, so the 16/8 asymmetric padding this button spec needs could not
   be expressed even once the keyword defect is fixed.
3. **Creation coordinates are exact; nothing drifts.** Measured off the rendered PNG:
   every button box landed at its specified pixel, 120×40, `x 216..335 y 176..215` and
   so on for all five probed. The "set style at creation time" rule holds — the
   hazard is in `move_shape`/`resize_shape`, not in creation.

## The cost of one-call-one-revision, measured

The file ended at **revn 64**, which reconciles exactly: 54 creates + 1 delete + 1
recreate + 2 probe frames + 4 successful probe writes + 2 probe deletes. So **every
successful write is exactly one revision, and failed writes consume none** — a 500
leaves no gap in the sequence.

The wall-clock cost is not what the ladder assumed, because the round trips need not
be serial: the 54 creates went out in **6 messages** of 8–15 parallel calls each. The
one-call-one-revision model is expensive in *revisions* — 54 undo steps for one board,
and a real race if the file is open elsewhere — but it is cheap in *wall clock* as
long as the calls are batched. The thing to avoid is a call-per-message loop, not the
model itself.

## Also learned: the PNG never needs to enter context

`export_frame_png` returns base64 that overflows the tool-result ceiling, and the
harness spills it to a file under the session's `tool-results/`. Decoding straight off
that file — the payload is JSON-in-JSON, the image under `content_base64` — puts the
PNG on disk without a single base64 character crossing into the conversation. A 1920×1440
export cost nothing to look at. This is the cheap render-and-look loop, and the
overflow error is the mechanism, not an obstacle.

## Named change

`lab/penpot-drill-ladder.md`: instrument facts corrected on all three points above,
and P3 filed under open findings.
