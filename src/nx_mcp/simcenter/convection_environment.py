"""NX Multiphysics Thermal Convection dependency selectors and constant readback."""

import math

from nx_mcp.runtime import NXToolError

SOURCES = {"fluid_ambient": 0, "radiative_ambient": 1, "specified": 2}


def validate_environment(source, temperature_k):
    if not isinstance(source, str) or source not in SOURCES:
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "Unknown convection temperature source",
            details={"mutation_outcome": "not_started"},
        )
    if source == "specified":
        if (
            type(temperature_k) not in (int, float)
            or not math.isfinite(temperature_k)
            or temperature_k < 0
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT",
                "Specified temperature requires finite temperature_k >= 0 K",
                details={"mutation_outcome": "not_started"},
            )
    elif temperature_k is not None:
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "temperature_k is only valid with specified temperature source",
            details={"mutation_outcome": "not_started"},
        )


def verify_convection_properties(properties, coefficient, source, temperature_k):
    rows = {p["name"]: p for p in properties}
    for name, value in (
        ("Convect From", 0),
        ("Specify", 0),
        ("Environment Temperature Type", SOURCES[source]),
    ):
        if rows.get(name, {}).get("value") != value:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", f"Convection selector differs: {name}")
    for name, expected, unit in (
        ("Convection Coefficient", coefficient, "ConvectionCoefficient_Metric8"),
        *(
            ([("Environment Temperature", temperature_k, "Kelvin")])
            if source == "specified"
            else []
        ),
    ):
        row = rows.get(name, {})
        try:
            valid = (
                row.get("representation") == "expression"
                and row.get("units") == unit
                and not row.get("inspection_status")
                and math.isclose(float(row["expression"]), expected, rel_tol=1e-12, abs_tol=1e-12)
            )
        except (KeyError, ValueError, TypeError):
            valid = False
        if not valid:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", f"Convection value/units differ: {name}")
    return {
        "environment_temperature_source": source,
        "environment_temperature_selector": SOURCES[source],
        "environment_temperature_k": temperature_k if source == "specified" else None,
        "environment_dependency": "boundary constant"
        if source == "specified"
        else "native solution ambient; effective value not resolved by this tool",
    }
