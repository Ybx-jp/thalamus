# Thalamus identity — specification

The drawn artefact is the Penpot file `D3 identity board`. This file is the other half
of it, and it exists because Penpot cannot hold the system: every colour and typography
tool the MCP exposes is a getter (`get_colors_library`, `get_typography_library`,
`get_design_tokens`), so shared assets cannot be written. A "system" here is a drawn
board plus this document, and nothing enforces the link but discipline.

Every ratio below was computed with `thalamus.eval.legibility`, the module that already
ships for the degraded-rendering arm. None of them is an estimate — but see **Prior
work** for what the model computing them can and cannot support.

## The argument

Thalamus already had three visual identities and they disagreed:

| surface | palette | provenance |
|---|---|---|
| console PWA | `#0e1116` / `#cdd8e4` / `#4db6a6` / `#9a8cff` | chosen by someone |
| graph viewer | `#1e293b` / `#64748b` / `#2563eb` / `#ef4444` | Tailwind defaults |
| repo diagrams | `#1f2328` / `#57606a` / `#6e7781` | GitHub's greys |

The system keeps what was **chosen**, retires what was **defaulted**, and does not
invent a fourth. The console is the basis because it is the surface the operator
actually touches and because its values were picked rather than inherited.

## Tokens

### Neutral — taken from the console unchanged

| token | value | on `#0e1116` | role |
|---|---|---|---|
| `bg` | `#0e1116` | — | the canvas |
| `panel` | `#161b22` | 1.09:1 | raised surface |
| `hair` | `#2a323d` | 1.46:1 | decorative rules only |
| `faint` | `#4d5661` | 2.54:1 | **decorative only** — below the 3:1 non-text floor |
| `muted` | `#7d8794` | 5.19:1 | secondary text, passes AA |
| `ink` | `#cdd8e4` | 13.09:1 | primary text |

`faint` is the one to watch: at 2.54:1 it fails WCAG 1.4.11 for anything
meaning-carrying. It is legal as a hairline and illegal as an icon.

### Brand — a pair, not a colour

| token | value | measured |
|---|---|---|
| `brand-on-dark` | `#9a8cff` | 6.82:1 on `#0e1116`; **2.77:1 on white — fails** |
| `brand-on-light` | `#6f65bb` | 4.60:1 on `#f7f7f5`, 4.94:1 on `#ffffff`; **3.83:1 on `#0e1116` — fails** |

Two tokens because each of these colours was measured failing on the other's surface —
2.77:1 and 3.83:1, both well under any candidate floor. That is the whole argument, and
it rests on this palette rather than on a borrowed number.

The repo's 4.35:1 figure is *not* the justification, though an earlier draft of this
document used it that way. It is an infeasibility proof for the "theme-neutral ink"
constraint that the `author-repo-diagram` skill already dropped, and 4.35-vs-4.5 is a
3% gap against a threshold whose provenance is far coarser than three digits imply
(literature, ticket `cfd9f409951e48c0`). It is context, not a budget.

### Signal — functional, never brand

| token | value | on `#0e1116` | was |
|---|---|---|---|
| `danger` | `#c55b50` | 4.49:1 | `#e0685c` |
| `warn` | `#c18c4e` | 6.42:1 | `#e0a45c` |
| `ok` | `#54c5b3` | 9.02:1 | `#4db6a6` |

Hue is never the only carrier. The shipped console encodes status in hue alone: its
signal colours sit within 1.13:1 of each other in luminance, so `danger` and `muted`
are 1.09:1 apart and become the same grey under greyscale or red-blindness. Worse, the
order is scrambled — desaturated, the shipped `warn` (`#b0b0b0`) reads *brighter* than
the shipped `ok` (`#a5a5a5`).

The corrected ramp is spaced to 1.41:1 minimum pairwise and rises monotonically with
severity: desaturated it is `#7b7b7b` → `#969696` → `#b3b3b3`. The 1.41:1 figure is
**declared here, not cited** — it is one step of a √2 ladder, chosen because it is the
smallest separation that survived the greyscale render legibly, not because a study
names it.

Hues are preserved from the console throughout; only luminance moved.

## The mark

A relay: several channels converge on one ring, one gated path leaves. The thalamus is
the brain's relay station, and the system routes many sessions through one scoped
memory, so the figure is literal on both readings.

Construction, in a 96-unit box:

- ring: centre (56, 48), r = 14, stroke 8
- inbound: three strokes from x = 6 to x = 34, at y = 20→38, 48→48, 76→58
- outbound: one stroke, (78, 48) → (90, 48)
- 8-unit gap between every stroke terminal and the ring edge
- round caps throughout, matching the D2 terminal style

Scaled to 24 px the stroke lands at exactly 2 px — the D2 icon weight — so the mark
scales *into* the icon set rather than sitting beside it. It is drawn once and scaled
uniformly; there is no separate small-size cut.

Known collision risk: at small sizes the fan reads as "merge" or "converge". That
misreading is semantically adjacent and was accepted deliberately, following D2's rule
that the move is not to escape collision but to choose one whose misreading is true.

## Type

