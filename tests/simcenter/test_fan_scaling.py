import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.fan_scaling import scale_curve


def curve():
    return {
        "name": "source",
        "pressure_convention": "static",
        "rpm": 1000,
        "reference_density_kg_m3": 1.2,
        "points": [{"flow_m3_s": 0, "pressure_Pa": 100}, {"flow_m3_s": 0.01, "pressure_Pa": 0}],
        "stall_region": "uncharacterized",
        "provenance": {"kind": "measured", "source": "test fixture"},
        "scaling_rpm_range": [500, 1500],
        "scaling_validity": "same geometry, assumed similarity",
    }


def test_fan_laws_preserve_source_and_identify_derived_assumptions():
    source = curve()
    scaled = scale_curve(source, "half", 500)
    assert scaled["points"][0]["pressure_Pa"] == 25
    assert scaled["points"][1]["flow_m3_s"] == 0.005
    assert scaled["provenance"]["kind"] == "assumed"
    assert "Source SHA256=" in scaled["provenance"]["source"]
    assert source == curve()
    assert scaled["extrapolation"] == "reject"


@pytest.mark.parametrize("rpm", [0, 499, 1501, True, float("nan"), float("inf")])
def test_invalid_or_out_of_range_speed_rejected(rpm):
    with pytest.raises(NXToolError):
        scale_curve(curve(), "derived", rpm)
