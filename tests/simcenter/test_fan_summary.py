from pathlib import Path

import pytest

from nx_mcp.simcenter.fan_summary import inspect_fan_operating_points
from nx_mcp.simcenter.flow_audit import inspect_flow_log

ROOT = Path(__file__).parent / "evidence"


@pytest.mark.parametrize(
    "name,flow,pressure",
    [("fine-k0-native.log", 0.0002524, 0.3691), ("fine-k2-native.log", 0.0001912, 0.5221)],
)
def test_recorded_native_points(name, flow, pressure):
    result = inspect_flow_log((ROOT / name).read_text())["fan_operating_points"]
    assert result["state"] == "reported"
    assert len(result["fans"]) == 1
    fan = result["fans"][0]
    assert fan["volume_flow_m3_s"] == pytest.approx(flow)
    assert fan["pressure_rise_Pa"] == pytest.approx(pressure)
    assert fan["pressure_convention"] == "unverified"
    assert not result["engineering_accepted"]


def test_unknown_pressure_units_and_repeated_headers_do_not_convert():
    text = (ROOT / "fine-k0-native.log").read_text()
    assert (
        inspect_fan_operating_points(text.replace("mN/mm^2", "psi"))["state"]
        == "units_not_verified"
    )
    line = next(line for line in text.splitlines() if line.strip().startswith("Fluid Pressure"))
    assert inspect_fan_operating_points(text + "\n" + line)["state"] == "units_not_verified"
    assert inspect_fan_operating_points("solver running")["state"] == "not_present"


def test_duplicate_summaries_and_unmatched_fan_names_are_explicit():
    text = (ROOT / "fine-k0-native.log").read_text()
    assert (
        inspect_fan_operating_points(text + "\nFan Curve Operating Point Summary")["state"]
        == "summary_not_verified"
    )
    text = text.replace("|   Duct Inlet    |", "|   Other Inlet   |")
    assert inspect_fan_operating_points(text)["state"] == "summary_not_verified"
