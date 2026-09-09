import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.radiation_objects import validate, verify


@pytest.mark.parametrize(
    "kind,value,side,environment",
    [
        ("emissivity", -1, "both", True),
        ("emissivity", 1.1, "both", True),
        ("emissivity", True, "both", True),
        ("emissivity", float("nan"), "both", True),
        ("emissivity", 0.8, "invalid", True),
        ("enclosure", None, "both", 1),
        ("invalid", None, "both", True),
    ],
)
def test_preflight_rejects_invalid_values(kind, value, side, environment):
    with pytest.raises(NXToolError) as error:
        validate(kind, value, side, environment)
    assert error.value.details["mutation_outcome"] == "not_started"


def test_enclosure_active_readback():
    rows = [
        {"name": "Calculation Method", "value": 1},
        {"name": "Include Radiative Environment", "value": False},
    ]
    verify(rows, "enclosure", None, "both", False)
    with pytest.raises(NXToolError):
        verify(rows, "enclosure", None, "both", True)
    rows[0]["value"] = 2
    with pytest.raises(NXToolError):
        verify(rows, "enclosure", None, "both", False)


def test_emissivity_selector_units_and_value():
    rows = [
        {
            "name": "Emissivity",
            "expression": "0.8",
            "representation": "expression",
            "units": "dimensionless",
        },
        {"name": "Apply Override Set to", "value": 0},
    ]
    verify(rows, "emissivity", 0.8, "both", True)
    for key, value in [
        ("units", "Kelvin"),
        ("expression", "-777777"),
        ("representation", "field_expression"),
    ]:
        bad = [dict(r) for r in rows]
        bad[0][key] = value
        with pytest.raises(NXToolError):
            verify(bad, "emissivity", 0.8, "both", True)
    with pytest.raises(NXToolError):
        verify(rows, "emissivity", 0.8, "top", True)
