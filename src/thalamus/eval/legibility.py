"""WCAG contrast arithmetic — the one place it is computed.

Split off `thalamus-eval`'s degraded-rendering research instrument (the SVG-aid
"arm" that tests whether a comprehension failure is actually a contrast failure)
when that module moved to a private companion repo. This piece stayed because
`tests/test_console_contrast.py` — which checks the live console's own CSS custom
properties, not a research artifact — depends on it directly, and the WCAG math has
one owner rather than a third hand-rolled copy.
"""

from __future__ import annotations

# WCAG 2.2 success criteria, as thresholds rather than as prose.
TEXT_THRESHOLD = 4.5
"""1.4.3 Contrast (Minimum), normal-size text."""

NON_TEXT_THRESHOLD = 3.0
"""1.4.11 Non-text Contrast — graphical objects required to understand the content."""


def _channel(value: int) -> float:
    """One sRGB byte to its linear-light value (WCAG 2.x relative luminance)."""
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


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
