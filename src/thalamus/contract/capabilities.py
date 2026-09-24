"""Dimensions — one choice a scope makes, answered by a preset the operator names.

A dimension declares *what may be set* — a closed list of keys, each with its closed
list of values — and nothing about which combinations exist. The combinations are the
operator's: named presets in `presets/<dimension>.yaml` under the config root, selected
by name from a manifest. One preset is built in, `inherit`, which sets nothing and is
what a scope that selects nothing gets, so declaring a dimension never changes a launch
by itself.

A dimension is harness-neutral: a preset says *what* it sets (a model class, an effort
level) and never *how* a harness spells it. The spelling is the harness layer's job,
done where each generated artifact is rendered, so one selection lands on every carrier
from one declaration rather than being restated per harness.

The keys are closed because everything a preset sets has to be read by code. A preset
that could set a key no renderer reads would change nothing while looking configured,
so an unknown key or value is refused when the preset is read, not when it is used.

A scope selects exactly one preset per dimension (Kconfig's `choice` block, with a
default). Nothing here lets one selection force another dimension's value; Kconfig's
`select` does that without checking the forced symbol's own dependencies, and that is
the relation this module does not have.

`launcher.Capability` is the harness-specific sibling: a posture whose *options differ
per harness* and contribute argv directly. A dimension is the opposite shape — one
preset, projected onto each harness by its renderer.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# The capability classes a preset may ask for, weakest first. A class, never a model
# name: the name is a harness's projection and changes with every release, while the
# preset that selects a class is operator-owned and should not have to.
MODEL_CLASSES = ("light", "standard", "strong", "frontier")

# Effort levels, lowest first, in Claude Code's vocabulary (`--effort`, agent `effort:`).
EFFORTS = ("low", "medium", "high", "xhigh", "max")

# The built-in preset every dimension has. Reserved: a presets file may not redefine it,
# since a scope with no selection must keep meaning "set nothing".
INHERIT = "inherit"

_PRESET_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")

_FILE_HEADER = (
    "# Presets for the `{key}` dimension, selected by name from an expert manifest.\n"
    "# Written by `thalamus preset`; hand edits are read the same, comments are not kept.\n"
)


@dataclass(frozen=True)
class Preset:
    name: str
    # What selecting it sets. Empty is the built-in `inherit`.
    sets: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Dimension:
    key: str
    title: str
    # What a preset may set, and the values each key admits.
    settings: dict[str, tuple[str, ...]]

    def preset(self, name: str, sets: Mapping[str, object]) -> Preset:
        """A validated preset. Raises on a bad name, an unknown key or a bad value."""
        if not _PRESET_NAME.match(name):
            raise ValueError(
                f"`{name}` is not a preset name: lowercase letters, digits and hyphens"
            )
        if name == INHERIT:
            raise ValueError(f"`{INHERIT}` is built in and cannot be redefined")
        checked: dict[str, str] = {}
        for key, value in sets.items():
            if key not in self.settings:
                raise ValueError(
                    f"`{self.key}` preset `{name}` sets unknown key `{key}`; "
                    f"expected one of {', '.join(self.settings)}"
                )
            if value not in self.settings[key]:
                raise ValueError(
                    f"`{self.key}` preset `{name}` sets {key}={value!r}; "
                    f"expected one of {', '.join(self.settings[key])}"
                )
            checked[key] = str(value)
        return Preset(name, checked)

    def presets(self, declared: Mapping[str, Mapping[str, object]]) -> dict[str, Preset]:
        """Every preset a scope may select: the built-in first, then the declared."""
        out = {INHERIT: Preset(INHERIT)}
        for name, sets in declared.items():
            out[name] = self.preset(name, sets or {})
        return out

    def resolve(self, name: str, declared: Mapping[str, Mapping[str, object]]) -> Preset:
        """The named preset. An unknown name raises: a manifest that selects a preset
        nobody defined should fail to load, not launch at a default it never chose."""
        available = self.presets(declared)
        if name not in available:
            raise ValueError(
                f"`{name}` is not a `{self.key}` preset; "
                f"defined: {', '.join(available)}"
            )
        return available[name]


# What an expert's sessions run on. Selected per scope in its manifest (`cost:`).
COST = Dimension(
    key="cost",
    title="Cost",
    settings={"model_class": MODEL_CLASSES, "effort": EFFORTS},
)

DIMENSIONS = {COST.key: COST}


def read_presets(dimension: Dimension, path: Path) -> dict[str, dict]:
    """The presets file's declarations, validated. A missing file declares none."""
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping of preset name to settings")
    declared = {str(name): dict(sets or {}) for name, sets in raw.items()}
    dimension.presets(declared)
    return declared


def write_presets(dimension: Dimension, declared: Mapping[str, Mapping], path: Path) -> None:
    """Validate, then replace the presets file. Validation first, so a bad preset
    never reaches the file every manifest load reads."""
    dimension.presets(declared)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump({k: dict(v) for k, v in declared.items()}, sort_keys=False)
    path.write_text(_FILE_HEADER.format(key=dimension.key) + (body if declared else ""))
