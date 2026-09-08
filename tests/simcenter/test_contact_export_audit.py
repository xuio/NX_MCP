import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

AUDIT = runpy.run_path(
    str(Path(__file__).parents[2] / "examples/simcenter/audit_contact_export.py")
)["audit"]


def fixture(mode):
    root = ET.fromstring(
        """<SolutionFile><Units><System>Millimeters</System><ForceConversionFactor>1000</ForceConversionFactor><LengthConversionFactor>1000</LengthConversionFactor><TemperatureConversionFactor>1</TemperatureConversionFactor></Units><ThermalCoupling><Selection step="1"><fa>4 1</fa></Selection><Selection step="2"><fa>104 1</fa></Selection></ThermalCoupling></SolutionFile>"""
    )
    row = root.find("ThermalCoupling")
    props = {
        "Override Secondary Region": 0,
        "Specify Region Side to Apply to": 0,
        "Type": 1 if mode == "resistance" else 0,
        "Per Element": 0,
        "Total Resistance": 5e-7,
        "Total Conductance": 2e6,
    }
    for name, value in props.items():
        ET.SubElement(ET.SubElement(row, "Property", name=name), "Value").text = str(value)
    return root


@pytest.mark.parametrize("mode,expected", [("resistance", 0.5), ("conductance", 2.0)])
def test_native_power_unit_conversion_and_two_contact_regions(mode, expected):
    assert AUDIT(fixture(mode), mode, expected)["si_value"] == expected


@pytest.mark.parametrize(
    "path,text",
    [
        (".//ForceConversionFactor", "1"),
        ('.//Property[@name="Type"]/Value', "1"),
        ('.//Property[@name="Per Element"]/Value', "1"),
        ('.//Property[@name="Total Conductance"]/Value', "2"),
        ('.//Property[@name="Override Secondary Region"]/Value', "1"),
    ],
)
def test_reject_wrong_units_selectors_or_unconverted_value(path, text):
    root = fixture("conductance")
    root.find(path).text = text
    with pytest.raises(ValueError):
        AUDIT(root, "conductance", 2.0)
