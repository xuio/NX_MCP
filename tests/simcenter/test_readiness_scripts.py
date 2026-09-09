import copy
import json
import runpy
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def test_export_real_region_pages_and_reject_mixed_or_missing_pages():
    collect = runpy.run_path(str(REPO / "examples/simcenter/export_region_receipt.py"))["collect"]
    receipt = json.loads(
        (REPO / "tests/simcenter/evidence/temperature-regions-public.json").read_text()
    )
    args = (["first", "second"], {"sink": 0, "heated": 1}, "contact-1W", "contact-explicit-r1")
    result = collect(receipt, *args)
    assert [r["node_count"] for r in result["regions"]] == [45, 45]
    assert result["regions"][1]["arithmetic_nodal_mean"] == 21.14748691982693
    assert result["engineering_accepted"] is False
    for names in (["first"], ["first", "first"]):
        with pytest.raises(ValueError):
            collect(receipt, names, *args[1:])
    for field, value in [("units", "K"), ("result_file", {"sha256": "changed"})]:
        bad = copy.deepcopy(receipt)
        bad["responses"]["second"]["structuredContent"][field] = value
        with pytest.raises(ValueError):
            collect(bad, *args)


def test_retained_coupled_gate_fails_without_reclassifying_native_cause():
    audit = runpy.run_path(str(REPO / "examples/simcenter/audit_baldower_readiness.py"))["audit"]
    result = audit(REPO)
    assert result["conclusion"] == "NOT READY"
    assert not result["temperature_mismatch"]["matches"]
    assert not result["specified_pressure_mismatch"]["matches"]
    assert not result["mesh_comparison"]["accepted_room_temperature_comparison"]
    assert result["density"]["solver_defect_demonstrated"] is False
    assert result["density"]["mcp_material_defect_demonstrated"] is False
