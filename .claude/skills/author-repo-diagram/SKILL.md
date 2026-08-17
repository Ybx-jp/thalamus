---
name: author-repo-diagram
description: Authoring hand-written SVG diagrams that ship in a repo and render on GitHub — the contrast ceiling that decides whether an aid may paint its own surface, GitHub's two rendering facts, palette closure including the non-text 3:1 rule, and the render-and-look and desc-drift disciplines. Use BEFORE drawing or revising any SVG committed to the repo, when picking a diagram's colours at all, when a diagram must read in both light and dark, and before claiming a figure is accessible.
---

# Authoring a Diagram That Ships in a Repo

A diagram committed to a repo is read by strangers on a surface you do not control, in a theme you
cannot detect, sometimes by someone who cannot see it. Five things decide whether it works,
and four of them are settled before the first shape is drawn.

## 1. You cannot make one ink work on both themes. Paint your own surface.

Sweep all 256 neutral greys, maximising the *worse* of the two contrast ratios against
GitHub's canvases (`#ffffff` and `#0d1117`):

```
best neutral grey: #797979 → 4.35:1
WCAG AA, normal text: 4.5:1
```

**4.35 is the ceiling for any single ink asked to sit on both.** Coloured inks do worse
than the neutral optimum, not better. So "theme-neutral ink" buys AA only at ≥24px labels,
which is a poster, not a diagram.

> **Every aid paints an opaque surface rect as its first element, and all contrast is
> measured against that known canvas rather than against the page.**

A working pair: ink `#1f2328` on surface `#f7f7f5` = 14.73:1, secondary `#57606a` = 5.96:1.
The aid then reads as a deliberate card on a dark page rather than a light diagram that
failed to adapt, and it survives screenshot, paste, and print.

The `<picture>` + `prefers-color-scheme` route is the documented alternative and it costs
**two files per aid** that must be kept in visual step — a drift bug waiting for the first
revision. Take it only if something else forces it.

## 2. Two GitHub facts, both found the expensive way

- **GitHub's Markdown sanitiser strips inline `<svg>`.** The carrier page must *reference*
  image files (`![alt](visual/x.svg)`), never paste markup.
- **`prefers-color-scheme` inside a referenced SVG resolves against the reader's OS**, not
  the GitHub theme they picked, and it does not work in Safari at all. A light-OS reader
  in dark GitHub gets the light artwork on a dark page — precisely the failure the media
  query was reached for. CSS inside an SVG loaded as an image also cannot match ancestor
  selectors, so `html[data-color-mode]` is unreachable from inside the file.

> **Never put `prefers-color-scheme` inside a standalone SVG.**

## 3. Palette closure — and non-text contrast is a *different* criterion

Enumerate every colour in the file and classify each one:

| class | rule |
|---|---|
| **surface** | the canvas the aid paints |
| **decorative** | hairlines, card borders, rules — carry no meaning; no threshold applies |
| **text** | ≥ 4.5:1 against its surface (WCAG 1.4.3) |
| **meaning-carrying non-text** | ≥ **3:1** against its surface (WCAG **1.4.11**) |

**The fourth row is the one that gets missed.** In the room that produced this skill, two
dashed markers shipped at **2.07:1** and **2.97:1** through two review rounds and two
reviewers, because everyone checked text contrast and non-text contrast is a separate
success criterion nobody owned. Both were load-bearing: one marked which tiers have no
writer, the other carried the elapsed time between two sessions.

A dashed pattern, a shape, or a position is what keeps a distinction from being carried by
colour alone — but the stroke still has to be perceivable. Check both.

```python
def lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def luminance(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

def contrast(a, b):
    hi, lo = max(luminance(a), luminance(b)), min(luminance(a), luminance(b))
    return (hi + 0.05) / (lo + 0.05)
```

## 4. Render it and look. Reading the markup is not checking.

```
google-chrome --headless --disable-gpu --screenshot=/tmp/aid.png \
  --window-size=1400,1100 /abs/path/to/aid.svg
```

Then **open the PNG**. Four real defects in the room that produced this skill were
invisible in source and obvious in the image: a stroke drawn through the most load-bearing
sentence in the aid, a callout clipped by the card below it, a note overflowing its card,
and a mono span colliding with text. Hand-authored SVG has no layout engine — nothing
reflows, and nothing warns you.

A rendered PNG that nobody opens produces the feeling of having checked. Look at it.

## 5. `<desc>` is the aid, delivered to a reader who cannot see it

Every aid carries `<title>` and `<desc>`, and the `<desc>` must teach the same thing the
picture teaches — in the same words, with no term the visible text has stopped using.

> **After any visible change, re-read `<title>` and `<desc>`.**

This drifts silently, because revising a picture never puts its description in front of
anyone. In the room that produced this skill it happened **twice in one session to the same
author**, once leaving a term undefined that had been removed from the visible text, and
once leaving the pre-fix version of a story the picture had already corrected. That is a
habit failing twice, which is the case for a rule rather than an intention.

## 6. Name the wrong reading and deny it

An aid that states the right answer beside an undisturbed wrong prior does not displace it.
Aids that explicitly *named and denied* the misreading beat a no-aid control three for
three in the cold reads that measured this — the reader arrives holding a wrong model, and
the picture has to contradict it, not merely out-argue it.

Concretely: *"These are not three sizes of the same thing, and you do not escalate along
them"* does work that a correct description of the three options does not.

## The check before you call it done

- [ ] Surface painted as the first element; all contrast measured against it
- [ ] Text pairs ≥ 4.5:1; meaning-carrying non-text ≥ 3:1
- [ ] No `prefers-color-scheme` anywhere in the file
- [ ] Every distinction also carried by shape, position or label — survives greyscale
- [ ] Rendered, and **looked at**
- [ ] `<title>` and `<desc>` present, current, and free of terms the picture dropped
- [ ] Referenced from the carrier page as an image file, with alt text
