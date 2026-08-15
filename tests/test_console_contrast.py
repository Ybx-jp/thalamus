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

from thalamus.eval import legibility

CSS = Path(__file__).parent.parent / "src" / "thalamus" / "console" / "static" / "style.css"
AA = 4.5


def _tokens() -> dict[str, str]:
    """The `:root` custom properties, as authored."""
    root = re.search(r":root\s*\{(.*?)\}", CSS.read_text(), re.S)
    assert root, "no :root block in style.css"
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", root.group(1)))


# The WCAG arithmetic has one owner. `eval/legibility.py` already carried it before
# this file existed, and it was hand-rolled three more times in one day — here, and
# twice in ad-hoc scripts — which is the same second-owner problem the rest of this
# suite is about, wearing a different hat.
contrast = legibility.contrast_ratio


def test_the_ratio_maths_is_right():
    """A checker that computes the wrong number passes everything forever.

    Kept after moving to the shared implementation, because "we import it" is not the
    same claim as "it is correct", and this file's assertions are only worth what the
    ratio is.
    """
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
    # Status hues carry a signal wherever they are painted, and `--pending` carries
    # text on the wait note, so both are held to the text floor on all three.
    "ok": ("bg", "panel", "panel-hi"),
    "pending": ("bg", "panel", "panel-hi"),
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


# Every colour the stylesheet spells out instead of naming. A literal is not a
# contrast bug by itself — it is the condition that makes contrast bugs invisible,
# because `_tokens()` reads `:root` and a literal is nowhere in it. So each one is
# declared here with the ground it is painted against and the floor that applies,
# and an undeclared literal fails the closure test below rather than being measured
# by nobody. `role` is what the colour means; if it cannot be stated, the colour is
# probably decoration that should have been a token.
LITERALS = {
    "#0b0e12": ("text on a filled control — chips, keycaps, primary actions", "chan", 4.5),
    "#4a2a29": ("the loose-chip and error border, a non-text carrier", "panel", 0.0),

    # Stated rather than composited. It was `#4db6a6` at `opacity: .5`, which paints
    # a colour appearing nowhere in the file: the declared teal measured 7.05:1 while
    # the surface received 2.72:1, under a 3:1 floor. An `opacity` is invisible to
    # every check here, so the receded value is written out where it can be measured.
    "#327e62": ("the done dot, receded from --ok — colour is the whole encoding",
                "panel", 3.0),

    "#100f1b": ("the base layer under the terminal art", "bg", 0.0),
}


def _literals() -> set[str]:
    """Hex colours the stylesheet spells out, minus the `:root` declarations."""
    text = CSS.read_text()
    root = re.search(r":root\s*\{(.*?)\}", text, re.S)
    assert root
    declared = set(re.findall(r"#[0-9a-fA-F]{6}", root.group(1)))
    return {c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}", text)} - {
        c.lower() for c in declared}


APP = CSS.parent / "app.js"


def _palette() -> dict[str, str]:
    """The identity hues, read from the client that owns them.

    `--chan` and `--tab` are assigned from JS, so the ground under a filled tab is
    not in the stylesheet at all and no amount of CSS parsing reaches it. The set is
    closed — `hueOf` draws from exactly this list — which is what makes it assertable
    without a browser.
    """
    source = APP.read_text()
    main = re.search(r'MAIN_HUE\s*=\s*"(#[0-9a-fA-F]{6})"', source)
    block = re.search(r"PALETTE\s*=\s*\[(.*?)\]", source, re.S)
    assert main and block, "MAIN_HUE / PALETTE not found in app.js"
    hues = {"main": main.group(1).lower()}
    for i, hue in enumerate(re.findall(r"#[0-9a-fA-F]{6}", block.group(1))):
        hues[f"palette[{i}]"] = hue.lower()
    return hues


def test_the_identity_palette_is_legible_in_both_roles():
    """A hue is a ground under `#0b0e12` on a filled tab and a foreground on a panel,
    so it carries an obligation in both directions and neither is in the stylesheet.

    Asserted against the palette constant rather than a rendered page: the set is
    closed, so this is complete without a browser, and it fails the day someone
    widens the palette — which is a live prospect, since the roster has seven expert
    scopes and the luminance budget fits six.
    """
    tokens = _tokens()
    for name, hue in sorted(_palette().items()):
        on_hue = contrast("#0b0e12", hue)
        assert on_hue >= AA, (
            f"{name} {hue} is {on_hue:.2f}:1 under #0b0e12 text on a filled control")
        as_ink = contrast(hue, tokens["panel-hi"])
        assert as_ink >= AA, (
            f"{name} {hue} is {as_ink:.2f}:1 as text on --panel-hi")


