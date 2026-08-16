"""The sizes §2 fixes are numbers, so they are checkable.

`lab/d4v2-handoff-spec.md` §2 sets six geometry figures and §4.3 sets a seventh, each
with a measurement behind it — Parhi's low-error band for the row and the destructive
controls, Yamanaka & Usuba's 4 mm for their separation, and the height change that
carries a terminal row without being read. Four of the seven had drifted by the time
anyone looked, and every one of them had drifted *in the declaration*: a `44px` where
the spec says 60, a `width` never overridden, a `text-transform` nobody costed.

**This file reads declared values, which is the weaker claim.** A declaration is not
what reaches the screen — a later rule, a flex parent or a transform can take a
declared 60 px and paint 44. `tests/js/contrast-dom.js` is the companion that measures
a real browser and says at length why static checks are blind; the same blindness
applies here. What this file buys is the cheap half: it runs in CI, it names a figure
against its spec line, and it is the check that would have caught all four drifts.

The rendered measurement is the one that settles conformance and is taken by hand
against a console on a spare port, the same way `contrast-dom.js` is driven.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS = Path(__file__).parent.parent / "src" / "thalamus" / "console" / "static" / "style.css"


def _block(selector: str) -> str:
    """The declarations of the last rule whose selector list contains `selector`.

    Last rather than first: a later rule of equal specificity wins in the cascade, so
    reading the first one would assert against a value the browser discards.

    Comments come out before anything is matched. This sheet explains its figures
    where it declares them — several of these numbers sit directly under the sentence
    justifying them — and a check that reads prose is a check that passes on a comment
    claiming the value it could not find.
    """
    text = re.sub(r"/\*.*?\*/", "", CSS.read_text(), flags=re.S)
    pattern = re.compile(r"([^{}]*?)\{([^{}]*)\}", re.S)
    found = [m.group(2) for m in pattern.finditer(text)
             if selector in [s.strip() for s in m.group(1).split(",")]]
    assert found, f"no rule for `{selector}` in style.css"
    return found[-1]


def _px(selector: str, prop: str) -> float:
    """A declared pixel length, or a failure naming what is missing."""
    block = _block(selector)
    m = re.search(rf"(?:^|;)\s*{re.escape(prop)}\s*:\s*([0-9.]+)px", block)
    assert m, f"`{selector}` declares no px `{prop}`"
    return float(m.group(1))


# ---- §2, the geometry table ----

def test_a_collapsed_row_is_60px():
    """9.5 mm — Parhi's low-error band, not his worst."""
    assert _px(".srow", "min-height") == 60


def test_the_group_header_is_44px():
    """Not a target; label only, so it takes the smaller figure deliberately."""
    assert _px(".grp", "height") == 44


def test_the_identity_bar_is_a_4px_rule_on_a_collapsed_row():
    assert _px(".srow::before", "width") == 4


@pytest.mark.parametrize("selector", [".srow-act", ".band-x"])
def test_a_destructive_control_is_at_least_60_in_both_axes(selector):
    """§2: `destructive control | >= 60 x 60 px`.

    Both axes. `.band-x` shipped 60 x 44 under a comment asserting ">=60 px", which was
    true of the width — a floor met on one axis is a target still 44 px tall under the
    thumb. `.srow-act` takes its width from `flex: 1 1 0`, so only its height is
    declared here and the row's own width carries the other axis.
    """
    assert _px(selector, "min-height") >= 60
    if selector == ".band-x":
        assert _px(selector, "min-width") >= 60


def test_destructive_controls_are_separated_by_4mm():
    """Yamanaka & Usuba 2019: unintended taps 5.2% -> 0% across 0-4 mm, no cost in time."""
    assert _px(".srow-acts", "gap") >= 25


# ---- §4.3, the terminal row ----

def test_a_terminal_rows_identity_bar_is_a_block_not_a_rule():
    """§4.3, third of the five channels: "a solid full-height block, not a 4 px rule".

    Asserted against the collapsed bar rather than against 12, because the figure is
    not what the spec decided — the *difference* is. A later change may widen both.
    """
    collapsed = _px(".srow::before", "width")
    terminal = _px(".srow.terminal::before", "width")
    assert terminal > collapsed, "the terminal bar is still the collapsed row's rule"
    assert terminal >= 3 * collapsed, (
        f"{terminal}px against a {collapsed}px rule does not read as a block")


# ---- §3.3, the group header label ----

def test_the_group_header_does_not_transform_its_label_case():
    """§3.3: the header prints `project`, or `basename(repo_root)`.

    Both are names with a case of their own, and `repo_root`'s basename is a path
    component on disk. Uppercasing shows the operator a string that is not the one
    the ledger recorded — the same defect class as §3.4's "a guess wearing the group
    header", one step smaller.
    """
    assert "text-transform" not in _block(".grp"), (
        "`.grp` transforms the case of a label the spec says is a name")
