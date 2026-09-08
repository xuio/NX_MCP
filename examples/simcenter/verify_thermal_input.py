"""Verify the exported uniform-heating fixture; not a general deck validator."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def verify(path):
    raw = Path(path).read_bytes()
    root = ET.fromstring(raw)

    def value(parent, name):
        return float(parent.find(f"Property[@name='{name}']/Value").text)

    units = root.find("Units")
    assert units.findtext("System") == "Millimeters"
    assert float(units.findtext("LengthConversionFactor")) == 1000
    assert float(units.findtext("ForceConversionFactor")) == 1000
    assert float(units.findtext("AbsoluteTemperatureShift")) == -273.15
    materials = root.findall("MaterialList/Material")
    assert len(materials) == 1
    expected = {"Mass Density Constant": 2.7e-6, "Specific Heat": 9e8, "Thermal Conductivity": 2e5}
    actual = {name: value(materials[0], name) for name in expected}
    assert actual == expected, actual
    loads = root.findall("Loads/ThermalLoadList/ThermalLoad")
    assert len(loads) == 1 and loads[0].attrib["type"] == "Heat Load"
    assert value(loads[0], "Heat Load") == 1e6
    assert value(loads[0], "Per Element") == value(loads[0], "Per Node") == 0
    selected = [int(e.text) for e in loads[0].findall("Selection/el")]
    assert len(selected) == len(set(selected)) == 2658
    boundaries = root.findall("Constraints/TemperatureList/Temperature")
    assert len(boundaries) == 1 and value(boundaries[0], "Temperature") == 20
    assert len(boundaries[0].findall("Selection/fa")) == 22
    return {
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "material_values_in_export_units": actual,
        "total_power_in_export_units": 1e6,
        "temperature_in_export_units": 20,
        "heat_selected_elements": len(selected),
        "temperature_selected_element_faces": 22,
        "scope": "Known fixture values and cardinality; no solve or geometric face-mapping acceptance",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    print(json.dumps(verify(parser.parse_args().input), indent=2))
