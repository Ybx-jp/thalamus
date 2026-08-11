"""The degraded-rendering arm — making a comprehension test sensitive to contrast.

[lab/056](../../../lab/056-the-charter-was-wrong-about-our-own-walls.md) recorded the
defect this exists for. Room `atlas` ran a cold-read instrument: rasterise an aid, hand
the image to a fresh reader with no repo access, score against a pre-registered key.
Every reader received a **full-fidelity** rendering, so every reader had perfect contrast
sensitivity, and the instrument was blind to contrast failure *by construction*. Two
dashed markers carrying meaning shipped at 2.07:1 and 2.97:1 — under WCAG 1.4.11's 3:1
floor for non-text content — past two reviewers and three rounds. No comprehension score
could have caught them, because the readers could all see them perfectly.

Both were load-bearing. One marked which trust tiers have no writer; a reader who cannot
resolve it sees the unwritten tiers as ordinary rows, which is the exact false picture the
marking existed to prevent. The other carried the elapsed time between two sessions;
lose it and the two sessions read as one continuous process.

> **The arm turns an accessibility check into a comprehension check** — which is the
> finding, because for these two defects they were the same check.

## Why the SVG is degraded and not the raster

Rasterising then filtering would need an imaging stack, and the harness stays installable
on a box without one (`pyproject.toml` keeps numpy/scipy behind the `experiments` extra).
Transforming the *source* needs no dependency at all, is exact rather than resampled, and
leaves a degraded SVG that can be diffed and looked at. It then renders through whatever
path already renders the original.

## The transform, and why the factor is not picked

Relative luminance is a linear combination of the linearised channels, so compressing
every channel toward the surface compresses the **luminance difference by exactly the same
factor**. With surface luminance `Ls`, a colour at `L`, and a retained fraction `a`:

    L' = Ls + a·(L - Ls)

Requiring that a pair sitting exactly on a WCAG threshold `T` lands on a chosen
just-legible floor `F` gives, with `S = Ls + 0.05`:

    L_T - Ls = S·(1/T - 1)        L_T' - Ls = S·(1/F - 1)
    a = (1/F - 1) / (1/T - 1)

**`S` cancels: the factor is independent of the surface.** One number degrades any aid,
and the arm becomes a *threshold amplifier* — contrast above `T` survives as legible,
contrast below `T` is pushed under the floor. At `T=3.0, F=1.5` the factor is exactly
`0.5`, and the two real defects land at 1.35:1 and 1.50:1 against a fix at 1.62:1.

## What this instrument does and does not claim

It **does** claim: after this transform, a pair that was below the WCAG threshold is
below the legibility floor, and one that was above is above. That is arithmetic, checkable
by `contrast_ratio`, and `report()` prints the mapping so it can be disputed.

It does **not** claim to simulate any particular person's vision. It is a screening
instrument keyed to a published threshold, not a clinical low-vision simulation, and the
distance between those two is not something this module closes. A reader who loses a
distinction in the degraded arm has demonstrated that the distinction was carried by
contrast the threshold does not protect — no more than that, and no claim about
prevalence, severity, or any real reader's experience.

Greyscale is a **separate axis**, deliberately. Removing chroma tests whether a
distinction is carried by hue alone; compressing luminance tests whether it survives
reduced contrast. An aid can pass either and fail the other, so composing them into one
arm would make a failure unattributable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# WCAG 2.2 success criteria, as thresholds rather than as prose.
TEXT_THRESHOLD = 4.5
"""1.4.3 Contrast (Minimum), normal-size text."""

NON_TEXT_THRESHOLD = 3.0
"""1.4.11 Non-text Contrast — graphical objects required to understand the content.
The criterion the room's reviewers did not check, having all checked 1.4.3."""

LEGIBILITY_FLOOR = 1.5
"""Where a pair sitting exactly on the threshold is placed by the transform.

Chosen, not derived — it sets how aggressive the arm is, and it is a parameter rather
than a discovery. What the arm rests on is the *ordering* the transform guarantees
(below-threshold lands below this, at-or-above lands at-or-above), which holds for any
floor in (1, T).
"""

HEX = re.compile(r"#([0-9a-fA-F]{6})\b")


# ---- colour, in WCAG's own terms -------------------------------------------------

