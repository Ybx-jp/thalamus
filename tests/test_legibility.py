"""The degraded-rendering arm.

The instrument exists because a comprehension test run only at full fidelity is blind
to contrast failure by construction (lab/056). These tests hold the two properties the
arm rests on: the transform's threshold-amplifying behaviour is arithmetic and exact,
and the audit separates the criterion the room checked (1.4.3, text) from the one it
missed (1.4.11, meaningful non-text).
"""

from pathlib import Path

import pytest

from thalamus.eval import legibility as leg

AIDS = Path(__file__).resolve().parent.parent / "docs" / "visual"

# The two defects room `atlas` shipped, and the value they were corrected to.
SHIPPED_DEFECT = 2.07
SECOND_DEFECT = 2.97
CORRECTED = 4.24


def test_the_retained_fraction_is_independent_of_the_surface():
    """
    Scenario: the same degradation is applied to aids painting different canvases

    The derivation cancels the surface term, and that is the property that makes one
    number degrade any aid. If it were surface-dependent, every aid would need its own
    calibration and "below threshold lands below the floor" would stop being general.
    """
    a = leg.retained_fraction(3.0, 1.5)
    assert a == pytest.approx(0.5)

    # Solve the same thing numerically against three very different canvases.
    for surface in ("#ffffff", "#f7f7f5", "#808080"):
        ls = leg.relative_luminance(surface)
        s = ls + 0.05
        at_threshold = s / 3.0 - 0.05          # a colour sitting exactly on 3:1
        landed = ls + a * (at_threshold - ls)  # where the transform puts it
        assert s / (landed + 0.05) == pytest.approx(1.5)


def test_below_threshold_lands_below_the_floor_and_at_threshold_lands_on_it():
    """
    Scenario: the arm is asked to separate a defect from a fix

    This is the whole instrument in one assertion. The transform is a threshold
    amplifier: it is not that everything gets fainter (everything does), it is that
    the WCAG threshold is carried onto the legibility floor, so the ordering either
    side of it is preserved and made visible.
    """
    a = leg.retained_fraction(3.0, 1.5)

    assert leg.degraded_ratio(3.0, a) == pytest.approx(1.5)
    assert leg.degraded_ratio(SHIPPED_DEFECT, a) < 1.5
    assert leg.degraded_ratio(SECOND_DEFECT, a) < 1.5
    assert leg.degraded_ratio(CORRECTED, a) > 1.5
    # Verifies: the separation is not a rounding artifact — the corrected marker sits
    # clear of the floor rather than just over it
    assert leg.degraded_ratio(CORRECTED, a) - 1.5 > 0.1


def test_the_shipped_aids_pass_their_own_gate():
    """
    Scenario: `thalamus eval legibility --strict` over what the repo ships

    A gate that cannot pass is a gate nobody runs. These four are the artifacts the
    fix landed on, so a failure here means either a regression in an aid or a defect
    in the instrument, and both are worth stopping for.
    """
    for svg in sorted(AIDS.glob("*.svg")):
        findings = leg.audit(leg.load(svg))
        assert findings, f"{svg.name}: no findings at all — surface detection failed"
        assert not [f for f in findings if f.fails], (
            f"{svg.name}: {[(f.color, round(f.ratio, 2), f.role) for f in findings if f.fails]}"
        )


def test_a_mutant_is_caught_and_its_parent_is_not():
    """
    Scenario: the marker is pushed back to the contrast it originally shipped at

    Ground truth by construction, which is the only honest way to show the arm
    discriminates: "the degraded reader missed it" is unfalsifiable on its own, since
    a reader can miss a thing for any number of reasons.
    """
    source = leg.load(AIDS / "trust.svg")
    assert not [f for f in leg.audit(source) if f.fails]

    mutant = leg.mutate(source, "#6e7781", SHIPPED_DEFECT)
    caught = [f for f in leg.audit(mutant) if f.fails]
    assert len(caught) == 1
    assert caught[0].role == leg.MEANINGFUL
    # Verifies: the mutant lands where it was aimed, so the defect under test is the
    # one that shipped rather than merely some failing value
    assert caught[0].ratio == pytest.approx(SHIPPED_DEFECT, abs=0.02)


def test_text_and_non_text_are_governed_by_different_criteria():
    """
    Scenario: the two WCAG criteria that this room got wrong in opposite directions

    Every reviewer checked 1.4.3 and nobody checked 1.4.11, so an instrument covering
    only one criterion would reproduce the original defect in the other direction. A
    colour at 4.0:1 is fine as a marking and fails as text; the audit must say which.
    """
    assert leg.ROLE_THRESHOLD[leg.TEXT] == 4.5
    assert leg.ROLE_THRESHOLD[leg.MEANINGFUL] == 3.0
    assert leg.ROLE_THRESHOLD[leg.DECORATIVE] == 0.0

    svg = (
        '<svg viewBox="0 0 100 100">'
        '<rect x="0" y="0" width="100" height="100" fill="#ffffff"/>'
        '<text x="1" y="1" fill="#767676">four point five four</text>'
        '<line x1="0" y1="0" x2="9" y2="9" stroke="#9a9a9a" stroke-dasharray="2 2"/>'
        '<line x1="0" y1="0" x2="9" y2="9" stroke="#eeeeee"/>'
        "</svg>"
    )
    by_color = {f.color: f for f in leg.audit(svg)}

    # #767676 is 4.54:1 on white — just over the text floor, and well over 3:1
    assert by_color["#767676"].role == leg.TEXT
    assert by_color["#767676"].passes
    # #9a9a9a is 2.81:1 — under BOTH floors, and it is the dashed one
    assert by_color["#9a9a9a"].role == leg.MEANINGFUL
    assert by_color["#9a9a9a"].fails
    # the plain hairline is governed by nothing, so it raises nothing
    assert by_color["#eeeeee"].role == leg.DECORATIVE
    assert not by_color["#eeeeee"].fails


