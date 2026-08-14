# Visual design — related work

The design canon this scope reasons from. [docs/11](../11-related-work.md) is the
memory, retrieval and evaluation literature; this is the perception and interaction
literature, and it lives separately because it is a **different domain, held by a
different scope**.

That separation is the point. `config/experts/designer.yaml` declares `tier: 2`
("design literature is tier 2 forever"), the `literature/finding` and
`literature/technique` claim kinds, and an allowlist of design-canon publishers, with
a note that the book-shaped parts of this canon arrive as hand-fed local files. The
scope was built to hold this material. Everything below is now in the graph under
`--scope designer`, so a designer session recalls it directly rather than spending a
consultation ticket to learn its own field.

## How to read a claim here

Four labels, carried from the same discipline [docs/11](../11-related-work.md) uses:

- **measured** — a study reports this number under stated conditions.
- **inference** — it follows from a cited result but was not itself measured. Say so.
- **convention** — widely repeated, no measurement behind it.
- **not found** — searched for and absent. Weak evidence, phrased provisionally.

The recurring lesson of this canon is that the labels do not line up with authority.
Several of the most-cited normative numbers in interface design are **convention**,
and one of them cites a real measurement in order to land on that measurement's worst
condition.

## 1. Touch targets

**measured.** Parhi, Karlson & Bederson, *Target Size Study for One-Handed Thumb Use
on Small Touchscreen Devices*, MobileHCI '06,
[doi:10.1145/1152215.1152260](https://dl.acm.org/doi/10.1145/1152215.1152260). n = 20,
one-handed right thumb, standing, targets surrounded by distractors at zero spacing —
a tab strip's exact geometry. Discrete-task error by target size:

| mm | 3.8 | 5.8 | 7.7 | 9.6 | 11.5 |
|---|---|---|---|---|---|
| error | 29.9% | 12.9% | 5.0% | 2.8% | 1.6% |

The knee is at **9.6 mm**: no significant error difference between 9.6 and 11.5,
though speed keeps improving. Recommendations are **9.2 mm single-target, 9.6 mm
multi-target** — and the 9.2 is *inference inside the paper*, from hit-distribution
analysis plus subjective ratings, so cite it as "Parhi's recommendation", not "Parhi
measured 9.2".

Serial (repeated) tapping has a **lower** error knee than discrete — 7.7 mm against
9.6 mm — which inverts the usual intuition that repeated targets need to be larger.
The recommendation still lands at 9.6 because serial error was uniformly higher at
every common size.

**measured.** Henze, Rukzio & Boll, *100,000,000 Taps*, MobileHCI '11 — 120.6 M touch
events. Two structural results transfer even though its absolute rates are a
stress-test ceiling (a time-pressured game, no target preview; the authors say so):
**border targets error at 31.68% against 17.59% in the centre** for sub-12 mm targets,
and users tap a systematic **0.72–1.50 mm below** key centres (CHI '12, 47.8 M
keystrokes). Extending a hit region below its ink is close to free and recovers most
of the second effect.

**measured.** Bi, Li & Zhai's dual-Gaussian / FFitts decomposition (CHI '13) gives an
irreducible finger precision σ_a = 0.94 mm (1D) / 1.5 mm (2D) — you cannot slow down
past it — and Bi & Zhai (UIST '16) turn it into a success-rate model,
`SR = erf(W/2√2σ_x)·erf(H/2√2σ_y)`, validated at W = 2–8 mm with >180 participants.
It is fit on **index fingers**, not thumbs.

### The unit, which decides the answer

**measured (definitional).** On a mobile viewport **1 CSS px = 1 Android dp = 1 iOS
pt**. It is *not* 1/96 inch — that anchor is for print and desktop. The wrong anchor
inflates a measurement by ~1.7× and reliably produces the reassuring answer. Convert
before arguing.

### Guideline provenance — the finding that generalises

**convention, all of it.**

- **Apple's 44 pt** (6.99 mm) carries no citation in the HIG. The justification
  offered is a screenshot of Apple's own Calculator app. The number is simultaneously
  the standard nav-bar and table-row height.
- **Material's 48 dp** (7.62 mm) carries none either; the provenance question was put
  to Google in 2020 ([material-components-android
  #1279](https://github.com/material-components/material-components-android/issues/1279))
  and closed unanswered. Google's own accessibility page then miscomputes 48 dp as
  "about 9 mm" — it is 7.62 — an 18% overstatement that lands the figure inside the
  uncited 7–10 mm band being used to justify it.
- **WCAG 2.5.5 (AAA, 44 CSS px)** cites the platform guidelines, which cite nothing,
  plus Dandekar et al. 2003 — a finite-element study of fingertip *skin mechanics*
  with no target-selection task and no finger-width survey.
- **WCAG 2.2's SC 2.5.8 (AA, 24 CSS px)** lists exactly one research reference:
  Parhi. On a phone 24 CSS px is **3.81 mm** — Parhi's *smallest tested size, at 29.9%
  error*, the size that paper exists to argue against.
- **"The MIT Touch Lab found the average finger pad is 10–14 mm"** is folklore; the
  finding is not in the paper it cites, and competing versions of the number circulate.

The honest form is: "Parhi measured a one-handed-thumb error knee at 9.6 mm and
recommends 9.2; Apple's 44 pt and Material's 48 dp are 7.0 and 7.6 mm, both below it,
and neither publishes a derivation."

## 2. Colour as a categorical channel

**measured.** Healey, *Choosing Effective Colours for Data Visualization*, IEEE
Visualization '96, 38 observers. **Seven** categories can be rapidly and accurately
detected in each other's presence — *from a deliberately isoluminant slice* through
CIE LUV at L\* = 67.1 — but only with colour distance, linear separation and colour
category differentiation controlled simultaneously. His first seven-colour set failed;
a second, category-corrected set succeeded. At seven and nine colours results were
"mixed": green and green-yellow developed 17–19 ms/element search slopes, i.e. stopped
being preattentive.

Two consequences worth stating plainly:

- **Isoluminance is not a defect per se.** "My palette is isoluminant, therefore it is
  broken" does not follow — Healey's control was isoluminance.
- **The "5 to 7 colours" rule is convention.** Healey quotes it as anecdotal evidence
  from an F-16A/B cockpit display retrofit (Hitt 1992) and notes the authors "offer no
  explanation for why this might be the case."

**measured.** Stone & Szafir, *An Engineering Model for Color Difference as a Function
of Size*, CIC 2014, 624 participants. Required colour difference scales as
`ND(p,s) = C + K/s` — linear in inverse size. A theoretical JND of 1 needs to be
**~6 at 2°** and **~11 at 0.33°**, and the weightings on L\*, a\*, b\* degrade
unevenly. 0.33° was their smallest tested size. **A mark smaller than that is outside
the measured range entirely**, which is the check to run before asking a small chip to
carry a categorical distinction. Extended in Szafir, IEEE TVCG 24(1), 2018.

**measured.** In the periphery we are nearly colour-blind (Bartram, Ware & Calvert
2003, citing Wyszecki & Stiles): peripheral colour miss rate rises **5.5% → 24%** and
detection time 2.3 s → 4.6 s from near to far field, and even when a colour change is
detected observers cannot say *which* item changed more than 15% of the time.
Conditions note: a phone at ~30 cm subtends only ~12–25° total, so the whole screen
sits inside their near band — the peripheral argument is weak for a handheld and
strong only for a propped second screen.

**measured.** Birch, *Worldwide prevalence of red-green color deficiency*, JOSA A
29(3), 2012: **~8% of men and ~0.4% of women of European ancestry**; 4–6.5% in men of
Chinese and Japanese ethnicity. Quote it with the ancestry qualifier — a large recent
meta-analysis gives 4.38% male overall, which a bare "8% of men" misstates.

### What the named palettes guarantee

- **Okabe-Ito** (Color Universal Design, 2002) — 8 colours, CVD-safe by construction
  and verification, and **deliberately not isoluminant**: it varies brightness and
  saturation, which is also why it survives greyscale. It is the direct
  counter-example to an isoluminant categorical set. No claim about small marks.
- **ColorBrewer** (Harrower & Brewer, 2003) — the load-bearing fact is that among the
  **qualitative** schemes the colourblind-safe filter **tops out at 4 classes**. It
  cannot supply a CVD-safe categorical 7. Designed for choropleth areas, not chips.
- **Crameri et al.**, *Nature Communications* 11:5444, 2020 — perceptual uniformity and
  monotonic lightness for **continuous** maps, with CVD-safe variants. It makes **no
  categorical-discriminability claim**; citing it for a qualitative UI palette is a
  category error.

**inference.** Every published artefact guaranteeing categorical CVD-safety does it by
varying lightness, and the one that reaches 8 varies it most. There is no published
isoluminant categorical palette above Healey's 7.

## 3. Horizontal overflow versus a vertical list

**not found.** No controlled experiment measures whether users *know* content exists
off-screen horizontally, or compares that to a vertical list. This is the single
largest gap in this canon relative to how confidently the question is usually answered.

**convention, widely miscited.** The famous carousel numbers are Runyon's 2013
Notre Dame analytics — 1.07% of 3.76 M visits clicked any slide, 89.1% of those on
slide 1. No control condition, desktop, marketing content, and it cannot separate
"didn't know slide 2 existed" from "wasn't interested". The NN/g piece most cited for
mobile carousels reports no original study, no n, and no quantitative data; the
"number one usability problem" claim rests on **one user's** comment.

**measured, and it points the other way.** Baymard/ConversionXL logged ~7.5 M mobile
carousel interactions over 11 months: **72% of visitors advanced the carousel at least
once**, and **swiping was the least-used interaction** — visible thumbnails (55%) and
arrows beat gestures. Peer-reviewed work agrees directionally (Kim et al., CIKM '16;
Warr & Chi, CHI '13; Dou & Sundar, IJHCI 2016, n = 252).

**measured — the defensible objection.** Eye-tracking at n = 87
([arXiv:2507.10135](https://arxiv.org/abs/2507.10135),
[arXiv:2604.21019](https://arxiv.org/abs/2604.21019)): **users prefer re-examining the
visible items to swiping for more**, swipes launch almost exclusively from the
rightmost visible item, and the assumed left-to-right decay fails. That is a claim
about **depth**, not visibility — so it bites hardest on a population with **no long
tail**, where any item may be the one that matters. Desktop, movie-selection task.

**not found.** No measured discovery-rate effect for a peek, an edge gradient, a
visible scrollbar, pagination dots, or an explicit count. All convention. The peek has
one gaze-transition inference behind it and no A/B test anywhere.

**measured, and the standing warning for this whole section.** Henze, Poppinga & Boll
(NordiCHI '10, ~3,934 accounts) **reversed the lab rankings in the wild** depending on
target density and device. Small-n lab findings here do not reliably survive contact
with real devices — which is the argument for instrumenting a decision rather than
citing one.

## 4. Thumb reach

**measured.** Le, Bader, Kosch & Henze, NordiCHI 2016,
[doi:10.1145/2971485.2971562](https://doi.org/10.1145/2971485.2971562), n = 24, 9 mm
targets, grip changes forbidden: **only 43.3% of top-row targets were touched at all**
(upper-left 38.3%) — over half skipped as unreachable. Upper-half error **63.6%**
against lower-half 42.4%; top row +636 ms (+34%), a figure that *understates* the
effect because unreachable targets were excluded from timing. 21 of 24 reported
difficulty reaching the upper half; 6 reported hand pain.

**The dominant cost is outright non-reachability, not an accuracy gradient.**

**measured.** Le et al., CHI 2018,
[doi:10.1145/3173574.3173605](https://doi.org/10.1145/3173574.3173605), motion
capture, n = 16: the thumb's comfortable area is a **fixed ~36 cm² that does not grow
with the device** (r = −.303, p = .697) — 43.9% of a 4″ face, **26.5% of a 5.96″ one**.
The penalty therefore worsens as phones grow, and every effect size above comes from a
phone smaller than a modern one, so they are conservative.

**measured.** Bergström-Lehtovirta & Oulasvirta, CHI 2014, n = 20, model the thumb's
functional area from grip kinematics. It is a **geometric reach model** and measures
neither time nor error inside versus outside the region.

**measured.** The bottom edge is **not** automatically safe: Kim & Ji (2018) and
Xiong & Muraki (2016) both place the lowermost strip outside the natural thumb zone.
The good region is a band, not a half — a bottom bar inset from the edge beats one
flush to it.

**measured (mechanism).** Reaching straight up is thumb flexion–extension, the
biomechanically inefficient direction (Trudeau, *Human Factors* 2012; Xiong & Muraki,
*Ergonomics* 2014, EMG-confirmed). The effect is an **axis** effect, not a distance
effect.

### Two attributions to get right

- **Hoober's grip figures are observational, not peer-reviewed, and he revised them.**
  The 2013 UXmatters study made 1,333 street observations (780 touching the screen):
  49% one-handed, 36% cradled, 15% two-handed. No demographics, no protocol, no
  inter-rater reliability, never replicated, and the author explicitly warns against
  converting his counts to population percentages. **In 2017 he revised to "fewer than
  50%" one-handed and disavowed the earlier assumptions** as "anecdotes or
  misrepresented data."
- **The thumb-zone heatmap is not Hoober's.** It traces to **Scott Hurff (2015)**, who
  drew the zones from his own hand and caveated "maybe you have bigger hands than I
  do." Hoober measured *grip*; Hurff drew *reach*. Citing "Hoober's thumb zones" merges
  two sources, and the diagram half is **convention** — Hoober describes his own reach
  charts as "coarse and vague because they are guidelines."

## 5. Motion, and what replaces it

**measured.** Bartram, Ware & Calvert, *Moticons*, IJHCS 58(5), 2003. Motion is the
best **capture** channel available: ~0% detection error, **flat from 7° to 52°
eccentricity**, against colour 5.5% → 24% and shape 2.0 → 4.4 s. Detection time ~1.0 s
flat for motion.

**measured.** It is also one of the worst **identification** channels. Motion type
beats direction except at 90° separation (Bartram & Ware 2002); non-coherent flicker
is at chance (Huber & Healey, IEEE Vis 2005: error 0.465 vs 0.009 coherent). Flicker
discrimination is ΔF 2–5% at the fovea but 100%+ in the periphery. **Motion has fewer
usable levels than colour.**

**measured.** Rensink, O'Regan & Clark, *Psychological Science* 8(5), 1997: masking the
motion transient takes change detection from **0.9 s to 10.9 s — about 12×** — on large
changes observers knew were coming.

**measured, and it is the design pivot.** Jonides & Yantis, *Perception &
Psychophysics* 43(4), 1988: **abrupt onsets capture attention involuntarily; colour and
brightness singletons do not.** Abrams & Christ (2005) refine it to the *onset* of
motion rather than motion itself. So **a badge appearing is an onset transient** — it
captures like animation, and unlike animation it **persists**, so it is still findable
on return in near-constant time (Treisman & Gelade 1980: feature search 3.1 ms/item
flat, against conjunction search 28.7 ms/item).

|  | captures when not looking | cheap to find on return |
|---|---|---|
| animation | **yes** | **no** — already over |
| persistent colour badge | **no** | **yes** |
| badge *appearing* | **yes** | **yes** |

**measured.** McCrickard et al., IJHCS 58(5), 2003, 70 participants: noticing latency
was ticker 54.3 s vs **instantaneous swap 33.6 s** vs fade 35.5 s — the smoothly
animated display was **65% slower to notice** than the instantaneous persistent change.
Bartoli & Benedetto, *PLoS ONE* 2022, N = 1,009: badged apps drew significantly more
first-clicks across all 15 conditions, all p < .001.

**measured.** Bartram's G1: motion "does not seem to interfere with existing colour and
form coding" — so layering motion on a persistent base is free. Tuning parameters from
the same paper: amplitude ~1° suffices (G3); 1–3 Hz all worked with no frequency effect
(G4); travelling and zooming are significantly more distracting than anchored motion
(G7, blink < linear < zoom < travel); slow linear oscillation is the sweet spot (G8).

**The design consequence: layer, do not substitute.** A state carried by a word plus a
persistent badge loses nothing when motion is removed, because motion was never the
sole carrier.

### prefers-reduced-motion

**not found.** No browser or OS vendor publishes user-side prevalence, and no published
RUM dataset exists. Any percentage in circulation is unsourced. What HTTP Archive
measures is the share of **pages shipping the query** (~50% by 2024–25) — developer
adoption, inflated by framework resets. The setting is also flipped for performance on
low-end hardware and in VMs, so the population is "users who will not see your
animation" — which is the population that matters — and **not** "users with a
vestibular disorder." **inference:** the only trustworthy figure for a given product is
to beacon `matchMedia('(prefers-reduced-motion: reduce)').matches` once per session.

**measured, and routinely misused.** Agrawal et al., NHANES 2001–2004, n = 5,086:
35.4% of US adults 40+ had vestibular dysfunction — but that is **postural dysfunction
on a modified Romberg test**, not sensitivity to interface animation. Vestibular
migraine, the more relevant construct, is **0.89–2.70%** of the general population
(Paz-Tamayo et al., 2020, N = 41,127). The circulated "8 million US adults" figure is
sourced to an advocacy site, not a study.

**convention.** WCAG **2.3.3 Animation from Interactions** cites no measurement, no
study and no prevalence figure; its reference list is MDN, a WebKit demo, CSS-Tricks,
A List Apart, an Apple support page and *Laptop Magazine*. It is a reasoned
accommodation and a defensible one — but citing it is citing an argument, not a
finding. **SC 2.2.2 Pause, Stop, Hide** binds harder and is easier to miss: it covers
**auto-updating content with no five-second exemption at all**, which puts any polling
roster inside it.

## 6. What this canon keeps teaching

Three patterns recur across every section above, and they are the reason this document
is organised by evidence rather than by topic:

1. **The normative number is usually convention.** 44 pt, 48 dp, "5 to 7 colours",
   the thumb-zone heatmap, every carousel affordance, WCAG 2.3.3. The one AA target-size
   threshold that cites a real measurement uses it to justify that measurement's worst
   condition. Check provenance before repeating a figure — the check has never yet come
   back clean.
2. **A correct measurement can carry a wrong diagnosis.** Isoluminance measured right
   and read backwards; horizontal overflow condemned for a reason the record refutes.
   The measurement and its interpretation are separate claims and need separate labels.
3. **Conditions travel worse than results.** Healey on a calibrated CRT under central
   fixation, Parhi on a 3.5″ PDA standing, Bartram at 7–52° eccentricity, every
   thumb-reach study on a phone smaller than the one in your hand. Say *conditions not
   met* — which is honest and usually sufficient — rather than *demonstrated not to
   work*, which is a result nobody has.

## Provenance of this document

Assembled from consultation tickets `cfd9f409951e48c0` (D3 — polarity, contrast,
typography) and `33e3e972ff6c4d99` (D4 — targets, categorical colour, overflow, reach,
motion), both answered by the `literature` scope going to primary sources because
neither its corpus nor this one held the material. The sources behind §1, §2, §4 and §5
are now ingested under `--scope designer` and recallable here; the D3 material
(Buchner 2009, Dobres 2016/2017, Henderson & Cote 1998) is **not yet ingested** and
remains a gap.

Two caveats the record itself demands:

- The §4 corrections (Le 2016/2018, the Hoober revision, the Hurff attribution) reached
  this scope **after** ticket `33e3e972ff6c4d99` had closed, and an agent cannot reopen
  an exchange — so the graph's exchange record for that ticket states the opposite of
  §4 and is superseded here.
- Contrast ratios throughout rest on WCAG 2.x, whose 4.5:1 is a 1988 CRT-workstation
  standard multiplied by 1.5, and whose +0.05 flare term misbehaves badly on dark
  surfaces (see [docs/11](../11-related-work.md) and `lab/d3-identity-spec.md`).
  Orderings survive that; absolute values are approximate.
