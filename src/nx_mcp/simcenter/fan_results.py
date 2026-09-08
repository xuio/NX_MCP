"""SI fan operating-point consistency checks; no inference of pressure convention."""

import math

from nx_mcp.simcenter.fan_summary import parse_native_fan_summary as parse_native_fan_summary
from nx_mcp.simcenter.inputs import FanCurve


def audit_operating_point(
    curve: FanCurve,
    *,
    flow_m3_s: float,
    pressure_rise_Pa: float,
    pressure_convention: str,
    absolute_tolerance_Pa: float,
    relative_tolerance: float,
) -> dict:
    """Compare a resolved solver point with the exact run's density/RPM curve.

    The caller supplies an already scaled curve from the immutable run manifest.
    This checks only curve consistency, not convergence, mesh quality, conservation,
    or whether the chosen static/total pressure extraction is physically correct.
    """
    for value in (flow_m3_s, pressure_rise_Pa, absolute_tolerance_Pa, relative_tolerance):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Fan result and tolerances must be finite SI numbers")
    if absolute_tolerance_Pa < 0 or not 0 <= relative_tolerance <= 1:
        raise ValueError("Require nonnegative pressure tolerance and relative tolerance in [0, 1]")
    result = {
        "accepted": False,
        "flow_m3_s": flow_m3_s,
        "pressure_rise_Pa": pressure_rise_Pa,
        "pressure_convention": pressure_convention,
        "curve_rpm": curve.rpm,
        "curve_reference_density_kg_m3": curve.reference_density_kg_m3,
        "curve_valid_flow_range_m3_s": [curve.points[0].flow_m3_s, curve.points[-1].flow_m3_s],
        "absolute_tolerance_Pa": absolute_tolerance_Pa,
        "relative_tolerance": relative_tolerance,
        "scope": "curve_consistency_only",
    }
    if pressure_convention not in ("static", "total"):
        return {**result, "reason": "pressure_convention_unverified"}
    if pressure_convention != curve.pressure_convention:
        return {**result, "reason": "pressure_convention_mismatch"}
    if not curve.points[0].flow_m3_s <= flow_m3_s <= curve.points[-1].flow_m3_s:
        return {**result, "reason": "flow_outside_curve_range"}
    expected = curve.pressure(flow_m3_s)
    error = abs(pressure_rise_Pa - expected)
    tolerance = absolute_tolerance_Pa + relative_tolerance * abs(expected)
    return {
        **result,
        "expected_pressure_rise_Pa": expected,
        "absolute_error_Pa": error,
        "allowed_error_Pa": tolerance,
        "accepted": error <= tolerance,
        "reason": "within_tolerance" if error <= tolerance else "pressure_curve_mismatch",
    }


def audit_pressure_decomposition(
    *,
    pressure_Pa,
    total_pressure_Pa,
    speed_m_s,
    density_kg_m3,
    absolute_tolerance_Pa,
    relative_tolerance,
):
    """Check recovered incompressible fields at the same location and revision.

    This checks p_total - p = rho*v²/2 only; it does not establish fan-boundary
    convention, absolute pressure reference, convergence, or physical validation.
    """
    values = (
        pressure_Pa,
        total_pressure_Pa,
        speed_m_s,
        density_kg_m3,
        absolute_tolerance_Pa,
        relative_tolerance,
    )
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("Pressure decomposition inputs must be finite SI numbers")
    if (
        speed_m_s < 0
        or density_kg_m3 <= 0
        or absolute_tolerance_Pa < 0
        or not 0 <= relative_tolerance <= 1
    ):
        raise ValueError(
            "Require nonnegative speed/tolerance, positive density and relative tolerance in [0, 1]"
        )
    expected = 0.5 * density_kg_m3 * speed_m_s**2
    observed = total_pressure_Pa - pressure_Pa
    if not math.isfinite(expected) or not math.isfinite(observed):
        raise ValueError("Pressure decomposition arithmetic overflow")
    error = abs(observed - expected)
    allowed = absolute_tolerance_Pa + relative_tolerance * abs(expected)
    return {
        "accepted": error <= allowed,
        "observed_dynamic_pressure_Pa": observed,
        "expected_dynamic_pressure_Pa": expected,
        "absolute_error_Pa": error,
        "allowed_error_Pa": allowed,
        "scope": "incompressible_field_consistency_only",
    }
