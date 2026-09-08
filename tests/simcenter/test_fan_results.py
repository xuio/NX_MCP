import pytest

from nx_mcp.simcenter.fan_results import audit_operating_point
from nx_mcp.simcenter.inputs import FanCurve


def audit(q, p, convention="static"):
    curve = FanCurve.model_validate(
        {
            "name": "synthetic",
            "pressure_convention": "static",
            "rpm": 1000,
            "reference_density_kg_m3": 1.2,
            "points": [{"flow_m3_s": 0, "pressure_Pa": 1}, {"flow_m3_s": 0.0004, "pressure_Pa": 0}],
            "stall_region": "not modeled",
            "provenance": {"kind": "assumed", "source": "benchmark"},
        }
    )
    return audit_operating_point(
        curve,
        flow_m3_s=q,
        pressure_rise_Pa=p,
        pressure_convention=convention,
        absolute_tolerance_Pa=0.001,
        relative_tolerance=0.01,
    )


def test_free_flow_endpoint_does_not_excuse_pressure_mismatch():
    result = audit(0.0004, -25.86)
    assert not result["accepted"] and result["reason"] == "pressure_curve_mismatch"
    assert result["absolute_error_Pa"] == 25.86


def test_interpolated_point_matches_with_explicit_tolerance():
    assert audit(0.0002, 0.5)["accepted"]
    assert not audit(0.0002, 0.52)["accepted"]


@pytest.mark.parametrize("q", [-0.001, 0.0004001])
def test_no_extrapolation(q):
    assert audit(q, 0)["reason"] == "flow_outside_curve_range"


def test_unknown_or_incompatible_pressure_is_not_accepted():
    assert audit(0.0002, 0.5, "unknown")["reason"] == "pressure_convention_unverified"
    assert audit(0.0002, 0.5, "total")["reason"] == "pressure_convention_mismatch"


def test_nonfinite_result_is_rejected():
    with pytest.raises(ValueError, match="finite"):
        audit(0.0002, float("nan"))


SUMMARY = """Fan Curve Operating Point Summary
| Duct Inlet | 0.000e+00 | 4.458e-04 | 2.660e-04 |
Total parallel flow solver time (s): 0.762
Volume/Mass Flow Summary
Duct Inlet     2.217E+05 mm^3/s  2.660E-04 kg/s
Duct Opening  -2.217E+05 mm^3/s -2.660E-04 kg/s
Solver Convergence
"""


def test_native_summary_preserves_units_sign_and_uncertainty():
    from nx_mcp.simcenter.fan_results import parse_native_fan_summary

    result = parse_native_fan_summary(SUMMARY, native_pressure_unit="mN/mm^2")
    assert result["fans"][0]["pressure_rise_Pa"] == pytest.approx(0.4458)
    assert result["fans"][0]["volume_flow_m3_s"] == pytest.approx(0.0002217)
    assert result["boundaries"][1]["mass_flow_kg_s"] < 0
    assert result["fans"][0]["pressure_convention"] == "unverified"
    assert not result["engineering_accepted"]


@pytest.mark.parametrize(
    "text",
    [
        "",
        SUMMARY + SUMMARY,
        SUMMARY.replace("Duct Opening", "Duct Inlet"),
        SUMMARY.replace("mm^3/s", "L/s"),
    ],
)
def test_ambiguous_or_unsupported_summaries_are_rejected(text):
    from nx_mcp.simcenter.fan_results import parse_native_fan_summary

    with pytest.raises(ValueError):
        parse_native_fan_summary(text, native_pressure_unit="mN/mm^2")


def test_native_pressure_decomposition():
    from nx_mcp.simcenter.fan_results import audit_pressure_decomposition

    args = {
        "pressure_Pa": 0.4911912977695465,
        "total_pressure_Pa": 0.6466395258903503,
        "speed_m_s": 0.5089994072914124,
        "density_kg_m3": 1.2,
        "absolute_tolerance_Pa": 1e-6,
        "relative_tolerance": 1e-5,
    }
    assert audit_pressure_decomposition(**args)["accepted"]
    assert not audit_pressure_decomposition(**{**args, "speed_m_s": 0.25})["accepted"]
    for change in ({"speed_m_s": -1}, {"density_kg_m3": 0}, {"pressure_Pa": float("nan")}):
        with pytest.raises(ValueError):
            audit_pressure_decomposition(**{**args, **change})
