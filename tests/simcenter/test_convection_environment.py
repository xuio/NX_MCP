import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.convection_environment import (
    validate_environment,
    verify_convection_properties,
)


@pytest.mark.parametrize(
    "source,value",
    [
        ("fluid_ambient", 293.15),
        ("radiative_ambient", 0),
        ("specified", None),
        ("specified", True),
        ("specified", float("nan")),
        ("specified", -1),
        ("unknown", None),
    ],
)
def test_invalid_dependency_combinations(source, value):
    with pytest.raises(NXToolError) as error:
        validate_environment(source, value)
    assert error.value.details["mutation_outcome"] == "not_started"


def rows():
    return [
        {"name": "Convect From", "value": 0},
        {"name": "Specify", "value": 0},
        {"name": "Environment Temperature Type", "value": 2},
        {
            "name": "Convection Coefficient",
            "expression": "10",
            "units": "ConvectionCoefficient_Metric8",
            "representation": "expression",
        },
        {
            "name": "Environment Temperature",
            "expression": "293.15",
            "units": "Kelvin",
            "representation": "expression",
        },
    ]


def test_explicit_kelvin_readback():
    assert (
        verify_convection_properties(rows(), 10, "specified", 293.15)["environment_temperature_k"]
        == 293.15
    )


@pytest.mark.parametrize(
    "index,key,value",
    [
        (2, "value", 0),
        (3, "units", "wrong"),
        (4, "units", "Celsius"),
        (4, "expression", "0"),
        (3, "representation", "field_expression"),
    ],
)
def test_ignored_selector_wrong_units_or_unverified_field_fail(index, key, value):
    data = rows()
    data[index][key] = value
    with pytest.raises(NXToolError):
        verify_convection_properties(data, 10, "specified", 293.15)
