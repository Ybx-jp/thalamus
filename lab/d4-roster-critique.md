# D4 — the console roster, measured against what it says it is

The drill asked for a phone redesign of the console's roster view and put critique
before pixels. This file is the critique half. The drawn half is the Penpot file
`D4 console roster`.

Everything below was measured on the running surface at 430×932, not read off the
source. The source was read afterwards, to explain what the measurements found.

## The instrument

`resize_window` reports success and does nothing when the Chrome window is
maximised — it returned `Successfully resized … to 430x932` while `innerWidth`
stayed 1920. A screenshot taken on that promise is a desktop screenshot captioned
as a phone. The working method is a **same-origin iframe** sized to the phone:
media queries resolve against the iframe's viewport, and because the parent
document is the same origin the frame stays scriptable, so geometry can be read
back rather than eyeballed off a picture.

```js
document.documentElement.innerHTML = '<body><iframe src="/console/" ' +
  'style="width:430px;height:932px;border:0"></iframe></body>'
// contentWindow.innerWidth === 430
```

This is the render-and-look loop from the earlier drills, with the same rule: a
number read off the DOM beats a number inferred from an image. Two findings below
(F1, F4) are invisible in a screenshot and only exist because the frame was
scriptable.

## The intent this is measured against

The console states its own design intent, in the first three lines of its
stylesheet. It is unusually explicit, which makes drift measurable rather than a
matter of taste:

> Thalamus console — a signal console. Dark, mobile-first, **one-handed**.
> Signature: **each expert is a relay channel with its own hue** and a live signal
> dot that **pulses when its screen changes**. Everything else stays quiet.
> — `src/thalamus/console/static/style.css:1-3`

Four promises: one-handed, a hue per expert, a pulse on change, and quiet
everywhere else. The last one is kept. The first three are not, and each fails for
a different reason.

## F1 — "each expert with its own hue" is false for three of seven experts

**Measured.** Session identity is a hue drawn from a six-colour palette by hashing
the scope name (`app.js:37-51`). There are seven expert scopes. Running the shipped
hash over the real roster:

| scope | slot | hue |
|---|---|---|
| `architect` | P[3] | `#e07a9c` rose |
| `designer` | P[1] | `#4db6a6` teal |
| `eval-methodology` | P[4] | `#8fce6b` moss |
| `homelab` | P[4] | `#8fce6b` moss |
| `literature` | P[5] | `#c79bf0` orchid |
| `qe` | P[4] | `#8fce6b` moss |
| `teacher` | P[0] | `#e0a45c` amber |

**`eval-methodology`, `homelab` and `qe` are the same colour. `#6db3f2` (sky) is
never used by anyone.** Seven names into six slots guarantees one collision by
pigeonhole; the hash delivers a three-way one and leaves a slot empty.

The source comment states the intent plainly — adding an expert manifest "colours
its tab without anyone editing a table here" (`app.js:39-40`). The mechanism
achieves the automation and loses the property the automation was for. A redundant
identity channel that collides is worse than no channel at all: two tabs in the
same colour do not read as *unassigned*, they read as *related*.

## F2 — the identity palette is very nearly isoluminant

**Measured** with `thalamus.eval.legibility`, the module already shipped for the
degraded-rendering arm. All seven hues, desaturated:

| hue | grey | L |
|---|---|---|
| rose `#e07a9c` | `#9a9a9a` | 0.323 |
| main `#9a8cff` | `#9b9b9b` | 0.328 |
| teal `#4db6a6` | `#a5a5a5` | 0.376 |
| sky `#6db3f2` | `#adadad` | 0.418 |
| orchid `#c79bf0` | `#adadad` | 0.418 |
| amber `#e0a45c` | `#b0b0b0` | 0.434 |
| moss `#8fce6b` | `#bdbdbd` | 0.509 |

Worst pairs: **sky vs orchid 1.00:1 — identical**; main vs rose 1.02:1; amber vs
sky 1.03:1. The whole set spans L 0.32–0.51.

Every hue individually clears 3:1 against the rail, so each is legible *as a mark*.
What collapses is telling them **apart**, which is the only job an identity colour
has.

