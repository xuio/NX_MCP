"""Audit the retained NX 2606 convection fixture export; never rewrite solver input."""

import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path


def audit(raw):
    root = ET.fromstring(raw)
    units = root.find("Units")
    factors = {
        name: float(units.findtext(name))
        for name in (
            "LengthConversionFactor",
            "ForceConversionFactor",
            "TemperatureConversionFactor",
            "AbsoluteTemperatureShift",
        )
    }
    if units.findtext("System") != "Millimeters" or list(factors.values()) != [
        1000.0,
        1000.0,
        1.0,
        -273.15,
    ]:
        raise ValueError("Unverified exported unit system")
    rows = root.findall(".//Convection")
    if len(rows) != 3:
        raise ValueError("Expected three convection boundaries")
    results = []
    regions = []
    for source, selector in [("fluid_ambient", 0), ("radiative_ambient", 1), ("specified", 2)]:
        matches = [r for r in rows if r.get("uname") == "MCP_ENV_" + source]
        if len(matches) != 1:
            raise ValueError("Missing/ambiguous convection boundary")
        row = matches[0]

        def value(name, row=row):
            props = [p for p in row.findall("Property") if p.get("name") == name]
            if len(props) != 1:
                raise ValueError("Missing/ambiguous convection property")
            return float(props[0].findtext("Value"))

        if (value("Convect From"), value("Specify"), value("Environment Temperature Type")) != (
            0,
            0,
            selector,
        ):
            raise ValueError("Inactive/mismatched convection selectors")
        # Heat-transfer coefficient has dimensions force/(length*time*temperature).
        h_si = (
            value("Convection Coefficient")
            * factors["LengthConversionFactor"]
            * factors["TemperatureConversionFactor"]
            / factors["ForceConversionFactor"]
        )
        if not math.isclose(h_si, 10.0, rel_tol=1e-7):
            raise ValueError("Convection coefficient mismatch")
        temperature_k = None
        if source == "specified":
            temperature_k = (
                value("Environment Temperature") - factors["AbsoluteTemperatureShift"]
            ) / factors["TemperatureConversionFactor"]
            if not math.isclose(temperature_k, 293.15, abs_tol=1e-6):
                raise ValueError("Specified temperature mismatch")
        selections = row.findall("Selection")
        if len(selections) != 1 or selections[0].get("step") != "1":
            raise ValueError("Unexpected step selection")
        faces = {tuple(map(int, f.text.split())) for f in selections[0].findall("fa")}
        if len(faces) != 14 or any(faces & region for region in regions):
            raise ValueError("Missing or overlapping face selections")
        regions.append(faces)
        results.append(
            {
                "source": source,
                "selector": selector,
                "coefficient_w_m2_k": h_si,
                "specified_temperature_k": temperature_k,
                "finite_element_faces": len(faces),
            }
        )
    return {
        "passed": True,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "boundaries": results,
        "units": factors,
        "numerical_acceptance": "not_performed",
        "scope": "Constant top-side convection selectors, SI coefficient, specified Kelvin conversion and disjoint step-1 FE faces; ambient effective values not evaluated",
    }


if __name__ == "__main__":
    path = Path(__file__).parents[2] / "tests/simcenter/evidence/convection-environment.xml"
    print(json.dumps(audit(path.read_bytes()), indent=2))