def _channel(value: int) -> float:
    """One sRGB byte to its linear-light value (WCAG 2.x relative luminance)."""
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _encode(linear: float) -> int:
    """Linear-light back to an sRGB byte. The inverse of `_channel`, clamped."""
    linear = min(1.0, max(0.0, linear))
    srgb = linear * 12.92 if linear <= 0.0031308 else 1.055 * (linear ** (1 / 2.4)) - 0.055
    return max(0, min(255, round(srgb * 255)))


def rgb(color: str) -> tuple[int, int, int]:
    h = color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def relative_luminance(color: str) -> float:
    r, g, b = rgb(color)
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio. Symmetric, so callers never have to order the pair."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# ---- the transform ---------------------------------------------------------------

def retained_fraction(threshold: float = NON_TEXT_THRESHOLD,
                      floor: float = LEGIBILITY_FLOOR) -> float:
    """The compression factor placing a pair at `threshold` exactly on `floor`.

    Independent of the surface — see the module docstring. Both arguments must exceed
    1.0, since a contrast ratio cannot be less than that, and `floor` must be below
    `threshold` or the transform would be asked to *raise* contrast.
    """
    if not threshold > floor > 1.0:
        raise ValueError(
            f"need threshold > floor > 1.0, got threshold={threshold}, floor={floor} — "
            "a ratio below 1.0 does not exist, and a floor above the threshold would "
            "ask this to increase contrast rather than reduce it"
        )
    return (1 / floor - 1) / (1 / threshold - 1)


def degraded_ratio(ratio: float, retained: float) -> float:
    """Where a pair at `ratio` against the surface lands. The inverse of the derivation."""
    return 1.0 / (1 + retained * (1 / ratio - 1))


def compress(color: str, surface: str, retained: float) -> str:
    """Move `color` toward `surface`, keeping `retained` of the linear-light difference."""
    out = []
    for c, s in zip(rgb(color), rgb(surface)):
        c_lin, s_lin = _channel(c), _channel(s)
        out.append(_encode(s_lin + retained * (c_lin - s_lin)))
    return "#%02x%02x%02x" % tuple(out)


def desaturate(color: str) -> str:
    """Chroma removed, luminance preserved — the greyscale axis, on its own.

    Preserving relative luminance is what makes this test *only* whether hue was
    load-bearing: a distinction that survives here was never carried by colour alone,
    and one that does not was.
    """
    grey = _encode(relative_luminance(color))
    return "#%02x%02x%02x" % (grey, grey, grey)


# ---- reading an aid --------------------------------------------------------------

def palette(source: str) -> list[str]:
    """Every distinct colour in the file, lowercased, in first-appearance order.

    Reads `fill=` and `stroke=` and anything else — a bare hex scan rather than an
    attribute-aware one, because the room's own reviewer audited `fill=` alone and
    reported a nine-colour palette as five, missing both defects on strokes.
    """
    seen: dict[str, None] = {}
    for match in HEX.finditer(source):
        seen.setdefault("#" + match.group(1).lower(), None)
    return list(seen)


def surface_of(source: str) -> str:
    """The opaque canvas the aid paints for itself, or "" if it paints none.

    An aid that ships in a repo cannot see the page theme, so it paints its own surface
    and measures against that (lab/056). The convention is that the surface is the fill
    of the first full-bleed rect, so that is what this reads — the first `fill` on a
    `<rect>` reaching the viewBox origin.
    """
    root = re.search(r'viewBox\s*=\s*"([^"]+)"', source)
    if not root:
        return ""
    for rect in re.finditer(r"<rect\b[^>]*>", source):
        tag = rect.group(0)
        fill = re.search(r'fill\s*=\s*"(#[0-9a-fA-F]{6})"', tag)
        width = re.search(r'width\s*=\s*"([\d.]+)"', tag)
        if not (fill and width):
            continue
        viewbox_width = float(root.group(1).split()[2])
        # Full-bleed within a rounding of the viewBox, so a 0.5 inset hairline counts.
        if float(width.group(1)) >= viewbox_width - 2:
            return fill.group(1).lower()
    return ""


TEXT = "text"
MEANINGFUL = "meaningful"
DECORATIVE = "decorative"

