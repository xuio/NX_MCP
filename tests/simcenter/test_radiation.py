import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.radiation import validate, verify


@pytest.mark.parametrize(
    "emissivity,source,temperature",
    [
        (-1, "specified", 293.15),
        (1.1, "specified", 293.15),
        (True, "specified", 293.15),
        (float("nan"), "specified", 293.15),
        (0.8, "invalid", None),
        (0.8, "specified", None),
        (0.8, "specified", -1),
        (0.8, "fluid_ambient", 293.15),
    ],
)
def test_invalid_radiation_preflight(emissivity, source, temperature):
    with pytest.raises(NXToolError) as error:
        validate(emissivity, source, temperature)
    assert error.value.details["mutation_outcome"] == "not_started"


def properties():
    return [
        {"name": "Radiation From", "value": 0},
        {"name": "Emissivity Type", "value": 2},
        {"name": "Temperature Type", "value": 2},
        {
            "name": "Effective Emissivity",
            "expression": "0.8",
            "representation": "expression",
            "units": "dimensionless",
        },
        {
            "name": "Temperature",
            "expression": "293.15",
            "representation": "expression",
            "units": "Kelvin",
        },
    ]


def test_radiation_value_and_unit_readback():
    verify(properties(), 0.8, "specified", 293.15)


@pytest.mark.parametrize(
    "index,key,value",
    [
        (0, "value", 1),
        (1, "value", 0),
        (2, "value", 0),
        (3, "expression", "-777777"),
        (4, "units", "Celsius"),
        (4, "expression", "0"),
    ],
)
def test_inactive_selectors_or_wrong_units_fail(index, key, value):
    rows = properties()
    rows[index][key] = value
    with pytest.raises(NXToolError):
        verify(rows, 0.8, "specified", 293.15)
