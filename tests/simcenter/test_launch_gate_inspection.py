import json

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.jobs import JobStore
from nx_mcp.simcenter.launch_gate import claim_launch_gate, inspect_launch_gate
from nx_mcp.workspace import Workspace


def test_unclaimed_inspection_creates_nothing(tmp_path):
    result = inspect_launch_gate(Workspace(tmp_path))
    assert result["state"] == "unclaimed"
    assert result["solver_process_state"] == "not_checked"
    assert not result["launch_authorized_by_inspection"]
    assert list(tmp_path.iterdir()) == []


def test_other_job_is_identified_without_mutation_or_expiry(tmp_path):
    ws = Workspace(tmp_path)
    store = JobStore(ws)
    store.reserve("owner", {"fixture": True})
    store.reserve("next", {"fixture": True})
    claim_launch_gate(store, "owner")
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = inspect_launch_gate(ws)
    assert result["state"] == "claimed" and result["job_id"] == "owner"
    assert result["recorded_job_state"] == "accepted" and not result["automatic_expiry"]
    with pytest.raises(NXToolError) as exc:
        claim_launch_gate(store, "next")
    assert exc.value.details["launch_gate"]["job_id"] == "owner"
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_partial_or_outside_owner_stays_unknown_and_is_preserved(tmp_path):
    ws = Workspace(tmp_path)
    owner = tmp_path / ".nx-sim-launch-owner.json"
    for data in [
        "{",
        json.dumps(
            {
                "schema": 1,
                "job_id": "owner",
                "job_directory": str(tmp_path.parent / "outside"),
                "request_sha256": "a" * 64,
            }
        ),
    ]:
        owner.write_text(data)
        result = inspect_launch_gate(ws)
        assert result["state"] == "unknown"
        assert owner.read_text() == data and not result["launch_authorized_by_inspection"]
