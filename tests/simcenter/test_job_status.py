from types import SimpleNamespace as NS

import pytest

from nx_mcp.simcenter.jobs import JobStore
from nx_mcp.simcenter.native import SimcenterMixin
from nx_mcp.workspace import Workspace, WorkspaceViolation


def test_compact_status_does_not_require_live_nx_objects(tmp_path):
    workspace = Workspace(tmp_path)
    store = JobStore(workspace)
    store.reserve("status", {"input": "large manifest excluded by default"})
    store.transition(
        "status",
        expected_revision=0,
        state="launch_requested",
        evidence={"intent": "recorded only"},
    )
    executor = NS(workspace=workspace)
    status = SimcenterMixin._sim_job_status(executor, "status")
    assert status["state"] == "launch_requested"
    assert status["live_process_state"] == "not_checked"
    assert not status["launch_retry_allowed"]
    assert "manifest" not in status and "evidence" not in status
    assert "process_binding_evidence" not in status
    expanded = SimcenterMixin._sim_job_status(
        executor, "status", include_manifest=True, include_evidence=True
    )
    assert expanded["evidence"]["intent"] == "recorded only"
    assert expanded["manifest"]["input"]


def test_unknown_and_outside_workspace(tmp_path):
    workspace = Workspace(tmp_path)
    store = JobStore(workspace)
    store.reserve("partial", {"input": "one"})
    (store.root / "partial" / "state-00001.json").write_bytes(b"{")
    result = SimcenterMixin._sim_job_status(NS(workspace=workspace), "partial")
    assert result["state"] == "unknown" and not result["launch_retry_allowed"]
    with pytest.raises(WorkspaceViolation):
        SimcenterMixin._sim_job_status(NS(workspace=workspace), "partial", job_folder="../outside")
