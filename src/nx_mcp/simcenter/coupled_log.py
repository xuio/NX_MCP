"""Read observed 2606 coupled summaries; preserve non-convergence and limited scope."""

import math
import re

_N = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def inspect_coupled_summary(text):
    def scalar(label, suffix, scale=1):
        matches = re.findall(re.escape(label) + r"\s+(" + _N + r")" + suffix, text)
        if len(matches) != 1:
            return None
        value = float(matches[0]) * scale
        if not math.isfinite(value):
            raise ValueError("Nonfinite coupled summary value")
        return value

    temperatures = []
    for match in re.finditer(
        r"^\s*(Fluid Temperature|Solid Temperature)\s+("
        + _N
        + r")\s+("
        + _N
        + r")\s+("
        + _N
        + r")\s+C\s*$",
        text,
        re.M,
    ):
        values = [float(match[i]) for i in (2, 3, 4)]
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Nonfinite coupled temperature summary")
        temperatures.append(
            dict(zip(("maximum", "minimum", "average"), values, strict=True))
            | {
                "quantity": match[1],
                "units": "degC",
                "association": "native summary row; region identity not established",
            }
        )
    limit_reached = bool(
        re.search(
            r"reached the maximum steady-state iteration limit\s*\|?\s*\|?\s*without satisfying",
            text,
        )
    )
    return {
        "ambient_temperature_degC": scalar("Ambient Temperature:", r"\s+C"),
        "temperature_summaries": temperatures,
        "applied_solid_power_W": scalar(
            "Total heat load on non-fluid elements", r"\s+mN-mm/s", 1e-6
        ),
        "heat_to_fluid_W": scalar("Total Heat Convected to Fluid  (*)", r"\s+mN-mm/s", 1e-6),
        "maximum_coupled_temperature_change_degC": scalar(
            "Coupled solution - Maximum temperature change", r"\s+C"
        ),
        "normalized_coupled_heat_imbalance": scalar(
            "Coupled solution - Normalized Heat Imbalance", r"\s"
        ),
        "iteration_limit_reached_without_convergence": limit_reached,
        "numerical_convergence": "failed" if limit_reached else "not_established",
        "warnings": {
            "coincident_thermal_nodes": "Coincident thermal nodes found" in text,
            "no_interior_pressure_anchor": "No interior node at which to anchor pressure found"
            in text,
        },
        "scope": "Rounded native log summaries; not independent field extraction, complete criteria validation or mesh acceptance",
    }
