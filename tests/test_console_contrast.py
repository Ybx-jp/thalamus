"""The console's text tokens must stay legible, and that is checkable.

The roster draws a non-observation dimmed, and §4.5 makes that the *majority* state
on some vantages — descriptors are partitioned by config dir, so a console can be
structurally unable to read most of them. A dim with no floor therefore made the
most common thing on the surface its least legible thing, at 2.54:1 against the page.

The dim was never what separates a reading from a non-observation: the mono versus
proportional-italic split is, and it survives a legible grey. So the floor costs the
design nothing, which is the argument for holding it here rather than in anyone's
judgement. Contrast is arithmetic over two colours; a review is not.

Ratios are WCAG 2.x relative luminance. 4.5:1 is AA for body text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS = Path(__file__).parent.parent / "src" / "thalamus" / "console" / "static" / "style.css"
AA = 4.5


def _tokens() -> dict[str, str]:
    """The `:root` custom properties, as authored."""
    root = re.search(r":root\s*\{(.*?)\}", CSS.read_text(), re.S)
    assert root, "no :root block in style.css"
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", root.group(1)))


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    out = 0.0
    for channel, weight in zip((h[0:2], h[2:4], h[4:6]), (0.2126, 0.7152, 0.0722)):
        c = int(channel, 16) / 255
        out += weight * (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def contrast(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def test_the_ratio_maths_is_right():
    """A checker that computes the wrong number passes everything forever."""
    assert contrast("#ffffff", "#000000") == pytest.approx(21.0, abs=0.01)
    assert contrast("#000000", "#000000") == pytest.approx(1.0, abs=0.01)
    # Order must not matter: the pair has one ratio, not two.
    assert contrast("#8b95a3", "#0e1116") == pytest.approx(contrast("#0e1116", "#8b95a3"))


# The grounds each text token is actually painted on. `--bg` is the page and the
# sheets; `--panel` is what an opened or terminal row paints under its own text;
# `--panel-hi` is chips, buttons and the selected tab, where only `--muted` and
# `--ink` are drawn. Listing them per token rather than crossing every pair keeps
# this asserting what is true — a checker that fails on a combination nothing draws
# gets relaxed, and a relaxed checker is the one that stops being read.
GROUNDS = {
    "ink": ("bg", "panel", "panel-hi"),
    "muted": ("bg", "panel", "panel-hi"),
    "faint": ("bg", "panel"),
}


@pytest.mark.parametrize(
    "token,ground",
    [(t, g) for t, grounds in GROUNDS.items() for g in grounds])
def test_text_tokens_clear_aa_on_every_ground_they_sit_on(token: str, ground: str):
    t = _tokens()
    assert token in t and ground in t, f"token or ground missing: {token} / {ground}"
    ratio = contrast(t[token], t[ground])
    assert ratio >= AA, (
        f"--{token} on --{ground} is {ratio:.2f}:1, below AA {AA}. "
        f"Dimming is not what carries the non-observation voice — the typeface split "
        f"is — so this can be raised without costing the design anything."
    )


def test_the_tiers_stay_distinguishable():
    """Legible is the floor, not the goal: three tiers that converge are one tier.

    A fix that satisfied the floor by flattening `faint` into `muted` would trade a
    legibility failure for a hierarchy failure, and the roster's line-2 lane depends
    on reading quieter than the session name above it.
    """
    t = _tokens()
    on_bg = {k: contrast(t[k], t["bg"]) for k in ("ink", "muted", "faint")}
    assert on_bg["faint"] < on_bg["muted"] < on_bg["ink"], on_bg
    assert on_bg["muted"] - on_bg["faint"] >= 0.5, (
        f"faint and muted are {on_bg['faint']:.2f} and {on_bg['muted']:.2f} — "
        "too close to read as separate tiers")