ROLE_THRESHOLD = {TEXT: TEXT_THRESHOLD, MEANINGFUL: NON_TEXT_THRESHOLD, DECORATIVE: 0.0}
"""Which criterion governs which role. Both are carried, because the room checked 1.4.3
and missed 1.4.11 — an instrument that covered only one would reproduce the defect it
was built to catch, in the other direction."""


@dataclass(frozen=True)
class Finding:
    """One colour measured against the surface it sits on."""

    color: str
    ratio: float
    role: str
    """`text` (1.4.3, 4.5:1), `meaningful` (1.4.11, 3:1), or `decorative` (no floor)."""

    on: tuple[str, ...] = ()
    """Other fills in the file this colour would clear its threshold against.

    A colour is measured against the surface, but not everything sits on the surface —
    white text on a dark chip is correct and reads as a catastrophic failure if the page
    canvas is assumed. Resolving that properly needs geometry and z-order this module
    does not do, so where a colour fails against the surface and *would* pass against
    some other fill present in the file, that fill is named and the finding is
    `indeterminate` rather than a failure. One specific question a reader settles by
    looking, instead of a false alarm — an instrument that cries wolf gets ignored,
    which is the failure mode this whole line of work is about.
    """

    @property
    def threshold(self) -> float:
        return ROLE_THRESHOLD[self.role]

    @property
    def governed(self) -> bool:
        return self.role != DECORATIVE

    @property
    def passes(self) -> bool:
        return self.ratio >= self.threshold

    @property
    def indeterminate(self) -> bool:
        return self.governed and not self.passes and bool(self.on)

    @property
    def fails(self) -> bool:
        """Governed, below its floor, and with no other ground that would save it."""
        return self.governed and not self.passes and not self.on


def _colors_in(source: str, pattern: str) -> set[str]:
    return {
        "#" + m.group(1).lower()
        for tag in re.finditer(pattern, source)
        for m in HEX.finditer(tag.group(0))
    }


def audit(source: str, surface: str = "") -> list[Finding]:
    """Every non-surface colour, with the criterion that governs it.

    Roles are read off usage rather than declared, because a declaration is a second
    thing to keep in step with the drawing:

    - **text** — the colour appears on a `<text>` element, or is the file's inherited
      `fill`. Governed by 1.4.3 at 4.5:1.
    - **meaningful** — the colour appears on something carrying `stroke-dasharray`. The
      house convention is that a dashed stroke marks something a reader must resolve,
      which is what both of the room's defects were. Governed by 1.4.11 at 3:1.
    - **decorative** — everything else: hairlines, card borders, rules. No floor applies,
      and inventing one would bury the real findings in noise.

    Text wins where a colour does both jobs, since 4.5 is the stricter floor and a single
    value doing two jobs should be held to the harder one.
    """
    surface = surface or surface_of(source)
    if not surface:
        return []
    text = _colors_in(source, r"<text\b[^>]*>")
    dashed = _colors_in(source, r"<[a-z]+\b[^>]*stroke-dasharray[^>]*>")
    # A root `fill` is inherited by every <text> that does not set its own.
    root = re.match(r"<svg\b[^>]*>", source.lstrip())
    if root:
        text |= _colors_in(root.group(0), r'fill\s*=\s*"#[0-9a-fA-F]{6}"')

    grounds = _colors_in(source, r'<(?:rect|circle|ellipse|path|polygon)\b[^>]*>')

    findings = []
    for color in palette(source):
        if color == surface:
            continue
        role = TEXT if color in text else MEANINGFUL if color in dashed else DECORATIVE
        ratio = contrast_ratio(color, surface)
        rescued: tuple[str, ...] = ()
        if role != DECORATIVE and ratio < ROLE_THRESHOLD[role]:
            rescued = tuple(sorted(
                ground for ground in grounds
                if ground not in (color, surface)
                and contrast_ratio(color, ground) >= ROLE_THRESHOLD[role]
            ))
        findings.append(Finding(color=color, ratio=ratio, role=role, on=rescued))
    return findings


# ---- producing the arms ----------------------------------------------------------

ARMS = ("full", "contrast", "greyscale")
"""The arms a cold read may run. `full` is the original bytes, unmodified — it is named
rather than implied so a results file records which arm produced a score."""


