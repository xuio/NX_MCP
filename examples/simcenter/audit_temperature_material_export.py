"""Audit native temperature-material export units/tables, not numerical response."""

import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path


def audit(path, name):
    root = ET.parse(path).getroot()
    assert root.attrib["class"] == "Thermal"
    units = root.find("Units")
    length = float(units.findtext("LengthConversionFactor"))
    force = float(units.findtext("ForceConversionFactor"))
    temp = float(units.findtext("TemperatureConversionFactor"))
    shift = float(units.findtext("AbsoluteTemperatureShift"))
    assert length == force == 1000 and temp == 1 and shift == -273.15
    matches = [
        m for m in root.findall(".//Material") if m.attrib.get("uname", "").split("::")[0] == name
    ]
    assert len(matches) == 1
    material = matches[0]
    assert material.attrib["type"] == "ISO"
    density = material.find('Property[@name="Mass Density Constant"]')
    assert density.attrib["type"] == "Constant"
    density_si = float(density.findtext("Value")) * length**3
    assert math.isclose(density_si, 2700, rel_tol=1e-10)
    result = {}
    for property_name, factor, values in [
        ("Thermal Conductivity", force, [100, 150, 200]),
        ("Specific Heat", force * length, [800, 900, 1000]),
    ]:
        prop = material.find('Property[@name="' + property_name + '"]')
        assert all(
            prop.attrib[k] == v
            for k, v in {
                "type": "XYTable",
                "x": "Temperature",
                "interpolation": "Linear",
                "algorithm": "Linear Linear",
                "outside": "Undefined",
            }.items()
        )
        native = [[float(v) for v in r.text.split()] for r in prop.findall("_")]
        actual = [[(x - shift) / temp, y / factor] for x, y in native]
        expected = [[t, y] for t, y in zip([273.15, 293.15, 313.15], values, strict=True)]
        assert len(actual) == len(expected)
        assert all(
            math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10)
            for row, exp in zip(actual, expected, strict=True)
            for a, b in zip(row, exp, strict=True)
        )
        result[property_name] = actual
    return {
        "passed": True,
        "material": name,
        "density_kg_m3": density_si,
        "tables_si": result,
        "scope": "Thermal millimeter export tables/units; assignment checked by native readback; no numerical acceptance",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--name", default="MCP_PUBLIC_TEMP")
    args = parser.parse_args()
    print(json.dumps(audit(args.path, args.name), indent=2))