**The obvious reading of this is wrong, and the literature consultation
(`33e3e972ff6c4d99`) corrected it.** Isoluminance is not a defect per se: Healey
(IEEE Vis '96, 38 observers) deliberately held luminance constant — every colour
drawn from one u′v′ slice at L\* = 67.1 — and still got seven rapidly-searchable
categories. Isoluminance was his *control*, not his flaw. "My hues are isoluminant,
therefore my palette is broken" does not follow.

What is actually wrong is **size**, and it is measurable. The dot is 8 CSS px =
1.27 mm, which at a 30 cm viewing distance subtends **0.243°**. Stone & Szafir
(Color and Imaging Conference 2014, 624 participants) fit colour difference as a
function of mark size and found you need ~6× the textbook JND at 2° and **~11× at
0.33°** — and 0.33° was the *smallest size they tested*. **The console's identity
dot is smaller than the smallest mark at which colour difference has been
measured**, and it is being asked to carry a seven-way categorical distinction.

So the finding stands but its cause moves: not isoluminance, but a mark below the
measured range doing categorical work. The correct verdict is **conditions not
met**, not "demonstrated defect" — Healey's result licenses isoluminant categorical
colour for large marks under central attention with colour distance, linear
separation and category differentiation all controlled. None of those hold here.

### The fix does not fit

Preserving every hue and separating only luminance — exactly the move D3 made for
the signal ramp — takes the worst greyscale pair from 1.00:1 to 1.23:1, but washes
the bright end out to pastel and still lands under D3's declared 1.41:1 floor.

The reason is arithmetic. On `--panel` `#161b22`, the 3:1 non-text floor puts the
dimmest usable identity colour at L = 0.132; the ceiling is white. **At 1.41:1
pairwise separation, six levels fit. The roster needs seven.**

| separation | levels that fit |
|---|---|
| 1.41:1 (D3's floor) | 6 |
| 1.30:1 | 7 |
| 1.23:1 | 9 |

This is an infeasibility proof of the same shape D3 used for the brand pair, and it
settles the redesign's encoding rule: **hue cannot carry seven-way identity on this
surface.** The label must, and hue becomes redundant reinforcement.

## F3 — status and identity share one 8px dot, and reduced motion collapses it

**Measured.** The dot carries five overlapping meanings on two channels — its fill
and its animation:

| state | encoding | survives reduced motion? |
|---|---|---|
| idle | `--faint` `#4d5661` | n/a |
| selected | `--tab` + 7px glow, **plus** 2px top border, panel-hi fill, ink label | yes — border and label |
| screen changed | `--tab` + 5px glow | yes, but see below |
| just changed | expanding ring, 1.1s | **no** — removed, nothing substituted |
| restarting | dot animates faint ↔ `--tab` | **no** — collapses to a static `--tab` dot |

Under `prefers-reduced-motion: reduce` (`style.css:857-860`) `.recycling` becomes a
static `--tab` dot — which is pixel-identical to `.active-live`, and to the selected
dot. **Three distinct states render as one.** The reduced-motion block was written,
which means the hazard was seen; what it does is remove the animation without
putting anything in its place.

And `dead`, `closing` and `policy_stale` have no rail encoding at all. A dead
session's tab is indistinguishable from a live idle one — the state most worth
seeing is the one the rail cannot say.

## F4 — the roster hides itself past five entries, silently

**Measured.** The roster was populated with the *minimum realistic* full
configuration — `main` plus one window per expert scope, eight tabs — by cloning a
live tab and relabelling it, so every width is the shipped CSS measuring real scope
names. The rail's `scrollWidth` is **799px against a 430px viewport, 1.86×**:

```
fully visible : main, architect, designer
clipped       : eval-methodology  (149.9 of 159.9px)
entirely off  : homelab, literature, qe, teacher
```

**Exactly half the roster is off-screen, and this is the floor, not the worst
case** — the operator runs several `main` windows (the live roster had two while
this was measured), and every extra window pushes another name off the right edge.

The scrollbar is explicitly suppressed on both engines (`style.css:157-160`:
`scrollbar-width: none` and `::-webkit-scrollbar { display: none }`). There is no
peek, no gradient, no edge fade, no count. **Half the roster is invisible and
nothing on screen indicates it exists.** A tab that has changed off-screen pulses
where no one can see it, which is the signature feature firing into a void.

**My framing of this was wrong, and the consultation refuted it.** I asked whether
horizontally off-screen content is undiscoverable. There is **no controlled
experiment measuring that at all** — not one — and the mobile data points the other
way: Baymard/ConversionXL logged ~7.5 M carousel interactions over 11 months and
found **72% of visitors advanced the carousel at least once**. The famous
"carousels fail" numbers (Runyon 2013: 1.07% of 3.76 M visits clicked a slide) are
desktop marketing banners with no control condition, and cannot separate "didn't
know slide 2 existed" from "wasn't interested". The NN/g piece most cited for this
exact question reports no study, no n, and no quantitative data.

The defensible concern is **depth, not invisibility**: eye-tracking at n = 87
(IUI '26, SIGIR '26) finds users prefer re-examining the visible items to swiping
for more. That is a claim about effort, not about awareness.

Which still condemns *this* strip, for a reason I had not identified. A
recommendation carousel has a long tail where the first few items dominate, so
depth-aversion costs little. **The roster has no tail — eight sessions, all of
which matter, any of which may be the one that needs attention.** Depth-aversion is
maximally expensive exactly here. And the affordances I would have reached for
first have no measured effect: peek, edge gradient, pagination dots and explicit
counts are all convention, with no discovery-rate measurement behind any of them.

## F5 — two tabs, identical in every channel including the tooltip

**Measured.** The roster currently shows two tabs labelled `main`. Their `title`
attributes are **both** `main — ~/code/thalamus`. Same label, same tooltip, same
hue (`main` is pinned to `MAIN_HUE`, bypassing the hash), same dot. The only thing
separating them is position in the strip.

There *is* a disambiguator: `.chan-tab .cwd`, a second line carrying the working
directory, shown "only while more than one directory is in play" (`style.css:185`).
It is keyed on **cwd**, and both `main` sessions are in the same cwd, so it never
fires. The mechanism is well-built and watches the wrong field — it assumes the only
way to get two identically-named tabs is two directories, and the roster produces
them within one.

A tooltip is also not a disambiguator on a phone. `title` requires hover; there is
no hover. On the surface the console is *for*, the disambiguating information exists
in the DOM and is unreachable.

## F6 — the most-repeated control sits in the least reachable band

**Measured** vertical geometry at 430×932:

| band | y | height |
|---|---|---|
| header | 0 – 41.8 | 41.8 |
| **rail (the roster)** | **41.8 – 77.2** | **35.4** |
| pane | 77.2 – 841.3 | 764.2 |
| composer | 841.3 – 932 | 90.7 |

The roster occupies the top 8% of the viewport. Switching sessions is the console's
primary navigation act, and it is the furthest thing from the thumb on a surface
whose stylesheet says "one-handed". The composer — already at the bottom, already in
reach — is correct; the roster is its mirror image.

**The penalty is measured, and it is severe.** Le, Bader, Kosch & Henze
(NordiCHI 2016, [doi:10.1145/2971485.2971562](https://doi.org/10.1145/2971485.2971562),
n = 24, one-handed, grip changes forbidden) found that only **43.3% of top-row
targets were touched at all** — over half were skipped as unreachable — with
**upper-half error 63.6% against lower-half 42.4%**, and top-row time +636 ms
(+34%), a figure that *understates* the effect because unreachable targets were
excluded from the timing. 21 of 24 participants reported difficulty reaching the
upper half; six reported hand pain.

The dominant cost is therefore **outright non-reachability**, not a gentle accuracy
gradient — which is a stronger objection to a top-mounted roster than the one I
expected to find.

Two qualifications that matter for the redesign:

- Le et al. (CHI 2018,
  [doi:10.1145/3173574.3173605](https://doi.org/10.1145/3173574.3173605), motion
  capture, n = 16) find the thumb's comfortable area is a **fixed ~36 cm² that does
  not grow with the device** (r = −.303, p = .697) — 43.9% of a 4″ face but **26.5%
  of a 5.96″ one**. Every effect size above comes from a phone *smaller* than the
  430×932 target, so they are conservative.
- **The bottom edge is not automatically safe.** Kim & Ji (2018) and Xiong & Muraki
  (2016) both place the lowermost strip outside the natural thumb zone. The good
  region is a band, not a half, so a bottom bar **inset from the edge** beats one
  flush to it.

**Provenance note, and it is a caveat on this section specifically.** The recorded
consultation answer concluded the opposite — that region affects preference but not
measurably error or time, and that no such measurement exists for a modern phone.
Le et al. reached the expert *after* the ticket had been closed, and an agent cannot
reopen an exchange, so **this correction is not in the graph's exchange record**;
it arrived alongside it and is recorded here instead. Two smaller corrections came
with it: Hoober revised his own one-handed figure to "fewer than 50%" in 2017 and
disavowed the earlier assumptions, and the ubiquitous thumb-zone heatmap traces to
**Scott Hurff (2015)**, who drew the zones from his own hand, not to Hoober, who
measured only grip. Anyone citing "Hoober's thumb zones" is merging two sources.

## F7 — hit targets, and a token doing work it was measured unfit for

**Measured.** No interactive target in any roster surface reaches 44 CSS px:

| target | height |
|---|---|
| rail tab (single line) | **34.4** |
| rail tab (two-line form) | ~46.3 |
| workspace chip `.ws` | ~20.5 |
| INFRA row button `.admin-act` | ~25.6 |
| keycap | 25.9 |

Separately, `--faint` `#4d5661` measures **2.32:1 against the rail** `#161b22` —
worse than the 2.54:1 D3 measured against `--bg`, because the rail is the lighter
surface. D3's rule 3 says `faint` is decorative and "if it carries meaning, it is
the wrong token." On the rail it is the **idle dot** — a status — and it is also
`.cwd` and `.cmd`, which are *text* at 8.8px, where the floor is 4.5:1 rather than
3:1. This is the open thread `console-palette-contrast-defects` reaching the surface
it actually damages.

### The threshold, now that it is cited

On a mobile viewport **1 CSS px = 1 dp = 1 iOS pt** — *not* 1/96 inch, which is the
desktop anchor. The wrong anchor turns 34.4 px into 9.10 mm, which sits right on
Parhi's recommendation and would have told me the targets were fine. On the correct
anchor:

| | CSS px | mm |
|---|---|---|
| **rail tab (shipped)** | **34.4** | **5.46** |
| WCAG 2.5.8 (AA) | 24 | 3.81 |
| Apple HIG | 44 | 6.99 |
| Material | 48 | 7.62 |
| **Parhi recommendation (multi-target)** | **60.5** | **9.6** |

Parhi, Karlson & Bederson (MobileHCI '06, n = 20, one-handed thumb, targets
surrounded by distractors at zero spacing — a tab strip's exact geometry) measured
discrete error at 29.9 / 12.9 / 5.0 / 2.8 / 1.6% across 3.8–11.5 mm, with **no
significant difference above 9.6 mm**. That is the knee. The shipped 5.46 mm sits
between their 3.8 mm and 5.8 mm points, interpolating to roughly **14–15% error**.

Because the tabs are full-width strips rather than squares, only the *height* binds,
which is the more forgiving case — Bi & Zhai's success-rate model puts a full-width
34.4 px-tall target at ~2% for an index finger against ~4% for a 34.4 px square.
The tabs are not squares, so the softer number applies; it is still 3–5× the error
of a 44 or 48 px row.

**And none of the platform numbers rest on a measurement.** Apple's 44 pt carries no
citation in the HIG and is justified by a screenshot of Apple's own Calculator app.
Material's 48 dp carries none either; the provenance question was put to Google
directly in 2020 and closed unanswered. WCAG 2.5.5's academic reference is a
finite-element study of fingertip *skin mechanics* containing no target-selection
task and no finger-width survey — while Apple and Google's pages cite the standard
back. The sharpest instance: **WCAG 2.2's AA target size, 24 CSS px, cites Parhi as
its one research reference and sets the floor at 3.81 mm — Parhi's smallest tested
size, at 29.9% error, the very size that paper exists to argue against.**

This is D3's 4.5:1 finding recurring in a harder form, and it is why this critique
specifies **60 px** from the measurement rather than 44 or 48 from a convention.

## F8 — pinch-zoom is disabled

**Measured.** `index.html:20` ships `maximum-scale=1` in the viewport meta. This
prevents the user scaling the page. Given the roster's 8.8px `.cwd` text and 8px
dots, the surface with the smallest type is also the one that cannot be magnified.
Handing this to `qe` as the machine-checkable seam, per the charter.

## What is *not* drift

The pane is right. "Everything else stays quiet" is kept: the roster is genuinely
unobtrusive, the wsbar hides itself when a single directory is in play, and the
recycle note appears only when it has something to say. The composer's bottom
placement and its `env(safe-area-inset-bottom)` padding are correct, and the 16px
textarea font deliberately defeats iOS zoom-on-focus (`style.css:646`). The INFRA
sheet encodes session state as **text**, not colour — which is what the rail should
have done, and evidence the right answer was already in the codebase.

The redesign should take from INFRA, not invent.

## The design that follows

Drawn in the Penpot file `D4 console roster`; PNG at
`lab/assets/d4-console-roster.png`. Four frames: the shipped surface measured, the
proposal at rest, the proposal with the roster open, and two spec frames.

### The structure, and the reason it is *not* the obvious one

The roster becomes a **vertical list in a bottom sheet**, opened from a persistent
56 px bar sitting in the thumb band. The strip goes away.

The reason is not that horizontal overflow is undiscoverable — that is folklore, and
§F4 records the consultation refuting it. The reason is **depth-aversion against a
population with no tail**. Users measurably prefer re-examining what is visible to
swiping for more (eye-tracking, n = 87); a recommendation carousel survives that
because its first few items dominate by design. A roster does not. Any of the eight
sessions may be the one that needs attention, so the cost of the items nobody scrolls
to is total rather than marginal.

Two consequences follow from the same evidence and are worth stating because they
constrain the implementer:

- **Ship a visible control, not a gesture.** 7.5 M logged mobile carousel
  interactions put swipe as the *least*-used path, behind visible thumbnails and
  arrows. The sheet opens from a tapped bar, and the list scrolls; nothing is
  gesture-only.
- **The affordances I would have reached for first are unmeasured.** Peek, edge
  gradient, pagination dots and explicit counts are all convention with no
  discovery-rate measurement behind any of them. The design uses none of them as
  load-bearing, and the aggregate count in the bar is there because it carries
  information, not because it is a signpost.

### The cost, stated

Chrome goes from 168 px (header 42 + rail 35 + composer 91) to 189 px (header 42 +
roster bar 56 + composer 91). **The pane loses 21 px.** That is the whole price, and
it buys the primary navigation out of a band where only 43.3% of targets were reached
at all. The bar also says three things the rail could not: which session you are in,
where it is rooted, and how many others have changed.

Per Kim & Ji (2018) and Xiong & Muraki (2016) the lowermost strip is *outside* the
natural thumb zone, so the bar sits above the composer rather than flush to the
bottom edge.

### Row spec

| property | value | why |
|---|---|---|
| row height | **60 px** (9.6 mm) | Parhi's measured knee, not Apple's 44 or Material's 48 — both below it, neither derived |
| hit area | 66 px, extending **6 px below** the ink | Henze's 0.72–1.50 mm systematic downward tap bias |
| identity bar | 4 px, full height, left edge | redundant reinforcement only |
| name | IBM Plex Mono 14, `--ink` | **this is the identity carrier** |
| second line | IBM Plex Sans 11, `--muted` (4.75:1) | cwd — never `--faint`, which fails as text |
| state | IBM Plex Mono 11, right | a word, always |
| change badge | 26 × 24 pill with a count | its *appearance* is the signal |

Rows carry cwd rather than a last-activity age deliberately: **the console has no
last-activity concept**, and designing a row around a field that does not exist would
be designing against imaginary data. If one is added, this line is where it goes.

### Encoding rules

1. **Identity is the label.** Hue is redundant and never sole — the infeasibility
   proof in F2 is why, not taste.
2. **Status is a word**, always, with colour and weight layered on top. This is
   already what the INFRA sheet does; the rail is the outlier.
3. **"Changed" is a badge that appears.** This is the one genuinely load-bearing
   design move and it comes straight from the record: an abrupt onset captures
   attention where a colour or brightness singleton does not (Jonides & Yantis 1988),
   and unlike an animation a badge *persists*, so it is still findable on return in
   near-constant time. It therefore survives `prefers-reduced-motion` **by
   construction** rather than by a fallback.
4. **Motion may be layered on top and never alone.** Bartram's orthogonality result
   says the layering is free; the persistent half carries the meaning when motion is
   removed. Nothing regresses to a single channel, which is precisely the failure F3
   found.
5. Every state the rail cannot currently say — `dead`, `closing`, `policy_stale` —
   has a row encoding.

### What this design does not settle

The literature will not decide the horizontal-vs-vertical question, and the strongest
warning in the whole consultation is that small-n lab rankings in this area reversed
in the wild once device and target density varied. **If this matters enough to build,
instrument it** — the console already polls, and a counter on roster-open and
session-switch would settle in a week what no citation can.

## Handoffs

- `qe` — F8 (pinch-zoom disabled) and F7's contrast failures are conformance
  checks, not judgement calls. This is the WCAG seam the charter names.
- The open thread `console-palette-contrast-defects` gains a second surface and
  should not be closed on the `--bg` measurement alone; `--faint` is worse on
  `--panel`, which is where it is actually used.
