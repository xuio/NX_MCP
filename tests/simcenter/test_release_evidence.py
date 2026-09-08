from pathlib import Path

from nx_mcp.simcenter.release_evidence import public_evidence
from nx_mcp.simcenter.server import NON_MODEL, READ_ONLY


def test_indexed_tools_exist_and_refer_to_recorded_evidence():
    rows = public_evidence("v2606")["tools"]
    root = Path(__file__).resolve().parents[2]
    for row in rows:
        assert row["tool"] in READ_ONLY | NON_MODEL
        assert (root / row["evidence"]).is_file()
        assert row["current_session_test"] == "not_performed_by_discovery"
        assert row["licence_checkout"] == "not_tested"


def test_other_version_does_not_inherit_tested_status():
    assert all(
        row["status"] == "implemented_but_untested" for row in public_evidence("v2706")["tools"]
    )


def test_unindexed_tools_are_explicit_and_not_treated_as_unavailable():
    result = public_evidence("v2606")
    names = {row["tool"] for row in result["tools"]}
    unindexed = set(result["unindexed_tools"])
    assert names | unindexed == READ_ONLY | NON_MODEL
    assert names.isdisjoint(unindexed)
    assert result["exposed_tool_count"] == len(names | unindexed)
    assert result["indexed_tool_count"] == len(names)
    assert "No assessment" in result["unindexed_semantics"]
    assert {"nx_sim_fan_table", "nx_sim_fan_tables", "nx_sim_objects", "nx_sim_assign_fan"} <= names