def test_a_colour_failing_on_the_surface_but_fine_on_a_chip_is_indeterminate():
    """
    Scenario: white text on a dark pill, on a light page

    Measuring every colour against the page canvas reports this as a catastrophic
    1.07:1 failure when it is really 15.8:1 and correct. Resolving it properly needs
    geometry this module does not do — so it names the ground that would save it and
    asks one specific question, rather than crying wolf. An instrument that produces
    false alarms is one that gets ignored, which is the failure this whole line of
    work is about.
    """
    svg = (
        '<svg viewBox="0 0 100 100">'
        '<rect x="0" y="0" width="100" height="100" fill="#f7f7f5"/>'
        '<rect x="10" y="10" width="40" height="10" fill="#1f2328"/>'
        '<text x="12" y="18" fill="#ffffff">on the pill</text>'
        "</svg>"
    )
    white = {f.color: f for f in leg.audit(svg)}["#ffffff"]

    assert white.role == leg.TEXT
    assert not white.passes          # against the page canvas, it does not
    assert white.indeterminate       # but a ground exists that would save it
    assert not white.fails           # so it is not reported as a failure
    assert white.on == ("#1f2328",)  # and the question names exactly which ground


def test_the_full_arm_returns_the_bytes_the_repo_ships():
    """
    Scenario: the control arm of a comprehension test

    The control has to be the artifact itself. Round-tripping it through the colour
    parser would make the control a *rendering* of the aid rather than the aid, and a
    difference between arms could then come from the round trip.
    """
    source = leg.load(AIDS / "loop.svg")
    assert leg.degrade(source, "full") is source


def test_greyscale_is_a_separate_axis_from_contrast():
    """
    Scenario: a distinction carried by hue at adequate luminance contrast

    Composing the two degradations into one arm would make a failure unattributable —
    an aid can be fine on contrast and fail on hue, or the reverse. Greyscale holds
    luminance fixed so that what it tests is *only* whether hue was load-bearing.
    """
    for color in ("#2c6a66", "#a01e1e", "#1f2328"):
        grey = leg.desaturate(color)
        assert leg.relative_luminance(grey) == pytest.approx(
            leg.relative_luminance(color), abs=0.005)
        assert grey[1:3] == grey[3:5] == grey[5:7]

    # And the contrast arm is not silently greyscaling on the way past.
    svg = ('<svg viewBox="0 0 10 10"><rect x="0" y="0" width="10" height="10" '
           'fill="#ffffff"/><text x="1" y="1" fill="#2c6a66">t</text></svg>')
    degraded = leg.degrade(svg, "contrast")
    moved = [c for c in leg.palette(degraded) if c != "#ffffff"][0]
    assert len(set((moved[1:3], moved[3:5], moved[5:7]))) > 1, "contrast arm lost hue"


def test_the_surface_is_the_full_bleed_rect_and_its_absence_is_refused():
    """
    Scenario: an aid that does not paint its own canvas

    The contrast arm compresses *toward the surface*, so without one there is nothing
    to compress toward. Guessing a canvas would silently measure every colour against
    a background the aid does not have, which is the false-positive class the
    indeterminate verdict exists to avoid — so this refuses instead.
    """
    painted = ('<svg viewBox="0 0 200 100">'
               '<rect x="0" y="0" width="200" height="100" fill="#f7f7f5"/></svg>')
    assert leg.surface_of(painted) == "#f7f7f5"

    # A small rect is a component, not a canvas.
    unpainted = ('<svg viewBox="0 0 200 100">'
                 '<rect x="5" y="5" width="20" height="10" fill="#eeeeee"/></svg>')
    assert leg.surface_of(unpainted) == ""
    assert leg.audit(unpainted) == []
    with pytest.raises(ValueError, match="paints no full-bleed rect"):
        leg.degrade(unpainted, "contrast")


def test_a_floor_above_the_threshold_is_refused():
    """
    Scenario: the arm is configured to raise contrast rather than reduce it

    Silently accepting it would produce a variant that is *easier* to read than the
    original while being labelled the degraded arm, which inverts every result read
    off it.
    """
    with pytest.raises(ValueError, match="threshold > floor > 1.0"):
        leg.retained_fraction(threshold=1.5, floor=3.0)
    with pytest.raises(ValueError, match="threshold > floor > 1.0"):
        leg.retained_fraction(threshold=3.0, floor=0.9)


def test_the_palette_scan_reads_strokes_and_not_only_fills():
    """
    Scenario: the audit method that missed both real defects

    The room's reviewer extracted every `fill=` and reported a nine-colour palette as
    five. Every colour it missed was on a stroke — and both defects were strokes, so
    the method could not have found them.
    """
    svg = ('<svg viewBox="0 0 10 10">'
           '<rect x="0" y="0" width="10" height="10" fill="#ffffff"/>'
           '<line x1="0" y1="0" x2="9" y2="9" stroke="#8a9199"/></svg>')
    assert set(leg.palette(svg)) == {"#ffffff", "#8a9199"}