def test_identity_colour_and_status_colour_share_no_value():
    """Two registries, two meanings, and a shared hex is a second owner for one fact.

    An identity hue is assigned by hashing a scope name, so it must mean *nothing* —
    a row is teal because of what it is called, never because it is well. A status
    colour means exactly one thing. Measured 2026-08-15: `#4db6a6` was both the
    palette's teal and the live beacon / ok dot, and `#e0a45c` both amber and the
    pending dot, so the status vocabulary was leaking onto rows at random and the
    palette could not be retuned without silently moving the status colours with it.

    Only signal-carrying literals are in scope. A border or an art base layer may
    coincide with a hue without asserting anything, because it does not mean anything.
    """
    # Both the literals that carry a signal and the status *tokens*. The fix for this
    # finding promoted two carriers from literals to tokens, which would have moved
    # them out of a literals-only scan — the guard would have gone green by losing
    # sight of its subject rather than by the collision being resolved.
    carriers = {c for c, (_, _, floor) in LITERALS.items() if floor > 0}
    t = _tokens()
    carriers |= {t[name] for name in ("ok", "pending") if name in t}
    collisions = {c.lower() for c in carriers} & {
        v.lower() for v in _palette().values()}
    assert not collisions, (
        f"{sorted(collisions)} serve as both an identity hue and a status colour. "
        f"Identity is assigned by hashing a name and must stay meaningless; a status "
        f"colour means one thing. Give the status carrier its own value.")


def test_every_colour_the_stylesheet_spells_out_is_declared():
    """Closure over the colour vocabulary, which is what makes the other checks mean
    something.

    A token-level check can only measure what `:root` names. Measured 2026-08-15 the
    stylesheet also carries 5 bare literals across 27 occurrences, and every one of
    them was outside the *range* of the shipped checker — not a missing row in a
    table, a colour the parser structurally cannot see. Two of the surface's real
    contrast defects live on colours in this set.

    So the assertion is not "no literals". It is that a literal is *declared*: named,
    with the ground it sits on and the floor that applies to it. A new one fails here
    and has to be either promoted to a token or given a role — which is the moment
    somebody thinks about its contrast, and the moment that was missing.
    """
    undeclared = _literals() - set(LITERALS)
    assert not undeclared, (
        f"undeclared colour literal(s) in style.css: {sorted(undeclared)}. Promote to "
        f"a `:root` token, or add to LITERALS with the ground it is painted on and "
        f"the floor that applies — a colour nothing can name is a colour nothing can "
        f"measure.")


def test_the_literal_registry_describes_colours_that_are_still_there():
    """The registry is a declaration, and a declaration rots in the other direction.

    A row for a colour the stylesheet no longer uses is a measurement of nothing that
    still reads as coverage — the same way the brief's own Part A table went on naming
    `#4d5661` and `#7d8794` after the palette had moved past them. Stale entries are
    removed, not kept "in case".
    """
    stale = set(LITERALS) - _literals()
    assert not stale, (
        f"LITERALS names colour(s) the stylesheet no longer contains: {sorted(stale)}")


@pytest.mark.parametrize("literal", sorted(LITERALS))
def test_each_declared_literal_clears_the_floor_its_role_implies(literal: str):
    """A floor of 0.0 is an explicit "this carries nothing", not an oversight."""
    role, ground, floor = LITERALS[literal]
    if floor == 0.0:
        return
    t = _tokens()
    assert ground in t, f"{literal} declares ground --{ground}, which is not a token"
    ratio = contrast(literal, t[ground])
    assert ratio >= floor, (
        f"{literal} ({role}) is {ratio:.2f}:1 on --{ground}, below its {floor} floor")


def test_faint_is_conformant_only_on_the_grounds_it_is_declared_for():
    """The pairing is the unit of conformance, so a narrow declaration is load-bearing.

    `--faint` measures 4.95 on `--bg` and 4.53 on `--panel` — and **4.15 on
    `--panel-hi`**, which is why `GROUNDS` lists only the first two and style.css:12
    says so in prose. That exclusion is not documentation, it is the thing keeping a
    failing pair off the surface: one new rule painting faint inside an opened row's
    chip ground fails silently at 4.15, and no token-level check would see it.

    Asserting the *excluded* pair genuinely fails keeps the exclusion honest in both
    directions. If someone lightens `--faint` until panel-hi clears, this test says so
    and the declaration may widen deliberately. Until then, widening it is a change
    somebody has to argue for rather than one that slips through.
    """
    t = _tokens()
    assert "panel-hi" not in GROUNDS["faint"], (
        "GROUNDS now lets --faint paint on --panel-hi; if that is intended, this test "
        "is the one that has to change, and the ratio below is why")
    assert contrast(t["faint"], t["panel-hi"]) < AA, (
        "--faint now clears AA on --panel-hi, so the exclusion in GROUNDS has stopped "
        "being load-bearing — widen it deliberately rather than leaving a rule whose "
        "reason has expired")
    # And the ground it *is* declared for has almost no room left: `--panel` may not
    # drift darker, nor `--faint` dimmer, without taking the pair under the floor.
    assert contrast(t["faint"], t["panel"]) >= AA


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


