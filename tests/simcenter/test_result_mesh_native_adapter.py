"""Offline dispatch tests; real geometry evidence is retained separately."""

import sys
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.native import SimcenterMixin


@pytest.mark.parametrize("mode", ["recorded", "legacy", "unreadable"])
def test_result_adapter_uses_recorded_budget_and_retains_inspection_failure(monkeypatch, mode):
    from nx_mcp.simcenter import (
        dependencies,
        jobs,
        mesh_guard,
        result_binding,
        result_identity,
        thermal_state,
    )

    class SimPart:
        FullPath = "case.sim"
        Simulation = NS(
            ActiveSolution=NS(Name="Thermal", SolverType="NX MULTIPHYSICS", AnalysisType="Thermal")
        )

    cae = NS(SimPart=SimPart)
    monkeypatch.setitem(sys.modules, "NXOpen", NS(CAE=cae))
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    sim = SimPart()
    manifest = (
        {}
        if mode == "legacy"
        else {"live_mesh_state": {"sha256": "baseline"}, "mesh_inspection_limit": 500}
    )
    monkeypatch.setattr(
        jobs, "JobStore", lambda *args: NS(inspect=lambda _: {"manifest": manifest})
    )
    monkeypatch.setattr(result_binding, "require_job_owner", lambda *a, **k: None)
    monkeypatch.setattr(
        result_identity,
        "inspect_result_identity",
        lambda *a, **k: {"files": [{"bytes": 10}], "result_freshness": "not_verified"},
    )
    monkeypatch.setattr(dependencies, "inspect_direct", lambda *a: {})
    monkeypatch.setattr(thermal_state, "capture_analysis_thermal_state", lambda *a: None)
    capture = Mock(return_value={"sha256": "actual"})
    if mode == "unreadable":
        capture.side_effect = NXToolError("NX_SIM_INSPECTION_LIMIT", "Too many entities")
    monkeypatch.setattr(mesh_guard, "capture", capture)
    audit = Mock(
        return_value={"model_result_freshness": "stale" if mode == "recorded" else "not_verified"}
    )
    monkeypatch.setattr(result_binding, "audit_job_result", audit)
    host = NS(
        objects=NS(resolve=lambda *a, **k: sim),
        session=NS(Parts=NS(BaseWork=sim)),
        workspace=object(),
        _reference=lambda *a: {"id": "sim"},
    )
    result = SimcenterMixin._sim_result_identity(host, "sim", maximum_bytes=1000, job_id="job")
    kwargs = audit.call_args.kwargs
    assert kwargs["maximum_bytes"] == 990
    if mode == "legacy":
        capture.assert_not_called()
        assert kwargs["live_mesh_state"] is None
    else:
        capture.assert_called_once_with(sim, 500)
    if mode == "unreadable":
        assert kwargs["mesh_inspection_error"]["code"] == "NX_SIM_INSPECTION_LIMIT"
        assert kwargs["live_mesh_state"] is None
    assert result["result_freshness"] == ("stale" if mode == "recorded" else "not_verified")
