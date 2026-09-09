"""Audit time/power export semantics; this does not establish a solved transient response."""

import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path


def audit(path):
    root = ET.parse(path).getroot()
    assert root.attrib["class"] == "Thermal"
    units = root.find("Units")
    power_factor = float(units.findtext("LengthConversionFactor")) * float(
        units.findtext("ForceConversionFactor")
    )
    assert math.isfinite(power_factor) and power_factor > 0
    loads = root.findall('.//ThermalLoad[@uname="MCP_TIME_HEAT"]')
    assert len(loads) == 1
    load = loads[0]
    table = load.find('Property[@name="Heat Load"]')
    expected = {
        "type": "XYTable",
        "x": "Time",
        "interpolation": "Linear",
        "algorithm": "Linear Linear",
        "outside": "Undefined",
    }
    assert all(table.attrib[k] == v for k, v in expected.items())
    actual = [[float(v) for v in row.text.split()] for row in table.findall("_")]
    assert len(actual) == 3
    samples = [[x, y / power_factor] for x, y in actual]
    assert samples == [[0, 0], [10, 2], [20, 0]]
    selections = load.findall("Selection")
    assert len(selections) == 1
    elements = [int(el.text) for el in selections[0].findall("el")]
    assert len(elements) == len(set(elements)) == 100
    return {
        "passed": True,
        "samples_s_w": samples,
        "export_power_units_per_watt": power_factor,
        "selection_element_count": len(elements),
        "selection_attribute": selections[0].attrib,
        "scope": "Native time/power table export and selected element count; no numerical solve or step-inheritance interpretation",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    print(json.dumps(audit(parser.parse_args().path), indent=2))
