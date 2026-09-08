import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

AUDIT = runpy.run_path(
    str(Path(__file__).parents[2] / "examples/simcenter/audit_head_loss_export.py")
)["audit"]


def fixture():
    return ET.fromstring("""<SolutionFile><SolutionStepList><SolutionStep stepid="1"/></SolutionStepList>
    <HeadLossList><HeadLoss uid="4"><Property name="Type"><Value>0</Value></Property>
    <Property name="Proportional to"><Value>0</Value></Property>
    <Property name="Head Loss Coefficient"><Value>2</Value></Property></HeadLoss></HeadLossList>
    <FlowBcList><FlowBc uname="Duct Opening" type="Opening"><Property name="Head Loss"><Value>4</Value></Property>
    <Selection step="1"><fa>395 1</fa></Selection></FlowBc></FlowBcList></SolutionFile>""")


def test_linked_active_coefficient_and_selection():
    assert AUDIT(fixture())["export_settings_verified"]


@pytest.mark.parametrize(
    "path,value",
    [
        ('.//Property[@name="Head Loss"]/Value', "999"),
        ('.//Property[@name="Type"]/Value', "1"),
        ('.//Property[@name="Proportional to"]/Value', "1"),
        ('.//Property[@name="Head Loss Coefficient"]/Value', "0"),
        ('.//Property[@name="Head Loss Coefficient"]/Value', "nan"),
    ],
)
def test_reject_wrong_association_inactive_or_changed_coefficient(path, value):
    root = fixture()
    root.find(path).text = value
    with pytest.raises(ValueError):
        AUDIT(root)


def test_reject_unknown_step_or_missing_selection():
    root = fixture()
    root.find(".//Selection").set("step", "99")
    with pytest.raises(ValueError):
        AUDIT(root)
    root.find(".//FlowBc").remove(root.find(".//Selection"))
    with pytest.raises(ValueError):
        AUDIT(root)
