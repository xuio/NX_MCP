import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
AUDIT = runpy.run_path(str(ROOT / "examples/simcenter/audit_radiation_objects_export.py"))["audit"]
RAW = (ROOT / "tests/simcenter/evidence/radiation-objects.xml").read_bytes()


def test_retained_radiation_object_export():
    assert AUDIT(RAW)["passed"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("Calculation Method", "2"),
        ("Include Radiative Environment", "0"),
        ("Emissivity", "0"),
        ("Apply Override Set to", "1"),
    ],
)
def test_wrong_active_settings_are_detected(key, value):
    root = ET.fromstring(RAW)
    rows = [p for p in root.findall(".//Property") if p.get("name") == key]
    assert len(rows) == 1
    rows[0].find("Value").text = value
    with pytest.raises(ValueError):
        AUDIT(ET.tostring(root))


def test_inactive_monte_carlo_value_is_not_a_setting_mismatch():
    root = ET.fromstring(RAW)
    next(
        p for p in root.findall(".//Radiation/Property") if p.get("name") == "Monte Carlo Settings"
    ).find("Value").text = "-777777"
    assert AUDIT(ET.tostring(root))["passed"]


def test_missing_face_mapping_is_detected():
    root = ET.fromstring(RAW)
    region = root.find(".//OverrideSetEmissivity/Selection")
    region.remove(region.find("fa"))
    with pytest.raises(ValueError):
        AUDIT(ET.tostring(root))
