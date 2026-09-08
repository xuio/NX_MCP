"""Observed translator material fixture; tests do not substitute for a native solve."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "translated_fluid", Path(__file__).parents[2] / "examples/simcenter/audit_translated_fluid.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def fixture():
    folder = Path(__file__).parent / "evidence"
    return (
        (folder / "finned-translated-flow.prp").read_text(),
        (folder / "finned-translated-flow.prm").read_text(),
    )


def test_real_translator_output_rejects_density_but_preserves_other_properties(fixture):
    result = module.inspect_material(*fixture)
    assert not result["all_properties_match"]
    assert result["properties"]["DENSITY"]["relative_error"] == pytest.approx(0.0786468015)
    assert all(
        row["matches_relative_1e_6"]
        for name, row in result["properties"].items()
        if name != "DENSITY"
    )


def test_unknown_units_cannot_match_by_accident(fixture):
    properties, controls = fixture
    with pytest.raises(ValueError, match="units"):
        module.inspect_material(
            properties, controls.replace("LENGTH_CONVERSION_FACTOR", "UNKNOWN_LENGTH_FACTOR")
        )


def test_field_dependent_density_is_not_read_as_a_constant(fixture):
    properties, controls = fixture
    import re

    changed = re.sub(r"(DENSITY\s+)0", r"\g<1>1", properties)
    with pytest.raises(ValueError, match="nonconstant"):
        module.inspect_material(changed, controls)


def test_matched_values_do_not_claim_physical_acceptance(fixture):
    properties, controls = fixture
    result = module.inspect_material(
        properties.replace("0.129437616181E-08", "0.120000000000E-08"), controls
    )
    assert result["all_properties_match"]
    assert "not solve or physical acceptance" in result["scope"]


def test_distinct_material_manifest_is_compared_without_changing_observations(fixture):
    expected = {
        "DENSITY": 2.0,
        "SPECIFIC_HEAT_P": 1200.0,
        "DYNAMIC_VISCOSITY": 3e-5,
        "CONDUCTIVITY": 0.05,
    }
    result = module.inspect_material(*fixture, expected_values=expected)
    assert not result["all_properties_match"]
    assert all(not r["matches_relative_1e_6"] for r in result["properties"].values())
    assert result["properties"]["DENSITY"]["translated"] == pytest.approx(1.29437616181)
    assert result["properties"]["DENSITY"]["intended"] == 2.0


@pytest.mark.parametrize(
    "values",
    [
        {"DENSITY": 2.0},
        {
            "DENSITY": float("nan"),
            "SPECIFIC_HEAT_P": 1200.0,
            "DYNAMIC_VISCOSITY": 3e-5,
            "CONDUCTIVITY": 0.05,
        },
    ],
)
def test_incomplete_or_nonfinite_expected_material_is_rejected(fixture, values):
    with pytest.raises(ValueError, match="all four"):
        module.inspect_material(*fixture, expected_values=values)


def test_tmg_density_survives_before_flow_translation():
    cards = 'PARAM UNITS 5 1000 1000 1 -273.15 1\nMAT 2 NAME "Generic air"\nMAT 2 PHASE LIQUID\nMAT 2 RHO 2e-9\n'
    assert module.inspect_density_card(cards)["density"] == 2.0
    for changed in [
        cards.replace("1000 1000", "1 1"),
        cards + "MAT 2 RHO 2e-9\n",
        cards.replace("RHO 2e-9", "RHO T12"),
        cards.replace("LIQUID", "GAS"),
    ]:
        with pytest.raises(ValueError):
            module.inspect_density_card(changed)


def test_retained_native_tmg_card_contains_requested_density():
    cards = (Path(__file__).parent / "evidence/finned-material-contrast-cards.txt").read_text()
    assert module.inspect_density_card(cards)["density"] == 2.0