def degrade(source: str, arm: str, *,
            surface: str = "",
            threshold: float = NON_TEXT_THRESHOLD,
            floor: float = LEGIBILITY_FLOOR) -> str:
    """One arm's variant of an aid, as SVG source.

    `full` returns the input unchanged rather than round-tripping it, so the control arm
    is provably the same bytes the repo ships.
    """
    if arm not in ARMS:
        raise ValueError(f"unknown arm `{arm}` — expected one of {', '.join(ARMS)}")
    if arm == "full":
        return source
    if arm == "greyscale":
        return HEX.sub(lambda m: desaturate("#" + m.group(1)), source)

    surface = surface or surface_of(source)
    if not surface:
        raise ValueError(
            "the contrast arm needs the surface the aid measures against, and this file "
            "paints no full-bleed rect — pass `surface` explicitly, or the transform "
            "would compress toward a canvas the aid does not have"
        )
    retained = retained_fraction(threshold, floor)
    keep = surface.lower()
    return HEX.sub(
        lambda m: (color if (color := "#" + m.group(1).lower()) == keep
                   else compress(color, surface, retained)),
        source,
    )


def report(source: str, *, surface: str = "",
           threshold: float = NON_TEXT_THRESHOLD,
           floor: float = LEGIBILITY_FLOOR) -> str:
    """What the contrast arm does to this aid, colour by colour.

    Printed rather than asserted: the instrument's whole claim is arithmetic, so the
    arithmetic is what it shows.
    """
    surface = surface or surface_of(source)
    if not surface:
        return "no full-bleed surface found — this aid does not paint its own canvas"
    retained = retained_fraction(threshold, floor)
    lines = [
        f"surface {surface} · floor {floor}:1 · retaining {retained:.4f} of contrast "
        f"(threshold {threshold}:1 lands on the floor)",
        f"{'colour':9}  {'role':10}  {'needs':>6}  {'before':>8}  {'after':>7}   verdict",
    ]
    for finding in sorted(audit(source, surface), key=lambda f: (-f.threshold, f.ratio)):
        after = degraded_ratio(finding.ratio, retained)
        needs = f"{finding.threshold:.1f}:1" if finding.governed else "—"
        if not finding.governed:
            verdict = "—"
        elif finding.passes:
            verdict = "legible"
        elif finding.indeterminate:
            verdict = f"indeterminate — clears it on {', '.join(finding.on)}"
        else:
            verdict = f"FAILS {finding.threshold}:1"
        lines.append(
            f"{finding.color:9}  {finding.role:10}  {needs:>6}  {finding.ratio:7.2f}:1  "
            f"{after:6.3f}:1   {verdict}"
        )
    return "\n".join(lines)


# ---- mutation, for validating the arm itself -------------------------------------

def mutate(source: str, color: str, target_ratio: float, surface: str = "") -> str:
    """Re-shade `color` to sit at exactly `target_ratio` against the surface.

    The arm has to be shown to discriminate, and the only honest way is a variant whose
    defect is known by construction. A mutant is that variant: take a shipped aid, push
    one marking to a chosen contrast, and check the arm separates it from the original.
    Without this, "the degraded reader missed it" is unfalsifiable — a reader can miss a
    thing for any number of reasons.

    Hue is preserved and only luminance moves, so the mutant differs from its parent in
    the one property under test.
    """
    surface = surface or surface_of(source)
    if not surface:
        raise ValueError("cannot place a ratio without a surface to measure against")
    surface_luminance = relative_luminance(surface)
    s = surface_luminance + 0.05
    # Darker than the surface is the case an aid on a light canvas exercises; the
    # brighter branch is solved from the same identity with the roles swapped.
    if relative_luminance(color) <= surface_luminance:
        wanted = s / target_ratio - 0.05
    else:
        wanted = s * target_ratio - 0.05
    current = relative_luminance(color)
    if abs(current - surface_luminance) < 1e-9:
        raise ValueError(f"{color} already sits on the surface; nothing to scale")
    # Solve for the compression that lands on `wanted`, then apply it per channel.
    retained = (wanted - surface_luminance) / (current - surface_luminance)
    shaded = compress(color, surface, retained)
    return source.replace(color, shaded).replace(color.upper(), shaded)


def load(path: str | Path) -> str:
    return Path(path).read_text()