# Every `opacity` below 1, with why it is allowed. An opacity is not a contrast bug
# by itself — it is the mechanism that makes contrast bugs *unmeasurable*, because it
# paints a colour appearing nowhere in the file. Worse, it compounds: opacity on a
# container multiplies with opacity on its descendants, so a subagent thinking block
# once painted its own label at .72 × .7 × .85 = 0.4284, and 2.15:1, through three
# rules none of which looked wrong alone.
#
# So each one is declared with its role, and a new one fails the closure test below —
# which is the moment somebody measures it, and the moment that was missing.
OPACITIES = {
    ".25": "the pending dot's pulse trough — animation on a non-text carrier",
    # Exempt under 1.4.3 as an inactive control — but the exemption is *earned*, not
    # claimed. A disabled `.srow-act` is also how an opened row shows an operation in
    # flight, and a control that carries state is not merely inactive. What keeps the
    # exemption honest is that the state is carried in text as well: `rowState` draws
    # `restarting 0:42` into `.srow-pill` at --danger, 5.19:1 on --panel. The dimming
    # reinforces; it does not carry. `test_the_disabled_exemption_is_still_earned`
    # below is what stops that from quietly ceasing to be true.
    ".4": "disabled controls — exempt as inactive, and the in-flight state they also "
          "signal is carried in text by the pill beside them",
    ".7": "the passthrough composer: dimming a redirected control is the signal, "
          "and --ink at .7 measures 6.46:1 on --panel",
}


def test_every_opacity_is_declared():
    """Closure over the one mechanism every static contrast check is blind to.

    Measured 2026-08-15: four undeclared opacities on text produced five AA failures,
    the worst at 2.15:1 — below anything the token or literal checks had found, and
    invisible to both, because the colour that reaches the surface is in no file.

    A declaration cannot prove the composited value is legible; only a rendered-DOM
    check can. What it does is stop one appearing *silently*, which is how all four
    of these arrived.
    """
    found = set(re.findall(r"opacity:\s*([0-9.]+)", CSS.read_text()))
    undeclared = {o for o in found if float(o) < 1} - set(OPACITIES)
    assert not undeclared, (
        f"undeclared opacity value(s) in style.css: {sorted(undeclared)}. Declare the "
        f"role, or express the recession as a colour — `opacity` composites to a value "
        f"nothing here can see, and it multiplies with any opacity above it.")


def test_the_disabled_exemption_is_still_earned():
    """The one role in the registry that can stop being true with nothing changing.

    `opacity: .4` on a disabled control is exempt under 1.4.3 — but only while the
    control is genuinely inactive rather than carrying meaning. On an opened row a
    disabled action is *also* how an operation in flight is shown, and at .4 it
    measures 1.99:1 for `--muted`, so if the dimming were ever the only channel
    saying "restarting" the exemption would be doing work it cannot do.

    It is not the only channel: `rowState` renders the op as text. This asserts that
    directly, so removing the word — or moving it into the disabled state alone —
    fails here rather than silently converting a reinforcement into a carrier.

    A colour check cannot see this, which is the point. The exemption's premise is a
    redundancy claim, and a redundancy claim is assertable even when the thing it
    licenses is not.
    """
    app = APP.read_text()
    for word in ("restarting", "closing"):
        assert re.search(rf'`{word} \$\{{|"{word}"|`{word} ', app), (
            f"`{word}` is no longer rendered as text by the client, so the disabled "
            f"control's dimming may now be the only thing saying an operation is in "
            f"flight — at which point opacity .4 is a carrier, not reinforcement, and "
            f"the 1.4.3 exemption in OPACITIES no longer applies.")


def test_the_opacity_registry_describes_declarations_that_are_still_there():
    """A registry rots in both directions; a row for a rule nobody has reads as
    coverage of a thing that no longer exists."""
    found = {o for o in re.findall(r"opacity:\s*([0-9.]+)", CSS.read_text())
             if float(o) < 1}
    stale = set(OPACITIES) - found
    assert not stale, (
        f"OPACITIES names value(s) style.css no longer declares: {sorted(stale)}")
