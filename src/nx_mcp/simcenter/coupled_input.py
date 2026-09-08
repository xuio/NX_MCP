"""Fail closed on the observed NX 2606 coupled ambient export discrepancy."""

import math
import xml.etree.ElementTree as ET


def inspect_ambient_pressure(data, native_mode, native_pressure_pa=None):
    """Check selector meaning before comparing an active specified pressure."""
    if type(native_mode) is not int or native_mode not in (0, 1):
        raise ValueError("Unsupported coupled ambient pressure selector")
    root = ET.fromstring(data)
    if root.get("class") != "Coupled Thermal-Flow":
        raise ValueError("Coupled solution exported a different analysis class")
    base = "./SolutionParameters/AmbientConditions/Property"
    modes = root.findall(base + "[@name='Ambient Pressure']/Value")
    if len(modes) != 1 or int(modes[0].text) != native_mode:
        raise ValueError("Coupled ambient pressure selector differs in exported input")
    if native_mode == 1:
        return {
            "mode": "altitude_standard_conditions",
            "stored_absolute_pressure_active": False,
            "matches": True,
            "scope": "selector only; altitude-derived pressure and density not verified",
        }
    if (
        native_pressure_pa is None
        or not math.isfinite(native_pressure_pa)
        or native_pressure_pa <= 0
    ):
        raise ValueError("Specified absolute pressure must be finite and positive in Pa")
    units = root.find("Units")
    if (
        units is None
        or units.findtext("System") != "Millimeters"
        or float(units.findtext("LengthConversionFactor", "nan")) != 1000.0
        or float(units.findtext("ForceConversionFactor", "nan")) != 1000.0
    ):
        raise ValueError("Coupled pressure export unit convention is unverified")
    rows = root.findall(base + "[@name='Absolute Pressure']/Value")
    if len(rows) != 1:
        raise ValueError("Expected exactly one exported absolute pressure")
    # Native millimeter solver units use mN/mm² = 1000 Pa.
    exported_pa = float(rows[0].text) * 1000.0
    if not math.isfinite(exported_pa):
        raise ValueError("Exported absolute pressure is nonfinite")
    return {
        "mode": "specified",
        "stored_absolute_pressure_active": True,
        "native_value": native_pressure_pa,
        "exported_value": exported_pa,
        "units": "Pa",
        "absolute_tolerance_Pa": 1e-3,
        "matches": math.isclose(native_pressure_pa, exported_pa, rel_tol=0, abs_tol=1e-3),
        "scope": "constant specified pressure only; not complete solve readiness",
    }


def inspect_ambient_temperature(data, native_value, native_unit):
    """Compare a constant Celsius readback with the observed millimeter XML layout.

    This narrow check does not validate other boundary conditions or accept a solve.
    Field/time-dependent temperatures require a separate verified export adapter.
    Call only after the bounded XML validation in input_export.
    """
    if native_unit != "Celsius" or not math.isfinite(native_value):
        raise ValueError("Coupled ambient check requires a finite constant Celsius readback")
    root = ET.fromstring(data)
    if root.get("class") != "Coupled Thermal-Flow":
        raise ValueError("Coupled solution exported a different analysis class")
    units = root.find("Units")
    if (
        units is None
        or float(units.findtext("TemperatureConversionFactor", "nan")) != 1.0
        or not math.isclose(
            float(units.findtext("AbsoluteTemperatureShift", "nan")),
            -273.15,
            rel_tol=0,
            abs_tol=1e-9,
        )
    ):
        raise ValueError("Coupled ambient export temperature convention is unverified")
    rows = root.findall(
        "./SolutionParameters/AmbientConditions/Property[@name='Fluid Temperature']/Value"
    )
    if len(rows) != 1:
        raise ValueError("Coupled ambient export requires exactly one scalar temperature")
    exported = float(rows[0].text)
    if not math.isfinite(exported):
        raise ValueError("Coupled ambient export temperature is nonfinite")
    return {
        "property": "Fluid Temperature",
        "native_value": native_value,
        "exported_value": exported,
        "units": "degC",
        "matches": math.isclose(native_value, exported, rel_tol=0, abs_tol=1e-6),
        "absolute_tolerance_degC": 1e-6,
        "scope": "constant ambient temperature only; not complete solve readiness",
    }