**IBM Plex Mono** (wordmark, code, identifiers) and **IBM Plex Sans** (prose, labels,
UI). Catalogue ids `gfont-ibm-plex-mono` and `gfont-ibm-plex-sans`; weights in use are
regular, 500 and 600, and all four faces are confirmed loading in the exported SVG.

Two reasons, and only one of them is a design argument:

1. **Paired by provenance.** They are one designed superfamily on a shared skeleton, so
   the pairing rests on the type designer's own system. The craft rule that one pairs
   faces by *contrast* of skeleton is convention; no measurement is offered for it here
   and none was found, so the choice is deliberately one that does not depend on it.
2. **Mono leads because the product is a CLI and a terminal PWA.** The wordmark is set
   in the face the operator types into. The console's own stylesheet already reaches for
   a monospace stack for screen text.

The wordmark is lowercase `thalamus` because the command is.

## Rules

1. Brand tokens are surface-bound. Never use `brand-on-dark` on a light canvas.
2. Status is never carried by hue alone — pair it with luminance, an icon, or a label.
3. `faint` is decorative. If it carries meaning, it is the wrong token.
4. Any aid that must survive both themes paints its own opaque surface first, and all
   contrast is measured against that surface rather than the page.
5. The mark is drawn once and scaled uniformly. No optical small-size variant exists
   yet; if one is cut, it is a new artefact and gets its own measurement.

## Prior work

Grounded through literature ticket `cfd9f409951e48c0`, answered with eight validated
citations after the expert reported the predicted thin-recall signature for visual
topics in that scope and went to primary sources. Claims are marked measured,
inference, or convention, per the discipline.

- **Dark-first is a product choice, not a legibility claim** (measured, and against us).
  The positive-polarity advantage — dark text on light — is real and large, but Buchner,
  Mayr & Brandt (2009) show it is a *luminance* effect that vanishes when luminance is
  equalised, and Dobres (2017) shows it collapses to p = 0.665 under bright ambient
  light. The eye-strain claim specifically is measured and **null**. So "a dark UI is
  easier on the eyes" is folklore the record contradicts; this identity is dark-first
  because that is the surface the operator uses, which is a reason evidence does not
  touch either way. The light-surface pair is therefore load-bearing, not a courtesy.
- **The contrast model is coarser than its digits** (measured). WCAG 2.x's 4.5:1 is
  3:1 — a 1988 CRT-workstation standard — multiplied by 1.5 from a one-page conference
  supplement. Its +0.05 term is sRGB's fixed 5% viewing-flare constant, which on
  `#0e1116` is about **nine times the background's actual luminance**; this is exactly
  why the model misbehaves on dark surfaces. Consequence for this document: the
  *ordering* of these ratios is sound, the absolute values are approximate, and the
  greyscale-separation argument — which is a comparison — survives better than any
  "passes AA" statement.
- **APCA is not an escape** (measured). No peer-reviewed validation, removed from the
  draft in 2023, and its own author agrees it is not a standard; WCAG 3 is a Working
  Draft whose algorithm is literally written `@@[contrast measure to be determined]`.
  Neither model has been validated against reading performance. WCAG 2.x is used here
  because it is the only model anything enforces, not because it is right.
- **Typeface style is not where legibility interventions go** (measured). Dobres (2016)
  measures typeface style at η²_G = 0.01 against polarity at η²_G = 0.13 in the same
  experiment. Small size is where the effect lives (d rises 0.28 → 0.72 from 4 mm to
  3 mm). This is a *convergence*: the mono/sans choice here was already argued on
  provenance and product honesty, never on legibility.
- **Pairing is convention with zero measurement** (convention — confirmed). The single
  paper called "font pairing" mines a design-specimen site and measures fashion, not
  effect. The expert added the useful consequence: every measured hierarchy lever lives
  *inside* one family, and only skeleton contrast requires a second face — which is an
  argument for the superfamily, arrived at independently.
- **"Simple marks are more memorable" is refuted** (measured). Henderson & Cote (1998)
  found elaborateness did not predict recognition (p = .533) or false recognition
  (p = .509); design explains 3–10% of recognition variance. The construct that does
  transfer to a favicon is ISO 9186-2 *element identification at rendered size* — which
  is what the 24 px / 2 px check above actually tests. No memorability claim is made
  for this mark, and none should be.
- **Icon contrast has a stricter reading than 1.4.11** (measured). IBM Carbon requires
  icons at 4.5:1, not WCAG's 3:1. Under either threshold `faint` at 2.54:1 fails, so
  that finding stands and strengthens.

Not found in this scan: any measured basis for pairing rules, and any visual-design
section in `docs/11-related-work.md` at all.

## Not settled

- The consultation's named ingest candidates — the Dobres 2016/2017 pair and Henderson
  & Cote 1998 — have **not** been ingested, so the citations above live in the exchange
  record and this file but not yet in the graph. `docs/11` has no visual-design section
  and was being edited by another session at the time of writing, so it was left alone.
  Doc and graph are therefore out of step on exactly this material.
- The identity is a drill deliverable. Nothing has adopted it: the console, the viewer
  and the diagrams are all unchanged, and the viewer's Tailwind defaults are the first
  thing this system would retire.
