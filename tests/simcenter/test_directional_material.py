import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.directional_material import validate_properties


@pytest.mark.parametrize(
    "values",
    [
        [1, 2],
        [1, 2, 0],
        [1, -2, 3],
        [True, 2, 3],
        [1, 2, float("nan")],
        [1, 2, float("inf")],
        ["1", 2, 3],
    ],
)
def test_invalid_tensor_diagonal_is_rejected(values):
    with pytest.raises(NXToolError):
        validate_properties(values, 1000, 900, "PCB", "Assumed effective properties")


def test_orthotropic_values_keep_axis_order_and_si_units():
    result = validate_properties([12, 7, 0.4], 1900, 900, "PCB", "Assumed effective properties")
    assert result["ThermalConductivity"] == (12, "ThermalConductivity_Metric3")
    assert result["ThermalConductivity2"][0] == 7
    assert result["ThermalConductivity3"][0] == 0.4
    assert result["MassDensity"] == (1900, "KilogramPerCubicMeter")
