import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
AUDIT = runpy.run_path(str(ROOT / "examples/simcenter/audit_convection_environment_export.py"))[
    "audit"
]
RAW = (ROOT / "tests/simcenter/evidence/convection-environment.xml").read_bytes()


def test_retained_native_convection_export():
    result = AUDIT(RAW)
    assert result["passed"]
    assert result["boundaries"][2]["specified_temperature_k"] == 293.15
    assert result["boundaries"][0]["specified_temperature_k"] is None


@pytest.mark.parametrize(
    "name,value",
    [
        ("Environment Temperature Type", "0"),
        ("Environment Temperature", "0"),
        ("Convection Coefficient", "1000"),
    ],
)
def test_export_mismatch_is_rejected(name, value):
    root = ET.fromstring(RAW)
    row = next(r for r in root.findall(".//Convection") if r.get("uname") == "MCP_ENV_specified")
    next(p for p in row.findall("Property") if p.get("name") == name).find("Value").text = value
    with pytest.raises(ValueError):
        AUDIT(ET.tostring(root))
