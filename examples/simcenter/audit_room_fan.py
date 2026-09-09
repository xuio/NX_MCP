"""Audit retained native room-temperature fan results; never launches a solver.

Usage: PYTHONPATH=src python examples/simcenter/audit_room_fan.py
The retained coarse/fine pair intentionally fails the declared mesh criterion.
"""

import json
import math
import re
from pathlib import Path

from nx_mcp.simcenter.coupled_log import inspect_coupled_summary

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def inspect_case(result, text):
    summary = inspect_coupled_summary(text)

    def scalar(label, unit):
        matches = re.findall(re.escape(label) + r"\s+(" + NUMBER + r")\s+" + unit, text)
        if len(matches) != 1:
            raise ValueError(f"Expected one {label} summary")
        value = float(matches[0])
        if not math.isfinite(value):
            raise ValueError("Nonfinite native summary")
        return value

    # Native fan summary is pressure in mN/mm² and mass flow in kg/s.
    final_fan_summary = text.rsplit("Fan Curve Operating Point Summary", 1)[-1]
    fan = re.findall(
        r"\|\s*Coupled Inlet\s*\|\s*("
        + NUMBER
        + r")\s*\|\s*("
        + NUMBER
        + r")\s*\|\s*("
        + NUMBER
        + r")",
        final_fan_summary,
    )
    if len(fan) != 1:
        raise ValueError("Expected exactly one fan operating point")
    density = result["density"]
    rho = density["minimum"]
    flow = float(fan[0][2]) / rho
    pressure = float(fan[0][1]) * 1000
    expected_pressure = 1 - flow / 0.0004
    mass = scalar("Flow solver - Mass imbalance", "Percent")
    energy = scalar("Flow solver - Energy imbalance", "Percent")
    thermal_delta = scalar("Thermal solver - Maximum temperature change", "C")
    coupled_delta = summary["maximum_coupled_temperature_change_degC"]
    checks = {
        "room_temperature": summary["ambient_temperature_degC"] == 20,
        "density": density["units"] == "kg/m3"
        and all(abs(density[key] - 1.2) <= 1e-5 for key in ("minimum", "maximum")),
        "coupled_convergence": "Coupled Solve complete" in text
        and not summary["iteration_limit_reached_without_convergence"]
        and thermal_delta <= 0.001
        and coupled_delta <= 0.001,
        "mass_balance": abs(mass) < 0.1,
        "energy_balance": abs(energy) < 1,
        "solid_fluid_heat": all(
            abs(summary[key] - 0.1) < 0.001 for key in ("applied_solid_power_W", "heat_to_fluid_W")
        ),
        "fan_curve": 0 < flow < 0.0004
        and abs(pressure - expected_pressure) <= max(0.01, 0.02 * expected_pressure),
        "positive_solid_rise": result["temperature"]["maximum"] > 20,
    }
    return {
        "checks": checks,
        "peak_degC": result["temperature"]["maximum"],
        "rise_K": result["temperature"]["maximum"] - 20,
        "flow_m3_s": flow,
        "fan_static_pressure_rise_Pa": pressure,
        "fan_curve_error_Pa": abs(pressure - expected_pressure),
        "mass_imbalance_percent": mass,
        "energy_imbalance_percent": energy,
        "native_log_summary": summary,
        "limitations": "Rounded fan/log values; scoped physical checks, not complete model freshness or product accuracy",
    }


def compare(coarse, fine):
    changes = {
        key: abs(fine[key] - coarse[key]) / abs(coarse[key]) for key in ("rise_K", "flow_m3_s")
    }
    temperature_ok = changes["rise_K"] <= 0.05 or abs(fine["rise_K"] - coarse["rise_K"]) <= 0.02
    return {
        "fractional_changes": changes,
        "temperature_passed": temperature_ok,
        "flow_passed": changes["flow_m3_s"] <= 0.05,
        "accepted": temperature_ok and changes["flow_m3_s"] <= 0.05,
        "limits": "5% peak temperature rise and volume flow; 0.02 K absolute temperature allowance",
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2] / "tests/simcenter/evidence"
    cases = {
        name: inspect_case(
            json.loads((root / receipt).read_text()), (root / f"room-fan-{name}.log").read_text()
        )
        for name, receipt in [
            ("coarse", "room-fan-coarse-results-r2.json"),
            ("fine", "room-fan-fine-results-r1.json"),
        ]
    }
    print(
        json.dumps(
            {"cases": cases, "mesh_comparison": compare(cases["coarse"], cases["fine"])}, indent=2
        )
    )
