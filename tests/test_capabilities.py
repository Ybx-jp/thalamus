"""
Dimension declarations and a manifest's selection of one variant.

Interfaces: thalamus.contract.capabilities, thalamus.contract.manifest
Infrastructure: none — pure declarations and pydantic validation
"""

import pytest
from pydantic import ValidationError

from thalamus.contract.capabilities import COST, SETTINGS, Dimension, Variant
from thalamus.contract.manifest import ExpertManifest
from thalamus.harness.pin import CLAUDE_MODEL_ALIASES


def test_cost_defaults_to_the_variant_that_sets_nothing():
    """The default is shipped behaviour; any setting on it would change every launch
    the moment the dimension was declared."""
    assert COST.variant(COST.default).sets == {}


def test_every_model_class_has_a_claude_projection():
    """A class with no alias would raise at render time for whichever scope first
    selected a variant that asks for it — far from the table that forgot it."""
    assert set(CLAUDE_MODEL_ALIASES) == set(SETTINGS["model_class"])


def test_a_variant_setting_an_undeclared_key_or_value_fails_at_declaration():
    with pytest.raises(ValueError, match="unknown key"):
        Variant("x", "X", {"temperature": "0.2"})
    with pytest.raises(ValueError, match="expected one of"):
        Variant("x", "X", {"effort": "extreme"})


def test_a_dimension_must_declare_its_default_and_no_repeats():
    with pytest.raises(ValueError, match="undeclared"):
        Dimension("d", "D", (Variant("a", "A"),), default="b")
    with pytest.raises(ValueError, match="repeats"):
        Dimension("d", "D", (Variant("a", "A"), Variant("a", "A2")), default="a")


def test_a_manifest_naming_an_unknown_cost_variant_fails_to_load():
    """An unknown selection must stop the manifest, not launch at a default the
    operator never chose."""
    with pytest.raises(ValidationError, match="not a `cost` variant"):
        ExpertManifest(scope="s", name="S", cost="lavish")


def test_a_manifest_with_no_cost_selects_the_default():
    manifest = ExpertManifest(scope="s", name="S")

    assert manifest.cost == COST.default
    assert manifest.cost_variant is COST.variant(COST.default)
