"""Retained native evidence must not turn a failed mesh check into a pass."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "room_audit", ROOT / "examples/simcenter/audit_room_fan.py"
)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
EVIDENCE = ROOT / "tests/simcenter/evidence"


def test_retained_native_cases_balance_but_fail_declared_mesh_limit():
    cases = []
    for name, receipt in [
        ("coarse", "room-fan-coarse-results-r2.json"),
        ("fine", "room-fan-fine-results-r1.json"),
    ]:
        data = json.loads((EVIDENCE / receipt).read_text())
        case = AUDIT.inspect_case(data, (EVIDENCE / f"room-fan-{name}.log").read_text())
        assert all(case["checks"].values())
        cases.append(case)
    comparison = AUDIT.compare(*cases)
    assert not comparison["accepted"]
    assert comparison["fractional_changes"]["rise_K"] == pytest.approx(0.20047651566)
    assert comparison["fractional_changes"]["flow_m3_s"] == pytest.approx(0.06625891947)


def test_missing_completion_and_wrong_effective_density_are_not_accepted():
    data = json.loads((EVIDENCE / "room-fan-fine-results-r1.json").read_text())
    data["density"]["minimum"] = data["density"]["maximum"] = 1.2944
    log = (
        (EVIDENCE / "room-fan-fine.log")
        .read_text()
        .replace("Coupled Solve complete", "Interrupted")
    )
    case = AUDIT.inspect_case(data, log)
    assert not case["checks"]["density"]
    assert not case["checks"]["coupled_convergence"]
