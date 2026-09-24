"""
Dimensions, the operator's named presets, and a manifest's selection of one.

Interfaces: thalamus.contract.capabilities, thalamus.contract.manifest, `thalamus preset`
Infrastructure: tmp_path config roots only
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from thalamus.contract.capabilities import (
    BUDGET,
    COST,
    INHERIT,
    MODEL_CLASSES,
    read_presets,
    write_presets,
)
from thalamus.contract.manifest import ExpertManifest, load_manifest, presets_file
from thalamus.harness.pin import CLAUDE_MODEL_ALIASES, CODEX_MODELS

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config"


def _config(tmp_path, presets: str | None, cost: str | None) -> Path:
    (tmp_path / "experts").mkdir()
    body = "scope: s\nname: S\n" + (f"cost: {cost}\n" if cost else "")
    (tmp_path / "experts" / "s.yaml").write_text(body)
    if presets is not None:
        (tmp_path / "presets").mkdir()
        (tmp_path / "presets" / "cost.yaml").write_text(presets)
    return tmp_path


def test_every_model_class_has_a_projection_on_every_harness_that_reads_cost():
    """A class with no alias would raise at render time for whichever scope first
    selected a preset that asks for it — far from the table that forgot it."""
    assert set(CLAUDE_MODEL_ALIASES) == set(MODEL_CLASSES)
    assert set(CODEX_MODELS) == set(MODEL_CLASSES)


def test_inherit_is_built_in_sets_nothing_and_cannot_be_redefined():
    assert COST.presets({})[INHERIT].sets == {}
    with pytest.raises(ValueError, match="built in"):
        COST.preset(INHERIT, {"effort": "low"})


@pytest.mark.parametrize("name, sets, message", [
    ("Deep Review", {}, "not a preset name"),
    ("x", {"temperature": "0.2"}, "unknown key"),
    ("x", {"effort": "extreme"}, "expected one of"),
])
def test_a_preset_is_refused_when_it_is_read_not_when_it_is_used(name, sets, message):
    with pytest.raises(ValueError, match=message):
        COST.preset(name, sets)


def test_a_manifest_with_no_cost_and_no_presets_file_loads_as_inherit(tmp_path):
    manifest = load_manifest("s", _config(tmp_path, None, None))

    assert manifest.cost == INHERIT
    assert manifest.cost_preset.sets == {}


def test_a_manifest_selecting_an_operator_preset_resolves_it(tmp_path):
    base = _config(tmp_path, "cheap:\n  model_class: light\n  effort: low\n", "cheap")

    assert load_manifest("s", base).cost_preset.sets == {
        "model_class": "light", "effort": "low",
    }


def test_a_manifest_naming_an_undefined_preset_fails_to_load(tmp_path):
    """An unknown selection must stop the manifest, not launch at a default the
    operator never chose — and say which file to look in."""
    base = _config(tmp_path, "cheap:\n  effort: low\n", "lavish")

    with pytest.raises(ValueError, match="s.yaml.*not a `cost` preset"):
        load_manifest("s", base)


def test_a_bad_presets_file_fails_every_manifest_that_loads_against_it(tmp_path):
    base = _config(tmp_path, "cheap:\n  effort: extreme\n", None)

    with pytest.raises(ValueError, match="expected one of"):
        load_manifest("s", base)


def test_written_presets_read_back_and_a_bad_one_never_reaches_the_file(tmp_path):
    path = tmp_path / "presets" / "cost.yaml"
    write_presets(COST, {"deep": {"model_class": "frontier", "effort": "max"}}, path)

    assert read_presets(COST, path) == {"deep": {"model_class": "frontier", "effort": "max"}}
    before = path.read_text()
    with pytest.raises(ValueError):
        write_presets(COST, {"deep": {"effort": "extreme"}}, path)
    assert path.read_text() == before


def test_the_shipped_example_presets_are_valid():
    COST.presets(read_presets(COST, presets_file(COST, REPO_CONFIG)))


def _preset(monkeypatch, tmp_path, *argv):
    from thalamus import cli

    monkeypatch.setenv("THALAMUS_CONFIG_DIR", str(tmp_path))
    command, dimension, *rest = argv
    args = SimpleNamespace(preset_command=command, dimension=dimension,
                           name=rest[0] if rest else None, settings=rest[1:])
    try:
        cli._cmd_preset(args, parser=None)
    except SystemExit as exit_:
        return exit_.code
    return None


def test_preset_set_then_remove_round_trips(monkeypatch, tmp_path):
    _config(tmp_path, None, None)

    assert _preset(monkeypatch, tmp_path, "set", "cost", "deep",
                   "model_class=frontier", "effort=max") is None
    assert read_presets(COST, tmp_path / "presets" / "cost.yaml") == {
        "deep": {"model_class": "frontier", "effort": "max"},
    }
    assert _preset(monkeypatch, tmp_path, "remove", "cost", "deep") is None
    assert read_presets(COST, tmp_path / "presets" / "cost.yaml") == {}


def test_preset_remove_is_refused_while_a_manifest_selects_it(monkeypatch, tmp_path):
    """Removing a selected preset would leave that scope unloadable."""
    _config(tmp_path, "cheap:\n  effort: low\n", "cheap")

    code = _preset(monkeypatch, tmp_path, "remove", "cost", "cheap")

    assert "selected by s" in str(code)
    assert "cheap" in read_presets(COST, tmp_path / "presets" / "cost.yaml")


def test_preset_set_refuses_a_bad_setting_without_writing(monkeypatch, tmp_path):
    _config(tmp_path, None, None)

    code = _preset(monkeypatch, tmp_path, "set", "cost", "x", "effort=extreme")

    assert "expected one of" in str(code)
    assert not (tmp_path / "presets" / "cost.yaml").exists()


def test_a_manifest_constructed_directly_resolves_inherit_without_a_config():
    assert ExpertManifest(scope="s", name="S").cost_preset.sets == {}


@pytest.mark.parametrize("value", ["0", "-3", "thirty", "2.5"])
def test_a_turn_budget_admits_only_a_positive_integer(value):
    with pytest.raises(ValueError, match="an integer ≥ 1"):
        BUDGET.preset("x", {"max_turns": value})


def test_a_turn_budget_set_from_the_command_line_is_written_as_a_number(monkeypatch, tmp_path):
    """`preset set` hands every value over as a string; the file an operator edits by
    hand should hold the count as the number it is."""
    _config(tmp_path, None, None)

    assert _preset(monkeypatch, tmp_path, "set", "budget", "short", "max_turns=30") is None

    path = tmp_path / "presets" / "budget.yaml"
    assert "max_turns: 30\n" in path.read_text()
    assert read_presets(BUDGET, path) == {"short": {"max_turns": 30}}


def test_a_manifest_resolves_each_dimension_against_its_own_presets_file(tmp_path):
    base = _config(tmp_path, "cheap:\n  effort: low\n", "cheap")
    (base / "experts" / "s.yaml").write_text("scope: s\nname: S\ncost: cheap\nbudget: short\n")
    (base / "presets" / "budget.yaml").write_text("short:\n  max_turns: 12\n")

    manifest = load_manifest("s", base)

    assert manifest.cost_preset.sets == {"effort": "low"}
    assert manifest.budget_preset.sets == {"max_turns": "12"}


def test_a_manifest_naming_an_undefined_budget_fails_to_load(tmp_path):
    base = _config(tmp_path, None, None)
    (base / "experts" / "s.yaml").write_text("scope: s\nname: S\nbudget: short\n")

    with pytest.raises(ValueError, match="s.yaml.*not a `budget` preset"):
        load_manifest("s", base)
