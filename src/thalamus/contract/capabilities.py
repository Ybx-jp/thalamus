"""Dimensions — one choice with a closed set of variants, and what each variant sets.

A dimension is harness-neutral: a variant says *what* it sets (a model class, an
effort level) and never *how* a harness spells it. The spelling is the harness layer's
job, done where each generated artifact is rendered, so one selection lands on every
carrier from one declaration rather than being restated per harness.

The rule a variant is held to is that everything it sets is read by code. A variant
that could only change prose is not one, which is why `SETTINGS` is a closed list of
keys each of which some renderer reads.

Mutual exclusion is the only relation between variants — a scope selects exactly one,
and a dimension always names the variant an unselected scope gets (Kconfig's `choice`
block with a default). Nothing here lets one selection force another dimension's
value; Kconfig's `select` does that without checking the forced symbol's own
dependencies, and that is the relation this module does not have.

`launcher.Capability` is the harness-specific sibling: a posture whose *options differ
per harness* and contribute argv directly. A dimension is the opposite shape — one
variant list, projected onto each harness by its renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The capability classes a variant may ask for, weakest first. A class, never a model
# name: the name is a harness's projection and changes with every release, while the
# manifest that selects a class is operator-owned and should not have to.
MODEL_CLASSES = ("light", "standard", "strong", "frontier")

# Effort levels, lowest first, in Claude Code's vocabulary (`--effort`, agent `effort:`).
EFFORTS = ("low", "medium", "high", "xhigh", "max")

# What a variant may set, and the values each key admits. Closed, so a typo in a
# variant table fails at import rather than rendering a field no harness reads.
SETTINGS = {
    "model_class": MODEL_CLASSES,
    "effort": EFFORTS,
}


@dataclass(frozen=True)
class Variant:
    """One selectable value of a dimension."""

    # Stable id, and what a manifest writes. Never the label, so relabelling does not
    # reinterpret a stored selection.
    value: str
    label: str
    # What selecting it sets, keyed from `SETTINGS`. Empty is a real answer: it is the
    # variant that sets nothing and leaves every carrier at its own default.
    sets: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for key, setting in self.sets.items():
            if key not in SETTINGS:
                raise ValueError(f"variant `{self.value}` sets unknown key `{key}`")
            if setting not in SETTINGS[key]:
                raise ValueError(
                    f"variant `{self.value}` sets {key}={setting!r}; "
                    f"expected one of {', '.join(SETTINGS[key])}"
                )


@dataclass(frozen=True)
class Dimension:
    key: str
    title: str
    variants: tuple[Variant, ...]
    # What a scope that selects nothing gets. It has to be the variant that preserves
    # shipped behaviour, or declaring the dimension would itself change every launch.
    default: str

    def __post_init__(self) -> None:
        values = [v.value for v in self.variants]
        if len(set(values)) != len(values):
            raise ValueError(f"dimension `{self.key}` repeats a variant")
        if self.default not in values:
            raise ValueError(f"dimension `{self.key}` defaults to undeclared `{self.default}`")

    def variant(self, value: str) -> Variant:
        """The named variant. An unknown value raises: a selection is written by the
        operator into a manifest, and a manifest that names a variant this release does
        not have should fail to load, not launch at a default it never asked for."""
        for variant in self.variants:
            if variant.value == value:
                return variant
        raise ValueError(
            f"`{value}` is not a `{self.key}` variant; "
            f"expected one of {', '.join(v.value for v in self.variants)}"
        )


# What an expert's sessions run on. Selected per scope in its manifest (`cost:`).
COST = Dimension(
    key="cost",
    title="Cost",
    variants=(
        Variant("inherit", "Inherit the caller's model and effort"),
        Variant("frugal", "Frugal", {"model_class": "standard", "effort": "low"}),
        Variant("balanced", "Balanced", {"model_class": "strong", "effort": "medium"}),
        Variant("max", "Max", {"model_class": "frontier", "effort": "high"}),
    ),
    default="inherit",
)
