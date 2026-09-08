"""Verify the retained constant total-heat fixture's XML, not solver convergence."""

import hashlib
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def inspect(data):
    root = ET.fromstring(data)
    units = root.find("Units")
    if units is None or units.findtext("System") != "Millimeters":
        raise ValueError("Requires the tested millimeter/second unit convention")
    length = float(units.findtext("LengthConversionFactor", "nan"))
    force = float(units.findtext("ForceConversionFactor", "nan"))
    if length != 1000 or force != 1000:
        raise ValueError("Unverified solver unit factors")
    loads = root.findall(".//ThermalLoad")
    if len(loads) != 1 or loads[0].get("type") != "Heat Load":
        raise ValueError("Expected one total heat load")
    load = loads[0]

    def scalar(name):
        values = load.findall(f"./Property[@name='{name}']/Value")
        if len(values) != 1:
            raise ValueError("Missing or ambiguous heat property: " + name)
        value = float(values[0].text)
        if not math.isfinite(value):
            raise ValueError("Nonfinite exported heat property")
        return value

    for selector in ("Per Element", "Per Node", "Override Region"):
        if scalar(selector) != 0:
            raise ValueError("Fixture does not use unmodified total-region power")
    raw = scalar("Heat Load")
    watts = raw / (length * force)
    if not math.isclose(watts, 0.2, rel_tol=0, abs_tol=1e-9):
        raise ValueError("Expected scaled 0.1 W × 2 = 0.2 W")
    selections = load.findall("Selection")
    if len(selections) != 1 or selections[0].get("step") != "1" or not selections[0].findall("el"):
        raise ValueError("Expected nonempty step-1 element selection")
    return {
        "passed": True,
        "xml_sha256": hashlib.sha256(data).hexdigest(),
        "exported_raw_value": raw,
        "power_W": watts,
        "absolute_tolerance_W": 1e-9,
        "force_and_length_conversion": [force, length],
        "time_convention": "seconds; tested NX 2606 Multiphysics millimeter fixture only",
        "selected_element_count": len(selections[0].findall("el")),
        "scope": "exported total heat value and nonempty step selection; not physical solution acceptance",
    }


if __name__ == "__main__":
    print(json.dumps(inspect(Path(sys.argv[1]).read_bytes()), indent=2))
